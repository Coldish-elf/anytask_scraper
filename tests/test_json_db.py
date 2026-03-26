from __future__ import annotations

from datetime import datetime
from pathlib import Path

from anytask_scraper.json_db import QueueJsonDB
from anytask_scraper.models import Comment, FileAttachment, QueueEntry, ReviewQueue, Submission


def _entry(*, status: str = "On Review", update_time: str = "2026-02-28 10:00") -> QueueEntry:
    return QueueEntry(
        student_name="Alice Smith",
        student_url="/users/alice/",
        task_title="HW 1",
        update_time=update_time,
        mark="8",
        status_color="warning",
        status_name=status,
        responsible_name="Bob",
        responsible_url="/users/bob/",
        has_issue_access=True,
        issue_url="/issue/421525",
    )


def _submission() -> Submission:
    return Submission(
        issue_id=421525,
        task_title="HW 1",
        student_name="Alice Smith",
        student_url="/users/alice/",
        reviewer_name="Bob",
        reviewer_url="/users/bob/",
        status="Accepted",
        grade="10",
        max_score="10",
        deadline="09-02-2026",
        comments=[
            Comment(
                author_name="Alice Smith",
                author_url="/users/alice/",
                timestamp=datetime(2026, 2, 28, 9, 30),
                content_html="<p>my solution</p>",
                files=[
                    FileAttachment(
                        filename="hw1.ipynb",
                        download_url="/media/files/hw1.ipynb",
                        is_notebook=True,
                    )
                ],
                links=["https://colab.research.google.com/drive/abc123"],
            ),
            Comment(
                author_name="Bob",
                author_url="/users/bob/",
                timestamp=datetime(2026, 2, 28, 10, 0),
                content_html="Статус изменен: Accepted",
                is_system_event=True,
            ),
        ],
    )


def test_sync_queue_creates_hierarchy_and_pull_new(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    queue = ReviewQueue(course_id=1250, entries=[_entry()])

    flagged = db.sync_queue(queue, course_title="Python")

    assert flagged == 1

    data = db.snapshot()
    course = data["courses"]["1250"]
    assert course["title"] == "Python"
    assert "/users/alice/" in course["students"]

    student = course["students"]["/users/alice/"]
    assignment = student["assignments"]["issue:421525"]
    assert assignment["task_title"] == "HW 1"
    assert assignment["queue_state"] == "new"
    assert assignment["files"] == []

    pulled = db.pull_new_entries(course_id=1250)
    assert len(pulled) == 1
    assert pulled[0]["assignment_key"] == "issue:421525"

    pulled_again = db.pull_new_entries(course_id=1250)
    assert pulled_again == []


def test_sync_queue_reflags_when_queue_state_changes(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")

    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))
    first_pull = db.pull_new_entries(course_id=1250)
    assert len(first_pull) == 1

    changed = _entry(status="Accepted", update_time="2026-02-28 10:30")
    flagged = db.sync_queue(ReviewQueue(course_id=1250, entries=[changed]))

    assert flagged == 1

    second_pull = db.pull_new_entries(course_id=1250)
    assert len(second_pull) == 1
    assert second_pull[0]["status"] == "Accepted"


def test_sync_queue_with_submission_tracks_files_and_issue_chain(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")

    queue = ReviewQueue(
        course_id=1250,
        entries=[_entry()],
        submissions={"/issue/421525": _submission()},
    )

    db.sync_queue(queue)
    first = db.snapshot()
    assignment = first["courses"]["1250"]["students"]["/users/alice/"]["assignments"][
        "issue:421525"
    ]

    assert assignment["files"]
    assert assignment["files"][0]["filename"] == "hw1.ipynb"

    event_types = {event["event_type"] for event in assignment["issue_chain"]}
    assert "queue_snapshot" in event_types
    assert "comment" in event_types
    assert "system_event" in event_types

    chain_len = len(assignment["issue_chain"])

    db.sync_queue(queue)
    second = db.snapshot()
    assignment_after = second["courses"]["1250"]["students"]["/users/alice/"]["assignments"][
        "issue:421525"
    ]
    assert len(assignment_after["issue_chain"]) == chain_len


def test_sync_queue_comment_dedup_is_stable_when_older_comment_is_inserted(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")

    first_submission = _submission()
    db.sync_queue(
        ReviewQueue(
            course_id=1250,
            entries=[_entry()],
            submissions={"/issue/421525": first_submission},
        )
    )
    before = db.snapshot()
    assignment_before = before["courses"]["1250"]["students"]["/users/alice/"]["assignments"][
        "issue:421525"
    ]

    inserted_comment = Comment(
        author_name="Alice Smith",
        author_url="/users/alice/",
        timestamp=datetime(2026, 2, 28, 9, 45),
        content_html="<p>follow-up</p>",
    )
    second_submission = _submission()
    second_submission.comments.insert(1, inserted_comment)

    db.sync_queue(
        ReviewQueue(
            course_id=1250,
            entries=[_entry()],
            submissions={"/issue/421525": second_submission},
        )
    )
    after = db.snapshot()
    assignment_after = after["courses"]["1250"]["students"]["/users/alice/"]["assignments"][
        "issue:421525"
    ]

    texts = [event.get("content_text", "") for event in assignment_after["issue_chain"]]

    assert len(assignment_after["issue_chain"]) == len(assignment_before["issue_chain"]) + 1
    assert texts.count("follow-up") == 1
    assert texts.count("Статус изменен: Accepted") == 1


def test_record_issue_write_appends_issue_chain_event(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))

    ok = db.record_issue_write(
        course_id=1250,
        issue_id=421525,
        action="grade",
        value="10/10",
        author="Bob",
        note="graded manually",
    )

    assert ok

    data = db.snapshot()
    assignment = data["courses"]["1250"]["students"]["/users/alice/"]["assignments"]["issue:421525"]
    write_events = [e for e in assignment["issue_chain"] if e["event_type"] == "write"]
    assert len(write_events) == 1
    assert write_events[0]["action"] == "grade"
    assert write_events[0]["value"] == "10/10"


def test_mark_entry_processed_changes_state(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))
    pulled = db.pull_new_entries(course_id=1250)

    ok = db.mark_entry_processed(
        course_id=1250,
        student_key=pulled[0]["student_key"],
        assignment_key=pulled[0]["assignment_key"],
    )

    assert ok

    data = db.snapshot()
    assignment = data["courses"]["1250"]["students"]["/users/alice/"]["assignments"]["issue:421525"]
    assert assignment["queue_state"] == "processed"


