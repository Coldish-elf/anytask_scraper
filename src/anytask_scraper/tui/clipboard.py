"""Clipboard helpers for TUI copy actions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable

from rich.text import Text

from anytask_scraper.models import QueueEntry, Submission, Task
from anytask_scraper.parser import strip_html

_CopyFn = Callable[[str], None]


def to_plain_text(value: object) -> str:
    """Convert rich/textual values to plain strings."""
    if isinstance(value, Text):
        return value.plain
    if value is None:
        return ""
    return str(value)


def rich_markup_to_plain(text: str) -> str:
    """Strip Rich markup tags from text when present."""
    if "[" not in text:
        return text
    if "[/" not in text and "[bold" not in text and "[dim" not in text:
        return text
    try:
        return Text.from_markup(text).plain
    except Exception:
        return text


def format_course_for_clipboard(course_id: int, title: str) -> str:
    """Format a course summary."""
    return f"Course ID: {course_id}\nTitle: {title}"


def format_task_for_clipboard(task: Task, *, teacher_view: bool) -> str:
    """Format task details for clipboard."""
    lines = [f"Task: {task.title}"]
    if teacher_view:
        lines.append(f"Section: {task.section or '-'}")
        lines.append(f"Max score: {task.max_score if task.max_score is not None else '-'}")
    else:
        if task.score is not None and task.max_score is not None:
            score = f"{task.score}/{task.max_score}"
        elif task.score is not None:
            score = str(task.score)
        else:
            score = "-"
        lines.append(f"Score: {score}")
        lines.append(f"Status: {task.status or '-'}")

    if task.deadline is not None:
        lines.append(f"Deadline: {task.deadline.strftime('%H:%M %d.%m.%Y')}")

    if task.description:
        lines.append("")
        lines.append("Description:")
        lines.append(strip_html(task.description))

    return "\n".join(lines).strip()


def format_queue_entry_for_clipboard(entry: QueueEntry) -> str:
    """Format queue entry details for clipboard."""
    lines = [
        f"Student: {entry.student_name}",
        f"Task: {entry.task_title}",
        f"Status: {entry.status_name}",
        f"Reviewer: {entry.responsible_name or '-'}",
        f"Updated: {entry.update_time}",
        f"Grade: {entry.mark or '-'}",
    ]
    if entry.issue_url:
        lines.append(f"Issue URL: {entry.issue_url}")
    return "\n".join(lines)


def format_submission_for_clipboard(submission: Submission) -> str:
    """Format full submission details for clipboard."""
    lines = [
        f"Issue ID: {submission.issue_id}",
        f"Task: {submission.task_title}",
        f"Student: {submission.student_name}",
        f"Reviewer: {submission.reviewer_name or '-'}",
        f"Status: {submission.status}",
        f"Grade: {submission.grade}/{submission.max_score}",
    ]
    if submission.deadline:
        lines.append(f"Deadline: {submission.deadline}")

    lines.append("")
    lines.append(f"Comments: {len(submission.comments)}")
    for index, comment in enumerate(submission.comments, 1):
        stamp = comment.timestamp.strftime("%d.%m.%Y %H:%M") if comment.timestamp else "-"
        late = " (LATE)" if comment.is_after_deadline else ""
        lines.append("")
        lines.append(f"[{index}] {comment.author_name} | {stamp}{late}")

        body = strip_html(comment.content_html).strip() if comment.content_html else ""
        if body:
            lines.append(body)
        if comment.files:
            files = ", ".join(file.filename for file in comment.files)
            lines.append(f"Files: {files}")
        if comment.links:
            links = ", ".join(comment.links)
            lines.append(f"Links: {links}")

    return "\n".join(lines).strip()


def format_table_row_for_clipboard(headers: list[str], values: list[object]) -> str:
    """Format a table row as key-value lines."""
    pairs: list[str] = []
    for index, raw_value in enumerate(values):
        if index >= len(headers):
            break
        key = headers[index].strip()
        value = to_plain_text(raw_value).strip()
        if key:
            pairs.append(f"{key}: {value}")
    return "\n".join(pairs)


def normalize_table_header(label: object) -> str:
    """Normalize headers by stripping sort arrows and padding."""
    text = to_plain_text(label).strip()
    if text.endswith("▲") or text.endswith("▼"):
        text = text[:-1].rstrip()
    return text


def copy_text_to_clipboard(text: str, *, app: object | None = None) -> tuple[bool, str]:
    """Copy text to clipboard with native command fallbacks across platforms.

    Returns:
        (success, method_name)
    """
    for method_name, copy_fn in _iter_clipboard_methods(app):
        try:
            copy_fn(text)
        except Exception:
            continue
        return True, method_name
    return False, ""


def _iter_clipboard_methods(app: object | None) -> list[tuple[str, _CopyFn]]:
    methods: list[tuple[str, _CopyFn]] = []

    if sys.platform == "darwin":
        if _command_exists("pbcopy"):
            methods.append(("pbcopy", _command_copier(["pbcopy"])))
    elif sys.platform.startswith("win"):
        if _command_exists("powershell"):
            methods.append(
                (
                    "powershell",
                    _command_copier(
                        [
                            "powershell",
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                        ]
                    ),
                )
            )
        if _command_exists("pwsh"):
            methods.append(
                (
                    "pwsh",
                    _command_copier(
                        [
                            "pwsh",
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                        ]
                    ),
                )
            )
        if _command_exists("clip"):
            methods.append(("clip", _command_copier(["clip"])))
    else:
        if _command_exists("wl-copy"):
            methods.append(("wl-copy", _command_copier(["wl-copy"])))
        if _command_exists("xclip"):
            methods.append(("xclip", _command_copier(["xclip", "-selection", "clipboard"])))
        if _command_exists("xsel"):
            methods.append(("xsel", _command_copier(["xsel", "--clipboard", "--input"])))
        if _command_exists("termux-clipboard-set"):
            methods.append(("termux-clipboard-set", _command_copier(["termux-clipboard-set"])))

    osc52_copy = getattr(app, "copy_to_clipboard", None) if app is not None else None
    if callable(osc52_copy):
        methods.append(("osc52", osc52_copy))

    return methods


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _command_copier(command: list[str]) -> _CopyFn:
    def _copy(value: str) -> None:
        _run_command(command, value)

    return _copy


def _run_command(command: list[str], text: str) -> None:
    subprocess.run(
        command,
        input=text,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
