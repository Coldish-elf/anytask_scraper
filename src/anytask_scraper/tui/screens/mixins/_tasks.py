from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from textual import on, work
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Label

from anytask_scraper.tui.widgets.filter_bar import TaskFilterBar

from ._helpers import _STATUS_STYLES, _format_score, _styled_deadline, _styled_status

if TYPE_CHECKING:
    from anytask_scraper.models import Submission, Task
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class TasksMixin:
    app: AnytaskApp

    all_tasks: list[Task]
    filtered_tasks: list[Task]
    is_teacher_view: bool
    _selected_course_id: int | None
    _task_submission_cache: dict[tuple[int | None, str], Submission]

    _show_status: Any
    _table_cursor_index: Any
    _push_submission_screen: Any

    def _copy_task_payload(self) -> tuple[str, str] | None:
        from anytask_scraper.tui.clipboard import format_task_for_clipboard

        if not self.filtered_tasks:
            return None
        table = self.query_one("#task-table", DataTable)  # type: ignore[attr-defined]
        row_index = self._table_cursor_index(table, len(self.filtered_tasks))
        if row_index is None:
            return None
        task = self.filtered_tasks[row_index]
        text = format_task_for_clipboard(task, teacher_view=self.is_teacher_view)
        return ("task", text)

    @on(TaskFilterBar.Changed)
    def _handle_task_filter(self, event: TaskFilterBar.Changed) -> None:
        needle = event.text.lower()
        self.filtered_tasks = [
            t
            for t in self.all_tasks
            if (not needle or needle in t.title.lower())
            and (not event.status or t.status == event.status)
            and (not event.section or t.section == event.section)
        ]
        self._rebuild_task_table()

    def _update_task_filter_options(self) -> None:
        statuses = sorted({t.status for t in self.all_tasks if t.status})
        sections = sorted({t.section for t in self.all_tasks if t.section})
        self.query_one("#task-filter-bar", TaskFilterBar).update_options(statuses, sections)  # type: ignore[attr-defined]

    @on(DataTable.RowHighlighted, "#task-table")
    def _task_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is None:
            return
        try:
            idx = int(event.row_key.value) - 1
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self.filtered_tasks):
            self._show_detail(self.filtered_tasks[idx])

    @on(DataTable.RowSelected, "#task-table")
    def _task_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        try:
            idx = int(event.row_key.value) - 1
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self.filtered_tasks):
            task = self.filtered_tasks[idx]
            self._show_detail(task)
            if not self.is_teacher_view:
                self._fetch_and_show_task_submission(task)

    @work(thread=True)
    def _fetch_and_show_task_submission(self, task: Task) -> None:
        from anytask_scraper.parser import extract_issue_id_from_breadcrumb, parse_submission_page

        submit_url = task.submit_url.strip()
        if not submit_url:
            self.app.call_from_thread(
                self._show_status,
                "No submission topic for this task",
                kind="warning",
            )
            return
        if task.status.strip() == "Новый":
            self.app.call_from_thread(
                self._show_status,
                "No submission yet for this task",
                kind="info",
            )
            return

        cache_key = (self._selected_course_id, submit_url)
        cached = self._task_submission_cache.get(cache_key)
        if cached is not None:
            self.app.call_from_thread(self._push_submission_screen, cached)
            return

        try:
            client = self.app.client
            if not client:
                return

            html = client.fetch_submission_page(submit_url)
            issue_id = extract_issue_id_from_breadcrumb(html)
            if issue_id == 0:
                self.app.call_from_thread(
                    self._show_status,
                    "Submission topic is unavailable",
                    kind="warning",
                )
                return

            sub = parse_submission_page(html, issue_id, issue_url=submit_url)
            self._task_submission_cache[cache_key] = sub
            self.app.call_from_thread(self._push_submission_screen, sub)
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Submission topic error: {e}",
                kind="error",
            )

    def _setup_task_table_columns(self) -> None:
        table = self.query_one("#task-table", DataTable)  # type: ignore[attr-defined]
        table.clear(columns=True)
        if self.is_teacher_view:
            table.add_columns("#", "Title", "Section", "Max", "Deadline")
        else:
            table.add_columns("#", "Title", "Score", "Status", "Deadline")

    def _rebuild_task_table(self) -> None:
        table = self.query_one("#task-table", DataTable)  # type: ignore[attr-defined]
        if not table.columns:
            self._setup_task_table_columns()
        table.clear()

        for idx, task in enumerate(self.filtered_tasks, 1):
            from rich.text import Text

            if self.is_teacher_view:
                table.add_row(
                    str(idx),
                    Text(task.title),
                    Text(task.section or "-", style="dim"),
                    str(task.max_score) if task.max_score is not None else "-",
                    _styled_deadline(task.deadline),
                    key=str(idx),
                )
            else:
                table.add_row(
                    str(idx),
                    Text(task.title),
                    _format_score(task),
                    _styled_status(task.status),
                    _styled_deadline(task.deadline),
                    key=str(idx),
                )

    def _clear_detail(self) -> None:
        scroll = self.query_one("#detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()
        scroll.mount(Label("[dim]Select a task[/dim]"))

    def _show_detail(self, task: Task) -> None:
        from anytask_scraper.parser import strip_html

        scroll = self.query_one("#detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()

        scroll.mount(Label(f"[bold]{task.title}[/bold]", classes="detail-heading"))

        if not self.is_teacher_view:
            score = _format_score(task)
            status_style = _STATUS_STYLES.get(task.status, "")
            status_txt = task.status or "-"
            scroll.mount(
                Label(
                    f"Score: {score}  Status: [{status_style}]{status_txt}[/{status_style}]",
                    classes="detail-text",
                )
            )
        else:
            parts: list[str] = []
            if task.max_score is not None:
                parts.append(f"Max: {task.max_score}")
            if task.section:
                parts.append(f"Group: {task.section}")
            if parts:
                scroll.mount(Label("  ".join(parts), classes="detail-text"))

        if task.deadline:
            now = datetime.now()
            dl = task.deadline.strftime("%H:%M %d.%m.%Y")
            if task.deadline < now:
                dl_text = f"[dim strike]{dl}[/dim strike] (passed)"
            elif task.deadline < now + timedelta(days=3):
                dl_text = f"[bold yellow]{dl}[/bold yellow] (soon)"
            else:
                dl_text = dl
            scroll.mount(Label(f"Deadline: {dl_text}", classes="detail-text"))

        if task.description:
            desc = strip_html(task.description)
            scroll.mount(Label(desc, classes="detail-text"))
        if not self.is_teacher_view and task.submit_url and task.status.strip() != "Новый":
            scroll.mount(
                Label(
                    "[dim]Press Enter or click to open submission topic[/dim]",
                    classes="detail-text",
                )
            )
