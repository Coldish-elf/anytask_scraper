"""Persistence helpers."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from anytask_scraper.models import Course, Gradebook, ReviewQueue, Submission, Task
from anytask_scraper.parser import format_student_folder, strip_html

logger = logging.getLogger(__name__)


def _resolve_output_path(
    output_dir: Path | str,
    default_filename: str,
    filename: str | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if filename is None:
        return output / default_filename

    requested = filename.strip()
    if not requested:
        return output / default_filename

    safe_name = Path(requested).name
    if not safe_name:
        raise ValueError("filename must not be empty")

    suffix = Path(default_filename).suffix
    if suffix and not Path(safe_name).suffix:
        safe_name = f"{safe_name}{suffix}"
    return output / safe_name


def save_course_json(
    course: Course,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save course to JSON."""
    path = _resolve_output_path(output_dir, f"course_{course.course_id}.json", filename)
    if columns is None:
        payload: dict[str, Any] = asdict(course)
    else:
        included = set(columns)
        tasks_payload: list[dict[str, Any]] = []
        for i, task in enumerate(course.tasks, 1):
            item: dict[str, Any] = {}
            if "#" in included:
                item["#"] = i
            if "Title" in included:
                item["title"] = task.title
            if "Section" in included:
                item["section"] = task.section
            if "Score" in included:
                item["score"] = task.score
            if "Max Score" in included:
                item["max_score"] = task.max_score
            if "Status" in included:
                item["status"] = task.status
            if "Deadline" in included:
                item["deadline"] = (
                    task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else None
                )
            tasks_payload.append(item)
        payload = {
            "course_id": course.course_id,
            "title": course.title,
            "teachers": list(course.teachers),
            "tasks": tasks_payload,
        }
    path.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    logger.info("Saved course JSON -> %s", path)
    return path


