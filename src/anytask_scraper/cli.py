"""CLI for anytask-scraper."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from anytask_scraper._logging import setup_logging
from anytask_scraper.client import AnytaskClient, LoginError
from anytask_scraper.display import (
    display_course,
    display_gradebook,
    display_queue,
    display_submission,
)
from anytask_scraper.models import QueueEntry, ReviewQueue
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    parse_course_page,
    parse_gradebook_page,
    parse_profile_page,
    parse_submission_page,
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
)

console = Console()
err_console = Console(stderr=True)

DEFAULT_SETTINGS_FILE = ".anytask_scraper_settings.json"
INIT_DEFAULTS: dict[str, Any] = {
    "credentials_file": "./credentials.json",
    "session_file": "./.anytask_session.json",
    "status_mode": "errors",
    "default_output": "./output",
    "save_session": True,
    "refresh_session": False,
    "auto_login_session": True,
}
SETTINGS_KEYS = (
    "credentials_file",
    "session_file",
    "status_mode",
    "default_output",
    "save_session",
    "refresh_session",
    "auto_login_session",
    "debug",
)

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", "-u", help="Anytask username")
    parser.add_argument("--password", "-p", help="Anytask password")
    parser.add_argument(
        "--credentials-file",
        help="Path to credentials file (json or key=value text)",
    )
    parser.add_argument(
        "--session-file",
        help="Path to persistent session file (cookies)",
    )
    parser.add_argument(
        "--status-mode",
        choices=["all", "errors"],
        default=None,
        help="Show all statuses or only errors",
    )
    parser.add_argument(
        "--default-output",
        help="Default output directory for course/queue commands",
    )
    parser.add_argument(
        "--save-session",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Save session file at the end",
    )
    parser.add_argument(
        "--refresh-session",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Ignore saved session and force re-login",
    )
    parser.add_argument(
        "--settings-file",
        default=DEFAULT_SETTINGS_FILE,
        help=f"Path to settings file (default: {DEFAULT_SETTINGS_FILE})",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        default=None,
        help="Enable debug logging output",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Write log output to file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("tui", help="Launch interactive TUI")

    discover_p = subparsers.add_parser("discover", help="Discover courses from user profile")
    discover_p.add_argument(
        "--role",
        choices=["all", "student", "teacher"],
        default="all",
        help="Filter by role (default: all)",
    )
    discover_p.add_argument(
        "--student-only",
        action="store_true",
        help="Show only courses where you are a student but not a teacher",
    )

    course_p = subparsers.add_parser("course", help="Scrape course tasks")
    course_p.add_argument("--course", "-c", type=int, nargs="+", required=True, help="Course ID(s)")
    course_p.add_argument(
        "--output",
        "-o",
        help="Output directory (default: --default-output or '.')",
    )
    course_p.add_argument(
        "--filename",
        help="Custom output filename (with or without extension)",
    )
    course_p.add_argument(
        "--format",
        "-f",
        choices=["json", "markdown", "csv", "table"],
        default="json",
        help="Output format (default: json). 'table' displays only, no file saved.",
    )
    course_p.add_argument(
        "--show",
        action="store_true",
        help="Print a rich table to terminal after saving",
    )
    course_p.add_argument(
        "--fetch-descriptions",
        action="store_true",
        help="Fetch task descriptions for teacher view (requires extra requests)",
    )
    course_p.add_argument(
        "--include-columns",
        nargs="+",
        default=None,
        help="Only include these columns in export",
    )
    course_p.add_argument(
        "--exclude-columns",
        nargs="+",
        default=None,
        help="Exclude these columns from export",
    )

    queue_p = subparsers.add_parser("queue", help="Scrape review queue")
    queue_p.add_argument("--course", "-c", type=int, required=True, help="Course ID")
    queue_p.add_argument(
        "--output",
        "-o",
        help="Output directory (default: --default-output or '.')",
    )
    queue_p.add_argument(
        "--filename",
        help="Custom output filename (with or without extension)",
    )
    queue_p.add_argument(
        "--format",
        "-f",
        choices=["json", "markdown", "csv", "table"],
        default="json",
        help="Output format (default: json). 'table' displays only, no file saved.",
    )
    queue_p.add_argument(
        "--show",
        action="store_true",
        help="Print a rich table to terminal after saving",
    )
    queue_p.add_argument(
        "--deep",
        action="store_true",
        help="Fetch full submission details for each queue entry",
    )
    queue_p.add_argument(
        "--download-files",
        action="store_true",
        help="Download files from submissions (implies --deep)",
    )
    queue_p.add_argument("--filter-task", help="Filter by task title (substring match)")
    queue_p.add_argument("--filter-reviewer", help="Filter by reviewer name (substring match)")
    queue_p.add_argument("--filter-status", help="Filter by status name (substring match)")
    queue_p.add_argument(
        "--last-name-from",
        default="",
        help="Keep only students whose last name >= this value (alphabetical, case-insensitive)",
    )
    queue_p.add_argument(
        "--last-name-to",
        default="",
        help="Keep only students whose last name <= this value (prefix-inclusive)",
    )
    queue_p.add_argument(
        "--include-columns",
        nargs="+",
        default=None,
        help="Only include these columns in export",
    )
    queue_p.add_argument(
        "--exclude-columns",
        nargs="+",
        default=None,
        help="Exclude these columns from export",
    )

    gradebook_p = subparsers.add_parser("gradebook", help="Scrape gradebook")
    gradebook_p.add_argument("--course", "-c", type=int, required=True, help="Course ID")
    gradebook_p.add_argument(
        "--output",
        "-o",
        help="Output directory (default: --default-output or '.')",
    )
    gradebook_p.add_argument(
        "--filename",
        help="Custom output filename (with or without extension)",
    )
    gradebook_p.add_argument(
        "--format",
        "-f",
        choices=["json", "markdown", "csv", "table"],
        default="json",
        help="Output format (default: json). 'table' displays only, no file saved.",
    )
    gradebook_p.add_argument(
        "--show",
        action="store_true",
        help="Print a rich table to terminal after saving",
    )
    gradebook_p.add_argument(
        "--filter-group",
        default="",
        help="Filter by group name (substring, case-insensitive)",
    )
    gradebook_p.add_argument(
        "--filter-student",
        default="",
        help="Filter by student name (substring, case-insensitive)",
    )
    gradebook_p.add_argument(
        "--filter-teacher",
        default="",
        help="Filter by teacher name (exact match)",
    )
    gradebook_p.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Keep only students with total score >= this value",
    )
    gradebook_p.add_argument(
        "--last-name-from",
        default="",
        help="Keep only students whose last name >= this value (alphabetical, case-insensitive)",
    )
    gradebook_p.add_argument(
        "--last-name-to",
        default="",
        help="Keep only students whose last name <= this value (prefix-inclusive)",
    )
    gradebook_p.add_argument(
        "--include-columns",
        nargs="+",
        default=None,
        help="Only include these columns in export",
    )
    gradebook_p.add_argument(
        "--exclude-columns",
        nargs="+",
        default=None,
        help="Exclude these columns from export",
    )

    settings_p = subparsers.add_parser("settings", help="Manage saved defaults")
    settings_sub = settings_p.add_subparsers(dest="settings_action", required=True)

    settings_sub.add_parser("init", help="Write recommended default settings")
    settings_sub.add_parser("show", help="Show saved settings")

    set_p = settings_sub.add_parser("set", help="Set one or more settings")
    set_p.add_argument("--credentials-file", dest="set_credentials_file")
    set_p.add_argument("--session-file", dest="set_session_file")
    set_p.add_argument("--status-mode", dest="set_status_mode", choices=["all", "errors"])
    set_p.add_argument("--default-output", dest="set_default_output")
    set_p.add_argument(
        "--save-session",
        dest="set_save_session",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    set_p.add_argument(
        "--refresh-session",
        dest="set_refresh_session",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    set_p.add_argument(
        "--auto-login-session",
        dest="set_auto_login_session",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    set_p.add_argument(
        "--debug",
        dest="set_debug",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    clear_p = settings_sub.add_parser("clear", help="Clear settings")
    clear_p.add_argument(
        "keys",
        nargs="*",
        choices=list(SETTINGS_KEYS),
        help="Keys to clear. Empty list clears all",
    )

    return parser


def _load_credentials_file(path: str) -> tuple[str, str]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8").strip()

    if file_path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Credentials JSON must be an object")
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        return username, password

    username = ""
    password = ""
    fallback: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            fallback.append(line)
            continue

        key = key.strip().lower()
        value = value.strip()

        if key in {"username", "user", "login"}:
            username = value
        elif key in {"password", "pass"}:
            password = value

    if (not username or not password) and len(fallback) >= 2:
        username = username or fallback[0].strip()
        password = password or fallback[1].strip()

    return username, password


def _load_settings(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Settings file must be a JSON object")

    settings: dict[str, Any] = {}
    for key in SETTINGS_KEYS:
        if key in raw:
            settings[key] = raw[key]
    return settings


def _save_settings(path: str, settings: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: settings[k] for k in SETTINGS_KEYS if k in settings}
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_credentials_stub(path: str) -> bool:
    """Create credentials file stub if it doesn't exist."""
    file_path = Path(path)
    if file_path.exists():
        return False
    file_path.parent.mkdir(parents=True, exist_ok=True)
    stub = {"username": "your_username", "password": "your_password"}
    file_path.write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def _merge_runtime_settings(args: argparse.Namespace, settings: dict[str, Any]) -> None:
    for key in SETTINGS_KEYS:
        current = getattr(args, key, None)
        if current is None and key in settings:
            setattr(args, key, settings[key])

    if args.status_mode is None:
        args.status_mode = "all"
    if args.save_session is None:
        args.save_session = True
    if args.refresh_session is None:
        args.refresh_session = False


