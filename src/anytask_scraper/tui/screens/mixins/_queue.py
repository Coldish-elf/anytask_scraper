from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import httpx
from textual import on, work
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Label

from anytask_scraper.tui.widgets.filter_bar import QueueFilterBar

from ._helpers import _QUEUE_STATUS_COLORS, _parse_mark, _parse_update_time

if TYPE_CHECKING:
    from anytask_scraper.models import QueueEntry, Submission
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class QueueMixin:

    app: AnytaskApp

    _selected_course_id: int | None
    _queue_loaded_for: int | None
    all_queue_entries: list[QueueEntry]
    filtered_queue_entries: list[QueueEntry]
    _queue_sort_column: int | None
    _queue_sort_reverse: bool
    _queue_preview_submission: Submission | None
    is_teacher_view: bool

    _show_status: Any
    _table_cursor_index: Any
    _push_submission_screen: Any

    def _copy_queue_payload(self) -> tuple[str, str] | None:
        from anytask_scraper.tui.clipboard import format_queue_entry_for_clipboard

        if not self.filtered_queue_entries:
            return None
        table = self.query_one("#queue-table", DataTable)  # type: ignore[attr-defined]
        row_index = self._table_cursor_index(table, len(self.filtered_queue_entries))
        if row_index is None:
            return None
        entry = self.filtered_queue_entries[row_index]
        text = format_queue_entry_for_clipboard(entry)
        return ("queue entry", text)

    @on(QueueFilterBar.Changed)
    def _handle_queue_filter(self, event: QueueFilterBar.Changed) -> None:
        needle = event.text.lower()
        self.filtered_queue_entries = [
            e
            for e in self.all_queue_entries
            if (not needle or needle in e.student_name.lower() or needle in e.task_title.lower())
            and (not event.student or e.student_name == event.student)
            and (not event.task or e.task_title == event.task)
            and (not event.status or e.status_name == event.status)
            and (not event.reviewer or e.responsible_name == event.reviewer)
        ]
        self._rebuild_queue_table()

    def _update_queue_filter_options(self) -> None:
        students = sorted({e.student_name for e in self.all_queue_entries if e.student_name})
        tasks = sorted({e.task_title for e in self.all_queue_entries if e.task_title})
        statuses = sorted({e.status_name for e in self.all_queue_entries if e.status_name})
        reviewers = sorted(
            {e.responsible_name for e in self.all_queue_entries if e.responsible_name}
        )
        self.query_one("#queue-filter-bar", QueueFilterBar).update_options(  # type: ignore[attr-defined]
            students, tasks, statuses, reviewers
        )

    @on(DataTable.RowHighlighted, "#queue-table")
    def _queue_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is None:
            return
        issue_url = event.row_key.value
        entry = next(
            (e for e in self.all_queue_entries if e.issue_url == issue_url),
            None,
        )
        if entry and entry.has_issue_access and entry.issue_url:
            self._load_queue_preview(entry)
        elif entry:
            self._show_queue_preview_info(entry)

    @on(DataTable.RowSelected, "#queue-table")
    def _queue_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        issue_url = event.row_key.value
        entry = next(
            (e for e in self.all_queue_entries if e.issue_url == issue_url),
            None,
        )
        if entry and entry.has_issue_access and entry.issue_url:
            self._fetch_and_show_submission(entry)

    def _show_queue_preview_info(self, entry: QueueEntry) -> None:
        self._queue_preview_submission = None
        self._update_queue_action_bar()
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()
        scroll.mount(
            Label(
                f"[bold]{entry.task_title}[/bold]",
                classes="detail-heading",
            )
        )
        scroll.mount(Label(f"Student: {entry.student_name}", classes="detail-text"))
        scroll.mount(Label(f"Status: {entry.status_name}", classes="detail-text"))
        scroll.mount(
            Label(
                f"Reviewer: {entry.responsible_name or '-'}",
                classes="detail-text",
            )
        )
        scroll.mount(Label(f"Updated: {entry.update_time}", classes="detail-text"))
        scroll.mount(Label(f"Grade: {entry.mark or '-'}", classes="detail-text"))

    @work(thread=True)
    def _load_queue_preview(self, entry: QueueEntry) -> None:
        from anytask_scraper.parser import extract_issue_id_from_breadcrumb, parse_submission_page

        try:
            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(self._selected_course_id)
                if cache and entry.issue_url in cache.submissions:
                    sub = cache.submissions[entry.issue_url]
                    self.app.call_from_thread(self._render_queue_preview, sub)
                    return

            client = self.app.client
            if not client:
                return

            self.app.call_from_thread(self._show_queue_preview_loading, entry)

            html = client.fetch_submission_page(entry.issue_url)
            issue_id = extract_issue_id_from_breadcrumb(html)
            if issue_id == 0:
                self.app.call_from_thread(self._show_queue_preview_info, entry)
                return

            sub = parse_submission_page(html, issue_id, issue_url=entry.issue_url)

            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(self._selected_course_id)
                if cache:
                    cache.submissions[entry.issue_url] = sub

            self.app.call_from_thread(self._render_queue_preview, sub)
        except Exception:
            logger.debug("Failed to load queue preview", exc_info=True)
            self.app.call_from_thread(self._show_queue_preview_info, entry)

    def _show_queue_preview_loading(self, entry: QueueEntry) -> None:
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()
        scroll.mount(
            Label(
                f"[bold]{entry.task_title}[/bold]",
                classes="detail-heading",
            )
        )
        scroll.mount(Label(f"Student: {entry.student_name}", classes="detail-text"))
        scroll.mount(Label("[dim]Loading...[/dim]", classes="detail-text"))

    def _render_queue_preview(self, sub: Submission) -> None:
        from anytask_scraper.parser import strip_html

        self._queue_preview_submission = sub
        self._update_queue_action_bar()
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()

        scroll.mount(Label(f"[bold]{sub.task_title}[/bold]", classes="detail-heading"))
        scroll.mount(Label(f"Student: {sub.student_name}", classes="detail-text"))
        scroll.mount(
            Label(
                f"Reviewer: {sub.reviewer_name or '-'}",
                classes="detail-text",
            )
        )
        scroll.mount(
            Label(
                f"Status: {sub.status}  |  Grade: {sub.grade}/{sub.max_score}",
                classes="detail-text",
            )
        )
        if sub.deadline:
            scroll.mount(Label(f"Deadline: {sub.deadline}", classes="detail-text"))

        if sub.comments:
            scroll.mount(
                Label(
                    f"\n[bold]Comments ({len(sub.comments)})[/bold]",
                    classes="detail-heading",
                )
            )
            for comment in sub.comments:
                ts = comment.timestamp.strftime("%d.%m.%Y %H:%M") if comment.timestamp else "-"
                after = " [bold red](LATE)[/bold red]" if comment.is_after_deadline else ""
                scroll.mount(
                    Label(
                        f"[bold]{comment.author_name}[/bold] [dim]{ts}[/dim]{after}",
                        classes="detail-text",
                    )
                )
                if comment.content_html:
                    text = strip_html(comment.content_html)
                    if text:
                        if comment.is_system_event:
                            text = f"[italic]{text}[/italic]"
                        scroll.mount(Label(text, classes="detail-text"))
                if comment.files:
                    fnames = ", ".join(f.filename for f in comment.files)
                    scroll.mount(
                        Label(
                            f"[dim]Files: {fnames}[/dim]",
                            classes="detail-text",
                        )
                    )

        scroll.mount(
            Label(
                "\n[dim]Enter - full view[/dim]",
                classes="detail-text",
            )
        )

    def _update_queue_action_bar(self) -> None:
        bar = self.query_one("#queue-action-bar", Horizontal)  # type: ignore[attr-defined]
        if self.is_teacher_view and self._queue_preview_submission is not None:
            bar.remove_class("hidden")
        else:
            bar.add_class("hidden")

    def _clear_queue_detail(self) -> None:
        self._queue_preview_submission = None
        self._update_queue_action_bar()
        scroll = self.query_one("#queue-detail-scroll", VerticalScroll)  # type: ignore[attr-defined]
        scroll.remove_children()
        scroll.mount(Label("[dim]Select a queue entry[/dim]"))

    @on(Button.Pressed, "#queue-btn-rate")
    def _queue_rate_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        sub = self._queue_preview_submission
        if sub is None:
            return
        from anytask_scraper.tui.screens.submission import AcceptAndRateScreen

        max_score_value: float | None = None
        if sub.max_score:
            with suppress(ValueError):
                max_score_value = float(sub.max_score)
        issue_url = sub.issue_url
        self.app.push_screen(
            AcceptAndRateScreen(max_score=max_score_value),
            lambda result: self._queue_write_accept_and_rate(sub.issue_id, result, issue_url),
        )

    @on(Button.Pressed, "#queue-btn-grade")
    def _queue_grade_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        sub = self._queue_preview_submission
        if sub is None:
            return
        from anytask_scraper.tui.screens.submission import GradeInputScreen

        max_score_value: float | None = None
        if sub.max_score:
            with suppress(ValueError):
                max_score_value = float(sub.max_score)
        issue_url = sub.issue_url
        self.app.push_screen(
            GradeInputScreen(max_score=max_score_value),
            lambda value: self._queue_write_grade(sub.issue_id, value, issue_url),
        )

    @on(Button.Pressed, "#queue-btn-status")
    def _queue_status_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        sub = self._queue_preview_submission
        if sub is None:
            return
        from anytask_scraper.tui.screens.submission import StatusSelectScreen

        issue_url = sub.issue_url
        self.app.push_screen(
            StatusSelectScreen(),
            lambda code: self._queue_write_status(sub.issue_id, code, issue_url),
        )

    @on(Button.Pressed, "#queue-btn-comment")
    def _queue_comment_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        sub = self._queue_preview_submission
        if sub is None:
            return
        from anytask_scraper.tui.screens.submission import CommentInputScreen

        issue_url = sub.issue_url
        self.app.push_screen(
            CommentInputScreen(),
            lambda text: self._queue_write_comment(sub.issue_id, text, issue_url),
        )

    def _queue_write_accept_and_rate(
        self, issue_id: int, result: tuple[float, str] | None, issue_url: str = ""
    ) -> None:
        if result is not None:
            grade, comment = result
            self._do_queue_accept_and_rate(issue_id, grade, comment, issue_url)

    def _queue_write_grade(self, issue_id: int, value: float | None, issue_url: str = "") -> None:
        if value is not None:
            self._do_queue_write("grade", issue_id, grade=value, issue_url=issue_url)

    def _queue_write_status(self, issue_id: int, code: int | None, issue_url: str = "") -> None:
        if code is not None:
            self._do_queue_write("status", issue_id, status=code, issue_url=issue_url)

    def _queue_write_comment(self, issue_id: int, text: str | None, issue_url: str = "") -> None:
        if text is not None:
            self._do_queue_write("comment", issue_id, comment=text, issue_url=issue_url)

    @work(thread=True)
    def _do_queue_write(
        self,
        action: str,
        issue_id: int,
        *,
        grade: float | None = None,
        status: int | None = None,
        comment: str | None = None,
        issue_url: str = "",
    ) -> None:
        client = self.app.client
        if not client:
            return
        try:
            if action == "grade" and grade is not None:
                result = client.set_grade(issue_id, grade, issue_url=issue_url)
            elif action == "status" and status is not None:
                result = client.set_status(issue_id, status, issue_url=issue_url)
            elif action == "comment" and comment is not None:
                result = client.add_comment(issue_id, comment, issue_url=issue_url)
            else:
                return

            if result.success:
                self.app.call_from_thread(self._show_status, result.message, kind="success")
                self._invalidate_queue_submission_cache(issue_id)
            else:
                self.app.call_from_thread(self._show_status, result.message, kind="error")
        except Exception as e:
            self.app.call_from_thread(self._show_status, f"Write failed: {e}", kind="error")

    @work(thread=True)
    def _do_queue_accept_and_rate(
        self, issue_id: int, grade: float, comment: str, issue_url: str = ""
    ) -> None:
        client = self.app.client
        if not client:
            return
        errors: list[str] = []
        try:
            result = client.set_grade(issue_id, grade, issue_url=issue_url)
            if not result.success:
                errors.append(f"Grade: {result.message}")

            result = client.set_status(issue_id, 5, issue_url=issue_url)
            if not result.success:
                errors.append(f"Status: {result.message}")

            if comment:
                result = client.add_comment(issue_id, comment, issue_url=issue_url)
                if not result.success:
                    errors.append(f"Comment: {result.message}")

            self._invalidate_queue_submission_cache(issue_id)

            if errors:
                msg = "; ".join(errors)
                self.app.call_from_thread(self._show_status, msg, kind="error")
            else:
                self.app.call_from_thread(
                    self._show_status,
                    f"Accepted with grade {grade}",
                    kind="success",
                )
        except Exception as e:
            self.app.call_from_thread(self._show_status, f"Rate failed: {e}", kind="error")

    def _invalidate_queue_submission_cache(self, issue_id: int) -> None:
        if self._selected_course_id is None:
            return
        cache = self.app.queue_cache.get(self._selected_course_id)
        if not cache:
            return
        url_to_remove = None
        for url, sub in cache.submissions.items():
            if sub.issue_id == issue_id:
                url_to_remove = url
                break
        if url_to_remove:
            del cache.submissions[url_to_remove]
            self._queue_preview_submission = None

    @on(DataTable.HeaderSelected, "#queue-table")
    def _queue_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_idx = event.column_index
        if self._queue_sort_column == col_idx:
            self._queue_sort_reverse = not self._queue_sort_reverse
        else:
            self._queue_sort_column = col_idx
            self._queue_sort_reverse = False
        self._sort_and_rebuild_queue()

    def _sort_and_rebuild_queue(self) -> None:
        col = self._queue_sort_column
        if col is None:
            return
        key_map: dict[int, Any] = {
            0: lambda e: 0,
            1: lambda e: e.student_name.lower(),
            2: lambda e: e.task_title.lower(),
            3: lambda e: e.status_name.lower(),
            4: lambda e: e.responsible_name.lower(),
            5: lambda e: _parse_update_time(e.update_time),
            6: lambda e: _parse_mark(e.mark),
        }
        key_fn = key_map.get(col)
        if key_fn:
            self.filtered_queue_entries.sort(key=key_fn, reverse=self._queue_sort_reverse)
            self._rebuild_queue_table()

    def _rebuild_queue_table(self) -> None:
        table = self.query_one("#queue-table", DataTable)  # type: ignore[attr-defined]
        table.clear(columns=True)

        base_columns = (
            "#",
            "Student",
            "Task",
            "Status",
            "Reviewer",
            "Updated",
            "Grade",
        )
        labels = []
        for i, col in enumerate(base_columns):
            if self._queue_sort_column == i:
                indicator = "▼" if self._queue_sort_reverse else "▲"
                labels.append(f"{col} {indicator}")
            else:
                labels.append(col)
        table.add_columns(*labels)

        from rich.text import Text

        for idx, entry in enumerate(self.filtered_queue_entries, 1):
            style = _QUEUE_STATUS_COLORS.get(entry.status_color, "")
            table.add_row(
                str(idx),
                entry.student_name,
                entry.task_title,
                Text(entry.status_name, style=style),
                entry.responsible_name,
                entry.update_time,
                entry.mark,
                key=entry.issue_url or str(idx),
            )

    def _maybe_load_queue(self) -> None:
        self._enable_queue_tab()
        if self._selected_course_id is None:
            return
        if not self.is_teacher_view:
            self.query_one("#queue-info-label", Label).update(  # type: ignore[attr-defined]
                "Queue available for teacher courses only"
            )
            return
        if self._queue_loaded_for == self._selected_course_id:
            return

        cache = self.app.queue_cache
        if self._selected_course_id in cache:
            queue = cache[self._selected_course_id]
            self.all_queue_entries = list(queue.entries)
            self.filtered_queue_entries = list(queue.entries)
            self._queue_loaded_for = self._selected_course_id
            self._update_queue_filter_options()
            self._rebuild_queue_table()
            self.query_one("#queue-info-label", Label).update(f"{len(queue.entries)} entries")  # type: ignore[attr-defined]
            return

        self.query_one("#queue-info-label", Label).update("Loading queue...")  # type: ignore[attr-defined]
        self._fetch_queue(self._selected_course_id)

    @work(thread=True)
    def _fetch_queue(self, course_id: int) -> None:
        from anytask_scraper.models import QueueEntry, ReviewQueue
        from anytask_scraper.parser import extract_csrf_from_queue_page

        try:
            client = self.app.client
            if not client:
                self.app.call_from_thread(self._show_status, "No client", kind="error")
                return

            queue_html = client.fetch_queue_page(course_id)
            csrf = extract_csrf_from_queue_page(queue_html)

            raw = client.fetch_all_queue_entries(course_id, csrf)
            entries = [
                QueueEntry(
                    student_name=str(r.get("student_name", "")),
                    student_url=str(r.get("student_url", "")),
                    task_title=str(r.get("task_title", "")),
                    update_time=str(r.get("update_time", "")),
                    mark=str(r.get("mark", "")),
                    status_color=str(r.get("status_color", "default")),
                    status_name=str(r.get("status_name", "")),
                    responsible_name=str(r.get("responsible_name", "")),
                    responsible_url=str(r.get("responsible_url", "")),
                    has_issue_access=bool(r.get("has_issue_access", False)),
                    issue_url=str(r.get("issue_url", "")),
                )
                for r in raw
            ]

            queue = ReviewQueue(course_id=course_id, entries=entries)
            self.app.queue_cache[course_id] = queue

            self.all_queue_entries = entries
            self.filtered_queue_entries = list(entries)
            self._queue_loaded_for = course_id

            self.app.call_from_thread(self._update_queue_filter_options)
            self.app.call_from_thread(self._rebuild_queue_table)
            self.app.call_from_thread(self._update_queue_info, f"{len(entries)} entries")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                self.app.call_from_thread(self._disable_queue_tab)
                self.app.call_from_thread(self._update_queue_info, "No permission to view queue")
            else:
                self.app.call_from_thread(
                    self._show_status,
                    f"Queue error: HTTP {e.response.status_code}",
                    kind="error",
                )
                self.app.call_from_thread(
                    self._update_queue_info, f"Error: HTTP {e.response.status_code}"
                )
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Queue error: {e}",
                kind="error",
            )
            self.app.call_from_thread(self._update_queue_info, f"Error: {e}")

    def _update_queue_info(self, text: str) -> None:
        self.query_one("#queue-info-label", Label).update(text)  # type: ignore[attr-defined]

    def _disable_queue_tab(self) -> None:
        self.query_one("#queue-filter-bar", QueueFilterBar).disabled = True  # type: ignore[attr-defined]
        self.query_one("#queue-table", DataTable).disabled = True  # type: ignore[attr-defined]
        self.query_one("#queue-info-label", Label).update("No permission to view queue")  # type: ignore[attr-defined]

    def _enable_queue_tab(self) -> None:
        self.query_one("#queue-filter-bar", QueueFilterBar).disabled = False  # type: ignore[attr-defined]
        self.query_one("#queue-table", DataTable).disabled = False  # type: ignore[attr-defined]

    @work(thread=True)
    def _fetch_and_show_submission(self, entry: QueueEntry) -> None:
        from anytask_scraper.parser import extract_issue_id_from_breadcrumb, parse_submission_page

        try:
            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(self._selected_course_id)
                if cache and entry.issue_url in cache.submissions:
                    sub = cache.submissions[entry.issue_url]
                    self.app.call_from_thread(self._push_submission_screen, sub)
                    return

            client = self.app.client
            if not client:
                return

            html = client.fetch_submission_page(entry.issue_url)
            issue_id = extract_issue_id_from_breadcrumb(html)
            if issue_id == 0:
                self.app.call_from_thread(
                    self._show_status,
                    "Could not find issue ID",
                    kind="warning",
                )
                return

            sub = parse_submission_page(html, issue_id, issue_url=entry.issue_url)

            if self._selected_course_id is not None:
                cache = self.app.queue_cache.get(self._selected_course_id)
                if cache:
                    cache.submissions[entry.issue_url] = sub

            self.app.call_from_thread(self._push_submission_screen, sub)
        except Exception as e:
            self.app.call_from_thread(
                self._show_status,
                f"Submission error: {e}",
                kind="error",
            )