def save_course_markdown(
    course: Course,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save course to Markdown."""
    path = _resolve_output_path(output_dir, f"course_{course.course_id}.md", filename)

    lines: list[str] = []
    lines.append(f"# {course.title}")
    lines.append("")
    if course.teachers:
        lines.append(f"**Teachers:** {', '.join(course.teachers)}")
        lines.append("")

    if columns is not None:
        has_sections = any(t.section for t in course.tasks)
        all_columns = (
            ["#", "Title", "Section", "Max Score", "Deadline"]
            if has_sections
            else ["#", "Title", "Score", "Status", "Deadline"]
        )
        selected = [c for c in all_columns if c in columns]
        if selected:
            lines.append("| " + " | ".join(selected) + " |")
            lines.append("|" + "|".join(["---"] * len(selected)) + "|")
            for i, task in enumerate(course.tasks, 1):
                row_data = {
                    "#": str(i),
                    "Title": task.title,
                    "Section": task.section or "",
                    "Max Score": str(task.max_score) if task.max_score is not None else "",
                    "Score": str(task.score) if task.score is not None else "",
                    "Status": task.status,
                    "Deadline": task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "",
                }
                lines.append("| " + " | ".join(row_data[c] for c in selected) + " |")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Saved course Markdown -> %s", path)
        return path

    has_sections = any(t.section for t in course.tasks)

    if has_sections:
        _md_teacher_tasks(course.tasks, lines)
    else:
        _md_student_tasks(course.tasks, lines)

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved course Markdown -> %s", path)
    return path


def _md_deadline(task: Task) -> str:
    if task.deadline is None:
        return "-"
    return task.deadline.strftime("%H:%M %d-%m-%Y")


def _md_student_tasks(tasks: list[Task], lines: list[str]) -> None:
    lines.append("| # | Title | Score | Status | Deadline |")
    lines.append("|---|-------|------:|--------|----------|")
    for i, task in enumerate(tasks, 1):
        score = str(task.score) if task.score is not None else "-"
        lines.append(f"| {i} | {task.title} | {score} | {task.status} | {_md_deadline(task)} |")

    lines.append("")
    for task in tasks:
        if task.description:
            lines.append(f"### {task.title}")
            lines.append("")
            lines.append(strip_html(task.description))
            lines.append("")


def _md_teacher_tasks(tasks: list[Task], lines: list[str]) -> None:
    sections: dict[str, list[Task]] = {}
    for task in tasks:
        sections.setdefault(task.section or "Unsorted", []).append(task)

    for section_name, section_tasks in sections.items():
        lines.append(f"## {section_name}")
        lines.append("")
        lines.append("| # | Title | Max Score | Deadline |")
        lines.append("|---|-------|----------:|----------|")
        for i, task in enumerate(section_tasks, 1):
            max_score = str(task.max_score) if task.max_score is not None else "-"
            lines.append(f"| {i} | {task.title} | {max_score} | {_md_deadline(task)} |")
        lines.append("")


def save_queue_json(
    queue: ReviewQueue,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save queue to JSON."""
    path = _resolve_output_path(output_dir, f"queue_{queue.course_id}.json", filename)
    if columns is None:
        payload: dict[str, Any] = asdict(queue)
    else:
        included = set(columns)
        entries_payload: list[dict[str, Any]] = []
        for i, entry in enumerate(queue.entries, 1):
            item: dict[str, Any] = {}
            if "#" in included:
                item["#"] = i
            if "Student" in included:
                item["student"] = entry.student_name
            if "Task" in included:
                item["task"] = entry.task_title
            if "Status" in included:
                item["status"] = entry.status_name
            if "Reviewer" in included:
                item["reviewer"] = entry.responsible_name
            if "Updated" in included:
                item["updated"] = entry.update_time
            if "Grade" in included:
                item["grade"] = entry.mark
            entries_payload.append(item)
        payload = {"course_id": queue.course_id, "entries": entries_payload}
    path.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    logger.info("Saved queue JSON -> %s", path)
    return path


def save_queue_markdown(
    queue: ReviewQueue,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save queue to Markdown."""
    path = _resolve_output_path(output_dir, f"queue_{queue.course_id}.md", filename)

    lines: list[str] = []
    lines.append(f"# Review Queue - Course {queue.course_id}")
    lines.append("")

    if columns is not None:
        all_columns = ["#", "Student", "Task", "Status", "Reviewer", "Updated", "Grade"]
        selected = [c for c in all_columns if c in columns]
        if selected:
            lines.append("| " + " | ".join(selected) + " |")
            lines.append("|" + "|".join(["---"] * len(selected)) + "|")
            for i, e in enumerate(queue.entries, 1):
                row_data = {
                    "#": str(i),
                    "Student": e.student_name,
                    "Task": e.task_title,
                    "Status": e.status_name,
                    "Reviewer": e.responsible_name,
                    "Updated": e.update_time,
                    "Grade": e.mark,
                }
                lines.append("| " + " | ".join(row_data[c] for c in selected) + " |")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Saved queue Markdown -> %s", path)
        return path

    if queue.entries:
        lines.append("| # | Student | Task | Status | Reviewer | Updated | Grade |")
        lines.append("|---|---------|------|--------|----------|---------|-------|")
        for i, e in enumerate(queue.entries, 1):
            lines.append(
                f"| {i} | {e.student_name} | {e.task_title} | "
                f"{e.status_name} | {e.responsible_name} | {e.update_time} | {e.mark} |"
            )
        lines.append("")

    if queue.submissions:
        lines.append("## Submissions")
        lines.append("")
        for _url, sub in queue.submissions.items():
            lines.append(f"### Issue {sub.issue_id}: {sub.task_title}")
            lines.append(f"**Student:** {sub.student_name}  ")
            lines.append(f"**Reviewer:** {sub.reviewer_name or '-'}  ")
            lines.append(f"**Status:** {sub.status}  ")
            lines.append(f"**Grade:** {sub.grade}/{sub.max_score}  ")
            lines.append(f"**Deadline:** {sub.deadline}")
            lines.append("")
            for j, c in enumerate(sub.comments, 1):
                ts = str(c.timestamp) if c.timestamp else "-"
                after = " [AFTER DEADLINE]" if c.is_after_deadline else ""
                lines.append(f"**{j}. {c.author_name}** ({ts}){after}")
                if c.content_html:
                    lines.append(f"> {strip_html(c.content_html)}")
                if c.files:
                    for f in c.files:
                        lines.append(f"  - File: {f.filename}")
                if c.links:
                    for link in c.links:
                        lines.append(f"  - Link: {link}")
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved queue Markdown -> %s", path)
    return path


def save_course_csv(
    course: Course,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save course tasks to CSV."""
    path = _resolve_output_path(output_dir, f"course_{course.course_id}.csv", filename)

    has_sections = any(t.section for t in course.tasks)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if has_sections:
            all_columns = ["#", "Title", "Section", "Max Score", "Deadline"]
            if columns is not None:
                filtered_columns = [c for c in all_columns if c in columns]
            else:
                filtered_columns = all_columns

            writer.writerow(filtered_columns)
            for i, task in enumerate(course.tasks, 1):
                row_data = {
                    "#": i,
                    "Title": task.title,
                    "Section": task.section,
                    "Max Score": str(task.max_score) if task.max_score is not None else "",
                    "Deadline": task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "",
                }
                writer.writerow([row_data[c] for c in filtered_columns])
        else:
            all_columns = ["#", "Title", "Score", "Status", "Deadline"]
            if columns is not None:
                filtered_columns = [c for c in all_columns if c in columns]
            else:
                filtered_columns = all_columns

            writer.writerow(filtered_columns)
            for i, task in enumerate(course.tasks, 1):
                row_data = {
                    "#": i,
                    "Title": task.title,
                    "Score": str(task.score) if task.score is not None else "",
                    "Status": task.status,
                    "Deadline": task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "",
                }
                writer.writerow([row_data[c] for c in filtered_columns])
    logger.info("Saved course CSV -> %s", path)
    return path


def save_queue_csv(
    queue: ReviewQueue,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save queue entries to CSV."""
    path = _resolve_output_path(output_dir, f"queue_{queue.course_id}.csv", filename)

    all_columns = ["#", "Student", "Task", "Status", "Reviewer", "Updated", "Grade"]
    if columns is not None:
        filtered_columns = [c for c in all_columns if c in columns]
    else:
        filtered_columns = all_columns

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(filtered_columns)
        for i, e in enumerate(queue.entries, 1):
            row_data = {
                "#": i,
                "Student": e.student_name,
                "Task": e.task_title,
                "Status": e.status_name,
                "Reviewer": e.responsible_name,
                "Updated": e.update_time,
                "Grade": e.mark,
            }
            writer.writerow([row_data[c] for c in filtered_columns])
    logger.info("Saved queue CSV -> %s", path)
    return path


def save_submissions_csv(
    submissions: dict[str, Submission] | list[Submission],
    course_id: int,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save submissions detail to CSV."""
    path = _resolve_output_path(output_dir, f"submissions_{course_id}.csv", filename)

    subs = submissions.values() if isinstance(submissions, dict) else submissions

    all_columns = [
        "Issue ID",
        "Task",
        "Student",
        "Reviewer",
        "Status",
        "Grade",
        "Max Score",
        "Deadline",
        "Comments",
    ]

    if columns is not None:
        filtered_columns = [c for c in all_columns if c in columns]
    else:
        filtered_columns = all_columns

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(filtered_columns)
        for sub in subs:
            row_data = {
                "Issue ID": sub.issue_id,
                "Task": sub.task_title,
                "Student": sub.student_name,
                "Reviewer": sub.reviewer_name,
                "Status": sub.status,
                "Grade": sub.grade,
                "Max Score": sub.max_score,
                "Deadline": sub.deadline,
                "Comments": len(sub.comments),
            }
            writer.writerow([row_data[c] for c in filtered_columns])
    logger.info("Saved submissions CSV -> %s", path)
    return path


def save_submissions_json(
    submissions: dict[str, Submission] | list[Submission],
    course_id: int,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save submissions detail to JSON."""
    path = _resolve_output_path(output_dir, f"submissions_{course_id}.json", filename)
    subs = submissions.values() if isinstance(submissions, dict) else submissions
    included = set(columns) if columns is not None else None

    items: list[dict[str, Any]] = []
    for sub in subs:
        item: dict[str, Any] = {}
        if included is None or "Issue ID" in included:
            item["issue_id"] = sub.issue_id
        if included is None or "Task" in included:
            item["task"] = sub.task_title
        if included is None or "Student" in included:
            item["student"] = sub.student_name
        if included is None or "Reviewer" in included:
            item["reviewer"] = sub.reviewer_name
        if included is None or "Status" in included:
            item["status"] = sub.status
        if included is None or "Grade" in included:
            item["grade"] = sub.grade
        if included is None or "Max Score" in included:
            item["max_score"] = sub.max_score
        if included is None or "Deadline" in included:
            item["deadline"] = str(sub.deadline) if sub.deadline is not None else None
        if included is None or "Comments" in included:
            item["comments"] = len(sub.comments)
        items.append(item)

    path.write_text(
        json.dumps({"course_id": course_id, "submissions": items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved submissions JSON -> %s", path)
    return path


def save_submissions_markdown(
    submissions: dict[str, Submission] | list[Submission],
    course_id: int,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save submissions detail to Markdown."""
    path = _resolve_output_path(output_dir, f"submissions_{course_id}.md", filename)
    subs = submissions.values() if isinstance(submissions, dict) else submissions

    all_columns = [
        "Issue ID",
        "Task",
        "Student",
        "Reviewer",
        "Status",
        "Grade",
        "Max Score",
        "Deadline",
        "Comments",
    ]
    selected = all_columns if columns is None else [c for c in all_columns if c in columns]

    lines: list[str] = [f"# Submissions - Course {course_id}", ""]
    if selected:
        lines.append("| " + " | ".join(selected) + " |")
        lines.append("|" + "|".join(["---"] * len(selected)) + "|")
        for sub in subs:
            row_data = {
                "Issue ID": str(sub.issue_id),
                "Task": sub.task_title,
                "Student": sub.student_name,
                "Reviewer": sub.reviewer_name or "",
                "Status": sub.status,
                "Grade": sub.grade,
                "Max Score": sub.max_score,
                "Deadline": str(sub.deadline) if sub.deadline is not None else "",
                "Comments": str(len(sub.comments)),
            }
            lines.append("| " + " | ".join(str(row_data[c]) for c in selected) + " |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved submissions Markdown -> %s", path)
    return path


def download_submission_files(
    client: object,
    submission: Submission,
    base_dir: Path | str,
) -> dict[str, Path]:
    """Download files from submission comments."""
    from anytask_scraper.client import AnytaskClient

    assert isinstance(client, AnytaskClient)
    base_dir = Path(base_dir)
    folder_name = (
        format_student_folder(submission.student_name)
        if submission.student_name
        else str(submission.issue_id)
    )
    student_dir = base_dir / folder_name
    student_dir.mkdir(parents=True, exist_ok=True)

    downloaded: dict[str, Path] = {}
    logger.debug("Downloading files for submission %d to %s", submission.issue_id, student_dir)

    for comment in submission.comments:
        for file_att in comment.files:
            dest = student_dir / file_att.filename
            result = client.download_file(file_att.download_url, str(dest))
            if result.success:
                downloaded[file_att.filename] = dest
            else:
                logger.debug("Download failed: %s (%s)", file_att.filename, result.reason)

        for link in comment.links:
            if "colab.research.google.com" not in link:
                continue
            nb_name = f"colab_{submission.issue_id}.ipynb"
            dest = student_dir / nb_name
            result = client.download_colab_notebook(link, str(dest))
            if result.success:
                downloaded[link] = dest
            else:
                url_file = student_dir / f"colab_{submission.issue_id}.url.txt"
                url_file.write_text(link)
                downloaded[link] = url_file

    return downloaded


def save_gradebook_json(
    gradebook: Gradebook,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save gradebook to JSON."""
    path = _resolve_output_path(output_dir, f"gradebook_{gradebook.course_id}.json", filename)
    if columns is None:
        payload: dict[str, Any] = asdict(gradebook)
    else:
        included = set(columns)
        all_tasks: list[str] = []
        for group in gradebook.groups:
            for task in group.task_titles:
                if task not in all_tasks:
                    all_tasks.append(task)

        entries_payload: list[dict[str, Any]] = []
        for group in gradebook.groups:
            for entry in group.entries:
                row: dict[str, Any] = {}
                if "Group" in included:
                    row["group"] = group.group_name
                if "Student" in included:
                    row["student"] = entry.student_name
                for task in all_tasks:
                    if task in included:
                        row[task] = entry.scores.get(task)
                if "Total" in included:
                    row["total"] = entry.total_score
                entries_payload.append(row)
        payload = {"course_id": gradebook.course_id, "entries": entries_payload}
    path.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    logger.info("Saved gradebook JSON -> %s", path)
    return path


def save_gradebook_markdown(
    gradebook: Gradebook,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save gradebook to Markdown."""
    path = _resolve_output_path(output_dir, f"gradebook_{gradebook.course_id}.md", filename)

    lines: list[str] = []
    lines.append(f"# Gradebook - Course {gradebook.course_id}")
    lines.append("")

    if columns is not None:
        all_tasks: list[str] = []
        for group in gradebook.groups:
            for task in group.task_titles:
                if task not in all_tasks:
                    all_tasks.append(task)
        all_columns = ["Group", "Student"] + all_tasks + ["Total"]
        selected = [c for c in all_columns if c in columns]
        if selected:
            lines.append("| " + " | ".join(selected) + " |")
            lines.append("|" + "|".join(["---"] * len(selected)) + "|")
            for group in gradebook.groups:
                for entry in group.entries:
                    row_data: dict[str, str] = {
                        "Group": group.group_name,
                        "Student": entry.student_name,
                        "Total": str(entry.total_score),
                    }
                    for task in all_tasks:
                        row_data[task] = str(entry.scores.get(task, ""))
                    lines.append("| " + " | ".join(row_data[c] for c in selected) + " |")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Saved gradebook Markdown -> %s", path)
        return path

    for group in gradebook.groups:
        teacher_info = f" ({group.teacher_name})" if group.teacher_name else ""
        lines.append(f"## {group.group_name}{teacher_info}")
        lines.append("")

        header = "| # | Student | " + " | ".join(group.task_titles) + " | Total |"
        sep = "|---|---------|" + "|".join(["------:" for _ in group.task_titles]) + "|------:|"
        lines.append(header)
        lines.append(sep)

        for i, entry in enumerate(group.entries, 1):
            scores_str = " | ".join(str(entry.scores.get(t, "-")) for t in group.task_titles)
            lines.append(f"| {i} | {entry.student_name} | {scores_str} | {entry.total_score} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved gradebook Markdown -> %s", path)
    return path


def save_gradebook_csv(
    gradebook: Gradebook,
    output_dir: Path | str = ".",
    columns: list[str] | None = None,
    filename: str | None = None,
) -> Path:
    """Save gradebook to CSV."""
    path = _resolve_output_path(output_dir, f"gradebook_{gradebook.course_id}.csv", filename)

    all_tasks: list[str] = []
    for group in gradebook.groups:
        for t in group.task_titles:
            if t not in all_tasks:
                all_tasks.append(t)

    all_columns = ["Group", "Student"] + all_tasks + ["Total"]

    if columns is not None:
        filtered_columns = [c for c in all_columns if c in columns]
    else:
        filtered_columns = all_columns

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(filtered_columns)
        for group in gradebook.groups:
            for entry in group.entries:
                row_data = {
                    "Group": group.group_name,
                    "Student": entry.student_name,
                    "Total": str(entry.total_score),
                }
                for t in all_tasks:
                    row_data[t] = str(entry.scores.get(t, ""))

                writer.writerow([row_data[c] for c in filtered_columns])
    logger.info("Saved gradebook CSV -> %s", path)
    return path
