from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from anytask_scraper._logging import setup_logging
from anytask_scraper.client import AnytaskClient, DownloadResult, LoginError
from anytask_scraper.json_db import QueueJsonDB
from anytask_scraper.models import (
    Comment,
    Course,
    FileAttachment,
    Gradebook,
    GradebookEntry,
    GradebookGroup,
    ProfileCourseEntry,
    QueueEntry,
    QueueFilters,
    ReviewQueue,
    Submission,
    Task,
    filter_gradebook,
)
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    format_student_folder,
    parse_course_page,
    parse_gradebook_page,
    parse_profile_page,
    parse_queue_filters,
    parse_submission_page,
    parse_task_edit_page,
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

if TYPE_CHECKING:
    from anytask_scraper.display import (
        display_course as display_course,
    )
    from anytask_scraper.display import (
        display_gradebook as display_gradebook,
    )
    from anytask_scraper.display import (
        display_queue as display_queue,
    )
    from anytask_scraper.display import (
        display_submission as display_submission,
    )
    from anytask_scraper.display import (
        display_task_detail as display_task_detail,
    )

try:
    __version__ = version("anytask-scraper")
except PackageNotFoundError:
    __version__ = "0.0.0"


def __getattr__(name: str) -> object:
    _display_names = {
        "display_course",
        "display_gradebook",
        "display_queue",
        "display_submission",
        "display_task_detail",
    }
    if name in _display_names:
        from anytask_scraper import display as _display

        return getattr(_display, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AnytaskClient",
    "Comment",
    "Course",
    "DownloadResult",
    "FileAttachment",
    "Gradebook",
    "GradebookEntry",
    "GradebookGroup",
    "LoginError",
    "ProfileCourseEntry",
    "QueueEntry",
    "QueueFilters",
    "QueueJsonDB",
    "ReviewQueue",
    "Submission",
    "Task",
    "display_course",
    "display_gradebook",
    "display_queue",
    "display_submission",
    "display_task_detail",
    "download_submission_files",
    "extract_csrf_from_queue_page",
    "extract_issue_id_from_breadcrumb",
    "filter_gradebook",
    "format_student_folder",
    "parse_course_page",
    "parse_gradebook_page",
    "parse_profile_page",
    "parse_queue_filters",
    "parse_submission_page",
    "parse_task_edit_page",
    "save_course_csv",
    "save_course_json",
    "save_course_markdown",
    "save_gradebook_csv",
    "save_gradebook_json",
    "save_gradebook_markdown",
    "save_queue_csv",
    "save_queue_json",
    "save_queue_markdown",
    "save_submissions_csv",
    "save_submissions_json",
    "save_submissions_markdown",
    "setup_logging",
    "strip_html",
    "__version__",
]