def test_get_all_entries_returns_all_states(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")

    entry1 = _entry()
    entry2 = QueueEntry(
        student_name="Carol",
        student_url="/users/carol/",
        task_title="HW 2",
        update_time="2026-02-28 11:00",
        mark="5",
        status_color="info",
        status_name="On Review",
        responsible_name="Dave",
        responsible_url="/users/dave/",
        has_issue_access=True,
        issue_url="/issue/999",
    )
    db.sync_queue(ReviewQueue(course_id=1250, entries=[entry1, entry2]))

    db.pull_new_entries(course_id=1250, limit=1)

    entries = db.get_all_entries(course_id=1250)
    assert len(entries) == 2

    states = {e["student_name"]: e["queue_state"] for e in entries}

    assert "pulled" in states.values()
    assert "new" in states.values()

    all_entries = db.get_all_entries()
    assert len(all_entries) == 2


def test_pull_new_entries_applies_filters_without_consuming_non_matching(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            _entry(),
            QueueEntry(
                student_name="Carol Adams",
                student_url="/users/carol/",
                task_title="HW 2",
                update_time="2026-02-28 11:00",
                mark="10",
                status_color="success",
                status_name="Accepted",
                responsible_name="Dave",
                responsible_url="/users/dave/",
                has_issue_access=True,
                issue_url="/issue/999",
            ),
        ],
    )
    db.sync_queue(queue)

    pulled = db.pull_new_entries(
        course_id=1250,
        student_contains="carol",
        task_contains="hw 2",
        status_contains="accept",
        reviewer_contains="dav",
        last_name_from="car",
        last_name_to="car",
        issue_id=999,
    )
    assert len(pulled) == 1
    assert pulled[0]["student_name"] == "Carol Adams"
    assert pulled[0]["issue_id"] == 999

    entries_after_filtered_pull = db.get_all_entries(course_id=1250)
    states_after_filtered_pull = {
        e["student_name"]: e["queue_state"] for e in entries_after_filtered_pull
    }
    assert states_after_filtered_pull["Carol Adams"] == "pulled"
    assert states_after_filtered_pull["Alice Smith"] == "new"

    pulled_alice = db.pull_new_entries(course_id=1250, student_contains="alice")
    assert len(pulled_alice) == 1
    assert pulled_alice[0]["student_name"] == "Alice Smith"


def test_get_all_entries_fields(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))

    entries = db.get_all_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["course_id"] == 1250
    assert e["student_name"] == "Alice Smith"
    assert e["task_title"] == "HW 1"
    assert e["issue_id"] == 421525
    assert e["issue_url"] == "/issue/421525"
    assert e["status"] == "On Review"
    assert e["grade"] == "8"
    assert e["reviewer"] == "Bob"
    assert e["queue_state"] == "new"


def test_mark_entry_pulled_single_entry(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))

    entries = db.get_all_entries(course_id=1250)
    assert len(entries) == 1
    assert entries[0]["queue_state"] == "new"

    ok = db.mark_entry_pulled(
        course_id=1250,
        student_key=entries[0]["student_key"],
        assignment_key=entries[0]["assignment_key"],
    )
    assert ok

    data = db.snapshot()
    assignment = data["courses"]["1250"]["students"]["/users/alice/"]["assignments"]["issue:421525"]
    assert assignment["queue_state"] == "pulled"
    assert assignment["pulled_at"] != ""


def test_mark_entry_pulled_not_found(tmp_path: Path) -> None:
    db = QueueJsonDB(tmp_path / "queue_db.json")
    db.sync_queue(ReviewQueue(course_id=1250, entries=[_entry()]))

    ok = db.mark_entry_pulled(
        course_id=1250,
        student_key="nonexistent",
        assignment_key="issue:421525",
    )
    assert not ok
