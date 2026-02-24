"""Simple modal action menu for right-click context actions."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option


class ActionMenuScreen(ModalScreen[str | None]):
    """Modal context menu with copy/close actions."""

    BINDINGS = [
        Binding("escape", "close_menu", "Close", show=False),
    ]

    def __init__(self, *, title: str = "Actions", copy_label: str = "Copy") -> None:
        super().__init__()
        self._title = title
        self._copy_label = copy_label

    def compose(self) -> ComposeResult:
        with Vertical(id="action-menu-box"):
            yield Label(self._title, id="action-menu-title")
            yield OptionList(
                Option(self._copy_label, id="copy"),
                Option("Close", id="close"),
                id="action-menu-options",
            )
            yield Label("[dim]Enter[/dim] Select  [dim]Esc[/dim] Cancel", id="action-menu-hint")

    def on_mount(self) -> None:
        self.query_one("#action-menu-options", OptionList).focus()

    def action_close_menu(self) -> None:
        self.dismiss(None)

    @on(OptionList.OptionSelected, "#action-menu-options")
    def _menu_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        option_id = event.option.id
        if option_id == "copy":
            self.dismiss("copy")
            return
        self.dismiss(None)
