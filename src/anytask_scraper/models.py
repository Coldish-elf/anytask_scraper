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


def parse_name_list(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in text.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _name_prefix_match(name_cf: str, entry_cf: str) -> bool:
    if not name_cf.startswith(entry_cf):
        return False
    return len(name_cf) == len(entry_cf) or name_cf[len(entry_cf)] == " "


def name_matches_list(name: str, name_list: list[str]) -> bool:
    if not name_list:
        return True
    cf = name.casefold()
    return any(_name_prefix_match(cf, entry.casefold()) for entry in name_list)


def check_name_list_matches(
    student_names: list[str],
    name_list: list[str],
) -> tuple[list[str], list[str]]:
    if not name_list:
        return [], []
    matched: list[str] = []
    unmatched: list[str] = []
    for entry in name_list:
        entry_cf = entry.casefold()
        if any(_name_prefix_match(sn.casefold(), entry_cf) for sn in student_names):
            matched.append(entry)
        else:
            unmatched.append(entry)
    return matched, unmatched


@dataclass
class Task:
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
    course_id: int
    title: str = ""
    teachers: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)


@dataclass
class ProfileCourseEntry:
    course_id: int
    title: str
    role: str


@dataclass
class QueueEntry:
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
    filename: str
    download_url: str
    is_notebook: bool = False


@dataclass
class Comment:
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
    issue_url: str = ""
    current_status: int = 0
    status_options: list[tuple[int, str]] = field(default_factory=list)
    has_grade_form: bool = False
    has_status_form: bool = False
    has_comment_form: bool = False
    comments: list[Comment] = field(default_factory=list)


@dataclass
class QueueFilters:
    students: list[tuple[str, str]] = field(default_factory=list)
    tasks: list[tuple[str, str]] = field(default_factory=list)
    reviewers: list[tuple[str, str]] = field(default_factory=list)
    statuses: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ReviewQueue:
    course_id: int
    entries: list[QueueEntry] = field(default_factory=list)
    submissions: dict[str, Submission] = field(default_factory=dict)


@dataclass
class GradebookEntry:
    student_name: str
    student_url: str
    scores: dict[str, float] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    issue_urls: dict[str, str] = field(default_factory=dict)
    total_score: float = 0.0


@dataclass
class GradebookGroup:
    group_name: str
    group_id: int
    teacher_name: str = ""
    task_titles: list[str] = field(default_factory=list)
    max_scores: dict[str, float] = field(default_factory=dict)
    entries: list[GradebookEntry] = field(default_factory=list)


@dataclass
class Gradebook:
    course_id: int
    groups: list[GradebookGroup] = field(default_factory=list)


@dataclass
class SubmissionForms:
    csrf_token: str = ""
    max_score: float | None = None
    current_status: int = 0
    status_options: list[tuple[int, str]] = field(default_factory=list)
    issue_id: int = 0
    has_grade_form: bool = False
    has_status_form: bool = False
    has_comment_form: bool = False
    page_url: str = ""


@dataclass
class WriteResult:
    success: bool
    action: str
    issue_id: int
    value: str
    message: str = ""


def filter_gradebook(
    gradebook: Gradebook,
    *,
    group: str = "",
    teacher: str = "",
    student: str = "",
    min_score: float | None = None,
    last_name_from: str = "",
    last_name_to: str = "",
    name_list: list[str] | None = None,
) -> Gradebook:
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
                e
                for e in entries
                if last_name_in_range(e.student_name, last_name_from, last_name_to)
            ]
        if name_list:
            entries = [e for e in entries if name_matches_list(e.student_name, name_list)]

        has_entry_filters = bool(
            student or min_score is not None or last_name_from or last_name_to or name_list
        )
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
