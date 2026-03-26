from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import httpx
from textual import events, on, work
from textual.widgets import (
    DataTable,
    Input,
    Label,
    OptionList,
    RadioSet,
    Static,
    TabbedContent,
)
from textual.widgets.option_list import Option

from anytask_scraper.tui.clipboard import (
    copy_text_to_clipboard,
    format_course_for_clipboard,
)
from anytask_scraper.tui.widgets.filter_bar import (
    GradebookFilterBar,
    QueueFilterBar,
    TaskFilterBar,
)

if TYPE_CHECKING:
    from anytask_scraper.models import Course, GradebookGroup, QueueEntry, Submission, Task
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class CoreMixin:
    app: AnytaskApp

    _help_visible: bool
    _action_menu_open: bool
    _selected_course_id: int | None
    _focus_left_pane: bool
    is_teacher_view: bool
    all_tasks: list[Task]
    filtered_tasks: list[Task]
    _task_submission_cache: dict[tuple[int | None, str], Submission]
    _task_filter_undo: dict[str, Any] | None
    all_queue_entries: list[QueueEntry]
    filtered_queue_entries: list[QueueEntry]
    _queue_loaded_for: int | None
    _queue_preview_submission: Submission | None
    _queue_filter_undo: dict[str, Any] | None
    _gradebook_loaded_for: int | None
    all_gradebook_groups: list[GradebookGroup]
    filtered_gradebook_groups: list[GradebookGroup]
    _gb_sort_column: int | None
    _gb_sort_reverse: bool
    _gb_all_tasks: list[str]
    _gb_filter_undo: dict[str, Any] | None

    focused: Any

    def _maybe_load_queue(self) -> None:
        raise NotImplementedError

    def _maybe_load_gradebook(self) -> None:
        raise NotImplementedError

    def _copy_task_payload(self) -> tuple[str, str] | None:
        raise NotImplementedError

    def _copy_queue_payload(self) -> tuple[str, str] | None:
        raise NotImplementedError

    def _copy_gradebook_payload(self) -> tuple[str, str] | None:
        raise NotImplementedError

    def _copy_export_preview_payload(self) -> tuple[str, str] | None:
        raise NotImplementedError

    def _export_focus_next(self) -> None:
        raise NotImplementedError

    def _export_focus_prev(self) -> None:
        raise NotImplementedError

    def _get_current_export_type(self) -> str:
        raise NotImplementedError

    def _update_export_filters(self) -> None:
        raise NotImplementedError

    def _update_params(self) -> None:
        raise NotImplementedError

    def _refresh_export_preview(self) -> None:
        raise NotImplementedError

    def _set_export_filters_loading_state(self) -> None:
        raise NotImplementedError

    def _set_export_status(self, text: str) -> None:
        raise NotImplementedError

    def _start_export_preload(self, export_type: str) -> None:
        raise NotImplementedError

    def _rebuild_task_table(self) -> None:
        raise NotImplementedError

    def _clear_detail(self) -> None:
        raise NotImplementedError

    def _update_task_filter_options(self) -> None:
        raise NotImplementedError

    def _setup_task_table_columns(self) -> None:
        raise NotImplementedError

    def _rebuild_queue_table(self) -> None:
        raise NotImplementedError

    def _clear_queue_detail(self) -> None:
        raise NotImplementedError

    def _rebuild_gradebook_table(self, groups: list[GradebookGroup]) -> None:
        raise NotImplementedError

    def _update_key_bar(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active

        common = (
            "[dim]ctrl+q[/dim] Quit  "
            "[dim]a[/dim] Add  "
            "[dim]d[/dim] Discover  "
            "[dim]x[/dim] Remove  "
            "[dim]ctrl+y[/dim] Copy  "
            "[dim]ctrl+l[/dim] Logout"
        )

        if active in ("tasks-tab", "queue-tab", "gradebook-tab"):
            hints = (
                "[dim]/[/dim] Filter  "
                "[dim]r[/dim] Reset  "
                "[dim]u[/dim] Undo  "
                "[dim]?[/dim] Help  " + common
            )
        elif active == "export-tab":
            hints = "[dim]ctrl+\u2191/\u2193[/dim] Navigate  [dim]?[/dim] Help  " + common
        else:
            hints = common

        self.query_one("#key-bar", Static).update(hints)  # type: ignore[attr-defined]

    def _show_status(self, message: str, kind: str = "info", timeout: float = 4) -> None:
        line = self.query_one("#status-line", Static)  # type: ignore[attr-defined]
        style_map = {
            "error": "[bold red]",
            "warning": "[bold yellow]",
            "success": "[bold green]",
            "info": "[dim]",
        }
        prefix = style_map.get(kind, "[dim]")
        close = prefix.replace("[", "[/")
        line.update(f"{prefix}{message}{close}")
        if timeout > 0:
            self.set_timer(timeout, self._clear_status)  # type: ignore[attr-defined]

    def _clear_status(self) -> None:
        self.query_one("#status-line", Static).update("")  # type: ignore[attr-defined]

    def action_toggle_help(self) -> None:
        panel = self.query_one("#help-panel", Static)  # type: ignore[attr-defined]
        self._help_visible = not self._help_visible
        if self._help_visible:
            panel.update(
                "[bold]Navigation[/bold]\n"
                "  Tab / Shift+Tab   cycle focus\n"
                "  h / l             left / right pane\n"
                "  j / k             up / down\n"
                "  1 / 2 / 3 / 4     switch tabs\n"
                "\n"
                "[bold]Filters[/bold]\n"
                "  /                 focus filter\n"
                "  Ctrl+\u2190/\u2192          cycle filter fields\n"
                "  Ctrl+\u2191            jump to filters\n"
                "  Ctrl+\u2193            jump to table\n"
                "  r                 reset filters\n"
                "  u                 undo reset\n"
                "\n"
                "[bold]Actions[/bold]\n"
                "  a                 add course\n"
                "  x                 remove course\n"
                "  Ctrl+Y            copy current selection\n"
                "  Right click       open action menu\n"
                "  Enter             select / open\n"
                "  Esc               back / dismiss\n"
                "  Ctrl+Q            quit\n"
                "  Ctrl+C \u00d72         quit"
            )
            panel.add_class("visible")
        else:
            panel.update("")
            panel.remove_class("visible")

    def action_tab_tasks(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tasks-tab"  # type: ignore[attr-defined]
        self.query_one("#task-table", DataTable).focus()  # type: ignore[attr-defined]

    def action_tab_queue(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "queue-tab"  # type: ignore[attr-defined]
        self.query_one("#queue-table", DataTable).focus()  # type: ignore[attr-defined]

    def action_tab_export(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "export-tab"  # type: ignore[attr-defined]
        self.query_one("#export-type-set", RadioSet).focus()  # type: ignore[attr-defined]

    def action_tab_gradebook(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "gradebook-tab"  # type: ignore[attr-defined]
        self.query_one("#gradebook-table", DataTable).focus()  # type: ignore[attr-defined]

    @on(TabbedContent.TabActivated, "#main-tabs")
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._update_key_bar()
        if event.pane.id == "queue-tab":
            self._maybe_load_queue()
        elif event.pane.id == "gradebook-tab":
            self._maybe_load_gradebook()

    def _get_focus_order(self) -> list[str]:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        zones = ["#course-list"]
        if active == "tasks-tab":
            zones += ["#task-table", "#task-filter-bar"]
        elif active == "queue-tab":
            zones += ["#queue-table", "#queue-filter-bar"]
        elif active == "gradebook-tab":
            zones += ["#gradebook-table", "#gb-filter-bar"]
        elif active == "export-tab":
            zones += [
                "#export-type-set",
                "#format-set",
                "#export-filter-task",
                "#export-filter-status",
                "#export-filter-reviewer",
                "#param-option-list",
                "#export-include-files-set",
                "#output-dir-input",
                "#export-filename-input",
                "#export-btn",
            ]
        return zones

    def action_cycle_focus(self) -> None:
        focused = self.focused
        if focused is not None:
            tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
            active = tabs.active
            if active == "tasks-tab":
                task_bar = self.query_one("#task-filter-bar", TaskFilterBar)  # type: ignore[attr-defined]
                if focused in task_bar.walk_children():
                    if task_bar.focus_next_filter():
                        return
                    self.query_one("#task-table", DataTable).focus()  # type: ignore[attr-defined]
                    return
            elif active == "queue-tab":
                queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)  # type: ignore[attr-defined]
                if focused in queue_bar.walk_children():
                    if queue_bar.focus_next_filter():
                        return
                    self.query_one("#queue-table", DataTable).focus()  # type: ignore[attr-defined]
                    return
            elif active == "gradebook-tab":
                gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)  # type: ignore[attr-defined]
                if focused in gb_bar.walk_children():
                    if gb_bar.focus_next_filter():
                        return
                    self.query_one("#gradebook-table", DataTable).focus()  # type: ignore[attr-defined]
                    return

        zones = self._get_focus_order()
        current = self._find_current_zone(zones)
        next_idx = (current + 1) % len(zones)
        self._focus_zone(zones[next_idx])

    def action_cycle_focus_back(self) -> None:
        focused = self.focused
        if focused is not None:
            tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
            active = tabs.active
            if active == "tasks-tab":
                task_bar = self.query_one("#task-filter-bar", TaskFilterBar)  # type: ignore[attr-defined]
                if focused in task_bar.walk_children():
                    if task_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
                    return
            elif active == "queue-tab":
                queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)  # type: ignore[attr-defined]
                if focused in queue_bar.walk_children():
                    if queue_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
                    return
            elif active == "gradebook-tab":
                gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)  # type: ignore[attr-defined]
                if focused in gb_bar.walk_children():
                    if gb_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
                    return

        zones = self._get_focus_order()
        current = self._find_current_zone(zones)
        prev_idx = (current - 1) % len(zones)
        self._focus_zone(zones[prev_idx])

    def _find_current_zone(self, zones: list[Any]) -> int:
        focused = self.focused
        if focused is None:
            return -1
        for i, zone_id in enumerate(zones):
            if isinstance(zone_id, str):
                try:
                    widget = self.query_one(zone_id)  # type: ignore[attr-defined]
                except Exception:
                    continue
            else:
                widget = zone_id
            if widget is focused or focused in widget.walk_children():
                return i
        return -1

    def _focus_zone(self, zone_id: str) -> None:
        if zone_id == "#task-filter-bar":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_text()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#queue-filter-bar":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_text()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#course-list":
            self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = True
        elif zone_id == "#task-table":
            self.query_one("#task-table", DataTable).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#queue-table":
            self.query_one("#queue-table", DataTable).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#gradebook-table":
            self.query_one("#gradebook-table", DataTable).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#gb-filter-bar":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_text()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#format-set":
            self.query_one("#format-set", RadioSet).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#output-dir-input":
            self.query_one("#output-dir-input", Input).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#export-filename-input":
            self.query_one("#export-filename-input", Input).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        elif zone_id == "#export-include-files-set":
            self.query_one("#export-include-files-set", RadioSet).focus()  # type: ignore[attr-defined]
            self._focus_left_pane = False
        else:
            with suppress(Exception):
                self.query_one(zone_id).focus()  # type: ignore[attr-defined]
                self._focus_left_pane = False

    def action_focus_left(self) -> None:
        self._focus_left_pane = True
        self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]

    def action_focus_right(self) -> None:
        self._focus_left_pane = False
        self.action_focus_table()

    def action_focus_filter(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "export-tab":
            self._export_focus_prev()
            return
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_text()  # type: ignore[attr-defined]
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_text()  # type: ignore[attr-defined]
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_text()  # type: ignore[attr-defined]

    def action_focus_table(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "export-tab":
            self._export_focus_next()
            return
        if active == "tasks-tab":
            self.query_one("#task-table", DataTable).focus()  # type: ignore[attr-defined]
        elif active == "queue-tab":
            self.query_one("#queue-table", DataTable).focus()  # type: ignore[attr-defined]
        elif active == "gradebook-tab":
            self.query_one("#gradebook-table", DataTable).focus()  # type: ignore[attr-defined]

    def action_filter_next(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            if getattr(focused, "id", None) in self._LN_INPUT_IDS:  # type: ignore[attr-defined]
                tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
                if tabs.active == "export-tab":
                    self._export_focus_next()
            return
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_next_filter()  # type: ignore[attr-defined]
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_next_filter()  # type: ignore[attr-defined]
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_next_filter()  # type: ignore[attr-defined]

    def action_filter_prev(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            if getattr(focused, "id", None) in self._LN_INPUT_IDS:  # type: ignore[attr-defined]
                tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
                if tabs.active == "export-tab":
                    self._export_focus_prev()
            return
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_prev_filter()  # type: ignore[attr-defined]
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_prev_filter()  # type: ignore[attr-defined]
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_prev_filter()  # type: ignore[attr-defined]

    def on_key(self, event: object) -> None:
        from textual.events import Key

        if not isinstance(event, Key):
            return

        focused = self.focused
        if focused is None:
            return

        if isinstance(focused, (OptionList, DataTable)):
            if event.key == "j":
                event.prevent_default()
                focused.action_cursor_down()
            elif event.key == "k":
                event.prevent_default()
                focused.action_cursor_up()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 3:
            return
        event.prevent_default()
        event.stop()
        self._open_action_menu()

    def _open_action_menu(self) -> None:
        if self._action_menu_open:
            return
        self._action_menu_open = True
        from anytask_scraper.tui.screens.action_menu import ActionMenuScreen

        self.app.push_screen(
            ActionMenuScreen(title="Actions", copy_label="Copy current selection"),
            self._handle_action_menu_result,
        )

    def _handle_action_menu_result(self, result: str | None) -> None:
        self._action_menu_open = False
        if result == "copy":
            self.action_copy_selection()

    def action_copy_selection(self) -> None:
        import sys

        payload = self._build_copy_payload()
        if payload is None:
            self._show_status("Nothing to copy", kind="warning", timeout=2)
            return

        label, text = payload
        _copy_fn = getattr(
            sys.modules.get("anytask_scraper.tui.screens.main"),
            "copy_text_to_clipboard",
            copy_text_to_clipboard,
        )
        success, method = _copy_fn(text, app=self.app)
        if not success:
            self._show_status("Failed to copy to clipboard", kind="error")
            return

        method_suffix = f" via {method}" if method else ""
        self._show_status(
            f"Copied {label} to clipboard{method_suffix}",
            kind="success",
            timeout=2,
        )

    def _build_copy_payload(self) -> tuple[str, str] | None:
        focused = self.focused
        if isinstance(focused, OptionList):
            return self._copy_course_payload()

        active = self.query_one("#main-tabs", TabbedContent).active  # type: ignore[attr-defined]
        if active == "tasks-tab":
            return self._copy_task_payload()
        if active == "queue-tab":
            return self._copy_queue_payload()
        if active == "gradebook-tab":
            return self._copy_gradebook_payload()
        if active == "export-tab":
            return self._copy_export_preview_payload()
        return None

    def _copy_course_payload(self) -> tuple[str, str] | None:
        if self._selected_course_id is None:
            return None
        course = self.app.courses.get(self._selected_course_id)
        title = course.title if course is not None else f"Course {self._selected_course_id}"
        text = format_course_for_clipboard(self._selected_course_id, title)
        return ("course", text)

    def _table_cursor_index(self, table: DataTable[Any], size: int) -> int | None:
        if size <= 0:
            return None
        cursor_row = getattr(table, "cursor_row", None)
        if not isinstance(cursor_row, int):
            return None
        if cursor_row < 0:
            return None
        if cursor_row >= size:
            return size - 1
        return cursor_row

    def action_reset_filters(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "tasks-tab":
            task_bar = self.query_one("#task-filter-bar", TaskFilterBar)  # type: ignore[attr-defined]
            self._task_filter_undo = task_bar.save_state()
            task_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)
        elif active == "queue-tab":
            queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)  # type: ignore[attr-defined]
            self._queue_filter_undo = queue_bar.save_state()
            queue_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)
        elif active == "gradebook-tab":
            gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)  # type: ignore[attr-defined]
            self._gb_filter_undo = gb_bar.save_state()
            gb_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)

    def action_undo_filters(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        active = tabs.active
        if active == "tasks-tab" and self._task_filter_undo is not None:
            task_bar = self.query_one("#task-filter-bar", TaskFilterBar)  # type: ignore[attr-defined]
            task_bar.restore_state(self._task_filter_undo)
            self._task_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        elif active == "queue-tab" and self._queue_filter_undo is not None:
            queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)  # type: ignore[attr-defined]
            queue_bar.restore_state(self._queue_filter_undo)
            self._queue_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        elif active == "gradebook-tab" and self._gb_filter_undo is not None:
            gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)  # type: ignore[attr-defined]
            gb_bar.restore_state(self._gb_filter_undo)
            self._gb_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        else:
            self._show_status("Nothing to undo", kind="warning", timeout=2)

    def action_add_course(self) -> None:
        bar = self.query_one("#course-add-bar")  # type: ignore[attr-defined]
        if "visible" in bar.classes:
            bar.remove_class("visible")
            self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
        else:
            bar.add_class("visible")
            inp = self.query_one("#course-id-input", Input)  # type: ignore[attr-defined]
            inp.value = ""
            inp.focus()

    @on(Input.Submitted, "#course-id-input")
    def _submit_course_id(self) -> None:
        inp = self.query_one("#course-id-input", Input)  # type: ignore[attr-defined]
        try:
            course_id = int(inp.value.strip())
        except ValueError:
            self._show_status("Enter a valid course ID", kind="error")
            return

        if course_id in self.app.courses:
            self._show_status(f"Course {course_id} already loaded", kind="warning")
            return

        inp.value = ""
        self.query_one("#course-add-bar").remove_class("visible")  # type: ignore[attr-defined]
        self._show_status(f"Loading course {course_id}...")
        self._fetch_course(course_id)

    def action_discover_courses(self) -> None:
        self._show_status("Discovering courses from profile...")
        self._do_discover_courses()

    @work(thread=True)
    def _do_discover_courses(self) -> None:
        from anytask_scraper.parser import parse_profile_page

        try:
            client = self.app.client
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            html = client.fetch_profile_page()
            entries = parse_profile_page(html)

            if not entries:
                self.app.call_from_thread(
                    self._show_status, "No courses found on profile", kind="warning"
                )
                return

            teacher_ids = {e.course_id for e in entries if e.role == "teacher"}
            student_only = [
                e for e in entries if e.role == "student" and e.course_id not in teacher_ids
            ]

            added = 0
            for entry in entries:
                if entry.course_id not in self.app.courses:
                    self.app.call_from_thread(self._fetch_course, entry.course_id)
                    added += 1

            role_info = f"{len(teacher_ids)} teacher, {len(student_only)} student-only"
            if added:
                self.app.call_from_thread(
                    self._show_status,
                    f"Discovered {len(entries)} courses ({role_info}), loading {added} new...",
                    kind="success",
                )
            else:
                self.app.call_from_thread(
                    self._show_status,
                    f"All {len(entries)} courses already loaded ({role_info})",
                    kind="info",
                )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Discover failed: {e}",
                kind="error",
            )

    def action_remove_course(self) -> None:
        if self._selected_course_id is None:
            self._show_status("No course selected", kind="warning")
            return
        cid = self._selected_course_id
        self.app.remove_course_id(cid)

        option_list = self.query_one("#course-list", OptionList)  # type: ignore[attr-defined]
        option_list.clear_options()
        for course in self.app.courses.values():
            title = course.title or f"Course {course.course_id}"
            option_list.add_option(Option(title, id=str(course.course_id)))

        self._selected_course_id = None
        self.all_tasks = []
        self.filtered_tasks = []
        self._rebuild_task_table()
        self._clear_detail()
        self.all_queue_entries = []
        self.filtered_queue_entries = []
        self._rebuild_queue_table()
        self._clear_queue_detail()
        self._queue_loaded_for = None
        self.query_one("#queue-info-label", Label).update("Select a teacher course to view queue")  # type: ignore[attr-defined]
        self._show_status(f"Removed course {cid}", kind="success")

    def action_dismiss_overlay(self) -> None:
        add_bar = self.query_one("#course-add-bar")  # type: ignore[attr-defined]
        if "visible" in add_bar.classes:
            add_bar.remove_class("visible")
            self.query_one("#course-list", OptionList).focus()  # type: ignore[attr-defined]
            return
        help_panel = self.query_one("#help-panel", Static)  # type: ignore[attr-defined]
        if self._help_visible:
            self._help_visible = False
            help_panel.update("")
            help_panel.remove_class("visible")

    def action_logout(self) -> None:
        if self.app.client is not None:
            self.app.client.close()
        self.app.client = None
        self.app.session_path = ""
        self.app.current_course = None
        self.app.courses = {}
        self.app.queue_cache = {}
        self.app.gradebook_cache = {}
        from anytask_scraper.tui.screens.login import LoginScreen

        self.app.switch_screen(LoginScreen())

    @on(OptionList.OptionSelected, "#course-list")
    def _course_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id is None:
            return
        course_id = int(option_id)
        course = self.app.courses.get(course_id)
        if course is None:
            return

        self._selected_course_id = course_id
        self.app.current_course = course
        self.all_tasks = list(course.tasks)
        self.is_teacher_view = any(t.section for t in self.all_tasks)

        self._update_task_filter_options()
        self._setup_task_table_columns()
        self.query_one("#task-filter-bar", TaskFilterBar).reset()  # type: ignore[attr-defined]
        self._clear_detail()

        self._queue_loaded_for = None
        self.all_queue_entries = []
        self.filtered_queue_entries = []
        self.query_one("#queue-filter-bar", QueueFilterBar).reset()  # type: ignore[attr-defined]
        self._clear_queue_detail()

        self._gradebook_loaded_for = None
        self.all_gradebook_groups = []
        self.filtered_gradebook_groups = []
        self._gb_sort_column = None
        self._gb_sort_reverse = False
        self._gb_all_tasks = []
        self.query_one("#gb-filter-bar", GradebookFilterBar).reset()  # type: ignore[attr-defined]
        self._rebuild_gradebook_table([])
        self.query_one("#gradebook-info-label", Label).update("Select a course to view gradebook")  # type: ignore[attr-defined]
        self._set_export_status("")

        try:
            from textual.widgets import RadioButton

            queue_export_radio = self.query_one("#queue-export-radio", RadioButton)  # type: ignore[attr-defined]
            subs_export_radio = self.query_one("#subs-export-radio", RadioButton)  # type: ignore[attr-defined]
            db_export_radio = self.query_one("#db-export-radio", RadioButton)  # type: ignore[attr-defined]
            queue_export_radio.disabled = not self.is_teacher_view
            subs_export_radio.disabled = not self.is_teacher_view
            db_export_radio.disabled = not self.is_teacher_view
        except Exception:
            logger.debug("Failed to update export radio buttons", exc_info=True)

        if self.is_teacher_view:
            self.query_one("#queue-info-label", Label).update("Queue loads on demand")  # type: ignore[attr-defined]
        else:
            self.query_one("#queue-info-label", Label).update(  # type: ignore[attr-defined]
                "Queue available for teacher courses only"
            )

        current_export_type = self._get_current_export_type()
        if current_export_type == "tasks-export-radio":
            self._update_export_filters()
            self._update_params()
            self._refresh_export_preview()
        else:
            self._set_export_filters_loading_state()
            self._update_params()
            self._refresh_export_preview()

        tabs = self.query_one("#main-tabs", TabbedContent)  # type: ignore[attr-defined]
        if tabs.active == "queue-tab":
            self._maybe_load_queue()
        elif tabs.active == "gradebook-tab":
            self._maybe_load_gradebook()
        elif tabs.active == "export-tab":
            self._start_export_preload(current_export_type)

    @work(thread=True)
    def _fetch_course(self, course_id: int) -> None:
        from anytask_scraper.parser import parse_course_page

        try:
            client = self.app.client
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            html = client.fetch_course_page(course_id)
            course = parse_course_page(html, course_id)

            self.app.courses[course_id] = course
            self.app.call_from_thread(self.app.save_course_ids)
            self.app.call_from_thread(self._add_course_option, course)
            self.app.call_from_thread(
                self._show_status,
                f"Loaded: {course.title or course_id}",
                kind="success",
            )
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 403:
                msg = f"Course {course_id}: closed or no access"
            elif code == 404:
                msg = f"Course {course_id}: not found"
            else:
                msg = f"Course {course_id}: HTTP {code}"
            self.app.call_from_thread(self._show_status, msg, kind="error")
            self.app.call_from_thread(
                self.app.remove_course_id,
                course_id,
            )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Failed to load {course_id}: {e}",
                kind="error",
            )
            self.app.call_from_thread(
                self.app.remove_course_id,
                course_id,
            )

    def _add_course_option(self, course: Course) -> None:
        option_list = self.query_one("#course-list", OptionList)  # type: ignore[attr-defined]
        title = course.title or f"Course {course.course_id}"
        option_list.add_option(Option(title, id=str(course.course_id)))
        if option_list.highlighted is None:
            option_list.highlighted = 0

    def _push_submission_screen(self, sub: Submission) -> None:
        from anytask_scraper.tui.screens.submission import (
            SubmissionScreen,
        )

        self.app.push_screen(
            SubmissionScreen(
                sub,
                teacher_mode=self.is_teacher_view,
                on_submission_refreshed=self._sync_submission_caches,
            )
        )

    def _sync_submission_caches(self, sub: Submission) -> None:
        if self._selected_course_id is None or not sub.issue_url:
            return

        course_id = self._selected_course_id
        for key, cached in list(self._task_submission_cache.items()):
            if key[0] != course_id:
                continue
            if key[1] == sub.issue_url or cached.issue_id == sub.issue_id:
                self._task_submission_cache[key] = sub

        queue = self.app.queue_cache.get(course_id)
        if queue is not None:
            queue.submissions[sub.issue_url] = sub

        if (
            self._queue_preview_submission is not None
            and self._queue_preview_submission.issue_id == sub.issue_id
        ):
            self._queue_preview_submission = sub
