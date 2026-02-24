"""Unified main screen for anytask-scraper TUI - tabbed layout."""

from __future__ import annotations

import logging
import re
import unicodedata
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
from rich.text import Text
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from anytask_scraper.models import (
    Course,
    Gradebook,
    GradebookEntry,
    GradebookGroup,
    QueueEntry,
    ReviewQueue,
    Submission,
    Task,
)
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    parse_course_page,
    parse_gradebook_page,
    parse_submission_page,
    strip_html,
)
from anytask_scraper.storage import (
    download_submission_files,
    save_course_csv,
    save_course_json,
    save_course_markdown,
    save_gradebook_csv,
    save_gradebook_json,
    save_gradebook_markdown,
    save_queue_csv,
    save_queue_json,
    save_queue_markdown,
    save_submissions_csv,
    save_submissions_json,
    save_submissions_markdown,
)
from anytask_scraper.tui.clipboard import (
    copy_text_to_clipboard,
    format_course_for_clipboard,
    format_queue_entry_for_clipboard,
    format_table_row_for_clipboard,
    format_task_for_clipboard,
    normalize_table_header,
    rich_markup_to_plain,
)
from anytask_scraper.tui.export_params import (
    QUEUE_PARAMS,
    SUBMISSIONS_PARAMS,
    TASKS_STUDENT_PARAMS,
    TASKS_TEACHER_PARAMS,
    gradebook_params,
)
from anytask_scraper.tui.widgets.filter_bar import (
    GradebookFilterBar,
    QueueFilterBar,
    TaskFilterBar,
)
from anytask_scraper.tui.widgets.param_selector import ParameterSelector

logger = logging.getLogger(__name__)

_STATUS_STYLES: dict[str, str] = {
    "Зачтено": "bold green",
    "На проверке": "bold yellow",
    "Не зачтено": "bold red",
    "Новый": "dim",
}

_QUEUE_STATUS_COLORS: dict[str, str] = {
    "success": "bold green",
    "warning": "bold yellow",
    "danger": "bold red",
    "info": "bold cyan",
    "default": "dim",
    "primary": "bold blue",
}


