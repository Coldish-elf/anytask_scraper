from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from rich.text import Text

from anytask_scraper.models import Comment, FileAttachment, Submission, Task
from anytask_scraper.tui import app as app_mod
from anytask_scraper.tui import clipboard as clipboard_mod
from anytask_scraper.tui.screens import action_menu as action_menu_mod
from anytask_scraper.tui.screens import main as main_mod
from anytask_scraper.tui.screens import submission as submission_mod


def test_format_task_for_clipboard_student_view() -> None:
    task = Task(
        task_id=1,
        title="HW 1",
        description="<p>Read <b>chapter 1</b></p>",
        score=8,
        max_score=10,
        status="На проверке",
        deadline=datetime(2026, 2, 1, 12, 30),
    )

    text = clipboard_mod.format_task_for_clipboard(task, teacher_view=False)

    assert "Task: HW 1" in text
    assert "Score: 8/10" in text
    assert "Status: На проверке" in text
    assert "Description:" in text
    assert "Read chapter 1" in text


def test_format_submission_for_clipboard_includes_comment_assets() -> None:
    submission = Submission(
        issue_id=42,
        task_title="Project",
        student_name="Alice",
        reviewer_name="Bob",
        status="На проверке",
        grade="9",
        max_score="10",
        comments=[
            Comment(
                author_name="Bob",
                author_url="/u/bob",
                timestamp=datetime(2026, 2, 2, 9, 15),
                content_html="<p>Looks good</p>",
                files=[FileAttachment(filename="report.pdf", download_url="/f/1")],
                links=["https://example.com"],
                is_after_deadline=True,
            )
        ],
    )

    text = clipboard_mod.format_submission_for_clipboard(submission)

    assert "Issue ID: 42" in text
    assert "Comments: 1" in text
    assert "(LATE)" in text
    assert "Looks good" in text
    assert "Files: report.pdf" in text
    assert "Links: https://example.com" in text


def test_action_copy_selection_copies_payload_and_shows_success(monkeypatch) -> None:
    copied: list[str] = []
    statuses: list[tuple[str, str]] = []
    screen = SimpleNamespace(
        app=SimpleNamespace(copy_to_clipboard=lambda text: copied.append(text)),
        _build_copy_payload=lambda: ("task", "payload"),
        _show_status=lambda message, kind="info", timeout=4: statuses.append((message, kind)),
    )
    monkeypatch.setattr(
        main_mod,
        "copy_text_to_clipboard",
        lambda text, app=None: (copied.append(text) is None, "osc52"),
    )

    main_mod.MainScreen.action_copy_selection(screen)

    assert copied == ["payload"]
    assert statuses[-1] == ("Copied task to clipboard via osc52", "success")


def test_copy_gradebook_payload_reads_cursor_row() -> None:
    class _FakeTable:
        def __init__(self) -> None:
            self.row_count = 1
            self.cursor_row = 0
            self.ordered_columns = [
                SimpleNamespace(label="#"),
                SimpleNamespace(label="Student"),
                SimpleNamespace(label="Total ▲"),
            ]

        def get_row_at(self, row_index: int) -> list[object]:
            assert row_index == 0
            return ["1", "Alice", Text("95", style="bold green")]

    table = _FakeTable()
    screen = SimpleNamespace(
        query_one=lambda _selector, _typ=None: table,
        _table_cursor_index=lambda _table, _size: 0,
    )

    payload = main_mod.MainScreen._copy_gradebook_payload(screen)

    assert payload is not None
    assert payload[0] == "gradebook row"
    assert "Student: Alice" in payload[1]
    assert "Total: 95" in payload[1]


def test_copy_export_preview_payload_strips_markup() -> None:
    preview = SimpleNamespace(content="[bold]Ready[/bold]\n[dim]2 rows[/dim]")
    screen = SimpleNamespace(query_one=lambda _selector, _typ=None: preview)

    payload = main_mod.MainScreen._copy_export_preview_payload(screen)

    assert payload == ("export preview", "Ready\n2 rows")


