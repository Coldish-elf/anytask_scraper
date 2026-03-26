from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from anytask_scraper.models import Course, Gradebook, QueueEntry, ReviewQueue
from anytask_scraper.tui.screens import main as main_mod


class _DummyPreview:
    def __init__(self) -> None:
        self.last = ""

    def update(self, text: str) -> None:
        self.last = text


class _OptionList:
    def __init__(self, widget_id: str) -> None:
        self.id = widget_id.removeprefix("#")
        self.disabled = False
        self.highlighted: int | None = None
        self.options: list[object] = []

    def clear_options(self) -> None:
        self.options = []

    def add_option(self, option: object) -> None:
        self.options.append(option)


class _FakeApp:
    def __init__(self, client: object) -> None:
        self.client = client
        self.queue_cache: dict[int, ReviewQueue] = {}
        self.gradebook_cache: dict[int, Gradebook] = {}

    def call_from_thread(self, fn: object, *args: object) -> object:
        return fn(*args)


def _fake_screen(app: _FakeApp) -> SimpleNamespace:
    preview = _DummyPreview()
    screen = SimpleNamespace()
    screen.app = app
    screen._selected_course_id = 1250
    screen.is_teacher_view = True
    screen._preview = preview
    screen.focused = None
    screen.all_queue_entries = []
    screen.filtered_queue_entries = []
    screen._queue_loaded_for = None
    screen.all_gradebook_groups = []
    screen.filtered_gradebook_groups = []
    screen._gradebook_loaded_for = None
    screen._export_preload_token = 0
    screen._export_filter_values = {
        "#export-filter-task": [],
        "#export-filter-status": [],
        "#export-filter-reviewer": [],
    }
    screen._export_filter_selected = {
        "#export-filter-task": set(),
        "#export-filter-status": set(),
        "#export-filter-reviewer": set(),
    }
    screen._export_filter_prompts = {
        "#export-filter-task": "Task",
        "#export-filter-status": "Status",
        "#export-filter-reviewer": "Reviewer",
    }

    def _set_filter_options(
        select: object,
        options: list[tuple[str, str]],
        previous_value: object,
        *,
        enabled: bool,
    ) -> None:
        main_mod.MainScreen._set_export_filter_options(
            screen,
            select,
            options,
            previous_value,
            enabled=enabled,
        )

    screen._set_export_status = lambda _msg, _kind="info": None
    screen._set_export_filter_options = _set_filter_options

    def _rebuild_filter_option_list(option_list: object, keep_highlight: int | None = None) -> None:
        main_mod.MainScreen._rebuild_export_filter_option_list(
            screen,
            option_list,
            keep_highlight=keep_highlight,
        )

    def _refresh_filter_label(widget_id: str, enabled: bool) -> None:
        main_mod.MainScreen._refresh_export_filter_label(
            screen,
            widget_id,
            enabled=enabled,
        )

    def _selected_filter_values(widget_id: str) -> list[str]:
        return main_mod.MainScreen._get_selected_export_filter_values(screen, widget_id)

    screen._rebuild_export_filter_option_list = _rebuild_filter_option_list
    screen._refresh_export_filter_label = _refresh_filter_label
    screen._get_selected_export_filter_values = _selected_filter_values
    screen._update_queue_filter_options = lambda: None
    screen._rebuild_queue_table = lambda: None
    screen._update_queue_info = lambda _msg: None
    screen._update_gb_filter_options = lambda: None
    screen._rebuild_gradebook_table = lambda _groups: None
    screen._update_gradebook_info = lambda _msg: None
    screen._preload_export_data = lambda _typ, _cid, _token: None
    screen.query_one = lambda _sel, _typ=None: preview
    return screen


