from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class LoadSessionRequest(BaseModel):
    session_file: str


class SaveSessionRequest(BaseModel):
    session_file: str


class DBSyncRequest(BaseModel):
    course_id: int
    db_file: str = "./queue_db.json"
    course_title: str = ""
    filter_task: str = ""
    filter_reviewer: str = ""
    filter_status: str = ""
    last_name_from: str = ""
    last_name_to: str = ""
    deep: bool = False


class DBPullRequest(BaseModel):
    db_file: str = "./queue_db.json"
    course_id: int | None = None
    limit: int | None = None
    student_contains: str = ""
    task_contains: str = ""
    status_contains: str = ""
    reviewer_contains: str = ""
    last_name_from: str = ""
    last_name_to: str = ""
    issue_id: int | None = None
    name_list: list[str] = []


class DBMarkPulledRequest(BaseModel):
    db_file: str = "./queue_db.json"
    course_id: int
    student_key: str
    assignment_key: str


class DBMarkProcessedRequest(BaseModel):
    db_file: str = "./queue_db.json"
    course_id: int
    student_key: str
    assignment_key: str


class DBWriteRequest(BaseModel):
    db_file: str = "./queue_db.json"
    course_id: int
    issue_id: int
    action: str
    value: str
    author: str = ""
    note: str = ""


class TaskSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CourseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    title: str = ""
    teachers: list[str] = []
    tasks: list[TaskSchema] = []


class ProfileCourseEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    title: str
    role: str


class QueueEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class FileAttachmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    download_url: str
    is_notebook: bool = False


class CommentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    author_name: str
    author_url: str
    timestamp: datetime | None
    content_html: str
    files: list[FileAttachmentSchema] = []
    links: list[str] = []
    is_after_deadline: bool = False
    is_system_event: bool = False


class SubmissionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    issue_id: int
    issue_url: str = ""
    task_title: str
    student_name: str = ""
    student_url: str = ""
    reviewer_name: str = ""
    reviewer_url: str = ""
    status: str = ""
    grade: str = ""
    max_score: str = ""
    deadline: str = ""
    comments: list[CommentSchema] = []


class ReviewQueueSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    entries: list[QueueEntrySchema] = []
    submissions: dict[str, SubmissionSchema] = {}


class GradebookEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_name: str
    student_url: str
    scores: dict[str, float] = {}
    statuses: dict[str, str] = {}
    issue_urls: dict[str, str] = {}
    total_score: float = 0.0


class GradebookGroupSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_name: str
    group_id: int
    teacher_name: str = ""
    task_titles: list[str] = []
    max_scores: dict[str, float] = {}
    entries: list[GradebookEntrySchema] = []


class GradebookSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    groups: list[GradebookGroupSchema] = []


class OkResponse(BaseModel):
    ok: bool = True


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str


class HealthResponse(BaseModel):
    status: str
    version: str


class DBSyncResponse(BaseModel):
    newly_flagged: int
    total_entries: int


DBEntry = dict[str, Any]


class SetGradeRequest(BaseModel):
    grade: float
    comment: str = ""


class SetStatusRequest(BaseModel):
    status: str
    comment: str = ""


class AddCommentRequest(BaseModel):
    comment: str


class WriteResultSchema(BaseModel):
    success: bool
    action: str
    issue_id: int
    value: str
    message: str = ""
