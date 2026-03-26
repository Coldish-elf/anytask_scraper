from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anytask_scraper.models import (
    Comment,
    QueueEntry,
    ReviewQueue,
    Submission,
    last_name_in_range,
    name_matches_list,
)
from anytask_scraper.parser import strip_html

SCHEMA_VERSION = 1
_ISSUE_ID_RE = re.compile(r"/issue/(\d+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dt_to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_./:-]", "", normalized)
    return normalized or "unknown"


def _event_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:20]


def _issue_id_from_url(issue_url: str) -> int:
    match = _ISSUE_ID_RE.search(issue_url)
    return int(match.group(1)) if match else 0


class QueueJsonDB:
    def __init__(self, path: Path | str, *, autosave: bool = True) -> None:
        self.path = Path(path)
        self.autosave = autosave
        self._data = self._load_or_init()

    def _load_or_init(self) -> dict[str, Any]:
        now = _now_iso()
        if not self.path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
                "courses": {},
            }

        raw_obj = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw_obj, dict):
            raise ValueError("QueueJsonDB file must contain a JSON object")

        schema_version = raw_obj.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version: {schema_version} (expected {SCHEMA_VERSION})"
            )

        courses = raw_obj.get("courses")
        if not isinstance(courses, dict):
            raise ValueError("QueueJsonDB payload must contain object key 'courses'")

        if "created_at" not in raw_obj:
            raw_obj["created_at"] = now
        if "updated_at" not in raw_obj:
            raw_obj["updated_at"] = now

        return raw_obj

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def sync_queue(self, queue: ReviewQueue, *, course_title: str = "") -> int:
        now = _now_iso()
        course = self._ensure_course(queue.course_id, course_title, now)

        newly_flagged = 0
        for entry in queue.entries:
            assignment = self._upsert_queue_entry(course, queue.course_id, entry, now)
            if assignment.get("queue_state") == "new" and assignment.get("_just_flagged"):
                newly_flagged += 1
                assignment.pop("_just_flagged", None)

        for issue_url, submission in queue.submissions.items():
            assignment = self._upsert_submission(
                course,
                queue.course_id,
                issue_url,
                submission,
                now,
            )
            if assignment.get("queue_state") == "new" and assignment.get("_just_flagged"):
                newly_flagged += 1
                assignment.pop("_just_flagged", None)

        self._data["updated_at"] = now
        if self.autosave:
            self.save()
        return newly_flagged

    def pull_new_entries(
        self,
        *,
        course_id: int | None = None,
        limit: int | None = None,
        student_contains: str = "",
        task_contains: str = "",
        status_contains: str = "",
        reviewer_contains: str = "",
        last_name_from: str = "",
        last_name_to: str = "",
        issue_id: int | None = None,
        name_list: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        pulled_at = _now_iso()
        pulled: list[dict[str, Any]] = []
        student_contains_cf = student_contains.strip().casefold()
        task_contains_cf = task_contains.strip().casefold()
        status_contains_cf = status_contains.strip().casefold()
        reviewer_contains_cf = reviewer_contains.strip().casefold()
        issue_filter = issue_id if issue_id is not None and issue_id > 0 else None

        for cid, course in self._iter_courses(course_id):
            students = course.get("students", {})
            if not isinstance(students, dict):
                continue
            for student_key in sorted(students):
                student = students.get(student_key)
                if not isinstance(student, dict):
                    continue
                assignments = student.get("assignments", {})
                if not isinstance(assignments, dict):
                    continue
                for assignment_key in sorted(assignments):
                    assignment = assignments.get(assignment_key)
                    if not isinstance(assignment, dict):
                        continue
                    if assignment.get("queue_state") != "new":
                        continue
                    queue = assignment.get("queue", {})
                    if not isinstance(queue, dict):
                        queue = {}

                    entry_issue_id = int(assignment.get("issue_id", 0) or 0)
                    student_name = str(assignment.get("student_name", ""))
                    task_title = str(assignment.get("task_title", ""))
                    status = str(queue.get("status", ""))
                    reviewer = str(queue.get("reviewer", ""))

                    if student_contains_cf and student_contains_cf not in student_name.casefold():
                        continue
                    if task_contains_cf and task_contains_cf not in task_title.casefold():
                        continue
                    if status_contains_cf and status_contains_cf not in status.casefold():
                        continue
                    if reviewer_contains_cf and reviewer_contains_cf not in reviewer.casefold():
                        continue
                    if issue_filter is not None and entry_issue_id != issue_filter:
                        continue
                    if (last_name_from or last_name_to) and not last_name_in_range(
                        student_name,
                        last_name_from.strip(),
                        last_name_to.strip(),
                    ):
                        continue
                    if name_list and not name_matches_list(student_name, name_list):
                        continue

                    assignment["queue_state"] = "pulled"
                    assignment["pulled_at"] = pulled_at
                    pulled.append(
                        {
                            "course_id": cid,
                            "student_key": student_key,
                            "assignment_key": assignment_key,
                            "student_name": student_name,
                            "task_title": task_title,
                            "issue_id": entry_issue_id,
                            "issue_url": assignment.get("issue_url", ""),
                            "status": status,
                            "grade": queue.get("grade", ""),
                            "reviewer": reviewer,
                            "updated": queue.get("updated", ""),
                            "queue_state": "pulled",
                        }
                    )

                    if limit is not None and len(pulled) >= limit:
                        self._data["updated_at"] = pulled_at
                        if self.autosave:
                            self.save()
                        return pulled

        self._data["updated_at"] = pulled_at
        if self.autosave:
            self.save()
        return pulled

    def get_all_entries(self, *, course_id: int | None = None) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for cid, course in self._iter_courses(course_id):
            students = course.get("students", {})
            if not isinstance(students, dict):
                continue
            for student_key, student in sorted(students.items()):
                if not isinstance(student, dict):
                    continue
                assignments = student.get("assignments", {})
                if not isinstance(assignments, dict):
                    continue
                for assignment_key, assignment in sorted(assignments.items()):
                    if not isinstance(assignment, dict):
                        continue
                    queue = assignment.get("queue", {})
                    entries.append(
                        {
                            "course_id": cid,
                            "student_key": student_key,
                            "assignment_key": assignment_key,
                            "student_name": assignment.get("student_name", ""),
                            "task_title": assignment.get("task_title", ""),
                            "issue_id": assignment.get("issue_id", 0),
                            "issue_url": assignment.get("issue_url", ""),
                            "status": (queue.get("status", "") if isinstance(queue, dict) else ""),
                            "grade": (queue.get("grade", "") if isinstance(queue, dict) else ""),
                            "reviewer": (
                                queue.get("reviewer", "") if isinstance(queue, dict) else ""
                            ),
                            "updated": (
                                queue.get("updated", "") if isinstance(queue, dict) else ""
                            ),
                            "queue_state": assignment.get("queue_state", "new"),
                        }
                    )
        return entries

    def mark_entry_pulled(
        self,
        *,
        course_id: int,
        student_key: str,
        assignment_key: str,
    ) -> bool:
        courses = self._data.get("courses", {})
        if not isinstance(courses, dict):
            return False

        course = courses.get(str(course_id))
        if not isinstance(course, dict):
            return False
        students = course.get("students", {})
        if not isinstance(students, dict):
            return False
        student = students.get(student_key)
        if not isinstance(student, dict):
            return False
        assignments = student.get("assignments", {})
        if not isinstance(assignments, dict):
            return False
        assignment = assignments.get(assignment_key)
        if not isinstance(assignment, dict):
            return False

        assignment["queue_state"] = "pulled"
        assignment["pulled_at"] = _now_iso()
        self._data["updated_at"] = assignment["pulled_at"]
        if self.autosave:
            self.save()
        return True

    def mark_entry_processed(
        self,
        *,
        course_id: int,
        student_key: str,
        assignment_key: str,
    ) -> bool:
        courses = self._data.get("courses", {})
        if not isinstance(courses, dict):
            return False

        course = courses.get(str(course_id))
        if not isinstance(course, dict):
            return False
        students = course.get("students", {})
        if not isinstance(students, dict):
            return False
        student = students.get(student_key)
        if not isinstance(student, dict):
            return False
        assignments = student.get("assignments", {})
        if not isinstance(assignments, dict):
            return False
        assignment = assignments.get(assignment_key)
        if not isinstance(assignment, dict):
            return False

        assignment["queue_state"] = "processed"
        assignment["processed_at"] = _now_iso()
        self._data["updated_at"] = assignment["processed_at"]
        if self.autosave:
            self.save()
        return True

    def record_issue_write(
        self,
        *,
        course_id: int,
        issue_id: int,
        action: str,
        value: str,
        author: str = "",
        note: str = "",
    ) -> bool:
        located = self._find_assignment_by_issue_id(course_id, issue_id)
        if located is None:
            return False

        assignment = located
        written_at = _now_iso()
        event = {
            "event_id": _event_id(
                str(issue_id),
                "write",
                action.strip(),
                value.strip(),
                author.strip(),
                written_at,
            ),
            "event_type": "write",
            "timestamp": written_at,
            "action": action.strip(),
            "value": value,
            "author": author,
            "note": note,
        }
        self._append_issue_chain_event(assignment, event)
        assignment["last_seen_at"] = written_at
        self._data["updated_at"] = written_at
        if self.autosave:
            self.save()
        return True

    def diff_assignment(
        self,
        *,
        course_id: int,
        student_key: str,
        assignment_key: str,
    ) -> list[dict[str, str]]:
        courses = self._data.get("courses", {})
        if not isinstance(courses, dict):
            return []

        course = courses.get(str(course_id))
        if not isinstance(course, dict):
            return []
        student = course.get("students", {}).get(student_key)
        if not isinstance(student, dict):
            return []
        assignment = student.get("assignments", {}).get(assignment_key)
        if not isinstance(assignment, dict):
            return []

        snapshots = [
            e
            for e in assignment.get("issue_chain", [])
            if isinstance(e, dict) and e.get("event_type") == "queue_snapshot"
        ]
        if len(snapshots) < 2:
            return []

        prev, curr = snapshots[-2], snapshots[-1]
        diffs: list[dict[str, str]] = []
        for field in ("status", "reviewer", "grade", "updated"):
            old_val = str(prev.get(field, ""))
            new_val = str(curr.get(field, ""))
            if old_val != new_val:
                diffs.append({"field": field, "old": old_val, "new": new_val})
        return diffs

    def get_changed_entries(
        self,
        *,
        course_id: int | None = None,
    ) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for cid, course in self._iter_courses(course_id):
            students = course.get("students", {})
            if not isinstance(students, dict):
                continue
            for student_key, student in sorted(students.items()):
                if not isinstance(student, dict):
                    continue
                assignments = student.get("assignments", {})
                if not isinstance(assignments, dict):
                    continue
                for assignment_key, assignment in sorted(assignments.items()):
                    if not isinstance(assignment, dict):
                        continue
                    diffs = self.diff_assignment(
                        course_id=cid,
                        student_key=student_key,
                        assignment_key=assignment_key,
                    )
                    if not diffs:
                        continue
                    queue = assignment.get("queue", {})
                    changed.append(
                        {
                            "course_id": cid,
                            "student_key": student_key,
                            "assignment_key": assignment_key,
                            "student_name": assignment.get("student_name", ""),
                            "task_title": assignment.get("task_title", ""),
                            "issue_id": assignment.get("issue_id", 0),
                            "diffs": diffs,
                            "current_status": (
                                queue.get("status", "") if isinstance(queue, dict) else ""
                            ),
                        }
                    )
        return changed

    def statistics(
        self,
        *,
        course_id: int | None = None,
    ) -> dict[str, Any]:
        counts: dict[str, int] = {"total": 0, "new": 0, "pulled": 0, "processed": 0}
        by_course: dict[int, dict[str, int]] = {}

        for cid, course in self._iter_courses(course_id):
            course_counts: dict[str, int] = {
                "total": 0,
                "new": 0,
                "pulled": 0,
                "processed": 0,
            }
            students = course.get("students", {})
            if not isinstance(students, dict):
                continue
            for student in students.values():
                if not isinstance(student, dict):
                    continue
                assignments = student.get("assignments", {})
                if not isinstance(assignments, dict):
                    continue
                for assignment in assignments.values():
                    if not isinstance(assignment, dict):
                        continue
                    state = assignment.get("queue_state", "new")
                    counts["total"] += 1
                    course_counts["total"] += 1
                    if state in counts:
                        counts[state] += 1
                    if state in course_counts:
                        course_counts[state] += 1
            by_course[cid] = course_counts

        return {**counts, "by_course": by_course}

    def _ensure_course(self, course_id: int, title: str, now: str) -> dict[str, Any]:
        courses = self._data.setdefault("courses", {})
        if not isinstance(courses, dict):
            raise ValueError("QueueJsonDB payload field 'courses' must be an object")

        key = str(course_id)
        if key not in courses or not isinstance(courses[key], dict):
            courses[key] = {
                "course_id": course_id,
                "title": title,
                "first_seen_at": now,
                "last_seen_at": now,
                "students": {},
            }

        course = courses[key]
        if not isinstance(course, dict):
            raise ValueError("QueueJsonDB course node must be an object")

        if title:
            course["title"] = title
        course["last_seen_at"] = now
        course.setdefault("students", {})
        return course

    def _ensure_student(
        self,
        course: dict[str, Any],
        *,
        student_name: str,
        student_url: str,
        now: str,
    ) -> tuple[str, dict[str, Any]]:
        students = course.setdefault("students", {})
        if not isinstance(students, dict):
            raise ValueError("QueueJsonDB students node must be an object")

        student_key = student_url.strip() or _slug(student_name)
        if student_key not in students or not isinstance(students[student_key], dict):
            students[student_key] = {
                "student_name": student_name,
                "student_url": student_url,
                "first_seen_at": now,
                "last_seen_at": now,
                "assignments": {},
            }

        student = students[student_key]
        if not isinstance(student, dict):
            raise ValueError("QueueJsonDB student node must be an object")

        if student_name:
            student["student_name"] = student_name
        if student_url:
            student["student_url"] = student_url
        student["last_seen_at"] = now
        student.setdefault("assignments", {})
        return student_key, student

    def _ensure_assignment(
        self,
        student: dict[str, Any],
        assignment_key: str,
        *,
        task_title: str,
        issue_url: str,
        issue_id: int,
        now: str,
    ) -> dict[str, Any]:
        assignments = student.setdefault("assignments", {})
        if not isinstance(assignments, dict):
            raise ValueError("QueueJsonDB assignments node must be an object")

        if assignment_key not in assignments or not isinstance(assignments[assignment_key], dict):
            assignments[assignment_key] = {
                "assignment_key": assignment_key,
                "task_title": task_title,
                "issue_id": issue_id,
                "issue_url": issue_url,
                "student_name": student.get("student_name", ""),
                "student_url": student.get("student_url", ""),
                "queue": {
                    "status": "",
                    "reviewer": "",
                    "grade": "",
                    "updated": "",
                    "has_issue_access": False,
                },
                "queue_signature": "",
                "queue_state": "new",
                "first_seen_at": now,
                "last_seen_at": now,
                "pulled_at": "",
                "processed_at": "",
                "issue": {
                    "issue_id": issue_id,
                    "status": "",
                    "grade": "",
                    "max_score": "",
                    "reviewer": "",
                    "deadline": "",
                },
                "files": [],
                "issue_chain": [],
            }

        assignment = assignments[assignment_key]
        if not isinstance(assignment, dict):
            raise ValueError("QueueJsonDB assignment node must be an object")

        if task_title:
            assignment["task_title"] = task_title
        if issue_url:
            assignment["issue_url"] = issue_url
        if issue_id:
            assignment["issue_id"] = issue_id
            issue = assignment.setdefault("issue", {})
            if isinstance(issue, dict):
                issue["issue_id"] = issue_id

        assignment["student_name"] = student.get("student_name", "")
        assignment["student_url"] = student.get("student_url", "")
        assignment["last_seen_at"] = now
        assignment.setdefault("issue_chain", [])
        assignment.setdefault("files", [])
        return assignment

    def _upsert_queue_entry(
        self,
        course: dict[str, Any],
        course_id: int,
        entry: QueueEntry,
        now: str,
    ) -> dict[str, Any]:
        student_key, student = self._ensure_student(
            course,
            student_name=entry.student_name,
            student_url=entry.student_url,
            now=now,
        )

        issue_id = _issue_id_from_url(entry.issue_url)
        assignment_key = f"issue:{issue_id}" if issue_id else f"task:{_slug(entry.task_title)}"
        assignment = self._ensure_assignment(
            student,
            assignment_key,
            task_title=entry.task_title,
            issue_url=entry.issue_url,
            issue_id=issue_id,
            now=now,
        )

        queue_signature = "|".join(
            [
                entry.status_name,
                entry.responsible_name,
                entry.mark,
                entry.update_time,
                entry.issue_url,
            ]
        )
        previous_signature = str(assignment.get("queue_signature", ""))

        assignment["queue"] = {
            "status": entry.status_name,
            "reviewer": entry.responsible_name,
            "grade": entry.mark,
            "updated": entry.update_time,
            "has_issue_access": entry.has_issue_access,
        }
        assignment["queue_signature"] = queue_signature

        if previous_signature != queue_signature:
            assignment["queue_state"] = "new"
            assignment["pulled_at"] = ""
            assignment["processed_at"] = ""
            assignment["_just_flagged"] = True
            self._append_issue_chain_event(
                assignment,
                {
                    "event_id": _event_id(
                        str(course_id),
                        student_key,
                        assignment_key,
                        "queue_snapshot",
                        queue_signature,
                    ),
                    "event_type": "queue_snapshot",
                    "timestamp": now,
                    "status": entry.status_name,
                    "reviewer": entry.responsible_name,
                    "grade": entry.mark,
                    "updated": entry.update_time,
                    "issue_url": entry.issue_url,
                },
            )

        return assignment

    def _upsert_submission(
        self,
        course: dict[str, Any],
        course_id: int,
        issue_url: str,
        submission: Submission,
        now: str,
    ) -> dict[str, Any]:
        student_key, student = self._ensure_student(
            course,
            student_name=submission.student_name,
            student_url=submission.student_url,
            now=now,
        )

        assignment_key = (
            f"issue:{submission.issue_id}"
            if submission.issue_id
            else f"task:{_slug(submission.task_title)}"
        )
        assignment = self._ensure_assignment(
            student,
            assignment_key,
            task_title=submission.task_title,
            issue_url=issue_url,
            issue_id=submission.issue_id,
            now=now,
        )

        issue = assignment.setdefault("issue", {})
        if isinstance(issue, dict):
            issue.update(
                {
                    "issue_id": submission.issue_id,
                    "status": submission.status,
                    "grade": submission.grade,
                    "max_score": submission.max_score,
                    "reviewer": submission.reviewer_name,
                    "deadline": submission.deadline,
                }
            )

        assignment["files"] = self._collect_files(submission.comments)

        for comment in submission.comments:
            event = self._comment_event(course_id, assignment_key, submission, comment)
            self._append_issue_chain_event(assignment, event)

        return assignment

    @staticmethod
    def _collect_files(comments: list[Comment]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        files: list[dict[str, Any]] = []
        for comment in comments:
            for file_att in comment.files:
                key = (file_att.filename, file_att.download_url)
                if key in seen:
                    continue
                seen.add(key)
                files.append(asdict(file_att))
        return files

    def _comment_event(
        self,
        course_id: int,
        assignment_key: str,
        submission: Submission,
        comment: Comment,
    ) -> dict[str, Any]:
        timestamp = _dt_to_iso(comment.timestamp)
        file_refs = ",".join(
            f"{file_att.filename}|{file_att.download_url}" for file_att in comment.files
        )
        links = ",".join(comment.links)
        content_text = strip_html(comment.content_html) if comment.content_html else ""

        event_type = "system_event" if comment.is_system_event else "comment"
        event_id = _event_id(
            str(course_id),
            assignment_key,
            str(submission.issue_id),
            event_type,
            timestamp,
            comment.author_name,
            comment.author_url,
            comment.content_html,
            content_text,
            str(comment.is_after_deadline),
            file_refs,
            links,
        )
        return {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "author_name": comment.author_name,
            "author_url": comment.author_url,
            "is_after_deadline": comment.is_after_deadline,
            "content_html": comment.content_html,
            "content_text": content_text,
            "files": [asdict(file_att) for file_att in comment.files],
            "links": list(comment.links),
        }

    @staticmethod
    def _append_issue_chain_event(assignment: dict[str, Any], event: dict[str, Any]) -> None:
        issue_chain = assignment.setdefault("issue_chain", [])
        if not isinstance(issue_chain, list):
            raise ValueError("QueueJsonDB issue_chain node must be an array")

        event_id = str(event.get("event_id", ""))
        existing_ids = {
            str(existing.get("event_id", ""))
            for existing in issue_chain
            if isinstance(existing, dict)
        }
        if event_id in existing_ids:
            return
        issue_chain.append(event)

    def _iter_courses(self, course_id: int | None) -> list[tuple[int, dict[str, Any]]]:
        courses = self._data.get("courses", {})
        if not isinstance(courses, dict):
            return []

        items: list[tuple[int, dict[str, Any]]] = []
        for key in sorted(courses, key=_course_sort_key):
            node = courses.get(key)
            if not isinstance(node, dict):
                continue
            cid = int(node.get("course_id", key))
            if course_id is not None and cid != course_id:
                continue
            items.append((cid, node))
        return items

    def _find_assignment_by_issue_id(
        self,
        course_id: int,
        issue_id: int,
    ) -> dict[str, Any] | None:
        for cid, course in self._iter_courses(course_id):
            if cid != course_id:
                continue
            students = course.get("students", {})
            if not isinstance(students, dict):
                continue
            for student in students.values():
                if not isinstance(student, dict):
                    continue
                assignments = student.get("assignments", {})
                if not isinstance(assignments, dict):
                    continue
                for assignment in assignments.values():
                    if not isinstance(assignment, dict):
                        continue
                    if int(assignment.get("issue_id", 0)) != issue_id:
                        continue
                    return assignment
        return None


def _course_sort_key(key: str) -> tuple[int, str]:
    return (0, f"{int(key):09d}") if key.isdigit() else (1, key)