def _preview_screen(app: _FakeApp) -> SimpleNamespace:
    screen = _fake_screen(app)
    screen._get_included_columns = lambda: []
    screen._get_current_export_filters = lambda: {}
    screen._resolve_export_filename = lambda name: name
    screen._preview_queue = lambda entries, fmt, course_id, total, included: (
        f"queue:{course_id}:{total}:{fmt}"
    )
    screen._preview_submissions = lambda entries, fmt, course_id, total, included: (
        f"subs:{course_id}:{total}:{fmt}"
    )
    screen._preview_gradebook = lambda groups, fmt, course_id, total, included: (
        f"gradebook:{course_id}:{total}:{fmt}"
    )
    screen._has_loaded_export_data = lambda export_type: (
        main_mod.MainScreen._has_loaded_export_data(screen, export_type)
    )
    return screen


def test_load_queue_for_export_fetches_when_not_cached(monkeypatch) -> None:
    class Client:
        def fetch_queue_page(self, course_id: int) -> str:
            assert course_id == 1250
            return "<html>queue</html>"

        def fetch_all_queue_entries(self, course_id: int, csrf: str) -> list[dict[str, object]]:
            assert course_id == 1250
            assert csrf == "csrf-token"
            return [
                {
                    "student_name": "Alice",
                    "student_url": "/u/alice",
                    "task_title": "Task A",
                    "update_time": "01-01-2026",
                    "mark": "10",
                    "status_color": "success",
                    "status_name": "Done",
                    "responsible_name": "Reviewer",
                    "responsible_url": "/u/reviewer",
                    "has_issue_access": True,
                    "issue_url": "/issue/1",
                }
            ]

    monkeypatch.setattr(main_mod, "extract_csrf_from_queue_page", lambda _html: "csrf-token")
    screen = _fake_screen(_FakeApp(Client()))

    queue = main_mod.MainScreen._load_queue_for_export(screen, 1250)

    assert len(queue.entries) == 1
    assert queue.entries[0].student_name == "Alice"
    assert screen._queue_loaded_for == 1250
    assert len(screen.all_queue_entries) == 1
    assert 1250 in screen.app.queue_cache


def test_load_gradebook_for_export_fetches_when_not_cached(monkeypatch) -> None:
    expected = Gradebook(course_id=1250, groups=[])

    class Client:
        def fetch_gradebook_page(self, course_id: int) -> str:
            assert course_id == 1250
            return "<html>gradebook</html>"

    monkeypatch.setattr(main_mod, "parse_gradebook_page", lambda _html, _cid: expected)
    screen = _fake_screen(_FakeApp(Client()))

    gradebook = main_mod.MainScreen._load_gradebook_for_export(screen, 1250)

    assert gradebook is expected
    assert screen._gradebook_loaded_for == 1250
    assert screen.app.gradebook_cache[1250] is expected


def test_load_queue_for_export_cached_updates_info() -> None:
    app = _FakeApp(client=object())
    app.queue_cache[1250] = ReviewQueue(course_id=1250, entries=[])
    screen = _fake_screen(app)
    seen: list[str] = []
    screen._update_queue_info = lambda msg: seen.append(msg)

    queue = main_mod.MainScreen._load_queue_for_export(screen, 1250)

    assert queue is app.queue_cache[1250]
    assert seen[-1] == "0 entries"


def test_start_export_preload_queue_sets_loading_preview() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    called: list[tuple[str, int, int]] = []
    screen._preload_export_data = lambda typ, cid, token: called.append((typ, cid, token))

    main_mod.MainScreen._start_export_preload(screen, "queue-export-radio")

    assert called == [("queue-export-radio", 1250, 1)]
    assert "Loading queue data" in screen._preview.last


def test_start_export_preload_gradebook_sets_loading_preview() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    called: list[tuple[str, int, int]] = []
    screen._preload_export_data = lambda typ, cid, token: called.append((typ, cid, token))

    main_mod.MainScreen._start_export_preload(screen, "gb-export-radio")

    assert called == [("gb-export-radio", 1250, 1)]
    assert "Loading gradebook data" in screen._preview.last


