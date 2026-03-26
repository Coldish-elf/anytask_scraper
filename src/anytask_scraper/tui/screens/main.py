from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from anytask_scraper.models import (
    GradebookGroup,
    QueueEntry,
    Submission,
    Task,
)
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,  # noqa: F401
    extract_issue_id_from_breadcrumb,  # noqa: F401
    parse_gradebook_page,  # noqa: F401
    parse_submission_page,  # noqa: F401
)
from anytask_scraper.storage import (
    download_submission_files,  # noqa: F401
    save_submissions_csv,  # noqa: F401
)
from anytask_scraper.tui.clipboard import (
    copy_text_to_clipboard,  # noqa: F401
)
from anytask_scraper.tui.widgets.filter_bar import (
    GradebookFilterBar,
    QueueFilterBar,
    TaskFilterBar,
)
from anytask_scraper.tui.widgets.param_selector import ParameterSelector

from .mixins import CoreMixin, ExportMixin, GradebookMixin, QueueMixin, TasksMixin
from .mixins._helpers import (
    ExportFilterValue,
    _csv_row,
    _extract_filter_text,
    _extract_filter_values,
    _format_score,
    _normalize_multi_values,
    _parse_mark,
    _parse_update_time,
    _styled_deadline,
    _styled_status,
    make_safe_id,
)

if TYPE_CHECKING:
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)

__all__ = [
    "MainScreen",
    "make_safe_id",
    "ExportFilterValue",
    "_csv_row",
    "_extract_filter_text",
    "_extract_filter_values",
    "_format_score",
    "_normalize_multi_values",
    "_parse_mark",
    "_parse_update_time",
    "_styled_deadline",
    "_styled_status",
]


class MainScreen(ExportMixin, GradebookMixin, QueueMixin, TasksMixin, CoreMixin, Screen[None]):
    app: AnytaskApp

    BINDINGS = [
        Binding("tab", "cycle_focus", "Next", show=False),
        Binding("shift+tab", "cycle_focus_back", "Prev", show=False),
        Binding("1", "tab_tasks", "Tasks", show=False),
        Binding("2", "tab_queue", "Queue", show=False),
        Binding("3", "tab_gradebook", "Gradebook", show=False),
        Binding("4", "tab_export", "Export", show=False),
        Binding("a", "add_course", "Add", show=True),
        Binding("d", "discover_courses", "Discover", show=True),
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
        self._task_submission_cache: dict[tuple[int | None, str], Submission] = {}
        self.is_teacher_view = False
        self._selected_course_id: int | None = None
        self.all_queue_entries: list[QueueEntry] = []
        self.filtered_queue_entries: list[QueueEntry] = []
        self._queue_loaded_for: int | None = None
        self._task_filter_undo: dict[str, Any] | None = None
        self._queue_filter_undo: dict[str, Any] | None = None
        self._queue_sort_column: int | None = None
        self._queue_sort_reverse = False
        self._queue_preview_submission: Submission | None = None
        self._queue_preview_token = 0
        self._queue_preview_issue_url = ""
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
        self._export_filter_values: dict[str, list[str]] = {
            "#export-filter-task": [],
            "#export-filter-status": [],
            "#export-filter-reviewer": [],
        }
        self._export_filter_selected: dict[str, set[str]] = {
            "#export-filter-task": set(),
            "#export-filter-status": set(),
            "#export-filter-reviewer": set(),
        }
        self._export_filter_prompts: dict[str, str] = {
            "#export-filter-task": "Task",
            "#export-filter-status": "Status",
            "#export-filter-reviewer": "Reviewer",
        }
        self._export_name_list: list[str] = []

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
                            with Horizontal(id="queue-action-bar", classes="hidden"):
                                yield Button(
                                    "Accept & Rate",
                                    id="queue-btn-rate",
                                    variant="success",
                                )
                                yield Button("Grade", id="queue-btn-grade")
                                yield Button("Status", id="queue-btn-status")
                                yield Button("Comment", id="queue-btn-comment")

                with TabPane("Gradebook", id="gradebook-tab"):
                    yield GradebookFilterBar(classes="filter-bar", id="gb-filter-bar")
                    yield Label(
                        "Select a course to view gradebook",
                        id="gradebook-info-label",
                    )
                    with Vertical(id="gradebook-body"):
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
                                yield RadioButton("DB", id="db-export-radio")
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
                            yield Label(
                                "Task (All)",
                                id="export-filter-task-label",
                                classes="export-filter-label",
                            )
                            yield OptionList(
                                id="export-filter-task",
                            )
                            yield Label(
                                "Status (All)",
                                id="export-filter-status-label",
                                classes="export-filter-label",
                            )
                            yield OptionList(
                                id="export-filter-status",
                            )
                            yield Label(
                                "Reviewer (All)",
                                id="export-filter-reviewer-label",
                                classes="export-filter-label",
                            )
                            yield OptionList(
                                id="export-filter-reviewer",
                            )
                            with Horizontal(id="export-ln-range-row"):
                                yield Input(
                                    placeholder="From (А … Иванов)",
                                    id="export-ln-from",
                                )
                                yield Input(
                                    placeholder="To (П … Петров)",
                                    id="export-ln-to",
                                )
                        with Container(
                            classes="export-section",
                            id="export-names-section",
                        ):
                            yield Label(
                                "Name List Filter",
                                classes="export-section-title",
                            )
                            yield Label(
                                "No names loaded (filter inactive)",
                                id="export-names-status-label",
                                classes="export-filter-desc",
                            )
                            with Horizontal(id="export-names-file-row"):
                                yield Input(
                                    placeholder="Path to .txt file (one name per line)...",
                                    id="export-names-file-input",
                                )
                                yield Button(
                                    "Load",
                                    id="export-names-load-btn",
                                )
                            yield TextArea(
                                id="export-names-textarea",
                            )
                        with Container(classes="export-section", id="export-params-section"):
                            yield ParameterSelector(id="param-selector", classes="export-section")
                        with Container(classes="export-section"):
                            yield Label("Submission Files", classes="export-section-title")
                            with RadioSet(id="export-include-files-set"):
                                yield RadioButton(
                                    "Skip files",
                                    id="export-subs-files-off-radio",
                                )
                                yield RadioButton(
                                    "Include files",
                                    id="export-subs-files-on-radio",
                                    value=True,
                                )
                        with Container(classes="export-section"):
                            yield Label("GitHub Repos", classes="export-section-title")
                            with RadioSet(id="export-clone-repos-set"):
                                yield RadioButton(
                                    "Skip repos",
                                    id="export-clone-repos-off-radio",
                                )
                                yield RadioButton(
                                    "Clone repos",
                                    value=True,
                                    id="export-clone-repos-on-radio",
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

        saved_ids = self.app.load_course_ids()
        for cid in saved_ids:
            if cid not in self.app.courses:
                self._fetch_course(cid)
        self._update_key_bar()


def _register_mixin_handlers(cls: type) -> None:
    dh: dict[Any, list[Any]] = getattr(cls, "_decorated_handlers", {})
    seen: set[int] = {id(h) for _, handlers in dh.items() for h, _ in handlers}
    for base in cls.__mro__:
        if base is cls:
            continue
        for value in vars(base).values():
            if callable(value) and hasattr(value, "_textual_on") and id(value) not in seen:
                seen.add(id(value))
                for msg_type, selectors in value._textual_on:
                    dh.setdefault(msg_type, []).append((value, selectors))


_register_mixin_handlers(MainScreen)
