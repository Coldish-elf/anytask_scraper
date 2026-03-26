from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Button, Input, Label

from anytask_scraper.client import AnytaskClient, LoginError
from anytask_scraper.tui.app import get_session_candidates

if TYPE_CHECKING:
    from anytask_scraper.tui.app import AnytaskApp

logger = logging.getLogger(__name__)


class LoginScreen(Screen[None]):
    app: AnytaskApp

    def _get_session_candidates(self) -> list[Path]:
        return get_session_candidates(self.app._load_settings())

    def _get_existing_session_path(self) -> Path | None:
        for candidate in self._get_session_candidates():
            if candidate.exists():
                return candidate
        return None

    def compose(self) -> ComposeResult:
        with Center(), Vertical(id="login-box"):
            yield Label("ANYTASK", id="login-title")

            with Vertical(classes="field"):
                yield Label("Username", classes="field-label")
                yield Input(placeholder="username", id="username")

            with Vertical(classes="field"):
                yield Label("Password", classes="field-label")
                yield Input(placeholder="password", password=True, id="password")

            with Vertical(id="btn-row"):
                yield Button("Login", variant="primary", id="login-btn")
                if self._get_existing_session_path() is not None:
                    yield Button(
                        "Continue with saved session",
                        variant="default",
                        id="session-btn",
                    )

            yield Label("", id="login-status")

    def on_mount(self) -> None:
        self.query_one("#username", Input).focus()

    def on_key(self, event: Key) -> None:
        if event.key not in ("up", "down"):
            return

        focusable: list[str] = ["#username", "#password", "#login-btn"]
        if self.query("#session-btn"):
            focusable.append("#session-btn")

        focused = self.focused
        if focused is None:
            return

        current_id = f"#{focused.id}"
        if current_id not in focusable:
            return

        event.prevent_default()
        idx = focusable.index(current_id)
        next_idx = (idx + 1) % len(focusable) if event.key == "down" else (idx - 1) % len(focusable)
        self.query_one(focusable[next_idx]).focus()

    @on(Input.Submitted, "#username")
    def _username_submitted(self) -> None:
        self.query_one("#password", Input).focus()

    @on(Input.Submitted, "#password")
    def _password_submitted(self) -> None:
        self._handle_login()

    @on(Button.Pressed, "#login-btn")
    def _handle_login(self) -> None:
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value.strip()
        if not username or not password:
            self._set_status("Enter username and password", "error")
            return
        self._set_status("Logging in...", "info")
        self._do_login(username, password)

    @on(Button.Pressed, "#session-btn")
    def _handle_session(self) -> None:
        path = self._get_existing_session_path()
        if path is None:
            self._set_status("Session file not found", "error")
            return
        self._set_status("Loading session...", "info")
        self._do_load_session(str(path))

    @work(thread=True)
    def _do_login(self, username: str, password: str) -> None:
        logger.info("TUI login attempt for user %s", username)
        try:
            client = AnytaskClient(username=username, password=password)
            client.login()
            self.app.client = client
            self.app.session_path = str(self._get_session_candidates()[0])
            logger.info("TUI login successful for user %s", username)
            self.app.call_from_thread(self._set_status, f"Logged in as {username}", "success")
            self.app.call_from_thread(self._go_main)
        except LoginError as e:
            logger.warning("TUI login failed: %s", e)
            self.app.call_from_thread(self._set_status, f"Login failed: {e}", "error")
        except Exception as e:
            logger.exception("TUI login error")
            self.app.call_from_thread(self._set_status, f"Error: {e}", "error")

    @work(thread=True)
    def _do_load_session(self, session_path: str) -> None:
        logger.info("Loading session from %s", session_path)
        try:
            client = AnytaskClient()
            success = client.load_session(session_path)
            if not success:
                logger.warning("Failed to load session from %s", session_path)
                self.app.call_from_thread(self._set_status, "Failed to load session", "error")
                return
            self.app.client = client
            self.app.session_path = session_path
            name = client.username or "saved session"
            logger.info("Session loaded for %s", name)
            self.app.call_from_thread(self._set_status, f"Loaded ({name})", "success")
            self.app.call_from_thread(self._go_main)
        except Exception as e:
            logger.exception("Error loading session")
            self.app.call_from_thread(self._set_status, f"Error: {e}", "error")

    def _set_status(self, message: str, kind: str = "info") -> None:
        label = self.query_one("#login-status", Label)
        label.update(message)
        label.remove_class("error", "success", "info")
        label.add_class(kind)

    def _go_main(self) -> None:
        from anytask_scraper.tui.screens.main import MainScreen

        self.app.push_screen(MainScreen())
