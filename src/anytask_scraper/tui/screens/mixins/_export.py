from __future__ import annotations

import logging
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from textual import on, work
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from anytask_scraper.tui.export_params import (
    QUEUE_PARAMS,
    SUBMISSIONS_PARAMS,
    TASKS_STUDENT_PARAMS,
    TASKS_TEACHER_PARAMS,
    gradebook_params,
)
from anytask_scraper.tui.widgets.param_selector import ParameterSelector

from ._helpers import (
    ExportFilterValue,
    _csv_row,
    _extract_filter_text,
    _extract_filter_values,
    _normalize_multi_values,
)

if TYPE_CHECKING:
    from anytask_scraper.models import GradebookGroup, QueueEntry, ReviewQueue, Task
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class ExportMixin:
    app: AnytaskApp

    _selected_course_id: int | None
    is_teacher_view: bool
    all_tasks: list[Task]
    all_gradebook_groups: list[GradebookGroup]
    _export_preload_token: int
    _export_filter_values: dict[str, list[str]]
    _export_filter_selected: dict[str, set[str]]
    _export_filter_prompts: dict[str, str]
    _export_name_list: list[str]
    _queue_loaded_for: int | None
    _gradebook_loaded_for: int | None

    focused: Any

    _EXPORT_FOCUS_ORDER = [
        "#export-type-set",
        "#format-set",
        "#export-filter-task",
        "#export-filter-status",
        "#export-filter-reviewer",
        "#export-ln-from",
        "#export-ln-to",
        "#export-names-file-input",
        "#export-names-textarea",
        "#param-option-list",
        "#export-include-files-set",
        "#export-clone-repos-set",
        "#output-dir-input",
        "#export-filename-input",
        "#export-btn",
    ]

    _LN_INPUT_IDS = ("export-ln-from", "export-ln-to")

    def _copy_export_preview_payload(self) -> tuple[str, str] | None:
        from anytask_scraper.tui.clipboard import rich_markup_to_plain

        preview = self.query_one("#export-preview-content", Static)  # type: ignore[attr-defined]
        raw = str(preview.content)
        text = rich_markup_to_plain(raw).strip()
        if not text:
            return None
        return ("export preview", text)

    def _export_focus_next(self) -> None:
        order = self._get_export_focus_order()
        if not order:
            return
        current = self._find_current_zone(order)  # type: ignore[attr-defined]
        if current < 0:
            order[0].focus()
            return
        next_idx = min(current + 1, len(order) - 1)
        order[next_idx].focus()

    def _export_focus_prev(self) -> None:
        order = self._get_export_focus_order()
        if not order:
            return
        current = self._find_current_zone(order)  # type: ignore[attr-defined]
        if current < 0:
            order[0].focus()
            return
        prev_idx = max(current - 1, 0)
        order[prev_idx].focus()

    def _get_export_focus_order(self) -> list[Any]:
        widgets: list[Any] = []
        for wid in self._EXPORT_FOCUS_ORDER:
            try:
                widget = self.query_one(wid)  # type: ignore[attr-defined]
            except Exception:
                continue
            if getattr(widget, "disabled", False):
                continue
            widgets.append(widget)
        return widgets

    @on(RadioSet.Changed, "#export-type-set")
    def _export_type_changed(self, event: RadioSet.Changed) -> None:
        export_type = self._get_current_export_type()
        if export_type == "tasks-export-radio" or self._has_loaded_export_data(export_type):
            self._update_export_filters()
            self._update_params()
            self._refresh_export_preview()
        else:
            self._update_export_filters()
            self._set_export_filters_loading_state()
            self._refresh_export_preview()
            self._start_export_preload(export_type)

    @on(RadioSet.Changed, "#format-set")
    def _format_changed(self, event: RadioSet.Changed) -> None:
        fmt = self._get_current_export_format()
        if fmt == "files":
            self._set_include_files_disabled(True)
        else:
            export_type = self._get_current_export_type()
            self._set_include_files_disabled(export_type != "subs-export-radio")
        self._refresh_export_preview()

    def _set_include_files_disabled(self, disabled: bool) -> None:
        with suppress(Exception):
            self.query_one("#export-include-files-set", RadioSet).disabled = disabled  # type: ignore[attr-defined]

    @on(OptionList.OptionSelected, "#export-filter-task")
    @on(OptionList.OptionSelected, "#export-filter-status")
    @on(OptionList.OptionSelected, "#export-filter-reviewer")
    def _export_filter_changed(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        option_list = event.option_list
        widget_id = f"#{option_list.id}" if option_list.id else ""
        if not widget_id:
            return
        options = self._export_filter_values.get(widget_id, [])
        idx = event.option_index
        if idx < 0 or idx >= len(options):
            return
        value = options[idx]
        selected = self._export_filter_selected.setdefault(widget_id, set())
        if value in selected:
            selected.remove(value)
        else:
            selected.add(value)
        self._rebuild_export_filter_option_list(option_list, keep_highlight=idx)
        self._refresh_export_filter_label(widget_id, enabled=not option_list.disabled)
        self._refresh_export_preview()

    @on(Input.Changed, "#export-ln-from")
    @on(Input.Changed, "#export-ln-to")
    def _export_ln_range_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._refresh_export_preview()

    @on(TextArea.Changed, "#export-names-textarea")
    def _export_names_textarea_changed(self, event: TextArea.Changed) -> None:
        event.stop()
        from anytask_scraper.models import parse_name_list

        self._export_name_list = parse_name_list(event.text_area.text)
        self._refresh_names_status_label()
        self._refresh_export_preview()

    @on(Button.Pressed, "#export-names-load-btn")
    def _export_names_load_btn_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        try:
            path_str = self.query_one("#export-names-file-input", Input).value.strip()  # type: ignore[attr-defined]
            if not path_str:
                return
            fpath = Path(path_str).expanduser()
            if fpath.stat().st_size > 100_000:
                self._set_export_status("Names file is too large (> 100 KB)", "error")
                return
            text = fpath.read_text(encoding="utf-8")
            ta = self.query_one("#export-names-textarea", TextArea)  # type: ignore[attr-defined]
            ta.load_text(text)
        except (OSError, UnicodeDecodeError) as e:
            self._set_export_status(f"Cannot load names file: {e}", "error")

    def _refresh_names_status_label(self) -> None:
        n = len(self._export_name_list)
        with suppress(Exception):
            self.query_one("#export-names-status-label", Label).update(  # type: ignore[attr-defined]
                f"Names loaded: {n}" if n else "No names loaded (filter inactive)"
            )

    def _update_export_filters(self) -> None:
        try:
            task_select = self.query_one("#export-filter-task", OptionList)  # type: ignore[attr-defined]
            status_select = self.query_one("#export-filter-status", OptionList)  # type: ignore[attr-defined]
            reviewer_select = self.query_one("#export-filter-reviewer", OptionList)  # type: ignore[attr-defined]
        except Exception:
            return

        export_type = self._get_current_export_type()
        prev_task = self._get_selected_export_filter_values("#export-filter-task")
        prev_status = self._get_selected_export_filter_values("#export-filter-status")
        prev_reviewer = self._get_selected_export_filter_values("#export-filter-reviewer")

        if export_type in ("queue-export-radio", "subs-export-radio"):
            self._export_filter_prompts["#export-filter-task"] = "Task"
            self._export_filter_prompts["#export-filter-status"] = "Status"
            self._export_filter_prompts["#export-filter-reviewer"] = "Reviewer"
        elif export_type == "tasks-export-radio":
            self._export_filter_prompts["#export-filter-task"] = "Title"
            self._export_filter_prompts["#export-filter-status"] = (
                "Section" if self.is_teacher_view else "Status"
            )
            self._export_filter_prompts["#export-filter-reviewer"] = "N/A"
        elif export_type == "gb-export-radio":
            self._export_filter_prompts["#export-filter-task"] = "Group"
            self._export_filter_prompts["#export-filter-status"] = "N/A"
            self._export_filter_prompts["#export-filter-reviewer"] = "Teacher"
        elif export_type == "db-export-radio":
            self._export_filter_prompts["#export-filter-task"] = "Task"
            self._export_filter_prompts["#export-filter-status"] = "Status"
            self._export_filter_prompts["#export-filter-reviewer"] = "Reviewer"
        else:
            self._export_filter_prompts["#export-filter-task"] = "Task"
            self._export_filter_prompts["#export-filter-status"] = "Status"
            self._export_filter_prompts["#export-filter-reviewer"] = "Reviewer"

        is_db_export = export_type == "db-export-radio"
        is_subs_export = export_type == "subs-export-radio"
        for widget_id, disabled in [
            ("#md-radio", is_db_export),
            ("#csv-radio", is_db_export),
            ("#files-radio", not is_subs_export or is_db_export),
        ]:
            with suppress(Exception):
                self.query_one(widget_id, RadioButton).disabled = disabled  # type: ignore[attr-defined]
        if is_db_export:
            with suppress(Exception):
                self.query_one("#json-radio", RadioButton).value = True  # type: ignore[attr-defined]
        subs_only = export_type != "subs-export-radio"
        with suppress(Exception):
            self.query_one("#export-include-files-set", RadioSet).disabled = subs_only  # type: ignore[attr-defined]
        with suppress(Exception):
            self.query_one("#export-clone-repos-set", RadioSet).disabled = subs_only  # type: ignore[attr-defined]

        is_tasks = export_type == "tasks-export-radio"
        with suppress(Exception):
            self.query_one("#export-ln-from", Input).disabled = is_tasks  # type: ignore[attr-defined]
        with suppress(Exception):
            self.query_one("#export-ln-to", Input).disabled = is_tasks  # type: ignore[attr-defined]
        with suppress(Exception):
            self.query_one("#export-names-section").disabled = is_tasks  # type: ignore[attr-defined]

        if export_type == "tasks-export-radio":
            titles = sorted({t.title for t in self.all_tasks if t.title})
            statuses = sorted({t.status for t in self.all_tasks if t.status})
            sections = sorted({t.section for t in self.all_tasks if t.section})
            self._set_export_filter_options(
                task_select,
                [(t, t) for t in titles],
                prev_task,
                enabled=bool(titles),
            )
            self._set_export_filter_options(
                status_select,
                [(s, s) for s in (sections if self.is_teacher_view else statuses)],
                prev_status,
                enabled=bool(sections if self.is_teacher_view else statuses),
            )
            self._set_export_filter_options(reviewer_select, [], set(), enabled=False)
        elif export_type in ("queue-export-radio", "subs-export-radio", "db-export-radio"):
            tasks = sorted({e.task_title for e in self.all_queue_entries if e.task_title})
            statuses = sorted({e.status_name for e in self.all_queue_entries if e.status_name})
            reviewers = sorted(
                {e.responsible_name for e in self.all_queue_entries if e.responsible_name}
            )
            self._set_export_filter_options(
                task_select,
                [(t, t) for t in tasks],
                prev_task,
                enabled=bool(tasks),
            )
            self._set_export_filter_options(
                status_select,
                [(s, s) for s in statuses],
                prev_status,
                enabled=bool(statuses),
            )
            self._set_export_filter_options(
                reviewer_select,
                [(r, r) for r in reviewers],
                prev_reviewer,
                enabled=bool(reviewers),
            )
        elif export_type == "gb-export-radio":
            groups = sorted({g.group_name for g in self.all_gradebook_groups if g.group_name})
            teachers = sorted({g.teacher_name for g in self.all_gradebook_groups if g.teacher_name})
            self._set_export_filter_options(
                task_select,
                [(g, g) for g in groups],
                prev_task,
                enabled=bool(groups),
            )
            self._set_export_filter_options(status_select, [], set(), enabled=False)
            self._set_export_filter_options(
                reviewer_select,
                [(t, t) for t in teachers],
                prev_reviewer,
                enabled=bool(teachers),
            )
        else:
            self._set_export_filter_options(task_select, [], set(), enabled=False)
            self._set_export_filter_options(status_select, [], set(), enabled=False)
            self._set_export_filter_options(reviewer_select, [], set(), enabled=False)

    def _set_export_filter_options(
        self,
        option_list: OptionList,
        options: list[tuple[str, str]],
        previous_value: object,
        *,
        enabled: bool,
    ) -> None:
        widget_id = f"#{option_list.id}" if option_list.id else ""
        if not widget_id:
            return

        values = [value for _, value in options]
        selected = _normalize_multi_values(previous_value)
        selected = {value for value in values if value in selected}

        self._export_filter_values[widget_id] = values
        self._export_filter_selected[widget_id] = selected if enabled else set()

        option_list.disabled = not enabled
        self._rebuild_export_filter_option_list(option_list)
        self._refresh_export_filter_label(widget_id, enabled=enabled)

        if not enabled:
            focused = self.focused
            if focused is option_list:
                with suppress(Exception):
                    self.query_one("#export-type-set", RadioSet).focus()  # type: ignore[attr-defined]

    def _rebuild_export_filter_option_list(
        self,
        option_list: OptionList,
        *,
        keep_highlight: int | None = None,
    ) -> None:
        from rich.text import Text

        widget_id = f"#{option_list.id}" if option_list.id else ""
        if not widget_id:
            return
        values = self._export_filter_values.get(widget_id, [])
        selected = self._export_filter_selected.get(widget_id, set())
        option_list.clear_options()
        for idx, value in enumerate(values):
            check = "[x]" if value in selected else "[ ]"
            label = Text()
            label.append(f"{check} {value}")
            option_list.add_option(Option(label, id=str(idx)))
        if not values:
            return
        if keep_highlight is not None and 0 <= keep_highlight < len(values):
            option_list.highlighted = keep_highlight
            return
        if option_list.highlighted is None:
            option_list.highlighted = 0

    def _refresh_export_filter_label(self, widget_id: str, *, enabled: bool) -> None:
        prompt = self._export_filter_prompts.get(widget_id, "Filter")
        selected_count = len(self._export_filter_selected.get(widget_id, set()))
        if not enabled:
            suffix = "N/A"
        elif selected_count == 0:
            suffix = "All"
        elif selected_count == 1:
            suffix = "1 selected"
        else:
            suffix = f"{selected_count} selected"
        label_id = f"#{widget_id.removeprefix('#')}-label"
        with suppress(Exception):
            self.query_one(label_id, Label).update(f"{prompt} ({suffix})")  # type: ignore[attr-defined]

    def _get_selected_export_filter_values(self, widget_id: str) -> list[str]:
        values = self._export_filter_values.get(widget_id, [])
        selected = self._export_filter_selected.get(widget_id, set())
        return [value for value in values if value in selected]

    def _set_export_filters_loading_state(self) -> None:
        for wid in (
            "#export-filter-task",
            "#export-filter-status",
            "#export-filter-reviewer",
        ):
            try:
                sel = self.query_one(wid, OptionList)  # type: ignore[attr-defined]
                sel.disabled = True
                self._refresh_export_filter_label(wid, enabled=False)
            except Exception:
                continue

    def _has_loaded_export_data(self, export_type: str) -> bool:
        course_id = self._selected_course_id
        if course_id is None:
            return False
        if export_type == "tasks-export-radio":
            return True
        if export_type in ("queue-export-radio", "subs-export-radio"):
            return self._queue_loaded_for == course_id or course_id in self.app.queue_cache
        if export_type == "gb-export-radio":
            return self._gradebook_loaded_for == course_id or course_id in self.app.gradebook_cache
        if export_type == "db-export-radio":
            return self._queue_loaded_for == course_id or course_id in self.app.queue_cache
        return True

    def _get_current_export_filters(self) -> dict[str, ExportFilterValue]:
        filters: dict[str, ExportFilterValue] = {}
        try:
            export_type = self._get_current_export_type()
            task_vals = self._get_selected_export_filter_values("#export-filter-task")
            status_vals = self._get_selected_export_filter_values("#export-filter-status")
            reviewer_vals = self._get_selected_export_filter_values("#export-filter-reviewer")
            if export_type == "tasks-export-radio":
                if task_vals:
                    filters["task"] = task_vals
                if status_vals:
                    filters["section" if self.is_teacher_view else "status"] = status_vals
            elif export_type in ("queue-export-radio", "subs-export-radio", "db-export-radio"):
                if task_vals:
                    filters["task"] = task_vals
                if status_vals:
                    filters["status"] = status_vals
                if reviewer_vals:
                    filters["reviewer"] = reviewer_vals
            elif export_type == "gb-export-radio":
                if task_vals:
                    filters["group"] = task_vals
                if reviewer_vals:
                    filters["teacher"] = reviewer_vals
            if export_type != "tasks-export-radio":
                ln_from = self.query_one("#export-ln-from", Input).value.strip()  # type: ignore[attr-defined]
                ln_to = self.query_one("#export-ln-to", Input).value.strip()  # type: ignore[attr-defined]
                if ln_from:
                    filters["last_name_from"] = ln_from
                if ln_to:
                    filters["last_name_to"] = ln_to
                if self._export_name_list:
                    filters["name_list"] = list(self._export_name_list)
        except Exception:
            logger.debug("Failed to collect export filters", exc_info=True)
        return filters

    def _update_params(self) -> None:
        try:
            selector = self.query_one("#param-selector", ParameterSelector)  # type: ignore[attr-defined]
        except Exception:
            return

        export_type = self._get_current_export_type()

        if export_type == "tasks-export-radio":
            params = TASKS_TEACHER_PARAMS if self.is_teacher_view else TASKS_STUDENT_PARAMS
        elif export_type == "queue-export-radio":
            params = QUEUE_PARAMS
        elif export_type == "subs-export-radio":
            params = SUBMISSIONS_PARAMS
        elif export_type == "gb-export-radio":
            all_tasks: list[str] = []
            for g in self.all_gradebook_groups:
                for t in g.task_titles:
                    if t not in all_tasks:
                        all_tasks.append(t)
            params = gradebook_params(all_tasks)
        elif export_type == "db-export-radio":
            params = []
        else:
            params = []

        selector.set_params(params)

    @on(ParameterSelector.Changed)
    def _params_changed(self, event: ParameterSelector.Changed) -> None:
        self._refresh_export_preview()

    @on(Input.Changed, "#export-filename-input")
    def _filename_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._refresh_export_preview()

    @on(RadioSet.Changed, "#export-include-files-set")
    def _include_files_changed(self, event: RadioSet.Changed) -> None:
        event.stop()
        self._refresh_export_preview()

    @on(RadioSet.Changed, "#export-clone-repos-set")
    def _clone_repos_changed(self, event: RadioSet.Changed) -> None:
        event.stop()
        self._refresh_export_preview()

    def _get_included_columns(self) -> list[str]:
        try:
            selector = self.query_one("#param-selector", ParameterSelector)  # type: ignore[attr-defined]
            result: list[str] = selector.get_included()
            return result
        except Exception:
            return []

    def _get_custom_export_filename(self) -> str | None:
        try:
            value = self.query_one("#export-filename-input", Input).value.strip()  # type: ignore[attr-defined]
        except Exception:
            return None
        return value or None

    def _resolve_export_filename(self, default_filename: str) -> str:
        custom = self._get_custom_export_filename()
        if not custom:
            return default_filename
        safe_name = Path(custom).name
        if not safe_name:
            return default_filename
        default_suffix = Path(default_filename).suffix
        if default_suffix and not Path(safe_name).suffix:
            return f"{safe_name}{default_suffix}"
        return safe_name

    def _get_include_submission_files(self) -> bool:
        try:
            files_set = self.query_one("#export-include-files-set", RadioSet)  # type: ignore[attr-defined]
            btn = files_set.pressed_button
            return bool(btn and btn.id == "export-subs-files-on-radio")
        except Exception:
            return False

    def _get_clone_repos(self) -> bool:
        try:
            repos_set = self.query_one("#export-clone-repos-set", RadioSet)  # type: ignore[attr-defined]
            btn = repos_set.pressed_button
            return bool(btn and btn.id == "export-clone-repos-on-radio")
        except Exception:
            return False

    def _refresh_export_preview(self) -> None:
        try:
            export_type = self._get_current_export_type()
            fmt = self._get_current_export_format()
            preview_text = self._generate_preview(export_type, fmt)
            self.query_one("#export-preview-content", Static).update(preview_text)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("Failed to update export preview", exc_info=True)

    def _start_export_preload(self, export_type: str) -> None:
        course_id = self._selected_course_id
        if course_id is None:
            return
        if export_type == "queue-export-radio" and not self.is_teacher_view:
            return
        if export_type == "subs-export-radio" and not self.is_teacher_view:
            return
        if export_type == "db-export-radio" and not self.is_teacher_view:
            return
        self._export_preload_token += 1
        token = self._export_preload_token
        if export_type == "queue-export-radio":
            self._set_export_status("Loading queue data...", "info")
            self.query_one("#export-preview-content", Static).update(  # type: ignore[attr-defined]
                "[dim]Loading queue data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)
        elif export_type == "subs-export-radio":
            self._set_export_status("Loading submissions source data...", "info")
            self.query_one("#export-preview-content", Static).update(  # type: ignore[attr-defined]
                "[dim]Loading submissions source data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)
        elif export_type == "gb-export-radio":
            self._set_export_status("Loading gradebook data...", "info")
            self.query_one("#export-preview-content", Static).update(  # type: ignore[attr-defined]
                "[dim]Loading gradebook data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)
        elif export_type == "db-export-radio":
            self._set_export_status("Loading queue data for DB export...", "info")
            self.query_one("#export-preview-content", Static).update(  # type: ignore[attr-defined]
                "[dim]Loading queue data for DB export...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)

    @work(thread=True)
    def _preload_export_data(self, export_type: str, course_id: int, token: int) -> None:
        try:
            loaded_message = "Preload complete"
            if export_type in ("queue-export-radio", "subs-export-radio"):
                queue = self._load_queue_for_export(course_id)
                loaded_message = f"Queue loaded: {len(queue.entries)} entries"
            elif export_type == "db-export-radio":
                queue = self._load_queue_for_export(course_id)
                loaded_message = f"Queue loaded for DB export: {len(queue.entries)} entries"
            elif export_type == "gb-export-radio":
                gradebook = self._load_gradebook_for_export(course_id)  # type: ignore[attr-defined]
                total = sum(len(g.entries) for g in gradebook.groups)
                loaded_message = (
                    f"Gradebook loaded: {len(gradebook.groups)} group(s), {total} students"
                )
            self.app.call_from_thread(
                self._finish_export_preload,
                export_type,
                token,
                loaded_message,
            )
        except Exception as e:
            logger.exception(
                "Export preload failed for export_type=%s course_id=%s",
                export_type,
                course_id,
            )
            error_text = str(e).strip() or e.__class__.__name__
            self.app.call_from_thread(
                self._finish_export_preload,
                export_type,
                token,
                "",
                error_text,
            )

    def _finish_export_preload(
        self,
        export_type: str,
        token: int,
        loaded_message: str,
        error: str | None = None,
    ) -> None:
        if token != self._export_preload_token:
            return
        if export_type != self._get_current_export_type():
            return
        self._update_export_filters()
        self._update_params()
        self._refresh_export_preview()
        if error is None:
            self._set_export_status(loaded_message, "success")
        else:
            details = f": {error}" if error else ""
            self._set_export_status(f"Failed to preload export data{details}", "error")

    def _get_current_export_type(self) -> str:
        try:
            btn = self.query_one("#export-type-set", RadioSet).pressed_button  # type: ignore[attr-defined]
            return (btn.id or "tasks-export-radio") if btn else "tasks-export-radio"
        except Exception:
            return "tasks-export-radio"

    def _get_current_export_format(self) -> str:
        try:
            btn = self.query_one("#format-set", RadioSet).pressed_button  # type: ignore[attr-defined]
            fmt_map = {
                "json-radio": "json",
                "md-radio": "markdown",
                "csv-radio": "csv",
                "files-radio": "files",
            }
            return fmt_map.get(btn.id or "", "json") if btn else "json"
        except Exception:
            return "json"

    def _generate_preview(self, export_type: str, format_type: str) -> str:
        from anytask_scraper.models import (
            GradebookGroup,
            ReviewQueue,
            last_name_in_range,
            name_matches_list,
        )

        if self._selected_course_id is None:
            return "[dim]Select a course first[/dim]"

        course_id = self._selected_course_id
        max_items = 5
        included = self._get_included_columns()
        filters = self._get_current_export_filters()
        task_filters = _extract_filter_values(filters, "task")
        status_filters = _extract_filter_values(filters, "status")
        section_filters = _extract_filter_values(filters, "section")
        reviewer_filters = _extract_filter_values(filters, "reviewer")
        group_filters = _extract_filter_values(filters, "group")
        teacher_filters = _extract_filter_values(filters, "teacher")
        last_name_from = _extract_filter_text(filters, "last_name_from")
        last_name_to = _extract_filter_text(filters, "last_name_to")
        name_list_filter = list(_extract_filter_values(filters, "name_list"))

        if export_type == "tasks-export-radio":
            tasks = list(self.all_tasks)
            if task_filters:
                tasks = [t for t in tasks if t.title in task_filters]
            if section_filters:
                tasks = [t for t in tasks if t.section in section_filters]
            if status_filters:
                tasks = [t for t in tasks if t.status in status_filters]
            if not tasks:
                return "[dim]No tasks available[/dim]"
            return self._preview_tasks(
                tasks[:max_items], format_type, course_id, len(tasks), included
            )

        elif export_type == "queue-export-radio":
            q_entries = list(self.all_queue_entries)
            if not q_entries:
                cache = self.app.queue_cache
                q_entries = list(cache.get(course_id, ReviewQueue(course_id=course_id)).entries)
            if task_filters:
                q_entries = [e for e in q_entries if e.task_title in task_filters]
            if status_filters:
                q_entries = [e for e in q_entries if e.status_name in status_filters]
            if reviewer_filters:
                q_entries = [e for e in q_entries if e.responsible_name in reviewer_filters]
            if last_name_from or last_name_to:
                q_entries = [
                    e
                    for e in q_entries
                    if last_name_in_range(
                        e.student_name,
                        last_name_from,
                        last_name_to,
                    )
                ]
            if name_list_filter:
                q_entries = [
                    e for e in q_entries if name_matches_list(e.student_name, name_list_filter)
                ]
            if not q_entries:
                if self._has_loaded_export_data(export_type):
                    return "[dim]No queue entries match current filters[/dim]"
                return "[dim]Queue data will be loaded during export[/dim]"
            return self._preview_queue(
                q_entries[:max_items], format_type, course_id, len(q_entries), included
            )

        elif export_type == "gb-export-radio":
            groups = list(self.all_gradebook_groups)
            if not groups:
                gb_cache = self.app.gradebook_cache
                cached = gb_cache.get(course_id)
                if cached is not None:
                    groups = list(cached.groups)
            if group_filters:
                groups = [g for g in groups if g.group_name in group_filters]
            if teacher_filters:
                groups = [g for g in groups if g.teacher_name in teacher_filters]
            if last_name_from or last_name_to or name_list_filter:
                groups = [
                    GradebookGroup(
                        group_name=g.group_name,
                        group_id=g.group_id,
                        teacher_name=g.teacher_name,
                        task_titles=list(g.task_titles),
                        max_scores=dict(g.max_scores),
                        entries=[
                            e
                            for e in g.entries
                            if last_name_in_range(e.student_name, last_name_from, last_name_to)
                            and (
                                not name_list_filter
                                or name_matches_list(e.student_name, name_list_filter)
                            )
                        ],
                    )
                    for g in groups
                ]
                groups = [g for g in groups if g.entries]
            total = sum(len(g.entries) for g in groups)
            if not total:
                if self._has_loaded_export_data(export_type):
                    return "[dim]No gradebook rows match current filters[/dim]"
                return "[dim]Gradebook data will be loaded during export[/dim]"
            return self._preview_gradebook(groups, format_type, course_id, total, included)

        elif export_type == "subs-export-radio":
            if format_type == "files":
                return "[dim]Files Only mode:\nDownloads submission files\nto student folders[/dim]"
            sub_entries = list(self.all_queue_entries)
            if not sub_entries:
                cache = self.app.queue_cache
                sub_entries = list(cache.get(course_id, ReviewQueue(course_id=course_id)).entries)
            if task_filters:
                sub_entries = [e for e in sub_entries if e.task_title in task_filters]
            if status_filters:
                sub_entries = [e for e in sub_entries if e.status_name in status_filters]
            if reviewer_filters:
                sub_entries = [e for e in sub_entries if e.responsible_name in reviewer_filters]
            if last_name_from or last_name_to:
                sub_entries = [
                    e
                    for e in sub_entries
                    if last_name_in_range(
                        e.student_name,
                        last_name_from,
                        last_name_to,
                    )
                ]
            if name_list_filter:
                sub_entries = [
                    e for e in sub_entries if name_matches_list(e.student_name, name_list_filter)
                ]
            if not sub_entries:
                if self._has_loaded_export_data(export_type):
                    return "[dim]No queue entries match current filters[/dim]"
                return "[dim]Queue data will be loaded during export[/dim]"
            return self._preview_submissions(
                sub_entries[:max_items], format_type, course_id, len(sub_entries), included
            )
        elif export_type == "db-export-radio":
            from anytask_scraper.json_db import QueueJsonDB

            queue_entries = list(self.all_queue_entries)
            queue_payload = self.app.queue_cache.get(
                course_id,
                ReviewQueue(course_id=course_id),
            )
            if not queue_entries:
                queue_entries = list(queue_payload.entries)
            if task_filters:
                queue_entries = [e for e in queue_entries if e.task_title in task_filters]
            if status_filters:
                queue_entries = [e for e in queue_entries if e.status_name in status_filters]
            if reviewer_filters:
                queue_entries = [e for e in queue_entries if e.responsible_name in reviewer_filters]
            if last_name_from or last_name_to:
                queue_entries = [
                    e
                    for e in queue_entries
                    if last_name_in_range(
                        e.student_name,
                        last_name_from,
                        last_name_to,
                    )
                ]
            if name_list_filter:
                queue_entries = [
                    e for e in queue_entries if name_matches_list(e.student_name, name_list_filter)
                ]
            if format_type != "json":
                return "[dim]DB export supports JSON format only[/dim]"
            import json as json_mod

            preview_issue_urls = {e.issue_url for e in queue_entries[:max_items] if e.issue_url}
            preview_submissions = {
                issue_url: sub
                for issue_url, sub in queue_payload.submissions.items()
                if issue_url in preview_issue_urls
            }
            preview_queue = ReviewQueue(
                course_id=course_id,
                entries=list(queue_entries[:max_items]),
                submissions=preview_submissions,
            )
            course = self.app.courses.get(course_id)
            preview_db = QueueJsonDB(
                Path(tempfile.gettempdir()) / f"anytask_preview_{course_id}_{uuid4().hex}.json",
                autosave=False,
            )
            preview_db.sync_queue(preview_queue, course_title=course.title if course else "")
            payload = {
                "schema_version": 1,
                "course_id": course_id,
                "filtered_queue_entries": len(queue_entries),
                "preview_sample_size": min(len(queue_entries), max_items),
                "hierarchy": "courses -> students -> assignments -> files",
                "issue_chain": "enabled",
                "snapshot_preview": preview_db.snapshot(),
            }
            preview = json_mod.dumps(payload, indent=2, ensure_ascii=False)
            name = self._resolve_export_filename(f"queue_db_{course_id}.json")
            return f"[bold]{name}[/bold]\n{preview}"

        return "[dim]Select export type[/dim]"

    def _preview_tasks(
        self, tasks: list[Task], fmt: str, course_id: int, total: int, included: list[str]
    ) -> str:
        import json as json_mod

        from anytask_scraper.parser import strip_html

        suffix = f"\n[dim]... and {total - len(tasks)} more[/dim]" if total > len(tasks) else ""

        if fmt == "json":
            items = []
            for i, t in enumerate(tasks, 1):
                item: dict[str, Any] = {}
                if not included or "#" in included:
                    item["#"] = i
                if not included or "Title" in included:
                    item["title"] = t.title
                if (not included or "Score" in included) and t.score is not None:
                    item["score"] = t.score
                if (not included or "Max Score" in included) and t.max_score is not None:
                    item["max_score"] = t.max_score
                if (not included or "Status" in included) and t.status:
                    item["status"] = t.status
                if (not included or "Deadline" in included) and t.deadline:
                    item["deadline"] = t.deadline.strftime("%Y-%m-%d %H:%M")
                if (not included or "Section" in included) and t.section:
                    item["section"] = t.section
                if (not included or "Description" in included) and t.description:
                    item["description"] = strip_html(t.description)[:100]
                items.append(item)
            preview = json_mod.dumps(
                {"course_id": course_id, "tasks": items},
                indent=2,
                ensure_ascii=False,
            )
            name = self._resolve_export_filename(f"course_{course_id}.json")
            return f"[bold]{name}[/bold]\n{preview}{suffix}"

        elif fmt == "csv":
            header_parts = []
            if not included or "#" in included:
                header_parts.append("#")
            if not included or "Title" in included:
                header_parts.append("Title")
            if self.is_teacher_view:
                if not included or "Section" in included:
                    header_parts.append("Section")
                if not included or "Max Score" in included:
                    header_parts.append("Max Score")
            else:
                if not included or "Score" in included:
                    header_parts.append("Score")
                if not included or "Status" in included:
                    header_parts.append("Status")
            if not included or "Deadline" in included:
                header_parts.append("Deadline")
            lines = [_csv_row(header_parts)]
            for i, t in enumerate(tasks, 1):
                row_parts = []
                if not included or "#" in included:
                    row_parts.append(str(i))
                if not included or "Title" in included:
                    row_parts.append(t.title)
                if self.is_teacher_view:
                    if not included or "Section" in included:
                        row_parts.append(t.section or "-")
                    if not included or "Max Score" in included:
                        row_parts.append(str(t.max_score) if t.max_score is not None else "-")
                else:
                    if not included or "Score" in included:
                        score = f"{t.score}/{t.max_score}" if t.score is not None else "-"
                        row_parts.append(score)
                    if not included or "Status" in included:
                        row_parts.append(t.status or "-")
                if not included or "Deadline" in included:
                    dl = t.deadline.strftime("%d.%m.%Y") if t.deadline else "-"
                    row_parts.append(dl)
                lines.append(_csv_row(row_parts))
            name = self._resolve_export_filename(f"course_{course_id}.csv")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        elif fmt == "markdown":
            lines = [f"# Course {course_id}", ""]
            for t in tasks:
                if not included or "Title" in included:
                    lines.append(f"## {t.title}")
                if (not included or "Status" in included) and t.status:
                    lines.append(f"Status: {t.status}")
                if (not included or "Deadline" in included) and t.deadline:
                    lines.append(f"Deadline: {t.deadline.strftime('%d.%m.%Y')}")
                lines.append("")
            name = self._resolve_export_filename(f"course_{course_id}.md")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        return "[dim]Select a format[/dim]"

    def _preview_queue(
        self, entries: list[QueueEntry], fmt: str, course_id: int, total: int, included: list[str]
    ) -> str:
        import json as json_mod

        suffix = f"\n[dim]... and {total - len(entries)} more[/dim]" if total > len(entries) else ""

        if fmt == "json":
            items = []
            for i, e in enumerate(entries, 1):
                item: dict[str, Any] = {}
                if not included or "#" in included:
                    item["#"] = i
                if not included or "Student" in included:
                    item["student"] = e.student_name
                if not included or "Task" in included:
                    item["task"] = e.task_title
                if not included or "Status" in included:
                    item["status"] = e.status_name
                if not included or "Reviewer" in included:
                    item["reviewer"] = e.responsible_name
                if not included or "Updated" in included:
                    item["updated"] = e.update_time
                if not included or "Grade" in included:
                    item["grade"] = e.mark
                items.append(item)
            preview = json_mod.dumps(
                {"course_id": course_id, "entries": items},
                indent=2,
                ensure_ascii=False,
            )
            name = self._resolve_export_filename(f"queue_{course_id}.json")
            return f"[bold]{name}[/bold]\n{preview}{suffix}"

        elif fmt == "csv":
            header_parts = []
            if not included or "#" in included:
                header_parts.append("#")
            if not included or "Student" in included:
                header_parts.append("Student")
            if not included or "Task" in included:
                header_parts.append("Task")
            if not included or "Status" in included:
                header_parts.append("Status")
            if not included or "Reviewer" in included:
                header_parts.append("Reviewer")
            if not included or "Updated" in included:
                header_parts.append("Updated")
            if not included or "Grade" in included:
                header_parts.append("Grade")
            lines = [_csv_row(header_parts)]
            for i, e in enumerate(entries, 1):
                row_parts = []
                if not included or "#" in included:
                    row_parts.append(str(i))
                if not included or "Student" in included:
                    row_parts.append(e.student_name)
                if not included or "Task" in included:
                    row_parts.append(e.task_title)
                if not included or "Status" in included:
                    row_parts.append(e.status_name)
                if not included or "Reviewer" in included:
                    row_parts.append(e.responsible_name)
                if not included or "Updated" in included:
                    row_parts.append(e.update_time)
                if not included or "Grade" in included:
                    row_parts.append(e.mark)
                lines.append(_csv_row(row_parts))
            name = self._resolve_export_filename(f"queue_{course_id}.csv")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        elif fmt == "markdown":
            lines = [f"# Queue - Course {course_id}", ""]
            for e in entries:
                parts = []
                if not included or "Student" in included:
                    parts.append(f"**{e.student_name}**")
                if not included or "Task" in included:
                    parts.append(e.task_title)
                if not included or "Status" in included:
                    parts.append(f"[{e.status_name}]")
                lines.append(f"- {' - '.join(parts)}")
            name = self._resolve_export_filename(f"queue_{course_id}.md")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        return "[dim]Select a format[/dim]"

    def _preview_submissions(
        self,
        entries: list[QueueEntry],
        fmt: str,
        course_id: int,
        total: int,
        included: list[str],
    ) -> str:
        import json as json_mod

        suffix = f"\n[dim]... and {total - len(entries)} more[/dim]" if total > len(entries) else ""

        if fmt == "json":
            items = []
            for e in entries:
                item: dict[str, Any] = {}
                if not included or "Issue ID" in included:
                    item["issue_id"] = "-"
                if not included or "Task" in included:
                    item["task"] = e.task_title
                if not included or "Student" in included:
                    item["student"] = e.student_name
                if not included or "Reviewer" in included:
                    item["reviewer"] = e.responsible_name
                if not included or "Status" in included:
                    item["status"] = e.status_name
                if not included or "Grade" in included:
                    item["grade"] = e.mark
                if not included or "Max Score" in included:
                    item["max_score"] = "-"
                if not included or "Deadline" in included:
                    item["deadline"] = "-"
                if not included or "Comments" in included:
                    item["comments"] = 0
                items.append(item)
            preview = json_mod.dumps(
                {"course_id": course_id, "submissions": items},
                indent=2,
                ensure_ascii=False,
            )
            name = self._resolve_export_filename(f"submissions_{course_id}.json")
            return f"[bold]{name}[/bold]\n{preview}{suffix}"

        elif fmt == "csv":
            header_parts = []
            if not included or "Issue ID" in included:
                header_parts.append("Issue ID")
            if not included or "Task" in included:
                header_parts.append("Task")
            if not included or "Student" in included:
                header_parts.append("Student")
            if not included or "Reviewer" in included:
                header_parts.append("Reviewer")
            if not included or "Status" in included:
                header_parts.append("Status")
            if not included or "Grade" in included:
                header_parts.append("Grade")
            if not included or "Max Score" in included:
                header_parts.append("Max Score")
            if not included or "Deadline" in included:
                header_parts.append("Deadline")
            if not included or "Comments" in included:
                header_parts.append("Comments")
            lines = [_csv_row(header_parts)]
            for e in entries:
                row_parts = []
                if not included or "Issue ID" in included:
                    row_parts.append("-")
                if not included or "Task" in included:
                    row_parts.append(e.task_title)
                if not included or "Student" in included:
                    row_parts.append(e.student_name)
                if not included or "Reviewer" in included:
                    row_parts.append(e.responsible_name)
                if not included or "Status" in included:
                    row_parts.append(e.status_name)
                if not included or "Grade" in included:
                    row_parts.append(e.mark)
                if not included or "Max Score" in included:
                    row_parts.append("-")
                if not included or "Deadline" in included:
                    row_parts.append("-")
                if not included or "Comments" in included:
                    row_parts.append("0")
                lines.append(_csv_row(row_parts))
            name = self._resolve_export_filename(f"submissions_{course_id}.csv")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        elif fmt == "markdown":
            lines = [f"# Submissions - Course {course_id}", ""]
            for e in entries:
                parts = []
                if not included or "Student" in included:
                    parts.append(f"**{e.student_name}**")
                if not included or "Task" in included:
                    parts.append(e.task_title)
                if not included or "Status" in included:
                    parts.append(f"[{e.status_name}]")
                if not included or "Grade" in included:
                    parts.append(f"Grade: {e.mark}")
                lines.append(f"- {' - '.join(parts)}")
            name = self._resolve_export_filename(f"submissions_{course_id}.md")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        elif fmt == "files":
            return "[dim]Files Only mode:\nDownloads submission files\nto student folders[/dim]"

        return "[dim]Select a format[/dim]"

    def _preview_gradebook(
        self,
        groups: list[GradebookGroup],
        fmt: str,
        course_id: int,
        total: int,
        included: list[str],
    ) -> str:
        import json as json_mod

        all_tasks: list[str] = []
        for g in groups:
            for t in g.task_titles:
                if t not in all_tasks:
                    all_tasks.append(t)

        if fmt == "json":
            items = []
            count = 0
            for g in groups:
                for e in g.entries[:2]:
                    entry_dict: dict[str, Any] = {}
                    if not included or "Group" in included:
                        entry_dict["group"] = g.group_name
                    if not included or "Student" in included:
                        entry_dict["student"] = e.student_name
                    for t in all_tasks:
                        if not included or t in included:
                            entry_dict[t] = e.scores.get(t, None)
                    if not included or "Total" in included:
                        entry_dict["total"] = e.total_score
                    items.append(entry_dict)
                    count += 1
                    if count >= 2:
                        break
                if count >= 2:
                    break
            suffix = f"\n[dim]... and {total - count} more[/dim]" if total > count else ""
            preview = json_mod.dumps(
                {"course_id": course_id, "entries": items},
                indent=2,
                ensure_ascii=False,
            )
            name = self._resolve_export_filename(f"gradebook_{course_id}.json")
            return f"[bold]{name}[/bold]\n{preview}{suffix}"

        elif fmt == "csv":
            header_parts = []
            if not included or "Group" in included:
                header_parts.append("Group")
            if not included or "Student" in included:
                header_parts.append("Student")
            for t in all_tasks:
                if not included or t in included:
                    header_parts.append(t)
            if not included or "Total" in included:
                header_parts.append("Total")
            lines = [_csv_row(header_parts)]
            count = 0
            for g in groups:
                for e in g.entries[:2]:
                    row_parts = []
                    if not included or "Group" in included:
                        row_parts.append(g.group_name)
                    if not included or "Student" in included:
                        row_parts.append(e.student_name)
                    for t in all_tasks:
                        if not included or t in included:
                            row_parts.append(str(e.scores.get(t, "")))
                    if not included or "Total" in included:
                        row_parts.append(str(e.total_score))
                    lines.append(_csv_row(row_parts))
                    count += 1
                    if count >= 2:
                        break
                if count >= 2:
                    break
            suffix = f"\n[dim]... and {total - count} more[/dim]" if total > count else ""
            name = self._resolve_export_filename(f"gradebook_{course_id}.csv")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        elif fmt == "markdown":
            lines = [f"# Gradebook - Course {course_id}", ""]
            count = 0
            for g in groups:
                lines.append(f"## {g.group_name}")
                for e in g.entries[:2]:
                    scores_str = ", ".join(
                        f"{t}: {e.scores.get(t, '-')}"
                        for t in g.task_titles[:3]
                        if not included or t in included
                    )
                    if scores_str:
                        lines.append(f"- {e.student_name}: {scores_str}, Total: {e.total_score}")
                    else:
                        lines.append(f"- {e.student_name}: Total {e.total_score}")
                    count += 1
                    if count >= 2:
                        break
                if count >= 2:
                    break
            suffix = f"\n[dim]... and {total - count} more[/dim]" if total > count else ""
            name = self._resolve_export_filename(f"gradebook_{course_id}.md")
            return f"[bold]{name}[/bold]\n" + "\n".join(lines) + suffix

        return "[dim]Select a format[/dim]"

    @on(Button.Pressed, "#export-btn")
    def _handle_export(self) -> None:
        if self._selected_course_id is None:
            self._set_export_status("Select a course first", "error")
            return

        format_set = self.query_one("#format-set", RadioSet)  # type: ignore[attr-defined]
        fmt_btn = format_set.pressed_button
        if not fmt_btn:
            self._set_export_status("Select a format", "error")
            return

        fmt_map = {
            "json-radio": "json",
            "md-radio": "markdown",
            "csv-radio": "csv",
            "files-radio": "files",
        }
        fmt = fmt_map.get(fmt_btn.id or "", "json")

        type_set = self.query_one("#export-type-set", RadioSet)  # type: ignore[attr-defined]
        type_btn = type_set.pressed_button
        export_type = type_btn.id if type_btn else "tasks-export-radio"

        output_dir = self.query_one("#output-dir-input", Input).value.strip() or "./output"  # type: ignore[attr-defined]
        output_path = Path(output_dir).expanduser().resolve()

        filters = self._get_current_export_filters()
        columns = self._get_included_columns()
        filename = self._get_custom_export_filename()
        include_files = self._get_include_submission_files() or fmt == "files"
        clone_repos = self._get_clone_repos()
        if export_type == "db-export-radio" and fmt != "json":
            self._set_export_status("DB export supports JSON format only", "error")
            return
        self._set_export_status(f"Exporting to {output_path}...", "info")
        self._do_export(
            fmt,
            output_path,
            export_type or "tasks-export-radio",
            filters,
            columns,
            filename,
            include_files,
            clone_repos,
        )

    def _set_export_status(self, message: str, kind: str = "info") -> None:
        label = self.query_one("#export-status-label", Label)  # type: ignore[attr-defined]
        label.update(message)
        label.remove_class("error", "success", "info")
        label.add_class(kind)

    @work(thread=True)
    def _do_export(
        self,
        fmt: str,
        output_path: Path,
        export_type: str = "tasks-export-radio",
        filters: dict[str, ExportFilterValue] | None = None,
        columns: list[str] | None = None,
        filename: str | None = None,
        include_files: bool = False,
        clone_repos: bool = False,
    ) -> None:
        import sys

        from anytask_scraper.models import (
            Course,
            GradebookGroup,
            ReviewQueue,
            check_name_list_matches,
            last_name_in_range,
            name_matches_list,
        )
        from anytask_scraper.parser import extract_issue_id_from_breadcrumb as _eid
        from anytask_scraper.parser import parse_submission_page as _psp
        from anytask_scraper.storage import (
            download_submission_files as _dsf,
        )
        from anytask_scraper.storage import (
            save_course_csv,
            save_course_json,
            save_course_markdown,
            save_gradebook_csv,
            save_gradebook_json,
            save_gradebook_markdown,
            save_queue_csv,
            save_queue_json,
            save_queue_markdown,
            save_submissions_json,
            save_submissions_markdown,
        )
        from anytask_scraper.storage import (
            save_submissions_csv as _ssc,
        )

        _main = sys.modules.get("anytask_scraper.tui.screens.main")
        extract_issue_id_from_breadcrumb = getattr(_main, "extract_issue_id_from_breadcrumb", _eid)
        parse_submission_page = getattr(_main, "parse_submission_page", _psp)
        download_submission_files = getattr(_main, "download_submission_files", _dsf)
        save_submissions_csv = getattr(_main, "save_submissions_csv", _ssc)

        try:
            output_path.mkdir(parents=True, exist_ok=True)
            course_id = self._selected_course_id or 0
            task_filters = _extract_filter_values(filters, "task")
            status_filters = _extract_filter_values(filters, "status")
            section_filters = _extract_filter_values(filters, "section")
            reviewer_filters = _extract_filter_values(filters, "reviewer")
            group_filters = _extract_filter_values(filters, "group")
            teacher_filters = _extract_filter_values(filters, "teacher")
            last_name_from = _extract_filter_text(filters, "last_name_from")
            last_name_to = _extract_filter_text(filters, "last_name_to")
            name_list_filter = list(_extract_filter_values(filters, "name_list"))

            if export_type == "tasks-export-radio":
                course = self.app.current_course
                if not course:
                    self.app.call_from_thread(
                        self._set_export_status, "No course selected", "error"
                    )
                    return

                tasks = list(course.tasks)

                if task_filters:
                    tasks = [t for t in tasks if t.title in task_filters]
                if section_filters:
                    tasks = [t for t in tasks if t.section in section_filters]
                if status_filters:
                    tasks = [t for t in tasks if t.status in status_filters]

                filtered_course = Course(
                    course_id=course.course_id,
                    title=course.title,
                    teachers=list(course.teachers),
                    tasks=tasks,
                )

                if fmt == "json":
                    saved = save_course_json(
                        filtered_course,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                elif fmt == "csv":
                    saved = save_course_csv(
                        filtered_course,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                else:
                    saved = save_course_markdown(
                        filtered_course,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )

            elif export_type == "queue-export-radio":
                queue = self._load_queue_for_export(course_id)

                entries = list(queue.entries)
                if task_filters:
                    entries = [e for e in entries if e.task_title in task_filters]
                if status_filters:
                    entries = [e for e in entries if e.status_name in status_filters]
                if reviewer_filters:
                    entries = [e for e in entries if e.responsible_name in reviewer_filters]
                if last_name_from or last_name_to:
                    entries = [
                        e
                        for e in entries
                        if last_name_in_range(
                            e.student_name,
                            last_name_from,
                            last_name_to,
                        )
                    ]
                if name_list_filter:
                    entries = [
                        e for e in entries if name_matches_list(e.student_name, name_list_filter)
                    ]
                    student_names = list({e.student_name for e in entries})
                    matched, unmatched = check_name_list_matches(
                        student_names, list(name_list_filter)
                    )
                    total_names = len(matched) + len(unmatched)
                    match_msg = f"{len(matched)}/{total_names} names matched"
                    if unmatched:
                        match_msg += f"; unmatched: {', '.join(unmatched[:5])}"
                        if len(unmatched) > 5:
                            match_msg += f" (+{len(unmatched) - 5} more)"
                    self.app.call_from_thread(self._set_export_status, match_msg, "info")

                filtered_queue = ReviewQueue(
                    course_id=queue.course_id,
                    entries=entries,
                )

                if fmt == "json":
                    saved = save_queue_json(
                        filtered_queue,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                elif fmt == "csv":
                    saved = save_queue_csv(
                        filtered_queue,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                else:
                    saved = save_queue_markdown(
                        filtered_queue,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )

            elif export_type == "subs-export-radio":
                queue = self._load_queue_for_export(course_id)
                entries = list(queue.entries)

                if task_filters:
                    entries = [e for e in entries if e.task_title in task_filters]
                if status_filters:
                    entries = [e for e in entries if e.status_name in status_filters]
                if reviewer_filters:
                    entries = [e for e in entries if e.responsible_name in reviewer_filters]
                if last_name_from or last_name_to:
                    entries = [
                        e
                        for e in entries
                        if last_name_in_range(
                            e.student_name,
                            last_name_from,
                            last_name_to,
                        )
                    ]
                if name_list_filter:
                    entries = [
                        e for e in entries if name_matches_list(e.student_name, name_list_filter)
                    ]
                    student_names = list({e.student_name for e in entries})
                    matched, unmatched = check_name_list_matches(
                        student_names, list(name_list_filter)
                    )
                    total_names = len(matched) + len(unmatched)
                    match_msg = f"{len(matched)}/{total_names} names matched"
                    if unmatched:
                        match_msg += f"; unmatched: {', '.join(unmatched[:5])}"
                        if len(unmatched) > 5:
                            match_msg += f" (+{len(unmatched) - 5} more)"
                    self.app.call_from_thread(self._set_export_status, match_msg, "info")

                accessible_entries = [e for e in entries if e.has_issue_access and e.issue_url]
                if not accessible_entries:
                    self.app.call_from_thread(
                        self._set_export_status,
                        "No accessible submissions found.",
                        "error",
                    )
                    return

                client = self.app.client
                if not client:
                    self.app.call_from_thread(
                        self._set_export_status,
                        "Not logged in",
                        "error",
                    )
                    return

                from anytask_scraper.models import Submission as SubmissionModel

                subs: list[SubmissionModel] = []
                fetch_failures = 0
                total = len(accessible_entries)
                for i, entry in enumerate(accessible_entries, 1):
                    self.app.call_from_thread(
                        self._set_export_status,
                        f"Fetching submissions: {i}/{total}...",
                        "info",
                    )
                    try:
                        sub_html = client.fetch_submission_page(entry.issue_url)
                        issue_id = extract_issue_id_from_breadcrumb(sub_html)
                        if issue_id == 0:
                            continue
                        sub = parse_submission_page(sub_html, issue_id, issue_url=entry.issue_url)
                        subs.append(sub)
                    except Exception:
                        logger.debug("Failed to fetch submission", exc_info=True)
                        fetch_failures += 1
                        continue

                if not subs:
                    msg = (
                        f"All {fetch_failures} submission(s) failed to fetch."
                        if fetch_failures > 0
                        else "No accessible submissions found."
                    )
                    self.app.call_from_thread(self._set_export_status, msg, "error")
                    return

                total_files = 0
                total_repos = 0
                if include_files:
                    self.app.call_from_thread(
                        self._set_export_status,
                        f"Downloading files for {len(subs)} submissions...",
                        "info",
                    )
                    for sub in subs:
                        downloaded = download_submission_files(client, sub, output_path)
                        total_files += len(downloaded)

                if clone_repos:
                    from anytask_scraper.storage import clone_submission_repos

                    self.app.call_from_thread(
                        self._set_export_status,
                        f"Cloning repos for {len(subs)} submissions...",
                        "info",
                    )
                    for sub in subs:
                        cloned = clone_submission_repos(sub, output_path)
                        total_repos += len(cloned)

                if fmt == "files":
                    status = f"Downloaded {total_files} files to {output_path}"
                    if total_repos:
                        status += f" ({total_repos} repos cloned)"
                    self.app.call_from_thread(
                        self._set_export_status,
                        status,
                        "success",
                    )
                    return
                elif fmt == "csv":
                    saved = save_submissions_csv(
                        subs,
                        course_id,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                elif fmt == "json":
                    saved = save_submissions_json(
                        subs,
                        course_id,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                else:
                    saved = save_submissions_markdown(
                        subs,
                        course_id,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )

                saved_label = saved.name if hasattr(saved, "name") else saved
                status = f"Saved: {saved_label}"
                if include_files:
                    status += f" ({total_files} files downloaded)"
                if clone_repos and total_repos:
                    status += f" ({total_repos} repos cloned)"
                if fetch_failures > 0:
                    status += f" ({fetch_failures} failed)"
                self.app.call_from_thread(
                    self._set_export_status,
                    status,
                    "success",
                )
                return
            elif export_type == "db-export-radio":
                from anytask_scraper.json_db import QueueJsonDB

                if fmt != "json":
                    self.app.call_from_thread(
                        self._set_export_status,
                        "DB export supports JSON format only",
                        "error",
                    )
                    return
                queue = self._load_queue_for_export(course_id)
                entries = list(queue.entries)
                if task_filters:
                    entries = [e for e in entries if e.task_title in task_filters]
                if status_filters:
                    entries = [e for e in entries if e.status_name in status_filters]
                if reviewer_filters:
                    entries = [e for e in entries if e.responsible_name in reviewer_filters]
                if last_name_from or last_name_to:
                    entries = [
                        e
                        for e in entries
                        if last_name_in_range(
                            e.student_name,
                            last_name_from,
                            last_name_to,
                        )
                    ]
                if name_list_filter:
                    entries = [
                        e for e in entries if name_matches_list(e.student_name, name_list_filter)
                    ]
                    student_names = list({e.student_name for e in entries})
                    matched, unmatched = check_name_list_matches(
                        student_names, list(name_list_filter)
                    )
                    total_names = len(matched) + len(unmatched)
                    match_msg = f"{len(matched)}/{total_names} names matched"
                    if unmatched:
                        match_msg += f"; unmatched: {', '.join(unmatched[:5])}"
                        if len(unmatched) > 5:
                            match_msg += f" (+{len(unmatched) - 5} more)"
                    self.app.call_from_thread(self._set_export_status, match_msg, "info")
                allowed_issue_urls = {e.issue_url for e in entries if e.issue_url}
                submissions = {
                    issue_url: sub
                    for issue_url, sub in queue.submissions.items()
                    if issue_url in allowed_issue_urls
                }
                filtered_queue = ReviewQueue(
                    course_id=queue.course_id,
                    entries=entries,
                    submissions=submissions,
                )
                default_name = f"queue_db_{course_id}.json"
                resolved_name = self._resolve_export_filename(default_name)
                db_path = output_path / resolved_name
                db = QueueJsonDB(db_path)
                course = self.app.courses.get(course_id)
                course_title = course.title if course else ""
                newly_flagged = db.sync_queue(filtered_queue, course_title=course_title)
                saved = db_path
                self.app.call_from_thread(
                    self._set_export_status,
                    f"Saved: {saved.name} ({newly_flagged} new/updated)",
                    "success",
                )
                return
            elif export_type == "gb-export-radio":
                from anytask_scraper.models import Gradebook

                gradebook = self._load_gradebook_for_export(course_id)  # type: ignore[attr-defined]

                groups = list(gradebook.groups)
                if group_filters:
                    groups = [g for g in groups if g.group_name in group_filters]
                if teacher_filters:
                    groups = [g for g in groups if g.teacher_name in teacher_filters]
                if last_name_from or last_name_to or name_list_filter:
                    groups = [
                        GradebookGroup(
                            group_name=g.group_name,
                            group_id=g.group_id,
                            teacher_name=g.teacher_name,
                            task_titles=list(g.task_titles),
                            max_scores=dict(g.max_scores),
                            entries=[
                                e
                                for e in g.entries
                                if last_name_in_range(e.student_name, last_name_from, last_name_to)
                                and (
                                    not name_list_filter
                                    or name_matches_list(e.student_name, name_list_filter)
                                )
                            ],
                        )
                        for g in groups
                    ]
                    groups = [g for g in groups if g.entries]
                if name_list_filter:
                    student_names = list({e.student_name for g in groups for e in g.entries})
                    matched, unmatched = check_name_list_matches(
                        student_names, list(name_list_filter)
                    )
                    total_names = len(matched) + len(unmatched)
                    match_msg = f"{len(matched)}/{total_names} names matched"
                    if unmatched:
                        match_msg += f"; unmatched: {', '.join(unmatched[:5])}"
                        if len(unmatched) > 5:
                            match_msg += f" (+{len(unmatched) - 5} more)"
                    self.app.call_from_thread(self._set_export_status, match_msg, "info")

                filtered_gradebook = Gradebook(
                    course_id=gradebook.course_id,
                    groups=groups,
                )

                if fmt == "json":
                    saved = save_gradebook_json(
                        filtered_gradebook,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                elif fmt == "csv":
                    saved = save_gradebook_csv(
                        filtered_gradebook,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
                else:
                    saved = save_gradebook_markdown(
                        filtered_gradebook,
                        output_path,
                        columns=columns,
                        filename=filename,
                    )
            else:
                self.app.call_from_thread(self._set_export_status, "Unknown export type", "error")
                return

            self.app.call_from_thread(
                self._set_export_status,
                f"Saved: {saved.name if hasattr(saved, 'name') else saved}",
                "success",
            )
        except Exception as e:
            self.app.call_from_thread(
                self._set_export_status,
                f"Export failed: {e}",
                "error",
            )

    def _load_queue_for_export(self, course_id: int) -> ReviewQueue:
        import sys

        from anytask_scraper.models import QueueEntry, ReviewQueue
        from anytask_scraper.parser import extract_csrf_from_queue_page as _extract_csrf

        _extract_csrf_fn = getattr(
            sys.modules.get("anytask_scraper.tui.screens.main"),
            "extract_csrf_from_queue_page",
            _extract_csrf,
        )

        cache = self.app.queue_cache
        cached = cache.get(course_id)
        if cached is not None:
            self.all_queue_entries = list(cached.entries)
            self.filtered_queue_entries = list(cached.entries)
            self._queue_loaded_for = course_id
            self.app.call_from_thread(self._update_queue_info, f"{len(cached.entries)} entries")  # type: ignore[attr-defined]
            return cached

        client = self.app.client
        if not client:
            raise RuntimeError("Not logged in")

        queue_html = client.fetch_queue_page(course_id)
        csrf = _extract_csrf_fn(queue_html)
        if not csrf:
            raise RuntimeError("Could not extract queue CSRF token")
        raw = client.fetch_all_queue_entries(course_id, csrf)
        entries = [
            QueueEntry(
                student_name=str(r.get("student_name", "")),
                student_url=str(r.get("student_url", "")),
                task_title=str(r.get("task_title", "")),
                update_time=str(r.get("update_time", "")),
                mark=str(r.get("mark", "")),
                status_color=str(r.get("status_color", "default")),
                status_name=str(r.get("status_name", "")),
                responsible_name=str(r.get("responsible_name", "")),
                responsible_url=str(r.get("responsible_url", "")),
                has_issue_access=bool(r.get("has_issue_access", False)),
                issue_url=str(r.get("issue_url", "")),
            )
            for r in raw
        ]
        queue = ReviewQueue(course_id=course_id, entries=entries)
        cache[course_id] = queue
        self.all_queue_entries = entries
        self.filtered_queue_entries = list(entries)
        self._queue_loaded_for = course_id
        self.app.call_from_thread(self._update_queue_filter_options)  # type: ignore[attr-defined]
        self.app.call_from_thread(self._rebuild_queue_table)  # type: ignore[attr-defined]
        self.app.call_from_thread(self._update_queue_info, f"{len(entries)} entries")  # type: ignore[attr-defined]
        return queue
