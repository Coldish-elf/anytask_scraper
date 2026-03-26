from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from anytask_scraper.cli import _build_parser, _run_db_sync_once, main
from anytask_scraper.json_db import QueueJsonDB
from anytask_scraper.models import QueueEntry, ReviewQueue


def _seed_db(path: Path) -> None:
    db = QueueJsonDB(path)
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice Smith",
                student_url="/users/alice/",
                task_title="HW 1",
                update_time="2026-02-28 10:00",
                mark="8",
                status_color="warning",
                status_name="On Review",
                responsible_name="Bob",
                responsible_url="/users/bob/",
                has_issue_access=True,
                issue_url="/issue/421525",
            )
        ],
    )
    db.sync_queue(queue, course_title="Python")


def test_parser_accepts_db_commands() -> None:
    parser = _build_parser()

    args = parser.parse_args(["db", "pull", "--db-file", "queue_db.json", "--limit", "5"])
    assert args.command == "db"
    assert args.db_action == "pull"
    assert args.limit == 5
    assert args.student_contains == ""

    args = parser.parse_args(
        [
            "db",
            "pull",
            "--db-file",
            "queue_db.json",
            "-c",
            "1250",
            "--student-contains",
            "alice",
            "--task-contains",
            "hw",
            "--status-contains",
            "review",
            "--reviewer-contains",
            "bob",
            "--last-name-from",
            "a",
            "--last-name-to",
            "s",
            "--issue-id",
            "421525",
        ]
    )
    assert args.student_contains == "alice"
    assert args.task_contains == "hw"
    assert args.status_contains == "review"
    assert args.reviewer_contains == "bob"
    assert args.last_name_from == "a"
    assert args.last_name_to == "s"
    assert args.issue_id == 421525

    args = parser.parse_args(
        [
            "db",
            "process",
            "-c",
            "1250",
            "--student-key",
            "/users/alice/",
            "--assignment-key",
            "issue:421525",
        ]
    )
    assert args.command == "db"
    assert args.db_action == "process"

    args = parser.parse_args(
        [
            "db",
            "write",
            "-c",
            "1250",
            "--issue-id",
            "421525",
            "--action",
            "grade",
            "--value",
            "10/10",
        ]
    )
    assert args.command == "db"
    assert args.db_action == "write"


def test_main_db_pull_process_write_without_credentials(tmp_path: Path) -> None:
    db_path = tmp_path / "queue_db.json"
    settings_path = tmp_path / "settings.json"
    _seed_db(db_path)

    main(
        [
            "--settings-file",
            str(settings_path),
            "db",
            "pull",
            "--db-file",
            str(db_path),
            "-c",
            "1250",
            "--limit",
            "1",
        ]
    )

    main(
        [
            "--settings-file",
            str(settings_path),
            "db",
            "process",
            "--db-file",
            str(db_path),
            "-c",
            "1250",
            "--student-key",
            "/users/alice/",
            "--assignment-key",
            "issue:421525",
        ]
    )

    main(
        [
            "--settings-file",
            str(settings_path),
            "db",
            "write",
            "--db-file",
            str(db_path),
            "-c",
            "1250",
            "--issue-id",
            "421525",
            "--action",
            "grade",
            "--value",
            "10/10",
            "--author",
            "Bob",
        ]
    )

    snapshot = QueueJsonDB(db_path).snapshot()
    assignment = snapshot["courses"]["1250"]["students"]["/users/alice/"]["assignments"][
        "issue:421525"
    ]
    assert assignment["queue_state"] == "processed"

    write_events = [e for e in assignment["issue_chain"] if e.get("event_type") == "write"]
    assert len(write_events) == 1
    assert write_events[0]["action"] == "grade"
    assert write_events[0]["value"] == "10/10"


def test_db_sync_pull_passes_name_list_to_db() -> None:
    args = SimpleNamespace(
        course=1250,
        filter_task="",
        filter_reviewer="",
        filter_status="",
        last_name_from="",
        last_name_to="",
        deep=False,
        db_file="queue_db.json",
        course_title="Python",
        pull=True,
        limit=1,
        student_contains="",
        task_contains="",
        status_contains="",
        reviewer_contains="",
        pull_last_name_from="",
        pull_last_name_to="",
        issue_id=None,
        format="table",
    )
    fake_db = MagicMock()
    fake_db.sync_queue.return_value = 1
    fake_db.pull_new_entries.return_value = []

    with (
        patch("anytask_scraper.cli._resolve_name_list", return_value=["Alice Smith"]),
        patch(
            "anytask_scraper.cli._fetch_review_queue",
            return_value=(ReviewQueue(course_id=1250, entries=[]), 0),
        ),
        patch("anytask_scraper.cli.QueueJsonDB", return_value=fake_db),
    ):
        _run_db_sync_once(args, client=MagicMock())

    fake_db.pull_new_entries.assert_called_once_with(
        course_id=1250,
        limit=1,
        student_contains="",
        task_contains="",
        status_contains="",
        reviewer_contains="",
        last_name_from="",
        last_name_to="",
        issue_id=None,
        name_list=["Alice Smith"],
    )
