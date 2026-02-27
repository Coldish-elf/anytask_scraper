"""Project data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def extract_last_name(name: str) -> str:
    return name.split()[0] if name.strip() else name


def last_name_in_range(name: str, from_name: str = "", to_name: str = "") -> bool:
    ln = extract_last_name(name).casefold()
    if from_name and ln < from_name.casefold():
        return False
    return not (to_name and ln > to_name.casefold() + "\uffff")


@dataclass
class Task:
    """Course task."""

    task_id: int
    title: str
    description: str = ""
    deadline: datetime | None = None
    max_score: float | None = None
    score: float | None = None
    status: str = ""
    section: str = ""
    edit_url: str = ""
    submit_url: str = ""


@dataclass
class Course:
    """Course with tasks."""

    course_id: int
    title: str = ""
    teachers: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)


@dataclass
class ProfileCourseEntry:
    """Course entry from user profile."""

    course_id: int
    title: str
    role: str


@dataclass
class QueueEntry:
    """One queue row."""

    student_name: str
    student_url: str
    task_title: str
    update_time: str
    mark: str
    status_color: str
    status_name: str
    responsible_name: str
    responsible_url: str
    has_issue_access: bool
    issue_url: str


@dataclass
class FileAttachment:
    """Comment attachment."""

    filename: str
    download_url: str
    is_notebook: bool = False


@dataclass
class Comment:
    """Submission comment."""

    author_name: str
    author_url: str
    timestamp: datetime | None
    content_html: str
    files: list[FileAttachment] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    is_after_deadline: bool = False
    is_system_event: bool = False


@dataclass
class Submission:
    """Submission details."""

    issue_id: int
    task_title: str
    student_name: str = ""
    student_url: str = ""
    reviewer_name: str = ""
    reviewer_url: str = ""
    status: str = ""
    grade: str = ""
    max_score: str = ""
    deadline: str = ""
    comments: list[Comment] = field(default_factory=list)


@dataclass
class QueueFilters:
    """Queue filter options."""

    students: list[tuple[str, str]] = field(default_factory=list)
    tasks: list[tuple[str, str]] = field(default_factory=list)
    reviewers: list[tuple[str, str]] = field(default_factory=list)
    statuses: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ReviewQueue:
    """Queue payload."""

    course_id: int
    entries: list[QueueEntry] = field(default_factory=list)
    submissions: dict[str, Submission] = field(default_factory=dict)


@dataclass
class GradebookEntry:
    """One student row in the gradebook."""

    student_name: str
    student_url: str
    scores: dict[str, float] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    issue_urls: dict[str, str] = field(default_factory=dict)
    total_score: float = 0.0


@dataclass
class GradebookGroup:
    """One group within the gradebook."""

    group_name: str
    group_id: int
    teacher_name: str = ""
    task_titles: list[str] = field(default_factory=list)
    max_scores: dict[str, float] = field(default_factory=dict)
    entries: list[GradebookEntry] = field(default_factory=list)


@dataclass
class Gradebook:
    """Gradebook for a course."""

    course_id: int
    groups: list[GradebookGroup] = field(default_factory=list)


def filter_gradebook(
    gradebook: Gradebook,
    *,
    group: str = "",
    teacher: str = "",
    student: str = "",
    min_score: float | None = None,
    last_name_from: str = "",
    last_name_to: str = "",
) -> Gradebook:
    """Return a filtered copy of *gradebook*.

    Parameters
    ----------
    group:
        If non-empty, keep only groups whose name contains this substring
        (case-insensitive).
    teacher:
        If non-empty, keep only groups whose teacher name matches exactly.
    student:
        If non-empty, keep only entries whose student name contains this
        substring (case-insensitive).
    min_score:
        If set, keep only entries with total_score >= min_score.
    last_name_from:
        If non-empty, keep only entries whose last name >= this value
    last_name_to:
        If non-empty, keep only entries whose last name <= this value
    """
    filtered_groups: list[GradebookGroup] = []
    for g in gradebook.groups:
        if group and group.lower() not in g.group_name.lower():
            continue
        if teacher and g.teacher_name != teacher:
            continue

        entries = list(g.entries)
        if student:
            needle = student.lower()
            entries = [e for e in entries if needle in e.student_name.lower()]
        if min_score is not None:
            entries = [e for e in entries if e.total_score >= min_score]
        if last_name_from or last_name_to:
            entries = [
                e for e in entries
                if last_name_in_range(e.student_name, last_name_from, last_name_to)
            ]

        has_entry_filters = bool(student or min_score is not None or last_name_from or last_name_to)
        if entries or not has_entry_filters:
            filtered_groups.append(
                GradebookGroup(
                    group_name=g.group_name,
                    group_id=g.group_id,
                    teacher_name=g.teacher_name,
                    task_titles=list(g.task_titles),
                    max_scores=dict(g.max_scores),
                    entries=entries,
                )
            )

    return Gradebook(course_id=gradebook.course_id, groups=filtered_groups)