def make_safe_id(name: str) -> str:
    """Convert arbitrary string to valid Textual widget ID fragment.

    Handles Cyrillic, CJK, accented Latin, and other non-ASCII characters.
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    if not safe:
        import hashlib

        safe = "h" + hashlib.md5(name.encode()).hexdigest()[:10]
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe


def _parse_mark(mark: str) -> float:
    """Parse grade/mark string to float for proper numeric sorting."""
    try:
        return float(mark.replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _parse_update_time(time_str: str) -> datetime:
    """Parse update_time string (DD-MM-YYYY or DD-MM-YYYY HH:MM) to datetime."""
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return datetime.min


def _styled_status(status: str) -> Text:
    style = _STATUS_STYLES.get(status, "")
    return Text(status or "-", style=style)


def _styled_deadline(deadline: datetime | None) -> Text:
    if deadline is None:
        return Text("-", style="dim")
    label = deadline.strftime("%d.%m.%Y")
    now = datetime.now()
    if deadline < now:
        return Text(label, style="dim strike")
    if deadline < now + timedelta(days=3):
        return Text(label, style="bold yellow")
    return Text(label)


def _format_score(task: Task) -> str:
    parts: list[str] = []
    if task.score is not None:
        parts.append(str(task.score))
    if task.max_score is not None:
        parts.append(f"/{task.max_score}")
    return " ".join(parts) if parts else "-"


class MainScreen(Screen[None]):
    """Main screen: left course pane + right TabbedContent (Tasks|Queue|Export)."""

    BINDINGS = [
        Binding("tab", "cycle_focus", "Next", show=False),
        Binding("shift+tab", "cycle_focus_back", "Prev", show=False),
        Binding("1", "tab_tasks", "Tasks", show=False),
        Binding("2", "tab_queue", "Queue", show=False),
        Binding("3", "tab_gradebook", "Gradebook", show=False),
        Binding("4", "tab_export", "Export", show=False),
        Binding("a", "add_course", "Add", show=True),
        Binding("x", "remove_course", "Remove", show=True),
        Binding("h", "focus_left", show=False),
        Binding("l", "focus_right", show=False),
        Binding("ctrl+up", "focus_filter", show=False),
        Binding("ctrl+down", "focus_table", show=False),
        Binding("ctrl+right", "filter_next", show=False),
        Binding("ctrl+left", "filter_prev", show=False),
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("r", "reset_filters", "Reset", show=True),
        Binding("u", "undo_filters", "Undo", show=True),
        Binding("ctrl+y", "copy_selection", "Copy", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True),
        Binding("escape", "dismiss_overlay", "Back", show=False),
        Binding("ctrl+l", "logout", "Logout", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._focus_left_pane = True
        self.all_tasks: list[Task] = []
        self.filtered_tasks: list[Task] = []
        self.is_teacher_view = False
        self._selected_course_id: int | None = None
        self.all_queue_entries: list[QueueEntry] = []
        self.filtered_queue_entries: list[QueueEntry] = []
        self._queue_loaded_for: int | None = None
        self._task_filter_undo: dict[str, Any] | None = None
        self._queue_filter_undo: dict[str, Any] | None = None
        self._queue_sort_column: int | None = None
        self._queue_sort_reverse = False
        self._gradebook_loaded_for: int | None = None
        self.all_gradebook_groups: list[GradebookGroup] = []
        self.filtered_gradebook_groups: list[GradebookGroup] = []
        self._gb_filter_undo: dict[str, Any] | None = None
        self._gb_sort_column: int | None = None
        self._gb_sort_reverse = False
        self._gb_all_tasks: list[str] = []
        self._help_visible = False
        self._export_preload_token = 0
        self._action_menu_open = False

    def compose(self) -> ComposeResult:
        client = getattr(self.app, "client", None)
        user = ""
        if client and hasattr(client, "username") and client.username:
            user = client.username

        yield Static(
            f"ANYTASK{('  ' + user) if user else ''}",
            id="header",
        )

        with Horizontal(id="body"):
            with Vertical(id="left-pane"):
                yield Static("Courses", id="left-title")
                yield OptionList(id="course-list")
                with Container(id="course-add-bar"):
                    yield Input(
                        placeholder="Course ID",
                        type="integer",
                        id="course-id-input",
                    )

            with (
                Vertical(id="right-pane"),
                TabbedContent("Tasks", "Queue", "Gradebook", "Export", id="main-tabs"),
            ):
                with TabPane("Tasks", id="tasks-tab"):
                    yield TaskFilterBar(classes="filter-bar", id="task-filter-bar")
                    with Vertical(id="task-area"):
                        yield DataTable(id="task-table")
                        with Container(id="detail-pane"):
                            yield VerticalScroll(
                                Label("[dim]Select a task[/dim]"),
                                id="detail-scroll",
                            )

                with TabPane("Queue", id="queue-tab"):
                    yield QueueFilterBar(classes="filter-bar", id="queue-filter-bar")
                    yield Label(
                        "Select a teacher course to view queue",
                        id="queue-info-label",
                    )
                    with Horizontal(id="queue-body"):
                        yield DataTable(id="queue-table")
                        with Container(id="queue-detail-pane"):
                            yield VerticalScroll(
                                Label("[dim]Select a queue entry[/dim]"),
                                id="queue-detail-scroll",
                            )

                with TabPane("Gradebook", id="gradebook-tab"):
                    yield GradebookFilterBar(classes="filter-bar", id="gb-filter-bar")
                    yield Label(
                        "Select a course to view gradebook",
                        id="gradebook-info-label",
                    )
                    yield DataTable(id="gradebook-table")

                with (
                    TabPane("Export", id="export-tab"),
                    Horizontal(id="export-body"),
                ):
                    with VerticalScroll(id="export-controls"):
                        with Container(classes="export-section"):
                            yield Label("Export Type", classes="export-section-title")
                            with RadioSet(id="export-type-set"):
                                yield RadioButton("Tasks", id="tasks-export-radio", value=True)
                                yield RadioButton("Queue", id="queue-export-radio")
                                yield RadioButton("Submissions", id="subs-export-radio")
                                yield RadioButton("Gradebook", id="gb-export-radio")
                        with Container(classes="export-section"):
                            yield Label("Format", classes="export-section-title")
                            with RadioSet(id="format-set"):
                                yield RadioButton("JSON", id="json-radio", value=True)
                                yield RadioButton("Markdown", id="md-radio")
                                yield RadioButton("CSV", id="csv-radio")
                                yield RadioButton("Files Only", id="files-radio")
                        with Container(
                            classes="export-section",
                            id="export-filter-section",
                        ):
                            yield Label(
                                "Row Filters",
                                classes="export-section-title",
                            )
                            yield Label(
                                "Filter exported rows (optional)",
                                classes="export-filter-desc",
                            )
                            yield Select[str](
                                [],
                                allow_blank=True,
                                value=Select.BLANK,
                                prompt="Task",
                                id="export-filter-task",
                            )
                            yield Select[str](
                                [],
                                allow_blank=True,
                                value=Select.BLANK,
                                prompt="Status",
                                id="export-filter-status",
                            )
                            yield Select[str](
                                [],
                                allow_blank=True,
                                value=Select.BLANK,
                                prompt="Reviewer",
                                id="export-filter-reviewer",
                            )
                        with Container(classes="export-section", id="export-params-section"):
                            yield ParameterSelector(id="param-selector", classes="export-section")
                        with Container(classes="export-section"):
                            yield Label("Submission Files", classes="export-section-title")
                            with RadioSet(id="export-include-files-set"):
                                yield RadioButton(
                                    "Skip files",
                                    id="export-subs-files-off-radio",
                                    value=True,
                                )
                                yield RadioButton(
                                    "Include files",
                                    id="export-subs-files-on-radio",
                                )
                        with Container(classes="export-section"):
                            yield Label("Output Directory", classes="export-section-title")
                            yield Input(value="./output", id="output-dir-input")
                        with Container(classes="export-section"):
                            yield Label("Custom File Name", classes="export-section-title")
                            yield Input(
                                placeholder="Optional (with or without extension)",
                                id="export-filename-input",
                            )
                        with Container(classes="export-section"):
                            yield Button("Export", variant="primary", id="export-btn")
                            yield Label("", id="export-status-label")
                    with Vertical(id="export-preview"):
                        yield Label("Preview", id="export-preview-title")
                        yield VerticalScroll(
                            Static(
                                "[dim]Select a course and format\nto see export preview[/dim]",
                                id="export-preview-content",
                            ),
                            id="export-preview-scroll",
                        )

        yield Static("", id="help-panel")
        yield Static("", id="status-line")
        yield Static("", id="key-bar")

    def on_mount(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._setup_task_table_columns()
        self._rebuild_task_table()

        qtable = self.query_one("#queue-table", DataTable)
        qtable.cursor_type = "row"
        qtable.zebra_stripes = True
        qtable.add_columns("#", "Student", "Task", "Status", "Reviewer", "Updated", "Grade")

        gtable = self.query_one("#gradebook-table", DataTable)
        gtable.cursor_type = "row"
        gtable.zebra_stripes = True
        self._rebuild_gradebook_table([])

        self.query_one("#course-list", OptionList).focus()

        saved_ids = self.app.load_course_ids()  # type: ignore[attr-defined]
        for cid in saved_ids:
            if cid not in self.app.courses:  # type: ignore[attr-defined]
                self._fetch_course(cid)
        self._update_key_bar()

    def _update_key_bar(self) -> None:
        """Update the key hints bar based on current context."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active

        common = (
            "[dim]ctrl+q[/dim] Quit  "
            "[dim]a[/dim] Add  "
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

        self.query_one("#key-bar", Static).update(hints)

    def _show_status(self, message: str, kind: str = "info", timeout: float = 4) -> None:
        """Show an inline message in the status line."""
        line = self.query_one("#status-line", Static)
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
            self.set_timer(timeout, self._clear_status)

    def _clear_status(self) -> None:
        self.query_one("#status-line", Static).update("")

    def action_toggle_help(self) -> None:
        panel = self.query_one("#help-panel", Static)
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
        self.query_one("#main-tabs", TabbedContent).active = "tasks-tab"
        self.query_one("#task-table", DataTable).focus()

    def action_tab_queue(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "queue-tab"
        self.query_one("#queue-table", DataTable).focus()

    def action_tab_export(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "export-tab"
        self.query_one("#export-type-set", RadioSet).focus()

    def action_tab_gradebook(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "gradebook-tab"
        self.query_one("#gradebook-table", DataTable).focus()

    @on(TabbedContent.TabActivated, "#main-tabs")
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._update_key_bar()
        if event.pane.id == "queue-tab":
            self._maybe_load_queue()
        elif event.pane.id == "gradebook-tab":
            self._maybe_load_gradebook()

    def _get_focus_order(self) -> list[str]:
        """Return IDs of focusable zones for current tab."""
        tabs = self.query_one("#main-tabs", TabbedContent)
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
            tabs = self.query_one("#main-tabs", TabbedContent)
            active = tabs.active
            if active == "tasks-tab":
                task_bar = self.query_one("#task-filter-bar", TaskFilterBar)
                if focused in task_bar.walk_children():
                    if task_bar.focus_next_filter():
                        return
                    self.query_one("#task-table", DataTable).focus()
                    return
            elif active == "queue-tab":
                queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)
                if focused in queue_bar.walk_children():
                    if queue_bar.focus_next_filter():
                        return
                    self.query_one("#queue-table", DataTable).focus()
                    return
            elif active == "gradebook-tab":
                gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)
                if focused in gb_bar.walk_children():
                    if gb_bar.focus_next_filter():
                        return
                    self.query_one("#gradebook-table", DataTable).focus()
                    return

        zones = self._get_focus_order()
        current = self._find_current_zone(zones)
        next_idx = (current + 1) % len(zones)
        self._focus_zone(zones[next_idx])

    def action_cycle_focus_back(self) -> None:
        focused = self.focused
        if focused is not None:
            tabs = self.query_one("#main-tabs", TabbedContent)
            active = tabs.active
            if active == "tasks-tab":
                task_bar = self.query_one("#task-filter-bar", TaskFilterBar)
                if focused in task_bar.walk_children():
                    if task_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()
                    return
            elif active == "queue-tab":
                queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)
                if focused in queue_bar.walk_children():
                    if queue_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()
                    return
            elif active == "gradebook-tab":
                gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)
                if focused in gb_bar.walk_children():
                    if gb_bar.focus_prev_filter():
                        return
                    self.query_one("#course-list", OptionList).focus()
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
                    widget = self.query_one(zone_id)
                except Exception:
                    continue
            else:
                widget = zone_id
            if widget is focused or focused in widget.walk_children():
                return i
        return -1

    def _focus_zone(self, zone_id: str) -> None:
        if zone_id == "#task-filter-bar":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_text()
            self._focus_left_pane = False
        elif zone_id == "#queue-filter-bar":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_text()
            self._focus_left_pane = False
        elif zone_id == "#course-list":
            self.query_one("#course-list", OptionList).focus()
            self._focus_left_pane = True
        elif zone_id == "#task-table":
            self.query_one("#task-table", DataTable).focus()
            self._focus_left_pane = False
        elif zone_id == "#queue-table":
            self.query_one("#queue-table", DataTable).focus()
            self._focus_left_pane = False
        elif zone_id == "#gradebook-table":
            self.query_one("#gradebook-table", DataTable).focus()
            self._focus_left_pane = False
        elif zone_id == "#gb-filter-bar":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_text()
            self._focus_left_pane = False
        elif zone_id == "#format-set":
            self.query_one("#format-set", RadioSet).focus()
            self._focus_left_pane = False
        elif zone_id == "#output-dir-input":
            self.query_one("#output-dir-input", Input).focus()
            self._focus_left_pane = False
        elif zone_id == "#export-filename-input":
            self.query_one("#export-filename-input", Input).focus()
            self._focus_left_pane = False
        elif zone_id == "#export-include-files-set":
            self.query_one("#export-include-files-set", RadioSet).focus()
            self._focus_left_pane = False

    def action_focus_left(self) -> None:
        self._focus_left_pane = True
        self.query_one("#course-list", OptionList).focus()

    def action_focus_right(self) -> None:
        self._focus_left_pane = False
        self.action_focus_table()

    def action_focus_filter(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "export-tab":
            self._export_focus_prev()
            return
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_text()
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_text()
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_text()

    def action_focus_table(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "export-tab":
            self._export_focus_next()
            return
        if active == "tasks-tab":
            self.query_one("#task-table", DataTable).focus()
        elif active == "queue-tab":
            self.query_one("#queue-table", DataTable).focus()
        elif active == "gradebook-tab":
            self.query_one("#gradebook-table", DataTable).focus()

    _EXPORT_FOCUS_ORDER = [
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

    def _export_focus_next(self) -> None:
        order = self._get_export_focus_order()
        if not order:
            return
        current = self._find_current_zone(order)
        if current < 0:
            order[0].focus()
            return
        next_idx = min(current + 1, len(order) - 1)
        order[next_idx].focus()

    def _export_focus_prev(self) -> None:
        order = self._get_export_focus_order()
        if not order:
            return
        current = self._find_current_zone(order)
        if current < 0:
            order[0].focus()
            return
        prev_idx = max(current - 1, 0)
        order[prev_idx].focus()

    def _get_export_focus_order(self) -> list[Any]:
        """Return export focus targets with disabled fields omitted."""
        widgets: list[Any] = []
        for wid in self._EXPORT_FOCUS_ORDER:
            try:
                widget = self.query_one(wid)
            except Exception:
                continue
            if getattr(widget, "disabled", False):
                continue
            widgets.append(widget)
        return widgets

    def action_filter_next(self) -> None:
        if isinstance(self.focused, Input):
            return
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_next_filter()
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_next_filter()
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_next_filter()

    def action_filter_prev(self) -> None:
        if isinstance(self.focused, Input):
            return
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "tasks-tab":
            self.query_one("#task-filter-bar", TaskFilterBar).focus_prev_filter()
        elif active == "queue-tab":
            self.query_one("#queue-filter-bar", QueueFilterBar).focus_prev_filter()
        elif active == "gradebook-tab":
            self.query_one("#gb-filter-bar", GradebookFilterBar).focus_prev_filter()

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
        payload = self._build_copy_payload()
        if payload is None:
            self._show_status("Nothing to copy", kind="warning", timeout=2)
            return

        label, text = payload
        success, method = copy_text_to_clipboard(text, app=self.app)
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

        active = self.query_one("#main-tabs", TabbedContent).active
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
        course = self.app.courses.get(self._selected_course_id)  # type: ignore[attr-defined]
        title = course.title if course is not None else f"Course {self._selected_course_id}"
        text = format_course_for_clipboard(self._selected_course_id, title)
        return ("course", text)

    def _copy_task_payload(self) -> tuple[str, str] | None:
        if not self.filtered_tasks:
            return None
        table = self.query_one("#task-table", DataTable)
        row_index = self._table_cursor_index(table, len(self.filtered_tasks))
        if row_index is None:
            return None
        task = self.filtered_tasks[row_index]
        text = format_task_for_clipboard(task, teacher_view=self.is_teacher_view)
        return ("task", text)

    def _copy_queue_payload(self) -> tuple[str, str] | None:
        if not self.filtered_queue_entries:
            return None
        table = self.query_one("#queue-table", DataTable)
        row_index = self._table_cursor_index(table, len(self.filtered_queue_entries))
        if row_index is None:
            return None
        entry = self.filtered_queue_entries[row_index]
        text = format_queue_entry_for_clipboard(entry)
        return ("queue entry", text)

    def _copy_gradebook_payload(self) -> tuple[str, str] | None:
        table = self.query_one("#gradebook-table", DataTable)
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

    def _copy_export_preview_payload(self) -> tuple[str, str] | None:
        preview = self.query_one("#export-preview-content", Static)
        raw = str(preview.content)
        text = rich_markup_to_plain(raw).strip()
        if not text:
            return None
        return ("export preview", text)

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
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "tasks-tab":
            task_bar = self.query_one("#task-filter-bar", TaskFilterBar)
            self._task_filter_undo = task_bar.save_state()
            task_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)
        elif active == "queue-tab":
            queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)
            self._queue_filter_undo = queue_bar.save_state()
            queue_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)
        elif active == "gradebook-tab":
            gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)
            self._gb_filter_undo = gb_bar.save_state()
            gb_bar.reset()
            self._show_status("Filters reset (u to undo)", kind="info", timeout=3)

    def action_undo_filters(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "tasks-tab" and self._task_filter_undo is not None:
            task_bar = self.query_one("#task-filter-bar", TaskFilterBar)
            task_bar.restore_state(self._task_filter_undo)
            self._task_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        elif active == "queue-tab" and self._queue_filter_undo is not None:
            queue_bar = self.query_one("#queue-filter-bar", QueueFilterBar)
            queue_bar.restore_state(self._queue_filter_undo)
            self._queue_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        elif active == "gradebook-tab" and self._gb_filter_undo is not None:
            gb_bar = self.query_one("#gb-filter-bar", GradebookFilterBar)
            gb_bar.restore_state(self._gb_filter_undo)
            self._gb_filter_undo = None
            self._show_status("Filters restored", kind="success", timeout=3)
        else:
            self._show_status("Nothing to undo", kind="warning", timeout=2)

    def action_add_course(self) -> None:
        bar = self.query_one("#course-add-bar")
        if "visible" in bar.classes:
            bar.remove_class("visible")
            self.query_one("#course-list", OptionList).focus()
        else:
            bar.add_class("visible")
            inp = self.query_one("#course-id-input", Input)
            inp.value = ""
            inp.focus()

    @on(Input.Submitted, "#course-id-input")
    def _submit_course_id(self) -> None:
        inp = self.query_one("#course-id-input", Input)
        try:
            course_id = int(inp.value.strip())
        except ValueError:
            self._show_status("Enter a valid course ID", kind="error")
            return

        if course_id in self.app.courses:  # type: ignore[attr-defined]
            self._show_status(f"Course {course_id} already loaded", kind="warning")
            return

        inp.value = ""
        self.query_one("#course-add-bar").remove_class("visible")
        self._show_status(f"Loading course {course_id}...")
        self._fetch_course(course_id)

    def action_remove_course(self) -> None:
        if self._selected_course_id is None:
            self._show_status("No course selected", kind="warning")
            return
        cid = self._selected_course_id
        self.app.remove_course_id(cid)  # type: ignore[attr-defined]

        option_list = self.query_one("#course-list", OptionList)
        option_list.clear_options()
        for course in self.app.courses.values():  # type: ignore[attr-defined]
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
        self.query_one("#queue-info-label", Label).update("Select a teacher course to view queue")
        self._show_status(f"Removed course {cid}", kind="success")

    def action_dismiss_overlay(self) -> None:
        add_bar = self.query_one("#course-add-bar")
        if "visible" in add_bar.classes:
            add_bar.remove_class("visible")
            self.query_one("#course-list", OptionList).focus()
            return
        help_panel = self.query_one("#help-panel", Static)
        if self._help_visible:
            self._help_visible = False
            help_panel.update("")
            help_panel.remove_class("visible")

    def action_logout(self) -> None:
        """Return to login screen."""
        if self.app.client is not None:  # type: ignore[attr-defined]
            self.app.client.close()  # type: ignore[attr-defined]
        self.app.client = None  # type: ignore[attr-defined]
        self.app.session_path = ""  # type: ignore[attr-defined]
        self.app.current_course = None  # type: ignore[attr-defined]
        self.app.courses = {}  # type: ignore[attr-defined]
        self.app.queue_cache = {}  # type: ignore[attr-defined]
        self.app.gradebook_cache = {}  # type: ignore[attr-defined]
        from anytask_scraper.tui.screens.login import LoginScreen

        self.app.switch_screen(LoginScreen())

    @on(OptionList.OptionSelected, "#course-list")
    def _course_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id is None:
            return
        course_id = int(option_id)
        course = self.app.courses.get(course_id)  # type: ignore[attr-defined]
        if course is None:
            return

        self._selected_course_id = course_id
        self.app.current_course = course  # type: ignore[attr-defined]
        self.all_tasks = list(course.tasks)
        self.is_teacher_view = any(t.section for t in self.all_tasks)

        self.filtered_tasks = list(self.all_tasks)
        self._update_task_filter_options()
        self._setup_task_table_columns()
        self._rebuild_task_table()
        self._clear_detail()

        self._queue_loaded_for = None
        self.all_queue_entries = []
        self.filtered_queue_entries = []
        self._rebuild_queue_table()
        self._clear_queue_detail()

        self._gradebook_loaded_for = None
        self.all_gradebook_groups = []
        self.filtered_gradebook_groups = []
        self._gb_sort_column = None
        self._gb_sort_reverse = False
        self._gb_all_tasks = []
        self.query_one("#gb-filter-bar", GradebookFilterBar).reset()
        self._rebuild_gradebook_table([])
        self.query_one("#gradebook-info-label", Label).update("Select a course to view gradebook")

        self._set_export_status("")

        try:
            queue_export_radio = self.query_one("#queue-export-radio", RadioButton)
            subs_export_radio = self.query_one("#subs-export-radio", RadioButton)
            queue_export_radio.disabled = not self.is_teacher_view
            subs_export_radio.disabled = not self.is_teacher_view
        except Exception:
            logger.debug("Failed to update export radio buttons", exc_info=True)

        if self.is_teacher_view:
            self.query_one("#queue-info-label", Label).update("Queue loads on demand")
        else:
            self.query_one("#queue-info-label", Label).update(
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

        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active == "queue-tab":
            self._maybe_load_queue()
        elif tabs.active == "gradebook-tab":
            self._maybe_load_gradebook()
        elif tabs.active == "export-tab":
            self._start_export_preload(current_export_type)

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
        self.query_one("#task-filter-bar", TaskFilterBar).update_options(statuses, sections)

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
            self._show_detail(self.filtered_tasks[idx])

    @on(QueueFilterBar.Changed)
    def _handle_queue_filter(self, event: QueueFilterBar.Changed) -> None:
        needle = event.text.lower()
        self.filtered_queue_entries = [
            e
            for e in self.all_queue_entries
            if (not needle or needle in e.student_name.lower() or needle in e.task_title.lower())
            and (not event.student or e.student_name == event.student)
            and (not event.task or e.task_title == event.task)
            and (not event.status or e.status_name == event.status)
            and (not event.reviewer or e.responsible_name == event.reviewer)
        ]
        self._rebuild_queue_table()

    def _update_queue_filter_options(self) -> None:
        students = sorted({e.student_name for e in self.all_queue_entries if e.student_name})
        tasks = sorted({e.task_title for e in self.all_queue_entries if e.task_title})
        statuses = sorted({e.status_name for e in self.all_queue_entries if e.status_name})
        reviewers = sorted(
            {e.responsible_name for e in self.all_queue_entries if e.responsible_name}
        )
        self.query_one("#queue-filter-bar", QueueFilterBar).update_options(
            students, tasks, statuses, reviewers
        )

    @on(DataTable.RowHighlighted, "#queue-table")
    def _queue_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is None:
            return
        issue_url = event.row_key.value
        entry = next(
            (e for e in self.all_queue_entries if e.issue_url == issue_url),
            None,
        )
        if entry and entry.has_issue_access and entry.issue_url:
            self._load_queue_preview(entry)
        elif entry:
            self._show_queue_preview_info(entry)

    @on(DataTable.RowSelected, "#queue-table")
    def _queue_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        issue_url = event.row_key.value
        entry = next(
            (e for e in self.all_queue_entries if e.issue_url == issue_url),
            None,
        )
        if entry and entry.has_issue_access and entry.issue_url:
            self._fetch_and_show_submission(entry)

    def _show_queue_preview_info(self, entry: QueueEntry) -> None:
        """Show basic queue entry info when no issue access."""
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)
        scroll.remove_children()
        scroll.mount(
            Label(
                f"[bold]{entry.task_title}[/bold]",
                classes="detail-heading",
            )
        )
        scroll.mount(Label(f"Student: {entry.student_name}", classes="detail-text"))
        scroll.mount(Label(f"Status: {entry.status_name}", classes="detail-text"))
        scroll.mount(
            Label(
                f"Reviewer: {entry.responsible_name or '-'}",
                classes="detail-text",
            )
        )
        scroll.mount(Label(f"Updated: {entry.update_time}", classes="detail-text"))
        scroll.mount(Label(f"Grade: {entry.mark or '-'}", classes="detail-text"))

    @work(thread=True)
    def _load_queue_preview(self, entry: QueueEntry) -> None:
        """Auto-load submission preview for queue detail pane."""
        try:
            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(  # type: ignore[attr-defined]
                    self._selected_course_id
                )
                if cache and entry.issue_url in cache.submissions:
                    sub = cache.submissions[entry.issue_url]
                    self.app.call_from_thread(self._render_queue_preview, sub)
                    return

            client = self.app.client  # type: ignore[attr-defined]
            if not client:
                return

            self.app.call_from_thread(self._show_queue_preview_loading, entry)

            html = client.fetch_submission_page(entry.issue_url)
            issue_id = extract_issue_id_from_breadcrumb(html)
            if issue_id == 0:
                self.app.call_from_thread(self._show_queue_preview_info, entry)
                return

            sub = parse_submission_page(html, issue_id)

            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(  # type: ignore[attr-defined]
                    self._selected_course_id
                )
                if cache:
                    cache.submissions[entry.issue_url] = sub

            self.app.call_from_thread(self._render_queue_preview, sub)
        except Exception:
            logger.debug("Failed to load queue preview", exc_info=True)
            self.app.call_from_thread(self._show_queue_preview_info, entry)

    def _show_queue_preview_loading(self, entry: QueueEntry) -> None:
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)
        scroll.remove_children()
        scroll.mount(
            Label(
                f"[bold]{entry.task_title}[/bold]",
                classes="detail-heading",
            )
        )
        scroll.mount(Label(f"Student: {entry.student_name}", classes="detail-text"))
        scroll.mount(Label("[dim]Loading...[/dim]", classes="detail-text"))

    def _render_queue_preview(self, sub: Submission) -> None:
        """Render submission preview in the queue detail pane."""
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)
        scroll.remove_children()

        scroll.mount(Label(f"[bold]{sub.task_title}[/bold]", classes="detail-heading"))
        scroll.mount(Label(f"Student: {sub.student_name}", classes="detail-text"))
        scroll.mount(
            Label(
                f"Reviewer: {sub.reviewer_name or '-'}",
                classes="detail-text",
            )
        )
        scroll.mount(
            Label(
                f"Status: {sub.status}  |  Grade: {sub.grade}/{sub.max_score}",
                classes="detail-text",
            )
        )
        if sub.deadline:
            scroll.mount(Label(f"Deadline: {sub.deadline}", classes="detail-text"))

        if sub.comments:
            scroll.mount(
                Label(
                    f"\n[bold]Comments ({len(sub.comments)})[/bold]",
                    classes="detail-heading",
                )
            )
            for comment in sub.comments:
                ts = comment.timestamp.strftime("%d.%m.%Y %H:%M") if comment.timestamp else "-"
                after = " [bold red](LATE)[/bold red]" if comment.is_after_deadline else ""
                scroll.mount(
                    Label(
                        f"[bold]{comment.author_name}[/bold] [dim]{ts}[/dim]{after}",
                        classes="detail-text",
                    )
                )
                if comment.content_html:
                    text = strip_html(comment.content_html)
                    if text:
                        scroll.mount(Label(text, classes="detail-text"))
                if comment.files:
                    fnames = ", ".join(f.filename for f in comment.files)
                    scroll.mount(
                        Label(
                            f"[dim]Files: {fnames}[/dim]",
                            classes="detail-text",
                        )
                    )

        scroll.mount(
            Label(
                "\n[dim]Press Enter for full view[/dim]",
                classes="detail-text",
            )
        )

    def _clear_queue_detail(self) -> None:
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)
        scroll.remove_children()
        scroll.mount(Label("[dim]Select a queue entry[/dim]"))

    @on(DataTable.HeaderSelected, "#queue-table")
    def _queue_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_idx = event.column_index
        if self._queue_sort_column == col_idx:
            self._queue_sort_reverse = not self._queue_sort_reverse
        else:
            self._queue_sort_column = col_idx
            self._queue_sort_reverse = False
        self._sort_and_rebuild_queue()

    def _sort_and_rebuild_queue(self) -> None:
        col = self._queue_sort_column
        if col is None:
            return
        key_map: dict[int, Any] = {
            0: lambda e: 0,
            1: lambda e: e.student_name.lower(),
            2: lambda e: e.task_title.lower(),
            3: lambda e: e.status_name.lower(),
            4: lambda e: e.responsible_name.lower(),
            5: lambda e: _parse_update_time(e.update_time),
            6: lambda e: _parse_mark(e.mark),
        }
        key_fn = key_map.get(col)
        if key_fn:
            self.filtered_queue_entries.sort(key=key_fn, reverse=self._queue_sort_reverse)
            self._rebuild_queue_table()

    @on(RadioSet.Changed, "#export-type-set")
    def _export_type_changed(self, event: RadioSet.Changed) -> None:
        export_type = self._get_current_export_type()
        if export_type == "tasks-export-radio" or self._has_loaded_export_data(export_type):
            self._update_export_filters()
            self._update_params()
            self._refresh_export_preview()
        else:
            self._set_export_filters_loading_state()
            self._refresh_export_preview()
            self._start_export_preload(export_type)

    @on(RadioSet.Changed, "#format-set")
    def _format_changed(self, event: RadioSet.Changed) -> None:
        self._refresh_export_preview()

    @on(Select.Changed, "#export-filter-task")
    @on(Select.Changed, "#export-filter-status")
    @on(Select.Changed, "#export-filter-reviewer")
    def _export_filter_changed(self, event: Select.Changed) -> None:
        """Handle row filter changes - refresh preview."""
        event.stop()
        self._refresh_export_preview()

    def _update_export_filters(self) -> None:
        """Update row filter dropdowns based on current export type."""
        try:
            task_select = self.query_one("#export-filter-task", Select)
            status_select = self.query_one("#export-filter-status", Select)
            reviewer_select = self.query_one("#export-filter-reviewer", Select)
        except Exception:
            return

        export_type = self._get_current_export_type()
        prev_task = task_select.value
        prev_status = status_select.value
        prev_reviewer = reviewer_select.value

        if export_type in ("queue-export-radio", "subs-export-radio"):
            task_select.prompt = "Task"
            status_select.prompt = "Status"
            reviewer_select.prompt = "Reviewer"
        elif export_type == "tasks-export-radio":
            task_select.prompt = "Title"
            status_select.prompt = "Section" if self.is_teacher_view else "Status"
            reviewer_select.prompt = "N/A"
        elif export_type == "gb-export-radio":
            task_select.prompt = "Group"
            status_select.prompt = "N/A"
            reviewer_select.prompt = "Teacher"
        else:
            task_select.prompt = "Task"
            status_select.prompt = "Status"
            reviewer_select.prompt = "Reviewer"

        try:
            files_radio = self.query_one("#files-radio", RadioButton)
            files_radio.disabled = export_type != "subs-export-radio"
        except Exception:
            logger.debug("Failed to update files radio", exc_info=True)
        try:
            include_files_set = self.query_one("#export-include-files-set", RadioSet)
            include_files_set.disabled = export_type != "subs-export-radio"
        except Exception:
            logger.debug("Failed to update include files selector", exc_info=True)

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
            self._set_export_filter_options(reviewer_select, [], Select.BLANK, enabled=False)
        elif export_type in ("queue-export-radio", "subs-export-radio"):
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
            self._set_export_filter_options(status_select, [], Select.BLANK, enabled=False)
            self._set_export_filter_options(
                reviewer_select,
                [(t, t) for t in teachers],
                prev_reviewer,
                enabled=bool(teachers),
            )
        else:
            self._set_export_filter_options(task_select, [], Select.BLANK, enabled=False)
            self._set_export_filter_options(status_select, [], Select.BLANK, enabled=False)
            self._set_export_filter_options(reviewer_select, [], Select.BLANK, enabled=False)

    def _set_export_filter_options(
        self,
        select: Select[str],
        options: list[tuple[str, str]],
        previous_value: object,
        *,
        enabled: bool,
    ) -> None:
        """Set options and keep previous selection if still available."""
        select.set_options(options)
        if not enabled:
            select.disabled = True
            select.value = Select.BLANK
            focused = self.focused
            if focused is not None and (focused is select or focused in select.walk_children()):
                with suppress(Exception):
                    self.query_one("#export-type-set", RadioSet).focus()
            return
        select.disabled = False
        values = {value for _, value in options}
        if previous_value is not Select.BLANK and str(previous_value) in values:
            select.value = str(previous_value)
        else:
            select.value = Select.BLANK

    def _set_export_filters_loading_state(self) -> None:
        """Disable row filters while related data is preloading."""
        for wid in (
            "#export-filter-task",
            "#export-filter-status",
            "#export-filter-reviewer",
        ):
            try:
                sel = self.query_one(wid, Select)
                sel.disabled = True
            except Exception:
                continue

    def _has_loaded_export_data(self, export_type: str) -> bool:
        """Return True if data for export filters/preview is already available."""
        if export_type == "tasks-export-radio":
            return True
        if export_type in ("queue-export-radio", "subs-export-radio"):
            return bool(self.all_queue_entries)
        if export_type == "gb-export-radio":
            return bool(self.all_gradebook_groups)
        return True

    def _get_current_export_filters(self) -> dict[str, str]:
        """Get current row filter values."""
        filters: dict[str, str] = {}
        try:
            export_type = self._get_current_export_type()
            task_val = self.query_one("#export-filter-task", Select).value
            status_val = self.query_one("#export-filter-status", Select).value
            reviewer_val = self.query_one("#export-filter-reviewer", Select).value
            if export_type == "tasks-export-radio":
                if task_val is not Select.BLANK:
                    filters["task"] = str(task_val)
                if status_val is not Select.BLANK:
                    filters["section" if self.is_teacher_view else "status"] = str(status_val)
            elif export_type in ("queue-export-radio", "subs-export-radio"):
                if task_val is not Select.BLANK:
                    filters["task"] = str(task_val)
                if status_val is not Select.BLANK:
                    filters["status"] = str(status_val)
                if reviewer_val is not Select.BLANK:
                    filters["reviewer"] = str(reviewer_val)
            elif export_type == "gb-export-radio":
                if task_val is not Select.BLANK:
                    filters["group"] = str(task_val)
                if reviewer_val is not Select.BLANK:
                    filters["teacher"] = str(reviewer_val)
        except Exception:
            logger.debug("Failed to collect export filters", exc_info=True)
        return filters

    def _update_params(self) -> None:
        """Rebuild parameter list based on current export type and course data."""
        try:
            selector = self.query_one("#param-selector", ParameterSelector)
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
        else:
            params = []

        selector.set_params(params)

    @on(ParameterSelector.Changed)
    def _params_changed(self, event: ParameterSelector.Changed) -> None:
        """Handle parameter selection changes - refresh preview."""
        self._refresh_export_preview()

    @on(Input.Changed, "#export-filename-input")
    def _filename_changed(self, event: Input.Changed) -> None:
        """Refresh preview when custom filename changes."""
        event.stop()
        self._refresh_export_preview()

    @on(RadioSet.Changed, "#export-include-files-set")
    def _include_files_changed(self, event: RadioSet.Changed) -> None:
        """Refresh preview when submissions include-files option changes."""
        event.stop()
        self._refresh_export_preview()

    def _get_included_columns(self) -> list[str]:
        """Get list of selected parameter names."""
        try:
            selector = self.query_one("#param-selector", ParameterSelector)
            return selector.get_included()
        except Exception:
            return []

    def _get_custom_export_filename(self) -> str | None:
        """Get optional custom filename from export controls."""
        try:
            value = self.query_one("#export-filename-input", Input).value.strip()
        except Exception:
            return None
        return value or None

    def _resolve_export_filename(self, default_filename: str) -> str:
        """Resolve preview filename, appending default suffix when needed."""
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
        """Return True when submissions export should download files."""
        try:
            files_set = self.query_one("#export-include-files-set", RadioSet)
            btn = files_set.pressed_button
            return bool(btn and btn.id == "export-subs-files-on-radio")
        except Exception:
            return False

    def _refresh_export_preview(self) -> None:
        """Regenerate the export preview pane."""
        try:
            export_type = self._get_current_export_type()
            fmt = self._get_current_export_format()
            preview_text = self._generate_preview(export_type, fmt)
            self.query_one("#export-preview-content", Static).update(preview_text)
        except Exception:
            logger.debug("Failed to update export preview", exc_info=True)

    def _start_export_preload(self, export_type: str) -> None:
        """Preload export data on type selection so preview/export are ready."""
        course_id = self._selected_course_id
        if course_id is None:
            return
        if export_type == "queue-export-radio" and not self.is_teacher_view:
            return
        if export_type == "subs-export-radio" and not self.is_teacher_view:
            return
        self._export_preload_token += 1
        token = self._export_preload_token
        if export_type == "queue-export-radio":
            self._set_export_status("Loading queue data...", "info")
            self.query_one("#export-preview-content", Static).update(
                "[dim]Loading queue data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)
        elif export_type == "subs-export-radio":
            self._set_export_status("Loading submissions source data...", "info")
            self.query_one("#export-preview-content", Static).update(
                "[dim]Loading submissions source data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)
        elif export_type == "gb-export-radio":
            self._set_export_status("Loading gradebook data...", "info")
            self.query_one("#export-preview-content", Static).update(
                "[dim]Loading gradebook data...[/dim]"
            )
            self._preload_export_data(export_type, course_id, token)

    @work(thread=True)
    def _preload_export_data(self, export_type: str, course_id: int, token: int) -> None:
        """Load required data for export type and refresh preview on completion."""
        try:
            loaded_message = "Preload complete"
            if export_type in ("queue-export-radio", "subs-export-radio"):
                queue = self._load_queue_for_export(course_id)
                loaded_message = f"Queue loaded: {len(queue.entries)} entries"
            elif export_type == "gb-export-radio":
                gradebook = self._load_gradebook_for_export(course_id)
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
        """Apply preload result only if still relevant for current export selection."""
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
            btn = self.query_one("#export-type-set", RadioSet).pressed_button
            return (btn.id or "tasks-export-radio") if btn else "tasks-export-radio"
        except Exception:
            return "tasks-export-radio"

    def _get_current_export_format(self) -> str:
        try:
            btn = self.query_one("#format-set", RadioSet).pressed_button
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
        """Generate a text preview of the export output."""
        if self._selected_course_id is None:
            return "[dim]Select a course first[/dim]"

        course_id = self._selected_course_id
        max_items = 2
        included = self._get_included_columns()
        filters = self._get_current_export_filters()

        if export_type == "tasks-export-radio":
            tasks = list(self.all_tasks)
            if filters.get("task"):
                tasks = [t for t in tasks if t.title == filters["task"]]
            if filters.get("section"):
                tasks = [t for t in tasks if t.section == filters["section"]]
            if filters.get("status"):
                tasks = [t for t in tasks if t.status == filters["status"]]
            if not tasks:
                return "[dim]No tasks available[/dim]"
            return self._preview_tasks(
                tasks[:max_items], format_type, course_id, len(tasks), included
            )

        elif export_type == "queue-export-radio":
            q_entries = list(self.all_queue_entries)
            if not q_entries:
                cache = self.app.queue_cache  # type: ignore[attr-defined]
                q_entries = list(cache.get(course_id, ReviewQueue(course_id=course_id)).entries)
            if filters.get("task"):
                q_entries = [e for e in q_entries if e.task_title == filters["task"]]
            if filters.get("status"):
                q_entries = [e for e in q_entries if e.status_name == filters["status"]]
            if filters.get("reviewer"):
                q_entries = [e for e in q_entries if e.responsible_name == filters["reviewer"]]
            if not q_entries:
                return "[dim]Queue data will be loaded during export[/dim]"
            return self._preview_queue(
                q_entries[:max_items], format_type, course_id, len(q_entries), included
            )

        elif export_type == "gb-export-radio":
            groups = list(self.all_gradebook_groups)
            if not groups:
                cache = self.app.gradebook_cache  # type: ignore[attr-defined]
                cached = cache.get(course_id)
                if cached is not None:
                    groups = list(cached.groups)
            if filters.get("group"):
                groups = [g for g in groups if g.group_name == filters["group"]]
            if filters.get("teacher"):
                groups = [g for g in groups if g.teacher_name == filters["teacher"]]
            total = sum(len(g.entries) for g in groups)
            if not total:
                return "[dim]Gradebook data will be loaded during export[/dim]"
            return self._preview_gradebook(groups, format_type, course_id, total, included)

        elif export_type == "subs-export-radio":
            if format_type == "files":
                if not self._get_include_submission_files():
                    return (
                        "[dim]Files Only mode requires enabling\n"
                        "'Include files (Submissions)'[/dim]"
                    )
                return "[dim]Files Only mode:\nDownloads submission files\nto student folders[/dim]"
            sub_entries = list(self.all_queue_entries)
            if not sub_entries:
                cache = self.app.queue_cache  # type: ignore[attr-defined]
                sub_entries = list(cache.get(course_id, ReviewQueue(course_id=course_id)).entries)
            if filters.get("task"):
                sub_entries = [e for e in sub_entries if e.task_title == filters["task"]]
            if filters.get("status"):
                sub_entries = [e for e in sub_entries if e.status_name == filters["status"]]
            if filters.get("reviewer"):
                sub_entries = [e for e in sub_entries if e.responsible_name == filters["reviewer"]]
            if not sub_entries:
                return "[dim]Queue data will be loaded during export[/dim]"
            return self._preview_submissions(
                sub_entries[:max_items], format_type, course_id, len(sub_entries), included
            )

        return "[dim]Select export type[/dim]"

    def _preview_tasks(
        self, tasks: list[Task], fmt: str, course_id: int, total: int, included: list[str]
    ) -> str:
        import json as json_mod

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
            lines = [",".join(header_parts)]
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
                lines.append(",".join(row_parts))
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
            lines = [",".join(header_parts)]
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
                lines.append(",".join(row_parts))
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
                lines.append(f"- {' — '.join(parts)}")
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
            lines = [",".join(header_parts)]
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
                lines.append(",".join(row_parts))
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
                lines.append(f"- {' — '.join(parts)}")
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
            lines = [",".join(header_parts)]
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
                    lines.append(",".join(row_parts))
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

        format_set = self.query_one("#format-set", RadioSet)
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

        type_set = self.query_one("#export-type-set", RadioSet)
        type_btn = type_set.pressed_button
        export_type = type_btn.id if type_btn else "tasks-export-radio"

        output_dir = self.query_one("#output-dir-input", Input).value.strip() or "./output"
        output_path = Path(output_dir).expanduser().resolve()

        filters = self._get_current_export_filters()
        columns = self._get_included_columns()
        filename = self._get_custom_export_filename()
        include_files = self._get_include_submission_files()
        if export_type == "subs-export-radio" and fmt == "files" and not include_files:
            self._set_export_status(
                "Enable 'Include files (Submissions)' for Files Only export",
                "error",
            )
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
        )

    def _set_export_status(self, message: str, kind: str = "info") -> None:
        label = self.query_one("#export-status-label", Label)
        label.update(message)
        label.remove_class("error", "success", "info")
        label.add_class(kind)

    @work(thread=True)
    def _do_export(
        self,
        fmt: str,
        output_path: Path,
        export_type: str = "tasks-export-radio",
        filters: dict[str, str] | None = None,
        columns: list[str] | None = None,
        filename: str | None = None,
        include_files: bool = False,
    ) -> None:
        try:
            output_path.mkdir(parents=True, exist_ok=True)
            course_id = self._selected_course_id or 0

            if export_type == "tasks-export-radio":
                course = self.app.current_course  # type: ignore[attr-defined]
                if not course:
                    self.app.call_from_thread(
                        self._set_export_status, "No course selected", "error"
                    )
                    return

                tasks = list(course.tasks)

                if filters and filters.get("task"):
                    tasks = [t for t in tasks if t.title == filters["task"]]
                if filters and filters.get("section"):
                    tasks = [t for t in tasks if t.section == filters["section"]]
                if filters and filters.get("status"):
                    tasks = [t for t in tasks if t.status == filters["status"]]

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
                if filters:
                    if filters.get("task"):
                        entries = [e for e in entries if e.task_title == filters["task"]]
                    if filters.get("status"):
                        entries = [e for e in entries if e.status_name == filters["status"]]
                    if filters.get("reviewer"):
                        entries = [e for e in entries if e.responsible_name == filters["reviewer"]]

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

                if filters:
                    if filters.get("task"):
                        entries = [e for e in entries if e.task_title == filters["task"]]
                    if filters.get("status"):
                        entries = [e for e in entries if e.status_name == filters["status"]]
                    if filters.get("reviewer"):
                        entries = [e for e in entries if e.responsible_name == filters["reviewer"]]

                accessible_entries = [e for e in entries if e.has_issue_access and e.issue_url]
                if not accessible_entries:
                    self.app.call_from_thread(
                        self._set_export_status,
                        "No accessible submissions found.",
                        "error",
                    )
                    return

                client = self.app.client  # type: ignore[attr-defined]
                if not client:
                    self.app.call_from_thread(
                        self._set_export_status,
                        "Not logged in",
                        "error",
                    )
                    return

                subs: list[Submission] = []
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
                        sub = parse_submission_page(sub_html, issue_id)
                        subs.append(sub)
                    except Exception:
                        logger.debug("Failed to fetch submission", exc_info=True)
                        continue

                if not subs:
                    self.app.call_from_thread(
                        self._set_export_status,
                        "No submissions could be fetched.",
                        "error",
                    )
                    return

                total_files = 0
                if include_files:
                    self.app.call_from_thread(
                        self._set_export_status,
                        f"Downloading files for {len(subs)} submissions...",
                        "info",
                    )
                    for sub in subs:
                        downloaded = download_submission_files(client, sub, output_path)
                        total_files += len(downloaded)

                if fmt == "files":
                    self.app.call_from_thread(
                        self._set_export_status,
                        f"Downloaded {total_files} files to {output_path}",
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
                self.app.call_from_thread(
                    self._set_export_status,
                    status,
                    "success",
                )
                return
            elif export_type == "gb-export-radio":
                gradebook = self._load_gradebook_for_export(course_id)

                groups = list(gradebook.groups)
                if filters:
                    if filters.get("group"):
                        groups = [g for g in groups if g.group_name == filters["group"]]
                    if filters.get("teacher"):
                        groups = [g for g in groups if g.teacher_name == filters["teacher"]]

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
        """Load queue data for export without requiring Queue tab activation."""
        cache = self.app.queue_cache  # type: ignore[attr-defined]
        cached = cast(ReviewQueue | None, cache.get(course_id))
        if cached is not None:
            self.all_queue_entries = list(cached.entries)
            self.filtered_queue_entries = list(cached.entries)
            self._queue_loaded_for = course_id
            self.app.call_from_thread(self._update_queue_info, f"{len(cached.entries)} entries")
            return cached

        client = self.app.client  # type: ignore[attr-defined]
        if not client:
            raise RuntimeError("Not logged in")

        queue_html = client.fetch_queue_page(course_id)
        csrf = extract_csrf_from_queue_page(queue_html)
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
        self.app.call_from_thread(self._update_queue_filter_options)
        self.app.call_from_thread(self._rebuild_queue_table)
        self.app.call_from_thread(self._update_queue_info, f"{len(entries)} entries")
        return queue

    def _load_gradebook_for_export(self, course_id: int) -> Gradebook:
        """Load gradebook data for export without requiring Gradebook tab activation."""
        cache = self.app.gradebook_cache  # type: ignore[attr-defined]
        cached = cast(Gradebook | None, cache.get(course_id))
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

        client = self.app.client  # type: ignore[attr-defined]
        if not client:
            raise RuntimeError("Not logged in")

        html = client.fetch_gradebook_page(course_id)
        gradebook = parse_gradebook_page(html, course_id)
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

    @work(thread=True)
    def _fetch_course(self, course_id: int) -> None:
        try:
            client = self.app.client  # type: ignore[attr-defined]
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            html = client.fetch_course_page(course_id)
            course = parse_course_page(html, course_id)

            self.app.courses[course_id] = course  # type: ignore[attr-defined]
            self.app.call_from_thread(
                self.app.save_course_ids  # type: ignore[attr-defined]
            )
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
                self.app.remove_course_id,  # type: ignore[attr-defined]
                course_id,
            )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Failed to load {course_id}: {e}",
                kind="error",
            )
            self.app.call_from_thread(
                self.app.remove_course_id,  # type: ignore[attr-defined]
                course_id,
            )

    def _add_course_option(self, course: Course) -> None:
        option_list = self.query_one("#course-list", OptionList)
        title = course.title or f"Course {course.course_id}"
        option_list.add_option(Option(title, id=str(course.course_id)))

    def _maybe_load_queue(self) -> None:
        self._enable_queue_tab()
        if self._selected_course_id is None:
            return
        if not self.is_teacher_view:
            self.query_one("#queue-info-label", Label).update(
                "Queue available for teacher courses only"
            )
            return
        if self._queue_loaded_for == self._selected_course_id:
            return

        cache = self.app.queue_cache  # type: ignore[attr-defined]
        if self._selected_course_id in cache:
            queue = cache[self._selected_course_id]
            self.all_queue_entries = list(queue.entries)
            self.filtered_queue_entries = list(queue.entries)
            self._queue_loaded_for = self._selected_course_id
            self._update_queue_filter_options()
            self._rebuild_queue_table()
            self.query_one("#queue-info-label", Label).update(f"{len(queue.entries)} entries")
            return

        self.query_one("#queue-info-label", Label).update("Loading queue...")
        self._fetch_queue(self._selected_course_id)

    @work(thread=True)
    def _fetch_queue(self, course_id: int) -> None:
        try:
            client = self.app.client  # type: ignore[attr-defined]
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            queue_html = client.fetch_queue_page(course_id)
            csrf = extract_csrf_from_queue_page(queue_html)

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
            self.app.queue_cache[course_id] = queue  # type: ignore[attr-defined]

            self.all_queue_entries = entries
            self.filtered_queue_entries = list(entries)
            self._queue_loaded_for = course_id

            self.app.call_from_thread(self._update_queue_filter_options)
            self.app.call_from_thread(self._rebuild_queue_table)
            self.app.call_from_thread(self._update_queue_info, f"{len(entries)} entries")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                self.app.call_from_thread(self._disable_queue_tab)
                self.app.call_from_thread(self._update_queue_info, "No permission to view queue")
            else:
                self.app.call_from_thread(
                    self._show_status,
                    f"Queue error: HTTP {e.response.status_code}",
                    kind="error",
                )
                self.app.call_from_thread(
                    self._update_queue_info, f"Error: HTTP {e.response.status_code}"
                )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Queue error: {e}",
                kind="error",
            )
            self.app.call_from_thread(self._update_queue_info, f"Error: {e}")

    def _update_queue_info(self, text: str) -> None:
        self.query_one("#queue-info-label", Label).update(text)

    def _disable_queue_tab(self) -> None:
        self.query_one("#queue-filter-bar", QueueFilterBar).disabled = True
        self.query_one("#queue-table", DataTable).disabled = True
        self.query_one("#queue-info-label", Label).update("No permission to view queue")

    def _enable_queue_tab(self) -> None:
        self.query_one("#queue-filter-bar", QueueFilterBar).disabled = False
        self.query_one("#queue-table", DataTable).disabled = False

    @work(thread=True)
    def _fetch_and_show_submission(self, entry: QueueEntry) -> None:
        try:
            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(  # type: ignore[attr-defined]
                    self._selected_course_id
                )
                if cache and entry.issue_url in cache.submissions:
                    sub = cache.submissions[entry.issue_url]
                    self.app.call_from_thread(self._push_submission_screen, sub)
                    return

            client = self.app.client  # type: ignore[attr-defined]
            if not client:
                return

            html = client.fetch_submission_page(entry.issue_url)
            issue_id = extract_issue_id_from_breadcrumb(html)
            if issue_id == 0:
                self.app.call_from_thread(
                    self._show_status,
                    "Could not find issue ID",
                    kind="warning",
                )
                return

            sub = parse_submission_page(html, issue_id)

            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(  # type: ignore[attr-defined]
                    self._selected_course_id
                )
                if cache:
                    cache.submissions[entry.issue_url] = sub

            self.app.call_from_thread(self._push_submission_screen, sub)
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Submission error: {e}",
                kind="error",
            )

    def _push_submission_screen(self, sub: Submission) -> None:
        from anytask_scraper.tui.screens.submission import (
            SubmissionScreen,
        )

        self.app.push_screen(SubmissionScreen(sub))

    def _setup_task_table_columns(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.clear(columns=True)
        if self.is_teacher_view:
            table.add_columns("#", "Title", "Section", "Max", "Deadline")
        else:
            table.add_columns("#", "Title", "Score", "Status", "Deadline")

    def _rebuild_task_table(self) -> None:
        table = self.query_one("#task-table", DataTable)
        if not table.columns:
            self._setup_task_table_columns()
        table.clear()

        for idx, task in enumerate(self.filtered_tasks, 1):
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

    def _rebuild_queue_table(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        table.clear(columns=True)

        base_columns = (
            "#",
            "Student",
            "Task",
            "Status",
            "Reviewer",
            "Updated",
            "Grade",
        )
        labels = []
        for i, col in enumerate(base_columns):
            if self._queue_sort_column == i:
                indicator = "▼" if self._queue_sort_reverse else "▲"
                labels.append(f"{col} {indicator}")
            else:
                labels.append(col)
        table.add_columns(*labels)

        for idx, entry in enumerate(self.filtered_queue_entries, 1):
            style = _QUEUE_STATUS_COLORS.get(entry.status_color, "")
            table.add_row(
                str(idx),
                entry.student_name,
                entry.task_title,
                Text(entry.status_name, style=style),
                entry.responsible_name,
                entry.update_time,
                entry.mark,
                key=entry.issue_url or str(idx),
            )

    def _clear_detail(self) -> None:
        scroll = self.query_one("#detail-scroll", VerticalScroll)
        scroll.remove_children()
        scroll.mount(Label("[dim]Select a task[/dim]"))

    def _show_detail(self, task: Task) -> None:
        scroll = self.query_one("#detail-scroll", VerticalScroll)
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

    _GRADEBOOK_COLOR_MAP: dict[str, str] = {
        "#65E31B": "bold green",
        "#F0AD4E": "bold yellow",
        "#818A91": "dim",
        "#D9534F": "bold red",
        "#5BC0DE": "bold cyan",
    }

    def _maybe_load_gradebook(self) -> None:
        if self._selected_course_id is None:
            return
        if self._gradebook_loaded_for == self._selected_course_id:
            return

        cache = self.app.gradebook_cache  # type: ignore[attr-defined]
        if self._selected_course_id in cache:
            gradebook = cache[self._selected_course_id]
            self._gradebook_loaded_for = self._selected_course_id
            self.all_gradebook_groups = list(gradebook.groups)
            self.filtered_gradebook_groups = list(gradebook.groups)
            self._update_gb_filter_options()
            self._rebuild_gradebook_table(gradebook.groups)
            total = sum(len(g.entries) for g in gradebook.groups)
            self.query_one("#gradebook-info-label", Label).update(
                f"{len(gradebook.groups)} group(s), {total} students"
            )
            return

        self.query_one("#gradebook-info-label", Label).update("Loading gradebook...")
        self._fetch_gradebook(self._selected_course_id)

    @work(thread=True)
    def _fetch_gradebook(self, course_id: int) -> None:
        try:
            client = self.app.client  # type: ignore[attr-defined]
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            html = client.fetch_gradebook_page(course_id)
            gradebook = parse_gradebook_page(html, course_id)

            self.app.gradebook_cache[course_id] = gradebook  # type: ignore[attr-defined]
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
        self.query_one("#gradebook-info-label", Label).update(
            f"{len(filtered)} group(s), {total} students"
        )

    def _update_gb_filter_options(self) -> None:
        groups = sorted({g.group_name for g in self.all_gradebook_groups if g.group_name})
        teachers = sorted({g.teacher_name for g in self.all_gradebook_groups if g.teacher_name})
        self.query_one("#gb-filter-bar", GradebookFilterBar).update_options(groups, teachers)

    def _rebuild_gradebook_table(self, groups: list[GradebookGroup]) -> None:
        table = self.query_one("#gradebook-table", DataTable)
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

        table = self.query_one("#gradebook-table", DataTable)
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
        self.query_one("#gradebook-info-label", Label).update(text)
