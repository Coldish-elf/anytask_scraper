from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Select


class TaskFilterBar(Widget):
    @dataclass
    class Changed(Message):
        text: str
        status: str
        section: str

    @dataclass
    class Reset(Message):
        pass

    def __init__(
        self,
        statuses: list[str] | None = None,
        sections: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._statuses = statuses or []
        self._sections = sections or []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search tasks...", id="task-filter-text")
        yield Select[str](
            [(s, s) for s in self._statuses],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Status",
            id="task-filter-status",
        )
        yield Select[str](
            [(s, s) for s in self._sections],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Section",
            id="task-filter-section",
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._emit_changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self._emit_changed()

    def _emit_changed(self) -> None:
        text = self.query_one("#task-filter-text", Input).value.strip()
        status_val = self.query_one("#task-filter-status", Select).value
        section_val = self.query_one("#task-filter-section", Select).value

        status = "" if status_val is Select.BLANK else str(status_val)
        section = "" if section_val is Select.BLANK else str(section_val)

        self.post_message(self.Changed(text=text, status=status, section=section))

    def reset(self) -> None:
        self.query_one("#task-filter-text", Input).value = ""
        self.query_one("#task-filter-status", Select).value = Select.BLANK
        self.query_one("#task-filter-section", Select).value = Select.BLANK
        self._emit_changed()
        self.post_message(self.Reset())

    def save_state(self) -> dict[str, Any]:
        return {
            "text": self.query_one("#task-filter-text", Input).value,
            "status": self.query_one("#task-filter-status", Select).value,
            "section": self.query_one("#task-filter-section", Select).value,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.query_one("#task-filter-text", Input).value = state.get("text", "")
        self.query_one("#task-filter-status", Select).value = state.get("status", Select.BLANK)
        self.query_one("#task-filter-section", Select).value = state.get("section", Select.BLANK)
        self._emit_changed()

    def focus_text(self) -> None:
        self.query_one("#task-filter-text", Input).focus()

    def focus_next_filter(self) -> bool:
        focusable = [
            self.query_one("#task-filter-text", Input),
            self.query_one("#task-filter-status", Select),
            self.query_one("#task-filter-section", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == len(focusable) - 1:
                    return False
                focusable[i + 1].focus()
                return True
        focusable[0].focus()
        return True

    def focus_prev_filter(self) -> bool:
        focusable = [
            self.query_one("#task-filter-text", Input),
            self.query_one("#task-filter-status", Select),
            self.query_one("#task-filter-section", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == 0:
                    return False
                focusable[i - 1].focus()
                return True
        focusable[-1].focus()
        return True

    def update_options(
        self,
        statuses: list[str],
        sections: list[str],
    ) -> None:
        self._statuses = statuses
        self._sections = sections

        status_select = self.query_one("#task-filter-status", Select)
        status_select.set_options([(s, s) for s in statuses])

        section_select = self.query_one("#task-filter-section", Select)
        section_select.set_options([(s, s) for s in sections])

        self.query_one("#task-filter-text", Input).value = ""


class QueueFilterBar(Widget):
    @dataclass
    class Changed(Message):
        text: str
        student: str
        task: str
        status: str
        reviewer: str

    @dataclass
    class Reset(Message):
        pass

    def __init__(
        self,
        students: list[str] | None = None,
        tasks: list[str] | None = None,
        statuses: list[str] | None = None,
        reviewers: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._students = students or []
        self._tasks = tasks or []
        self._statuses = statuses or []
        self._reviewers = reviewers or []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search queue...", id="queue-filter-text")
        yield Select[str](
            [(s, s) for s in self._students],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Student",
            id="queue-filter-student",
        )
        yield Select[str](
            [(t, t) for t in self._tasks],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Task",
            id="queue-filter-task",
        )
        yield Select[str](
            [(s, s) for s in self._statuses],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Status",
            id="queue-filter-status",
        )
        yield Select[str](
            [(r, r) for r in self._reviewers],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Reviewer",
            id="queue-filter-reviewer",
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._emit_changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self._emit_changed()

    def _emit_changed(self) -> None:
        text = self.query_one("#queue-filter-text", Input).value.strip()
        student_val = self.query_one("#queue-filter-student", Select).value
        task_val = self.query_one("#queue-filter-task", Select).value
        status_val = self.query_one("#queue-filter-status", Select).value
        reviewer_val = self.query_one("#queue-filter-reviewer", Select).value

        student = "" if student_val is Select.BLANK else str(student_val)
        task = "" if task_val is Select.BLANK else str(task_val)
        status = "" if status_val is Select.BLANK else str(status_val)
        reviewer = "" if reviewer_val is Select.BLANK else str(reviewer_val)

        self.post_message(
            self.Changed(text=text, student=student, task=task, status=status, reviewer=reviewer)
        )

    def reset(self) -> None:
        self.query_one("#queue-filter-text", Input).value = ""
        self.query_one("#queue-filter-student", Select).value = Select.BLANK
        self.query_one("#queue-filter-task", Select).value = Select.BLANK
        self.query_one("#queue-filter-status", Select).value = Select.BLANK
        self.query_one("#queue-filter-reviewer", Select).value = Select.BLANK
        self._emit_changed()
        self.post_message(self.Reset())

    def save_state(self) -> dict[str, Any]:
        return {
            "text": self.query_one("#queue-filter-text", Input).value,
            "student": self.query_one("#queue-filter-student", Select).value,
            "task": self.query_one("#queue-filter-task", Select).value,
            "status": self.query_one("#queue-filter-status", Select).value,
            "reviewer": self.query_one("#queue-filter-reviewer", Select).value,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.query_one("#queue-filter-text", Input).value = state.get("text", "")
        self.query_one("#queue-filter-student", Select).value = state.get("student", Select.BLANK)
        self.query_one("#queue-filter-task", Select).value = state.get("task", Select.BLANK)
        self.query_one("#queue-filter-status", Select).value = state.get("status", Select.BLANK)
        self.query_one("#queue-filter-reviewer", Select).value = state.get("reviewer", Select.BLANK)
        self._emit_changed()

    def focus_text(self) -> None:
        self.query_one("#queue-filter-text", Input).focus()

    def focus_next_filter(self) -> bool:
        focusable = [
            self.query_one("#queue-filter-text", Input),
            self.query_one("#queue-filter-student", Select),
            self.query_one("#queue-filter-task", Select),
            self.query_one("#queue-filter-status", Select),
            self.query_one("#queue-filter-reviewer", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == len(focusable) - 1:
                    return False
                focusable[i + 1].focus()
                return True
        focusable[0].focus()
        return True

    def focus_prev_filter(self) -> bool:
        focusable = [
            self.query_one("#queue-filter-text", Input),
            self.query_one("#queue-filter-student", Select),
            self.query_one("#queue-filter-task", Select),
            self.query_one("#queue-filter-status", Select),
            self.query_one("#queue-filter-reviewer", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == 0:
                    return False
                focusable[i - 1].focus()
                return True
        focusable[-1].focus()
        return True

    def update_options(
        self,
        students: list[str],
        tasks: list[str],
        statuses: list[str],
        reviewers: list[str] | None = None,
    ) -> None:
        self._students = students
        self._tasks = tasks
        self._statuses = statuses
        if reviewers is not None:
            self._reviewers = reviewers

        self.query_one("#queue-filter-student", Select).set_options([(s, s) for s in students])
        self.query_one("#queue-filter-task", Select).set_options([(t, t) for t in tasks])
        self.query_one("#queue-filter-status", Select).set_options([(s, s) for s in statuses])
        if reviewers is not None:
            self.query_one("#queue-filter-reviewer", Select).set_options(
                [(r, r) for r in reviewers]
            )
        self.query_one("#queue-filter-text", Input).value = ""


class GradebookFilterBar(Widget):
    @dataclass
    class Changed(Message):
        text: str
        group: str
        teacher: str

    @dataclass
    class Reset(Message):
        pass

    def __init__(
        self,
        groups: list[str] | None = None,
        teachers: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._groups = groups or []
        self._teachers = teachers or []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search students...", id="gb-filter-text")
        yield Select[str](
            [(g, g) for g in self._groups],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Group",
            id="gb-filter-group",
        )
        yield Select[str](
            [(t, t) for t in self._teachers],
            allow_blank=True,
            value=Select.BLANK,  # type: ignore[arg-type]
            prompt="Teacher",
            id="gb-filter-teacher",
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._emit_changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self._emit_changed()

    def _emit_changed(self) -> None:
        text = self.query_one("#gb-filter-text", Input).value.strip()
        group_val = self.query_one("#gb-filter-group", Select).value
        teacher_val = self.query_one("#gb-filter-teacher", Select).value

        group = "" if group_val is Select.BLANK else str(group_val)
        teacher = "" if teacher_val is Select.BLANK else str(teacher_val)

        self.post_message(self.Changed(text=text, group=group, teacher=teacher))

    def reset(self) -> None:
        self.query_one("#gb-filter-text", Input).value = ""
        self.query_one("#gb-filter-group", Select).value = Select.BLANK
        self.query_one("#gb-filter-teacher", Select).value = Select.BLANK
        self._emit_changed()
        self.post_message(self.Reset())

    def save_state(self) -> dict[str, Any]:
        return {
            "text": self.query_one("#gb-filter-text", Input).value,
            "group": self.query_one("#gb-filter-group", Select).value,
            "teacher": self.query_one("#gb-filter-teacher", Select).value,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.query_one("#gb-filter-text", Input).value = state.get("text", "")
        self.query_one("#gb-filter-group", Select).value = state.get("group", Select.BLANK)
        self.query_one("#gb-filter-teacher", Select).value = state.get("teacher", Select.BLANK)
        self._emit_changed()

    def focus_text(self) -> None:
        self.query_one("#gb-filter-text", Input).focus()

    def focus_next_filter(self) -> bool:
        focusable = [
            self.query_one("#gb-filter-text", Input),
            self.query_one("#gb-filter-group", Select),
            self.query_one("#gb-filter-teacher", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == len(focusable) - 1:
                    return False
                focusable[i + 1].focus()
                return True
        focusable[0].focus()
        return True

    def focus_prev_filter(self) -> bool:
        focusable = [
            self.query_one("#gb-filter-text", Input),
            self.query_one("#gb-filter-group", Select),
            self.query_one("#gb-filter-teacher", Select),
        ]
        for i, widget in enumerate(focusable):
            if widget.has_focus:
                if i == 0:
                    return False
                focusable[i - 1].focus()
                return True
        focusable[-1].focus()
        return True

    def update_options(
        self,
        groups: list[str],
        teachers: list[str],
    ) -> None:
        self._groups = groups
        self._teachers = teachers

        self.query_one("#gb-filter-group", Select).set_options([(g, g) for g in groups])
        self.query_one("#gb-filter-teacher", Select).set_options([(t, t) for t in teachers])
        self.query_one("#gb-filter-text", Input).value = ""
