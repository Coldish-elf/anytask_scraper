from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Static, TextArea

from anytask_scraper.models import Submission
from anytask_scraper.parser import (
    extract_issue_id_from_breadcrumb,
    parse_submission_page,
    strip_html,
)
from anytask_scraper.tui.clipboard import copy_text_to_clipboard, format_submission_for_clipboard
from anytask_scraper.tui.screens.mixins._helpers import resolve_accept_status_code

if TYPE_CHECKING:
    from anytask_scraper.tui.app import AnytaskApp


class GradeInputScreen(ModalScreen[float | None]):
    def __init__(self, max_score: float | None = None) -> None:
        super().__init__()
        self.max_score = max_score

    def compose(self) -> ComposeResult:
        with Vertical(id="grade-modal"):
            yield Label(f"Enter grade (max: {self.max_score or '?'}):")
            yield Input(placeholder="e.g. 10.5", id="grade-input")
            with Horizontal(id="grade-modal-buttons"):
                yield Button("Submit", variant="primary", id="grade-submit")
                yield Button("Cancel", id="grade-cancel")

    def on_mount(self) -> None:
        self.query_one("#grade-input", Input).focus()

    @on(Button.Pressed, "#grade-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    @on(Button.Pressed, "#grade-submit")
    def _submit(self, event: Button.Pressed) -> None:
        event.stop()
        input_widget = self.query_one("#grade-input", Input)
        try:
            value = float(input_widget.value)
            self.dismiss(value)
        except ValueError:
            self.notify("Invalid number", severity="error")


class StatusSelectScreen(ModalScreen[int | None]):
    def __init__(
        self,
        status_options: list[tuple[int, str]],
        current_status: int = 0,
    ) -> None:
        super().__init__()
        self.status_options = list(status_options)
        self.current_status = current_status

    def compose(self) -> ComposeResult:
        with Vertical(id="status-modal"):
            yield Label("Select status:")
            with RadioSet(id="status-set"):
                for code, label in self.status_options:
                    yield RadioButton(
                        f"{label} ({code})",
                        id=f"status-{code}",
                        value=(code == self.current_status),
                    )
            with Horizontal(id="status-modal-buttons"):
                yield Button("Submit", variant="primary", id="status-submit")
                yield Button("Cancel", id="status-cancel")

    @on(Button.Pressed, "#status-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    @on(Button.Pressed, "#status-submit")
    def _submit(self, event: Button.Pressed) -> None:
        event.stop()
        radio_set = self.query_one("#status-set", RadioSet)
        btn = radio_set.pressed_button
        if btn and btn.id:
            code = int(btn.id.split("-")[1])
            self.dismiss(code)
        else:
            self.notify("Please select a status", severity="error")


class CommentInputScreen(ModalScreen[str | None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="comment-modal"):
            yield Label("Enter comment:")
            yield TextArea(id="comment-input")
            with Horizontal(id="comment-modal-buttons"):
                yield Button("Submit", variant="primary", id="comment-submit")
                yield Button("Cancel", id="comment-cancel")

    def on_mount(self) -> None:
        self.query_one("#comment-input", TextArea).focus()

    @on(Button.Pressed, "#comment-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    @on(Button.Pressed, "#comment-submit")
    def _submit(self, event: Button.Pressed) -> None:
        event.stop()
        text_area = self.query_one("#comment-input", TextArea)
        value = text_area.text.strip()
        if value:
            self.dismiss(value)
        else:
            self.notify("Comment cannot be empty", severity="error")


class AcceptAndRateScreen(ModalScreen[tuple[float, str] | None]):
    def __init__(self, max_score: float | None = None) -> None:
        super().__init__()
        self.max_score = max_score

    def compose(self) -> ComposeResult:
        with Vertical(id="rate-modal"):
            yield Label(f"[bold]Accept & Rate[/bold]  (max: {self.max_score or '?'})")
            yield Label("Grade:")
            yield Input(placeholder="e.g. 10.5", id="rate-grade-input")
            yield Label("Comment (optional):")
            yield TextArea(id="rate-comment-input")
            with Horizontal(id="rate-modal-buttons"):
                yield Button("Rate", variant="success", id="rate-submit")
                yield Button("Cancel", id="rate-cancel")

    def on_mount(self) -> None:
        self.query_one("#rate-grade-input", Input).focus()

    @on(Button.Pressed, "#rate-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    @on(Button.Pressed, "#rate-submit")
    def _submit(self, event: Button.Pressed) -> None:
        event.stop()
        grade_input = self.query_one("#rate-grade-input", Input)
        comment_area = self.query_one("#rate-comment-input", TextArea)
        try:
            grade = float(grade_input.value)
        except ValueError:
            self.notify("Invalid grade number", severity="error")
            return
        comment = comment_area.text.strip()
        self.dismiss((grade, comment))


class SubmissionScreen(Screen[None]):
    app: AnytaskApp

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+y", "copy_submission", "Copy", show=True),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
    ]

    def __init__(
        self,
        submission: Submission,
        *,
        teacher_mode: bool = False,
        on_submission_refreshed: Callable[[Submission], None] | None = None,
    ) -> None:
        super().__init__()
        self.submission = submission
        self.teacher_mode = teacher_mode
        self._action_menu_open = False
        self._on_submission_refreshed = on_submission_refreshed

    def compose(self) -> ComposeResult:
        sub = self.submission
        can_rate = self._can_accept_and_rate()

        yield Static(
            f"Issue {sub.issue_id}: {sub.task_title}",
            id="sub-header",
        )

        with Vertical(id="sub-metadata"):
            yield Label(
                f"Student: [bold]{sub.student_name}[/bold]",
                classes="meta-line",
            )
            yield Label(
                f"Reviewer: [bold]{sub.reviewer_name or '-'}[/bold]",
                classes="meta-line",
            )
            status_line = (
                f"Status: {sub.status}  |  Grade: {sub.grade}/{sub.max_score}"
                f"  |  Deadline: {sub.deadline}"
            )
            yield Label(status_line, classes="meta-line")

        with VerticalScroll(id="sub-scroll"):
            if not sub.comments:
                yield Label("No comments", classes="no-comments")
            else:
                yield Label(
                    f"[bold]Comments ({len(sub.comments)})[/bold]",
                    classes="detail-heading",
                )
                for comment in sub.comments:
                    card = Container(classes="comment-card")
                    if comment.is_after_deadline:
                        card.add_class("-after-deadline")
                    if comment.is_system_event:
                        card.add_class("-system-event")

                    ts = comment.timestamp.strftime("%d.%m.%Y %H:%M") if comment.timestamp else "-"
                    after_tag = " [bold red](LATE)[/bold red]" if comment.is_after_deadline else ""

                    header_label = Label(
                        f"[bold]{comment.author_name}[/bold]  [dim]{ts}[/dim]{after_tag}",
                        classes="comment-header",
                    )
                    card.compose_add_child(header_label)

                    if comment.content_html:
                        text = strip_html(comment.content_html)
                        if text:
                            if comment.is_system_event:
                                text = f"[italic]{text}[/italic]"
                            card.compose_add_child(Label(text, classes="comment-body"))

                    if comment.files:
                        files_str = "\n".join(f"  {f.filename}" for f in comment.files)
                        card.compose_add_child(
                            Label(
                                f"[dim]Files:\n{files_str}[/dim]",
                                classes="comment-files",
                            )
                        )

                    if comment.links:
                        links_str = "\n".join(f"  {lnk}" for lnk in comment.links)
                        card.compose_add_child(
                            Label(
                                f"[dim]Links:\n{links_str}[/dim]",
                                classes="comment-links",
                            )
                        )

                    yield card

        if self.teacher_mode:
            with Horizontal(id="sub-action-bar"):
                yield Button(
                    "Accept & Rate",
                    variant="success",
                    id="sub-btn-rate",
                    disabled=not can_rate,
                )
                yield Button("Grade", id="sub-btn-grade", disabled=not sub.has_grade_form)
                yield Button("Status", id="sub-btn-status", disabled=not sub.has_status_form)
                yield Button("Comment", id="sub-btn-comment", disabled=not sub.has_comment_form)

        hints = "[dim]Esc[/dim] Back  [dim]Ctrl+Y[/dim] Copy  [dim]j/k[/dim] Scroll"
        if self.teacher_mode:
            hints += "  [dim]Tab[/dim] Actions"
        yield Static(hints, id="sub-key-bar")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 3:
            return
        event.prevent_default()
        event.stop()
        self._open_action_menu()

    def _open_action_menu(self) -> None:
        if self._action_menu_open:
            return
        self._action_menu_open = True
        from anytask_scraper.tui.screens.action_menu import ActionMenuScreen

        self.app.push_screen(
            ActionMenuScreen(
                title="Submission actions",
                copy_label="Copy submission",
                actions=self._teacher_actions() if self.teacher_mode else None,
            ),
            self._handle_action_menu_result,
        )

    def _handle_action_menu_result(self, result: str | None) -> None:
        self._action_menu_open = False
        if result == "copy":
            self.action_copy_submission()
        elif result == "rate":
            self._open_rate_modal()
        elif result == "grade":
            self._open_grade_modal()
        elif result == "status":
            self._open_status_modal()
        elif result == "comment":
            self._open_comment_modal()

    def _open_grade_modal(self) -> None:
        if not self.submission.has_grade_form:
            self.notify("Grade action is unavailable for this submission", severity="warning")
            return
        max_score_value: float | None = None
        if self.submission.max_score:
            with contextlib.suppress(ValueError):
                max_score_value = float(self.submission.max_score)
        self.app.push_screen(
            GradeInputScreen(max_score=max_score_value),
            self._on_grade_input,
        )

    def _open_status_modal(self) -> None:
        if not self.submission.has_status_form or not self.submission.status_options:
            self.notify("Status action is unavailable for this submission", severity="warning")
            return
        self.app.push_screen(
            StatusSelectScreen(
                self.submission.status_options,
                self.submission.current_status,
            ),
            self._on_status_select,
        )

    def _open_comment_modal(self) -> None:
        if not self.submission.has_comment_form:
            self.notify("Comment action is unavailable for this submission", severity="warning")
            return
        self.app.push_screen(CommentInputScreen(), self._on_comment_input)

    def _open_rate_modal(self) -> None:
        if not self._can_accept_and_rate():
            self.notify("Accept & Rate is unavailable for this submission", severity="warning")
            return
        max_score_value: float | None = None
        if self.submission.max_score:
            with contextlib.suppress(ValueError):
                max_score_value = float(self.submission.max_score)
        self.app.push_screen(
            AcceptAndRateScreen(max_score=max_score_value),
            self._on_rate_input,
        )

    @on(Button.Pressed, "#sub-btn-rate")
    def _rate_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._open_rate_modal()

    @on(Button.Pressed, "#sub-btn-grade")
    def _grade_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._open_grade_modal()

    @on(Button.Pressed, "#sub-btn-status")
    def _status_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._open_status_modal()

    @on(Button.Pressed, "#sub-btn-comment")
    def _comment_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._open_comment_modal()

    def _on_grade_input(self, value: float | None) -> None:
        if value is not None:
            self._submit_grade(value)

    def _on_status_select(self, code: int | None) -> None:
        if code is not None:
            self._submit_status(code)

    def _on_comment_input(self, text: str | None) -> None:
        if text is not None:
            self._submit_comment(text)

    def _on_rate_input(self, result: tuple[float, str] | None) -> None:
        if result is not None:
            grade, comment = result
            self._submit_accept_and_rate(grade, comment)

    def action_copy_submission(self) -> None:
        success, _method = copy_text_to_clipboard(
            format_submission_for_clipboard(self.submission),
            app=self.app,
        )
        if not success:
            self.notify("Failed to copy submission", severity="error")
            return

        self.notify("Submission copied to clipboard", timeout=2)

    def action_scroll_down(self) -> None:
        self.query_one("#sub-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#sub-scroll", VerticalScroll).scroll_up()

    def _teacher_actions(self) -> list[tuple[str, str]]:
        actions: list[tuple[str, str]] = []
        if self._can_accept_and_rate():
            actions.append(("rate", "Accept & Rate"))
        if self.submission.has_grade_form:
            actions.append(("grade", "Set grade"))
        if self.submission.has_status_form and self.submission.status_options:
            actions.append(("status", "Set status"))
        if self.submission.has_comment_form:
            actions.append(("comment", "Add comment"))
        return actions

    def _can_accept_and_rate(self) -> bool:
        return (
            self.submission.has_grade_form
            and self.submission.has_status_form
            and resolve_accept_status_code(self.submission.status_options) is not None
        )

    def _rebuild_ui(self) -> None:
        new_screen = SubmissionScreen(
            self.submission,
            teacher_mode=self.teacher_mode,
            on_submission_refreshed=self._on_submission_refreshed,
        )
        self.app.switch_screen(new_screen)

    def _apply_refreshed_submission(self, submission: Submission) -> None:
        self.submission = submission
        if self._on_submission_refreshed is not None:
            self._on_submission_refreshed(submission)
        self._rebuild_ui()

    @work(thread=True)
    def _refresh_submission(self) -> None:
        client = self.app.client
        if client is None:
            return
        try:
            html = client.fetch_submission_page(self.submission.issue_url)
            issue_id = extract_issue_id_from_breadcrumb(html) or self.submission.issue_id
            self.submission = parse_submission_page(
                html, issue_id, issue_url=self.submission.issue_url
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Refresh failed: {e}", severity="warning")
            return
        self.app.call_from_thread(self._apply_refreshed_submission, self.submission)

    @work(thread=True)
    def _submit_grade(self, grade: float) -> None:
        client = self.app.client
        if client is None:
            return
        try:
            result = client.set_grade(
                self.submission.issue_id,
                grade,
                issue_url=self.submission.issue_url,
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Grade failed: {e}", severity="error")
            return
        if result.success:
            self.app.call_from_thread(self.notify, result.message)
            self._refresh_submission()
        else:
            self.app.call_from_thread(self.notify, result.message, severity="error")

    @work(thread=True)
    def _submit_status(self, status: int) -> None:
        client = self.app.client
        if client is None:
            return
        try:
            result = client.set_status(
                self.submission.issue_id,
                status,
                issue_url=self.submission.issue_url,
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Status failed: {e}", severity="error")
            return
        if result.success:
            self.app.call_from_thread(self.notify, result.message)
            self._refresh_submission()
        else:
            self.app.call_from_thread(self.notify, result.message, severity="error")

    @work(thread=True)
    def _submit_comment(self, comment: str) -> None:
        client = self.app.client
        if client is None:
            return
        try:
            result = client.add_comment(
                self.submission.issue_id,
                comment,
                issue_url=self.submission.issue_url,
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Comment failed: {e}", severity="error")
            return
        if result.success:
            self.app.call_from_thread(self.notify, result.message)
            self._refresh_submission()
        else:
            self.app.call_from_thread(self.notify, result.message, severity="error")

    @work(thread=True)
    def _submit_accept_and_rate(self, grade: float, comment: str) -> None:
        client = self.app.client
        if client is None:
            return
        issue_id = self.submission.issue_id
        url = self.submission.issue_url
        accepted_status = resolve_accept_status_code(self.submission.status_options)
        if accepted_status is None:
            self.app.call_from_thread(
                self.notify,
                "Accepted status is unavailable for this submission",
                severity="warning",
            )
            return
        errors: list[str] = []

        try:
            result = client.set_grade(issue_id, grade, issue_url=url)
            if not result.success:
                errors.append(f"Grade: {result.message}")

            result = client.set_status(issue_id, accepted_status, issue_url=url)
            if not result.success:
                errors.append(f"Status: {result.message}")

            if comment:
                result = client.add_comment(issue_id, comment, issue_url=url)
                if not result.success:
                    errors.append(f"Comment: {result.message}")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Rate failed: {e}", severity="error")
            return

        if errors:
            msg = "; ".join(errors)
            self.app.call_from_thread(self.notify, msg, severity="error")
        else:
            self.app.call_from_thread(self.notify, f"Accepted with grade {grade}")
            self._refresh_submission()