def test_get_export_focus_order_skips_disabled_widgets() -> None:
    class _Widget:
        def __init__(self, disabled: bool) -> None:
            self.disabled = disabled

    screen = _fake_screen(_FakeApp(client=object()))
    screen._EXPORT_FOCUS_ORDER = ["#a", "#b", "#c"]
    widgets = {"#a": _Widget(False), "#b": _Widget(True), "#c": _Widget(False)}
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    order = main_mod.MainScreen._get_export_focus_order(screen)

    assert order == [widgets["#a"], widgets["#c"]]


def test_update_export_filters_disables_empty_selects() -> None:
    class _Radio:
        def __init__(self) -> None:
            self.disabled = False

    screen = _fake_screen(_FakeApp(client=object()))
    task_select = _OptionList("#export-filter-task")
    status_select = _OptionList("#export-filter-status")
    reviewer_select = _OptionList("#export-filter-reviewer")
    files_radio = _Radio()
    screen.all_queue_entries = []
    screen.all_gradebook_groups = []
    screen.all_tasks = []
    screen._get_current_export_type = lambda: "queue-export-radio"
    widgets = {
        "#export-filter-task": task_select,
        "#export-filter-status": status_select,
        "#export-filter-reviewer": reviewer_select,
        "#files-radio": files_radio,
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    main_mod.MainScreen._update_export_filters(screen)

    assert task_select.disabled is True
    assert status_select.disabled is True
    assert reviewer_select.disabled is True


def test_update_export_filters_populates_queue_selects_when_data_loaded() -> None:
    class _Radio:
        def __init__(self) -> None:
            self.disabled = False

    class _Entry:
        def __init__(self, task: str, status: str, reviewer: str) -> None:
            self.task_title = task
            self.status_name = status
            self.responsible_name = reviewer

    screen = _fake_screen(_FakeApp(client=object()))
    task_select = _OptionList("#export-filter-task")
    status_select = _OptionList("#export-filter-status")
    reviewer_select = _OptionList("#export-filter-reviewer")
    files_radio = _Radio()
    screen.all_queue_entries = [
        _Entry("Task 1", "New", "Alice"),
        _Entry("Task 2", "Done", "Bob"),
    ]
    screen._get_current_export_type = lambda: "queue-export-radio"
    widgets = {
        "#export-filter-task": task_select,
        "#export-filter-status": status_select,
        "#export-filter-reviewer": reviewer_select,
        "#files-radio": files_radio,
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    main_mod.MainScreen._update_export_filters(screen)

    assert task_select.disabled is False
    assert status_select.disabled is False
    assert reviewer_select.disabled is False
    assert screen._export_filter_values["#export-filter-task"] == ["Task 1", "Task 2"]
    assert screen._export_filter_values["#export-filter-status"] == ["Done", "New"]
    assert screen._export_filter_values["#export-filter-reviewer"] == ["Alice", "Bob"]


def test_update_export_filters_populates_db_selects_when_data_loaded() -> None:
    class _Radio:
        def __init__(self) -> None:
            self.disabled = False

    class _Entry:
        def __init__(self, task: str, status: str, reviewer: str) -> None:
            self.task_title = task
            self.status_name = status
            self.responsible_name = reviewer

    screen = _fake_screen(_FakeApp(client=object()))
    task_select = _OptionList("#export-filter-task")
    status_select = _OptionList("#export-filter-status")
    reviewer_select = _OptionList("#export-filter-reviewer")
    files_radio = _Radio()
    screen.all_queue_entries = [
        _Entry("Task 1", "New", "Alice"),
        _Entry("Task 2", "Done", "Bob"),
    ]
    screen._get_current_export_type = lambda: "db-export-radio"
    widgets = {
        "#export-filter-task": task_select,
        "#export-filter-status": status_select,
        "#export-filter-reviewer": reviewer_select,
        "#files-radio": files_radio,
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    main_mod.MainScreen._update_export_filters(screen)

    assert task_select.disabled is False
    assert status_select.disabled is False
    assert reviewer_select.disabled is False
    assert screen._export_filter_values["#export-filter-task"] == ["Task 1", "Task 2"]
    assert screen._export_filter_values["#export-filter-status"] == ["Done", "New"]
    assert screen._export_filter_values["#export-filter-reviewer"] == ["Alice", "Bob"]


def test_update_export_filters_db_disables_non_json_formats_and_selects_json() -> None:
    class _Radio:
        def __init__(self, value: bool = False) -> None:
            self.disabled = False
            self.value = value

    class _Entry:
        def __init__(self, task: str, status: str, reviewer: str) -> None:
            self.task_title = task
            self.status_name = status
            self.responsible_name = reviewer

    screen = _fake_screen(_FakeApp(client=object()))
    task_select = _OptionList("#export-filter-task")
    status_select = _OptionList("#export-filter-status")
    reviewer_select = _OptionList("#export-filter-reviewer")
    json_radio = _Radio(value=False)
    md_radio = _Radio()
    csv_radio = _Radio()
    files_radio = _Radio()
    screen.all_queue_entries = [_Entry("Task 1", "New", "Alice")]
    screen._get_current_export_type = lambda: "db-export-radio"
    widgets = {
        "#export-filter-task": task_select,
        "#export-filter-status": status_select,
        "#export-filter-reviewer": reviewer_select,
        "#json-radio": json_radio,
        "#md-radio": md_radio,
        "#csv-radio": csv_radio,
        "#files-radio": files_radio,
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    main_mod.MainScreen._update_export_filters(screen)

    assert md_radio.disabled is True
    assert csv_radio.disabled is True
    assert files_radio.disabled is True
    assert json_radio.value is True


def test_generate_preview_queue_shows_empty_loaded_state() -> None:
    app = _FakeApp(client=object())
    app.queue_cache[1250] = ReviewQueue(course_id=1250, entries=[])
    screen = _preview_screen(app)
    screen._queue_loaded_for = 1250

    preview = main_mod.MainScreen._generate_preview(screen, "queue-export-radio", "json")

    assert preview == "[dim]No queue entries match current filters[/dim]"


def test_generate_preview_submissions_shows_empty_loaded_state() -> None:
    app = _FakeApp(client=object())
    app.queue_cache[1250] = ReviewQueue(course_id=1250, entries=[])
    screen = _preview_screen(app)
    screen._queue_loaded_for = 1250

    preview = main_mod.MainScreen._generate_preview(screen, "subs-export-radio", "json")

    assert preview == "[dim]No queue entries match current filters[/dim]"


def test_generate_preview_gradebook_shows_empty_loaded_state() -> None:
    app = _FakeApp(client=object())
    app.gradebook_cache[1250] = Gradebook(course_id=1250, groups=[])
    screen = _preview_screen(app)
    screen._gradebook_loaded_for = 1250

    preview = main_mod.MainScreen._generate_preview(screen, "gb-export-radio", "json")

    assert preview == "[dim]No gradebook rows match current filters[/dim]"


def test_finish_export_preload_ignores_stale_token() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    calls: list[str] = []
    screen._export_preload_token = 2
    screen._get_current_export_type = lambda: "queue-export-radio"
    screen._update_export_filters = lambda: calls.append("filters")
    screen._update_params = lambda: calls.append("params")
    screen._refresh_export_preview = lambda: calls.append("preview")
    screen._set_export_status = lambda _msg, _kind="info": calls.append("status")

    main_mod.MainScreen._finish_export_preload(screen, "queue-export-radio", 1, "ok")

    assert calls == []


def test_finish_export_preload_error_without_details_has_no_trailing_colon() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    seen: list[tuple[str, str]] = []
    screen._export_preload_token = 1
    screen._get_current_export_type = lambda: "queue-export-radio"
    screen._update_export_filters = lambda: None
    screen._update_params = lambda: None
    screen._refresh_export_preview = lambda: None
    screen._set_export_status = lambda msg, kind="info": seen.append((msg, kind))

    main_mod.MainScreen._finish_export_preload(screen, "queue-export-radio", 1, "", "")

    assert seen[-1] == ("Failed to preload export data", "error")


def test_get_current_export_filters_tasks_teacher_mapping() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    screen.is_teacher_view = True
    screen._get_current_export_type = lambda: "tasks-export-radio"
    screen._export_filter_values["#export-filter-task"] = ["Task A", "Task B"]
    screen._export_filter_selected["#export-filter-task"] = {"Task A"}
    screen._export_filter_values["#export-filter-status"] = ["G1", "G2"]
    screen._export_filter_selected["#export-filter-status"] = {"G1"}

    filters = main_mod.MainScreen._get_current_export_filters(screen)

    assert filters == {"task": ["Task A"], "section": ["G1"]}


def test_get_current_export_filters_gradebook_mapping() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    screen._get_current_export_type = lambda: "gb-export-radio"
    screen._export_filter_values["#export-filter-task"] = ["Group 1", "Group 2"]
    screen._export_filter_selected["#export-filter-task"] = {"Group 1"}
    screen._export_filter_values["#export-filter-reviewer"] = ["Teacher A", "Teacher B"]
    screen._export_filter_selected["#export-filter-reviewer"] = {"Teacher A"}
    widgets = {
        "#export-ln-from": SimpleNamespace(value=""),
        "#export-ln-to": SimpleNamespace(value=""),
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    filters = main_mod.MainScreen._get_current_export_filters(screen)

    assert filters == {"group": ["Group 1"], "teacher": ["Teacher A"]}


def test_get_current_export_filters_db_mapping() -> None:
    screen = _fake_screen(_FakeApp(client=object()))
    screen._get_current_export_type = lambda: "db-export-radio"
    screen._export_filter_values["#export-filter-task"] = ["Task 1", "Task 2"]
    screen._export_filter_selected["#export-filter-task"] = {"Task 1"}
    screen._export_filter_values["#export-filter-status"] = ["New", "Done"]
    screen._export_filter_selected["#export-filter-status"] = {"Done"}
    screen._export_filter_values["#export-filter-reviewer"] = ["Alice", "Bob"]
    screen._export_filter_selected["#export-filter-reviewer"] = {"Bob"}
    widgets = {
        "#export-ln-from": SimpleNamespace(value="a"),
        "#export-ln-to": SimpleNamespace(value="s"),
    }
    screen.query_one = lambda sel, _typ=None: widgets[sel]

    filters = main_mod.MainScreen._get_current_export_filters(screen)

    assert filters == {
        "task": ["Task 1"],
        "status": ["Done"],
        "reviewer": ["Bob"],
        "last_name_from": "a",
        "last_name_to": "s",
    }


def test_handle_export_passes_columns_and_filename() -> None:
    class _RadioSet:
        def __init__(self, button_id: str) -> None:
            self.pressed_button = SimpleNamespace(id=button_id)

    widgets = {
        "#format-set": _RadioSet("csv-radio"),
        "#export-type-set": _RadioSet("subs-export-radio"),
        "#output-dir-input": SimpleNamespace(value="./output"),
    }
    captured: list[object] = []
    screen = SimpleNamespace(
        _selected_course_id=1250,
        query_one=lambda sel, _typ=None: widgets[sel],
        _get_current_export_filters=lambda: {"task": "Task 1"},
        _get_included_columns=lambda: ["Student", "Task"],
        _get_custom_export_filename=lambda: "my_queue",
        _get_include_submission_files=lambda: False,
        _get_clone_repos=lambda: False,
        _set_export_status=lambda _msg, _kind="info": None,
        _do_export=lambda *args: captured.append(args),
    )

    main_mod.MainScreen._handle_export(screen)

    assert len(captured) == 1
    (
        fmt,
        output_path,
        export_type,
        filters,
        columns,
        filename,
        include_files,
        clone_repos,
    ) = captured[0]
    assert fmt == "csv"
    assert export_type == "subs-export-radio"
    assert filters == {"task": "Task 1"}
    assert columns == ["Student", "Task"]
    assert filename == "my_queue"
    assert include_files is False
    assert clone_repos is False
    assert str(output_path).endswith("/output")


def test_do_export_submissions_skips_file_download_when_include_files_is_false(
    monkeypatch, tmp_path
) -> None:
    from anytask_scraper.models import QueueEntry, ReviewQueue, Submission

    statuses: list[tuple[str, str]] = []
    download_calls: list[int] = []
    saved_calls: list[int] = []

    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice",
                student_url="/u/alice",
                task_title="Task 1",
                update_time="01-01-2026",
                mark="10",
                status_color="success",
                status_name="Done",
                responsible_name="Bob",
                responsible_url="/u/bob",
                has_issue_access=True,
                issue_url="/issue/1",
            )
        ],
    )

    class _Client:
        def fetch_submission_page(self, _issue_url: str) -> str:
            return "<html>sub</html>"

    app = SimpleNamespace(client=_Client(), call_from_thread=lambda fn, *args: fn(*args))
    screen = SimpleNamespace(
        _selected_course_id=1250,
        app=app,
        _load_queue_for_export=lambda _course_id: queue,
        _set_export_status=lambda msg, kind="info": statuses.append((msg, kind)),
    )

    monkeypatch.setattr(main_mod, "extract_issue_id_from_breadcrumb", lambda _html: 7)
    monkeypatch.setattr(
        main_mod,
        "parse_submission_page",
        lambda _html, _issue_id, **_kw: Submission(
            issue_id=7, task_title="Task 1", student_name="Alice"
        ),
    )

    def _download(_client: object, _sub: Submission, _path: object) -> dict[str, object]:
        download_calls.append(1)
        return {"file": tmp_path / "file.txt"}

    def _save(
        _subs: object,
        _course_id: int,
        _output_path: object,
        columns: object = None,
        filename: object = None,
    ) -> Path:
        saved_calls.append(1)
        path = tmp_path / "subs.csv"
        path.write_text("ok", encoding="utf-8")
        return path

    monkeypatch.setattr(main_mod, "download_submission_files", _download)
    monkeypatch.setattr(main_mod, "save_submissions_csv", _save)

    main_mod.MainScreen._do_export.__wrapped__(
        screen,
        "csv",
        tmp_path,
        "subs-export-radio",
        None,
        ["Task"],
        None,
        False,
    )

    assert download_calls == []
    assert saved_calls == [1]
    assert statuses[-1] == ("Saved: subs.csv", "success")


def test_generate_preview_db_json() -> None:
    screen = SimpleNamespace(
        _selected_course_id=1250,
        all_queue_entries=[],
        app=SimpleNamespace(queue_cache={}, courses={}),
        _get_included_columns=lambda: [],
        _get_current_export_filters=lambda: {},
        _resolve_export_filename=lambda default: default,
    )

    preview = main_mod.MainScreen._generate_preview(screen, "db-export-radio", "json")

    assert "queue_db_1250.json" in preview
    payload = json.loads(preview.split("\n", 1)[1])
    assert payload["schema_version"] == 1
    assert payload["course_id"] == 1250
    assert payload["filtered_queue_entries"] == 0
    assert payload["preview_sample_size"] == 0
    courses = payload["snapshot_preview"]["courses"]
    assert set(courses.keys()) == {"1250"}
    assert courses["1250"]["students"] == {}


def test_generate_preview_db_json_applies_filters() -> None:
    entries = [
        QueueEntry(
            student_name="Alice",
            student_url="/u/alice",
            task_title="Task 1",
            update_time="01-01-2026",
            mark="10",
            status_color="success",
            status_name="Done",
            responsible_name="Bob",
            responsible_url="/u/bob",
            has_issue_access=True,
            issue_url="/issue/1",
        ),
        QueueEntry(
            student_name="Carol",
            student_url="/u/carol",
            task_title="Task 2",
            update_time="01-01-2026",
            mark="5",
            status_color="warning",
            status_name="New",
            responsible_name="Dan",
            responsible_url="/u/dan",
            has_issue_access=True,
            issue_url="/issue/2",
        ),
    ]
    screen = SimpleNamespace(
        _selected_course_id=1250,
        all_queue_entries=entries,
        app=SimpleNamespace(queue_cache={}, courses={}),
        _get_included_columns=lambda: [],
        _get_current_export_filters=lambda: {
            "task": ["Task 1"],
            "status": ["Done"],
            "reviewer": ["Bob"],
            "last_name_from": "a",
            "last_name_to": "a",
        },
        _resolve_export_filename=lambda default: default,
    )

    preview = main_mod.MainScreen._generate_preview(screen, "db-export-radio", "json")

    payload = json.loads(preview.split("\n", 1)[1])
    assert payload["filtered_queue_entries"] == 1
    assert payload["preview_sample_size"] == 1
    students = payload["snapshot_preview"]["courses"]["1250"]["students"]
    assert set(students.keys()) == {"/u/alice"}


def test_do_export_db_json_saves_snapshot(tmp_path: Path) -> None:
    statuses: list[tuple[str, str]] = []
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice",
                student_url="/u/alice",
                task_title="Task 1",
                update_time="01-01-2026",
                mark="10",
                status_color="success",
                status_name="Done",
                responsible_name="Bob",
                responsible_url="/u/bob",
                has_issue_access=True,
                issue_url="/issue/1",
            )
        ],
    )
    app = SimpleNamespace(
        courses={1250: Course(course_id=1250, title="Python")},
        call_from_thread=lambda fn, *args: fn(*args),
    )
    screen = SimpleNamespace(
        _selected_course_id=1250,
        app=app,
        _load_queue_for_export=lambda _course_id: queue,
        _resolve_export_filename=lambda default: default,
        _set_export_status=lambda msg, kind="info": statuses.append((msg, kind)),
    )

    main_mod.MainScreen._do_export.__wrapped__(
        screen,
        "json",
        tmp_path,
        "db-export-radio",
        None,
        [],
        None,
        False,
    )

    exported = tmp_path / "queue_db_1250.json"
    assert exported.exists()
    text = exported.read_text(encoding="utf-8")
    assert '"schema_version": 1' in text
    assert '"courses"' in text
    assert statuses[-1] == ("Saved: queue_db_1250.json (1 new/updated)", "success")