def test_submission_screen_copy_uses_clipboard(monkeypatch) -> None:
    copied: list[str] = []
    notices: list[tuple[str, str]] = []
    submission = Submission(issue_id=1, task_title="Task A")
    monkeypatch.setattr(
        submission_mod,
        "copy_text_to_clipboard",
        lambda text, app=None: (copied.append(text) is None, "osc52"),
    )
    screen = SimpleNamespace(
        app=SimpleNamespace(copy_to_clipboard=lambda _text: None),
        submission=submission,
        notify=lambda message, **kwargs: notices.append((message, kwargs.get("severity", "info"))),
    )

    submission_mod.SubmissionScreen.action_copy_submission(screen)

    assert len(copied) == 1
    assert "Issue ID: 1" in copied[0]
    assert notices[-1] == ("Submission copied to clipboard", "info")


def test_copy_text_to_clipboard_tries_next_method_when_first_fails(monkeypatch) -> None:
    attempts: list[str] = []

    def _bad(_text: str) -> None:
        attempts.append("bad")
        raise RuntimeError("fail")

    def _good(_text: str) -> None:
        attempts.append("good")

    monkeypatch.setattr(
        clipboard_mod,
        "_iter_clipboard_methods",
        lambda _app: [("bad", _bad), ("good", _good)],
    )

    success, method = clipboard_mod.copy_text_to_clipboard("hello", app=object())

    assert success is True
    assert method == "good"
    assert attempts == ["bad", "good"]


def test_iter_clipboard_methods_linux_order(monkeypatch) -> None:
    monkeypatch.setattr(clipboard_mod.sys, "platform", "linux")
    monkeypatch.setattr(
        clipboard_mod,
        "_command_exists",
        lambda name: name in {"wl-copy", "xclip"},
    )
    app = SimpleNamespace(copy_to_clipboard=lambda _text: None)

    methods = clipboard_mod._iter_clipboard_methods(app)
    names = [name for name, _ in methods]

    assert names == ["wl-copy", "xclip", "osc52"]


def test_iter_clipboard_methods_windows_order(monkeypatch) -> None:
    monkeypatch.setattr(clipboard_mod.sys, "platform", "win32")
    monkeypatch.setattr(
        clipboard_mod,
        "_command_exists",
        lambda name: name in {"powershell", "clip"},
    )
    app = SimpleNamespace(copy_to_clipboard=lambda _text: None)

    methods = clipboard_mod._iter_clipboard_methods(app)
    names = [name for name, _ in methods]

    assert names == ["powershell", "clip", "osc52"]


def test_main_right_click_opens_action_menu() -> None:
    opened: list[bool] = []

    class _Event:
        def __init__(self) -> None:
            self.button = 3
            self.prevented = False
            self.stopped = False

        def prevent_default(self) -> None:
            self.prevented = True

        def stop(self) -> None:
            self.stopped = True

    event = _Event()
    screen = SimpleNamespace(_open_action_menu=lambda: opened.append(True))

    main_mod.MainScreen.on_mouse_down(screen, event)

    assert opened == [True]
    assert event.prevented is True
    assert event.stopped is True


def test_main_action_menu_result_copy_triggers_copy() -> None:
    called: list[str] = []
    screen = SimpleNamespace(
        _action_menu_open=True,
        action_copy_selection=lambda: called.append("copy"),
    )

    main_mod.MainScreen._handle_action_menu_result(screen, "copy")

    assert screen._action_menu_open is False
    assert called == ["copy"]


def test_submission_right_click_opens_action_menu() -> None:
    opened: list[bool] = []

    class _Event:
        def __init__(self) -> None:
            self.button = 3
            self.prevented = False
            self.stopped = False

        def prevent_default(self) -> None:
            self.prevented = True

        def stop(self) -> None:
            self.stopped = True

    event = _Event()
    screen = SimpleNamespace(_open_action_menu=lambda: opened.append(True))

    submission_mod.SubmissionScreen.on_mouse_down(screen, event)

    assert opened == [True]
    assert event.prevented is True
    assert event.stopped is True


def test_get_session_candidates_prefers_configured_path_and_keeps_legacy_fallback() -> None:
    candidates = app_mod.get_session_candidates({"session_file": "state/custom-session.json"})

    assert candidates == [Path("state/custom-session.json"), Path(".anytask_session.json")]