def _resolve_credentials(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[str, str]:
    file_username = ""
    file_password = ""

    if args.credentials_file:
        try:
            file_username, file_password = _load_credentials_file(args.credentials_file)
        except Exception as e:
            parser.error(f"Could not read credentials file: {e}")

    username = args.username or file_username
    password = args.password or file_password

    if username and not password:
        parser.error("Password is missing")
    if password and not username:
        parser.error("Username is missing")

    if not args.session_file and (not username or not password):
        parser.error(
            "Credentials required: use --username/--password or --credentials-file. "
            "If you only want saved session auth, pass --session-file"
        )

    return username, password


def _resolve_output_dir(args: argparse.Namespace) -> str:
    output = getattr(args, "output", None)
    if output:
        return str(output)
    if args.default_output:
        return str(args.default_output)
    return "."


def _run_discover(args: argparse.Namespace, client: AnytaskClient) -> None:
    with console.status("[bold blue]Fetching profile..."):
        html = client.fetch_profile_page()
        entries = parse_profile_page(html)

    if args.student_only:
        teacher_ids = {e.course_id for e in entries if e.role == "teacher"}
        entries = [e for e in entries if e.role == "student" and e.course_id not in teacher_ids]
    elif args.role != "all":
        entries = [e for e in entries if e.role == args.role]

    if not entries:
        console.print("[yellow]No courses found[/yellow]")
        return

    _print_ok(args, f"Found {len(entries)} course(s)")
    for entry in entries:
        role_tag = "[blue]teacher[/blue]" if entry.role == "teacher" else "[green]student[/green]"
        console.print(f"  {role_tag}  [bold]{entry.course_id}[/bold]  {entry.title}")


def _print_ok(args: argparse.Namespace, message: str) -> None:
    if args.status_mode == "all":
        console.print(f"[green][OK][/green] {message}")


def _run_settings(args: argparse.Namespace) -> None:
    try:
        settings = _load_settings(args.settings_file)
    except Exception as e:
        err_console.print(f"[bold red]Settings error:[/bold red] {e}")
        sys.exit(1)

    if args.settings_action == "init":
        defaults = dict(INIT_DEFAULTS)
        _save_settings(args.settings_file, defaults)
        credentials_file = str(defaults.get("credentials_file", "./credentials.json"))
        created = _ensure_credentials_stub(credentials_file)
        console.print(f"[green][OK][/green] Initialized settings -> {args.settings_file}")
        if created:
            console.print(f"[green][OK][/green] Created credentials stub -> {credentials_file}")
        else:
            console.print(
                f"[blue][INFO][/blue] Credentials file already exists -> {credentials_file}"
            )
        return

    if args.settings_action == "show":
        if settings:
            console.print_json(data=settings)
        else:
            console.print("{}")
        return

    if args.settings_action == "set":
        updates = {
            "credentials_file": args.set_credentials_file,
            "session_file": args.set_session_file,
            "status_mode": args.set_status_mode,
            "default_output": args.set_default_output,
            "save_session": args.set_save_session,
            "refresh_session": args.set_refresh_session,
            "auto_login_session": args.set_auto_login_session,
            "debug": args.set_debug,
        }
        changed = False
        for key, value in updates.items():
            if value is None:
                continue
            settings[key] = value
            changed = True

        if not changed:
            err_console.print("[bold red]Error:[/bold red] Nothing to update")
            sys.exit(1)

        _save_settings(args.settings_file, settings)
        console.print(f"[green][OK][/green] Saved settings -> {args.settings_file}")
        return

    if args.settings_action == "clear":
        keys = list(args.keys)
        if keys:
            for key in keys:
                settings.pop(key, None)
        else:
            settings = {}
        _save_settings(args.settings_file, settings)
        console.print(f"[green][OK][/green] Updated settings -> {args.settings_file}")
        return


def _run_course(args: argparse.Namespace, client: AnytaskClient) -> None:
    output_dir = _resolve_output_dir(args)
    if args.filename and len(args.course) > 1:
        raise ValueError("--filename can only be used with a single --course value")

    for course_id in args.course:
        with console.status(f"[bold blue]Fetching course {course_id}..."):
            html = client.fetch_course_page(course_id)
            course = parse_course_page(html, course_id)

        if args.fetch_descriptions:
            tasks_needing_desc = [t for t in course.tasks if not t.description and t.edit_url]
            if tasks_needing_desc:
                with console.status(
                    f"[bold blue]Fetching {len(tasks_needing_desc)} task descriptions..."
                ):
                    for task in tasks_needing_desc:
                        try:
                            task.description = client.fetch_task_description(task.task_id)
                        except Exception as e:
                            err_console.print(
                                f"[yellow]Warning:[/yellow] "
                                f"Could not fetch description for '{task.title}': {e}"
                            )

        if args.format == "table":
            display_course(course, console)
        elif args.format == "json":
            path = save_course_json(course, output_dir, filename=args.filename)
            _print_ok(
                args,
                f"Course {course_id} ([bold]{course.title}[/bold]): "
                f"{len(course.tasks)} tasks -> {path}",
            )
        elif args.format == "markdown":
            path = save_course_markdown(course, output_dir, filename=args.filename)
            _print_ok(
                args,
                f"Course {course_id} ([bold]{course.title}[/bold]): "
                f"{len(course.tasks)} tasks -> {path}",
            )
        elif args.format == "csv":
            columns = None
            if args.include_columns:
                columns = args.include_columns
            elif args.exclude_columns:
                has_sections = any(t.section for t in course.tasks)
                if has_sections:
                    all_cols = ["#", "Title", "Section", "Max Score", "Deadline"]
                else:
                    all_cols = ["#", "Title", "Score", "Status", "Deadline"]
                columns = [c for c in all_cols if c not in args.exclude_columns]
            path = save_course_csv(course, output_dir, columns=columns, filename=args.filename)
            _print_ok(
                args,
                f"Course {course_id} ([bold]{course.title}[/bold]): "
                f"{len(course.tasks)} tasks -> {path}",
            )

        if args.show and args.format != "table":
            display_course(course, console)


def _parse_ajax_entry(row: dict[str, object]) -> QueueEntry:
    """Convert AJAX row to ``QueueEntry``."""
    return QueueEntry(
        student_name=str(row.get("student_name", "")),
        student_url=str(row.get("student_url", "")),
        task_title=str(row.get("task_title", "")),
        update_time=str(row.get("update_time", "")),
        mark=str(row.get("mark", "")),
        status_color=str(row.get("status_color", "")),
        status_name=str(row.get("status_name", "")),
        responsible_name=str(row.get("responsible_name", "")),
        responsible_url=str(row.get("responsible_url", "")),
        has_issue_access=bool(row.get("has_issue_access", False)),
        issue_url=str(row.get("issue_url", "")),
    )


def _run_queue(args: argparse.Namespace, client: AnytaskClient) -> None:
    course_id = args.course
    output_dir = _resolve_output_dir(args)

    if args.download_files:
        args.deep = True

    with console.status("[bold blue]Fetching queue page..."):
        queue_html = client.fetch_queue_page(course_id)
        csrf = extract_csrf_from_queue_page(queue_html)
        if not csrf:
            err_console.print("[bold red]Error:[/bold red] Could not extract CSRF token")
            sys.exit(1)

    with console.status("[bold blue]Fetching queue entries..."):
        raw_entries = client.fetch_all_queue_entries(course_id, csrf)

    entries = [_parse_ajax_entry(row) for row in raw_entries]

    if args.filter_task:
        needle = args.filter_task.lower()
        entries = [e for e in entries if needle in e.task_title.lower()]
    if args.filter_reviewer:
        needle = args.filter_reviewer.lower()
        entries = [e for e in entries if needle in e.responsible_name.lower()]
    if args.filter_status:
        needle = args.filter_status.lower()
        entries = [e for e in entries if needle in e.status_name.lower()]
    if args.last_name_from or args.last_name_to:
        from anytask_scraper.models import last_name_in_range
        entries = [
            e for e in entries
            if last_name_in_range(e.student_name, args.last_name_from, args.last_name_to)
        ]

    queue = ReviewQueue(course_id=course_id, entries=entries)

    _print_ok(
        args,
        f"Queue: {len(entries)} entries"
        + (f" (filtered from {len(raw_entries)})" if len(entries) != len(raw_entries) else ""),
    )

    if args.deep:
        accessible = [e for e in entries if e.has_issue_access and e.issue_url]
        with console.status(f"[bold blue]Fetching {len(accessible)} submissions..."):
            for entry in accessible:
                try:
                    sub_html = client.fetch_submission_page(entry.issue_url)
                    issue_id = extract_issue_id_from_breadcrumb(sub_html)
                    if issue_id == 0:
                        continue
                    sub = parse_submission_page(sub_html, issue_id)
                    queue.submissions[entry.issue_url] = sub
                except Exception as e:
                    err_console.print(
                        f"[yellow]Warning:[/yellow] Could not fetch {entry.issue_url}: {e}"
                    )
        _print_ok(args, f"Fetched {len(queue.submissions)} submissions")

    if args.download_files:
        total = 0
        with console.status("[bold blue]Downloading files..."):
            for sub in queue.submissions.values():
                downloaded = download_submission_files(client, sub, output_dir)
                total += len(downloaded)
        _print_ok(args, f"Downloaded {total} files -> {output_dir}")

    if args.format == "table":
        display_queue(queue, console)
        if queue.submissions:
            for sub in queue.submissions.values():
                display_submission(sub, console)
    elif args.format == "json":
        path = save_queue_json(queue, output_dir, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")
    elif args.format == "markdown":
        path = save_queue_markdown(queue, output_dir, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")
    elif args.format == "csv":
        columns = None
        if args.include_columns:
            columns = args.include_columns
        elif args.exclude_columns:
            all_cols = ["#", "Student", "Task", "Status", "Reviewer", "Updated", "Grade"]
            columns = [c for c in all_cols if c not in args.exclude_columns]
        path = save_queue_csv(queue, output_dir, columns=columns, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")
        if queue.submissions:
            sub_path = save_submissions_csv(queue.submissions, course_id, output_dir)
            _print_ok(args, f"Saved submissions -> {sub_path}")

    if args.show and args.format != "table":
        display_queue(queue, console)
        if queue.submissions:
            for sub in queue.submissions.values():
                display_submission(sub, console)


def _run_gradebook(args: argparse.Namespace, client: AnytaskClient) -> None:
    from anytask_scraper.models import filter_gradebook

    course_id = args.course
    output_dir = _resolve_output_dir(args)

    with console.status(f"[bold blue]Fetching gradebook for course {course_id}..."):
        html = client.fetch_gradebook_page(course_id)
        gradebook = parse_gradebook_page(html, course_id)

    gradebook = filter_gradebook(
        gradebook,
        group=args.filter_group,
        teacher=args.filter_teacher,
        student=args.filter_student,
        min_score=args.min_score,
        last_name_from=args.last_name_from,
        last_name_to=args.last_name_to,
    )

    total_entries = sum(len(g.entries) for g in gradebook.groups)
    _print_ok(
        args,
        f"Gradebook: {len(gradebook.groups)} group(s), {total_entries} students",
    )

    if args.format == "table":
        display_gradebook(gradebook, console)
    elif args.format == "json":
        path = save_gradebook_json(gradebook, output_dir, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")
    elif args.format == "markdown":
        path = save_gradebook_markdown(gradebook, output_dir, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")
    elif args.format == "csv":
        columns = None
        if args.include_columns:
            columns = args.include_columns
        elif args.exclude_columns:
            all_cols = ["Group", "Student"]
            for g in gradebook.groups:
                for t in g.task_titles:
                    if t not in all_cols:
                        all_cols.append(t)
            all_cols.append("Total")
            columns = [c for c in all_cols if c not in args.exclude_columns]
        path = save_gradebook_csv(gradebook, output_dir, columns=columns, filename=args.filename)
        _print_ok(args, f"Saved -> {path}")

    if args.show and args.format != "table":
        display_gradebook(gradebook, console)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "settings":
        _run_settings(args)
        return

    try:
        settings = _load_settings(args.settings_file)
    except Exception as e:
        err_console.print(f"[bold red]Settings error:[/bold red] {e}")
        sys.exit(1)

    debug = args.debug if args.debug is not None else settings.get("debug", False)
    log_level = logging.DEBUG if debug else logging.WARNING
    setup_logging(level=log_level, log_file=args.log_file)

    if args.command == "tui":
        from anytask_scraper.tui import run

        run(debug=debug)
        return

    try:
        _merge_runtime_settings(args, settings)
    except Exception as e:
        err_console.print(f"[bold red]Settings error:[/bold red] {e}")
        sys.exit(1)

    username, password = _resolve_credentials(args, parser)

    try:
        with AnytaskClient(username, password) as client:
            session_loaded = False
            if args.session_file and not args.refresh_session:
                with console.status("[bold blue]Loading saved session..."):
                    session_loaded = client.load_session(args.session_file)
                if session_loaded:
                    _print_ok(args, f"Loaded session from {args.session_file}")

            if not session_loaded:
                with console.status("[bold blue]Logging in..."):
                    try:
                        client.login()
                    except LoginError as e:
                        err_console.print(f"[bold red]Login failed:[/bold red] {e}")
                        sys.exit(1)

            if args.command == "course":
                _run_course(args, client)
            elif args.command == "discover":
                _run_discover(args, client)
            elif args.command == "gradebook":
                _run_gradebook(args, client)
            elif args.command == "queue":
                _run_queue(args, client)

            if args.session_file and args.save_session:
                client.save_session(args.session_file)
                _print_ok(args, f"Session saved to {args.session_file}")

    except LoginError as e:
        err_console.print(f"[bold red]Auth error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