def test_do_export_db_json_applies_filters(tmp_path: Path) -> None:
    statuses: list[tuple[str, str]] = []
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice",
                student_url="/u/alice",
                task_title="Task 1",
                update_time="01-01-2026",
                mark="10",
                status_color="success",
                status_name="Done",
                responsible_name="Bob",
                responsible_url="/u/bob",
                has_issue_access=True,
                issue_url="/issue/1",
            ),
            QueueEntry(
                student_name="Carol",
                student_url="/u/carol",
                task_title="Task 2",
                update_time="01-01-2026",
                mark="5",
                status_color="warning",
                status_name="New",
                responsible_name="Dan",
                responsible_url="/u/dan",
                has_issue_access=True,
                issue_url="/issue/2",
            ),
        ],
    )
    app = SimpleNamespace(
        courses={1250: Course(course_id=1250, title="Python")},
        call_from_thread=lambda fn, *args: fn(*args),
    )
    screen = SimpleNamespace(
        _selected_course_id=1250,
        app=app,
        _load_queue_for_export=lambda _course_id: queue,
        _resolve_export_filename=lambda default: default,
        _set_export_status=lambda msg, kind="info": statuses.append((msg, kind)),
    )

    main_mod.MainScreen._do_export.__wrapped__(
        screen,
        "json",
        tmp_path,
        "db-export-radio",
        {
            "task": ["Task 1"],
            "status": ["Done"],
            "reviewer": ["Bob"],
            "last_name_from": "a",
            "last_name_to": "a",
        },
        [],
        None,
        False,
    )

    exported = tmp_path / "queue_db_1250.json"
    payload = json.loads(exported.read_text(encoding="utf-8"))
    students = payload["courses"]["1250"]["students"]
    assert set(students.keys()) == {"/u/alice"}
    assert statuses[-1] == ("Saved: queue_db_1250.json (1 new/updated)", "success")
