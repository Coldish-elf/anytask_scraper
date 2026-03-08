from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
from rich.text import Text
from textual import on, work
from textual.widgets import DataTable, Label

from anytask_scraper.tui.widgets.filter_bar import GradebookFilterBar

if TYPE_CHECKING:
    from anytask_scraper.models import Gradebook, GradebookEntry, GradebookGroup
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class GradebookMixin:

    app: AnytaskApp

    _selected_course_id: int | None
    _gradebook_loaded_for: int | None
    all_gradebook_groups: list[GradebookGroup]
    filtered_gradebook_groups: list[GradebookGroup]
    _gb_sort_column: int | None
    _gb_sort_reverse: bool
    _gb_all_tasks: list[str]

    _show_status: Any
    _table_cursor_index: Any

    _GRADEBOOK_COLOR_MAP: dict[str, str] = {
        "#65E31B": "bold green",
        "#F0AD4E": "bold yellow",
        "#818A91": "dim",
        "#D9534F": "bold red",
        "#5BC0DE": "bold cyan",
    }

    def _copy_gradebook_payload(self) -> tuple[str, str] | None:
        from anytask_scraper.tui.clipboard import (
            format_table_row_for_clipboard,
            normalize_table_header,
        )

        table = self.query_one("#gradebook-table", DataTable)  # type: ignore[attr-defined]
        row_count = getattr(table, "row_count", 0)
        if not isinstance(row_count, int) or row_count <= 0:
            return None

        row_index = self._table_cursor_index(table, row_count)
        if row_index is None:
            return None

        headers = [normalize_table_header(column.label) for column in table.ordered_columns]
        row_values = table.get_row_at(row_index)
        text = format_table_row_for_clipboard(headers, row_values)
        if not text:
            return None
        return ("gradebook row", text)

    def _maybe_load_gradebook(self) -> None:
        if self._selected_course_id is None:
            return
        if self._gradebook_loaded_for == self._selected_course_id:
            return

        cache = self.app.gradebook_cache
        if self._selected_course_id in cache:
            gradebook = cache[self._selected_course_id]
            self._gradebook_loaded_for = self._selected_course_id
            self.all_gradebook_groups = list(gradebook.groups)
            self.filtered_gradebook_groups = list(gradebook.groups)
            self._update_gb_filter_options()
            self._rebuild_gradebook_table(gradebook.groups)
            total = sum(len(g.entries) for g in gradebook.groups)
            self.query_one("#gradebook-info-label", Label).update(  # type: ignore[attr-defined]
                f"{len(gradebook.groups)} group(s), {total} students"
            )
            return

        self.query_one("#gradebook-info-label", Label).update("Loading gradebook...")  # type: ignore[attr-defined]
        self._fetch_gradebook(self._selected_course_id)

    @work(thread=True)
    def _fetch_gradebook(self, course_id: int) -> None:
        from anytask_scraper.parser import parse_gradebook_page

        try:
            client = self.app.client
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            html = client.fetch_gradebook_page(course_id)
            gradebook = parse_gradebook_page(html, course_id)

            self.app.gradebook_cache[course_id] = gradebook
            self._gradebook_loaded_for = course_id
            self.all_gradebook_groups = list(gradebook.groups)
            self.filtered_gradebook_groups = list(gradebook.groups)

            self.app.call_from_thread(self._update_gb_filter_options)
            self.app.call_from_thread(self._rebuild_gradebook_table, gradebook.groups)
            total = sum(len(g.entries) for g in gradebook.groups)
            self.app.call_from_thread(
                self._update_gradebook_info,
                f"{len(gradebook.groups)} group(s), {total} students",
            )
        except httpx.HTTPStatusError as e:
            self.app.call_from_thread(
                self._show_status,
                f"Gradebook error: HTTP {e.response.status_code}",
                kind="error",
            )
            self.app.call_from_thread(
                self._update_gradebook_info,
                f"Error: HTTP {e.response.status_code}",
            )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Gradebook error: {e}",
                kind="error",
            )
            self.app.call_from_thread(self._update_gradebook_info, f"Error: {e}")

    @on(GradebookFilterBar.Changed)
    def _handle_gb_filter(self, event: GradebookFilterBar.Changed) -> None:
        from anytask_scraper.models import GradebookGroup

        needle = event.text.lower()
        filtered: list[GradebookGroup] = []
        for g in self.all_gradebook_groups:
            if event.group and event.group != g.group_name:
                continue
            if event.teacher and event.teacher != g.teacher_name:
                continue
            if needle:
                entries = [e for e in g.entries if needle in e.student_name.lower()]
            else:
                entries = list(g.entries)
            if entries or (not needle):
                filtered.append(
                    GradebookGroup(
                        group_name=g.group_name,
                        group_id=g.group_id,
                        teacher_name=g.teacher_name,
                        task_titles=list(g.task_titles),
                        max_scores=dict(g.max_scores),
                        entries=entries,
                    )
                )
        self.filtered_gradebook_groups = filtered
        if self._gb_sort_column is not None:
            self._sort_and_rebuild_gradebook()
        else:
            self._rebuild_gradebook_table(filtered)
        total = sum(len(g.entries) for g in filtered)
        self.query_one("#gradebook-info-label", Label).update(  # type: ignore[attr-defined]
            f"{len(filtered)} group(s), {total} students"
        )

    def _update_gb_filter_options(self) -> None:
        groups = sorted({g.group_name for g in self.all_gradebook_groups if g.group_name})
        teachers = sorted({g.teacher_name for g in self.all_gradebook_groups if g.teacher_name})
        self.query_one("#gb-filter-bar", GradebookFilterBar).update_options(groups, teachers)  # type: ignore[attr-defined]

    def _rebuild_gradebook_table(self, groups: list[GradebookGroup]) -> None:
        table = self.query_one("#gradebook-table", DataTable)  # type: ignore[attr-defined]
        table.clear(columns=True)

        if not groups:
            table.add_column("Info")
            table.add_row("No gradebook data")
            return

        all_tasks: list[str] = []
        for g in groups:
            for t in g.task_titles:
                if t not in all_tasks:
                    all_tasks.append(t)
        self._gb_all_tasks = all_tasks

        base_columns = ["#", "Group", "Student", "Teacher"] + all_tasks + ["Total"]
        labels = []
        for i, col in enumerate(base_columns):
            if self._gb_sort_column == i:
                indicator = " ▼" if self._gb_sort_reverse else " ▲"
                labels.append(f"{col}{indicator}")
            else:
                labels.append(f"{col}  ")
        table.add_columns(*labels)

        row_num = 0
        for group in groups:
            for entry in group.entries:
                row_num += 1
                row: list[str | Text] = [
                    str(row_num),
                    group.group_name,
                    entry.student_name,
                    group.teacher_name,
                ]
                for t in all_tasks:
                    score = entry.scores.get(t)
                    color_hex = entry.statuses.get(t, "")
                    style = self._GRADEBOOK_COLOR_MAP.get(color_hex, "")
                    score_str = str(score) if score is not None else "-"
                    row.append(Text(score_str, style=style))
                row.append(str(entry.total_score))
                table.add_row(*row, key=str(row_num))

    @on(DataTable.HeaderSelected, "#gradebook-table")
    def _gb_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_idx = event.column_index
        if col_idx == 0:
            return
        if self._gb_sort_column == col_idx:
            self._gb_sort_reverse = not self._gb_sort_reverse
        else:
            self._gb_sort_column = col_idx
            self._gb_sort_reverse = False
        self._sort_and_rebuild_gradebook()

    def _sort_and_rebuild_gradebook(self) -> None:
        col = self._gb_sort_column
        if col is None:
            return

        flat: list[tuple[GradebookGroup, GradebookEntry]] = []
        for g in self.filtered_gradebook_groups:
            for e in g.entries:
                flat.append((g, e))

        all_tasks: list[str] = []
        for g in self.filtered_gradebook_groups:
            for t in g.task_titles:
                if t not in all_tasks:
                    all_tasks.append(t)
        self._gb_all_tasks = all_tasks

        num_fixed = 4
        total_col = num_fixed + len(all_tasks)

        if col == 1:
            flat.sort(key=lambda x: x[0].group_name.lower(), reverse=self._gb_sort_reverse)
        elif col == 2:
            flat.sort(key=lambda x: x[1].student_name.lower(), reverse=self._gb_sort_reverse)
        elif col == 3:
            flat.sort(key=lambda x: x[0].teacher_name.lower(), reverse=self._gb_sort_reverse)
        elif col == total_col:
            flat.sort(key=lambda x: x[1].total_score, reverse=self._gb_sort_reverse)
        elif num_fixed <= col < total_col:
            task_name = all_tasks[col - num_fixed]

            def _task_score(item: tuple[GradebookGroup, GradebookEntry]) -> float:
                return item[1].scores.get(task_name, -1.0)

            flat.sort(
                key=_task_score,
                reverse=self._gb_sort_reverse,
            )

        table = self.query_one("#gradebook-table", DataTable)  # type: ignore[attr-defined]
        table.clear(columns=True)

        base_columns = ["#", "Group", "Student", "Teacher"] + all_tasks + ["Total"]
        labels = []
        for i, col_name in enumerate(base_columns):
            if self._gb_sort_column == i:
                indicator = " ▼" if self._gb_sort_reverse else " ▲"
                labels.append(f"{col_name}{indicator}")
            else:
                labels.append(f"{col_name}  ")
        table.add_columns(*labels)

        for row_num, (group, entry) in enumerate(flat, 1):
            row: list[str | Text] = [
                str(row_num),
                group.group_name,
                entry.student_name,
                group.teacher_name,
            ]
            for t in all_tasks:
                score = entry.scores.get(t)
                color_hex = entry.statuses.get(t, "")
                style = self._GRADEBOOK_COLOR_MAP.get(color_hex, "")
                score_str = str(score) if score is not None else "-"
                row.append(Text(score_str, style=style))
            row.append(str(entry.total_score))
            table.add_row(*row, key=str(row_num))

    def _update_gradebook_info(self, text: str) -> None:
        self.query_one("#gradebook-info-label", Label).update(text)  # type: ignore[attr-defined]

    def _load_gradebook_for_export(self, course_id: int) -> Gradebook:
        import sys

        from anytask_scraper.parser import parse_gradebook_page as _parse_gb

        _parse_gb_fn = getattr(
            sys.modules.get("anytask_scraper.tui.screens.main"),
            "parse_gradebook_page",
            _parse_gb,
        )

        cache = self.app.gradebook_cache
        cached = cache.get(course_id)
        if cached is not None:
            self.all_gradebook_groups = list(cached.groups)
            self.filtered_gradebook_groups = list(cached.groups)
            self._gradebook_loaded_for = course_id
            total = sum(len(g.entries) for g in cached.groups)
            self.app.call_from_thread(
                self._update_gradebook_info,
                f"{len(cached.groups)} group(s), {total} students",
            )
            return cached

        client = self.app.client
        if not client:
            raise RuntimeError("Not logged in")

        html = client.fetch_gradebook_page(course_id)
        gradebook = _parse_gb_fn(html, course_id)
        cache[course_id] = gradebook
        self.all_gradebook_groups = list(gradebook.groups)
        self.filtered_gradebook_groups = list(gradebook.groups)
        self._gradebook_loaded_for = course_id
        self.app.call_from_thread(self._update_gb_filter_options)
        self.app.call_from_thread(self._rebuild_gradebook_table, gradebook.groups)
        total = sum(len(g.entries) for g in gradebook.groups)
        self.app.call_from_thread(
            self._update_gradebook_info,
            f"{len(gradebook.groups)} group(s), {total} students",
        )
        return gradebook
