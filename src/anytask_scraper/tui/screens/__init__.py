"""TUI screens for anytask-scraper."""

from __future__ import annotations

from anytask_scraper.tui.screens.action_menu import ActionMenuScreen
from anytask_scraper.tui.screens.login import LoginScreen
from anytask_scraper.tui.screens.main import MainScreen
from anytask_scraper.tui.screens.submission import SubmissionScreen

__all__ = [
    "ActionMenuScreen",
    "LoginScreen",
    "MainScreen",
    "SubmissionScreen",
]