def test_submission_teacher_actions_hide_unavailable_actions() -> None:
    submission = Submission(
        issue_id=1,
        task_title="Task A",
        has_grade_form=True,
        has_status_form=True,
        has_comment_form=False,
        status_options=[(3, "На проверке")],
    )
    screen = submission_mod.SubmissionScreen(submission, teacher_mode=True)

    assert screen._teacher_actions() == [("grade", "Set grade"), ("status", "Set status")]


def test_submission_teacher_actions_include_accept_rate_when_accept_status_exists() -> None:
    submission = Submission(
        issue_id=1,
        task_title="Task A",
        has_grade_form=True,
        has_status_form=True,
        has_comment_form=True,
        status_options=[(3, "Review"), (7, "Accepted")],
    )
    screen = submission_mod.SubmissionScreen(submission, teacher_mode=True)

    assert screen._teacher_actions() == [
        ("rate", "Accept & Rate"),
        ("grade", "Set grade"),
        ("status", "Set status"),
        ("comment", "Add comment"),
    ]


def test_action_menu_option_selected_copy() -> None:
    dismissed: list[object] = []
    screen = SimpleNamespace(dismiss=lambda result: dismissed.append(result))
    event = SimpleNamespace(
        option=SimpleNamespace(id="copy"),
        stop=lambda: None,
    )

    action_menu_mod.ActionMenuScreen._menu_option_selected(screen, event)

    assert dismissed == ["copy"]


def test_task_row_selected_opens_submission_topic_for_student_view() -> None:
    task = Task(
        task_id=1,
        title="HW 1",
        status="На проверке",
        submit_url="/issue/get_or_create/1/2",
    )
    calls: list[tuple[str, Task]] = []
    screen = SimpleNamespace(
        filtered_tasks=[task],
        is_teacher_view=False,
        _show_detail=lambda t: calls.append(("detail", t)),
        _fetch_and_show_task_submission=lambda t: calls.append(("open", t)),
    )
    event = SimpleNamespace(row_key=SimpleNamespace(value="1"))

    main_mod.MainScreen._task_row_selected(screen, event)

    assert calls == [("detail", task), ("open", task)]


def test_task_row_selected_does_not_open_submission_topic_for_teacher_view() -> None:
    task = Task(
        task_id=1,
        title="HW 1",
        section="Group 1",
        submit_url="/issue/get_or_create/1/2",
    )
    calls: list[tuple[str, Task]] = []
    screen = SimpleNamespace(
        filtered_tasks=[task],
        is_teacher_view=True,
        _show_detail=lambda t: calls.append(("detail", t)),
        _fetch_and_show_task_submission=lambda t: calls.append(("open", t)),
    )
    event = SimpleNamespace(row_key=SimpleNamespace(value="1"))

    main_mod.MainScreen._task_row_selected(screen, event)

    assert calls == [("detail", task)]


def test_fetch_and_show_task_submission_uses_cached_submission() -> None:
    task = Task(
        task_id=1,
        title="HW 1",
        status="На проверке",
        submit_url="/issue/get_or_create/1/2",
    )
    sub = Submission(issue_id=7, task_title="HW 1")
    pushed: list[Submission] = []
    app = SimpleNamespace(
        client=SimpleNamespace(
            fetch_submission_page=lambda _url: (_ for _ in ()).throw(AssertionError("no fetch"))
        ),
        call_from_thread=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )
    screen = SimpleNamespace(
        _selected_course_id=9001,
        _task_submission_cache={(9001, task.submit_url): sub},
        app=app,
        _push_submission_screen=lambda s: pushed.append(s),
    )

    main_mod.MainScreen._fetch_and_show_task_submission.__wrapped__(screen, task)

    assert pushed == [sub]


def test_fetch_and_show_task_submission_skips_new_tasks() -> None:
    task = Task(
        task_id=1,
        title="HW 1",
        status="Новый",
        submit_url="/issue/get_or_create/1/2",
    )
    statuses: list[tuple[str, str]] = []
    app = SimpleNamespace(
        client=object(),
        call_from_thread=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )
    screen = SimpleNamespace(
        _selected_course_id=9001,
        _task_submission_cache={},
        app=app,
        _show_status=lambda message, kind="info", **_kwargs: statuses.append((message, kind)),
    )

    main_mod.MainScreen._fetch_and_show_task_submission.__wrapped__(screen, task)

    assert statuses == [("No submission yet for this task", "info")]
