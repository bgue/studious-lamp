"""Workflow action menu: the record's state, each transition, and why a blocked one is blocked.

(P0-I3-T15; brief 8.) Opened with `w`. The list shows every transition that starts in the record's
state with ``✓ allowed`` or ``✗ blocked``; below it the guards of the highlighted transition, each
with its message, so a blocked transition explains itself (a missing expected link, a role, a
property required in the target state). Enter runs an allowed transition through
`ClientInterface.transition`.

STUB (P0-I3-T15): the layout (`compose`), constructor and key bindings are final; the functions
and methods marked `raise NotImplementedError` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from tl_core.services.workflow import TransitionOption, WorkflowStatus

from tl_tui.client import ClientInterface


def header_text(status: WorkflowStatus) -> str:
    """Two lines: ``KEY  workflow vN`` and ``State: <label>  (since <time>)``."""
    raise NotImplementedError


def option_line(option: TransitionOption) -> str:
    """``<label> → <to state>  ✓ allowed`` or ``…  ✗ blocked``."""
    raise NotImplementedError


def guard_lines(option: TransitionOption) -> list[str]:
    """One line per guard, ``  ✓ <kind>: <message>`` or ``  ✗ <kind>: <message>``; a transition
    with no guards gives ``["  (no guards)"]``."""
    raise NotImplementedError


class WorkflowMenu(ModalScreen[bool]):
    """Dismisses with ``True`` after a transition ran, ``False`` otherwise."""

    KEY_HINTS: ClassVar[str] = "↑↓ choose  Enter run  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
    ]

    DEFAULT_CSS = """
    WorkflowMenu { align: center middle; }
    WorkflowMenu > Vertical {
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    WorkflowMenu #wf-header { text-style: bold; }
    WorkflowMenu #wf-options { height: auto; max-height: 8; border: none; }
    WorkflowMenu #wf-status { color: $error; height: auto; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        record: dict[str, Any],
        *,
        roles: Sequence[str] = (),
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.record = record
        self.roles = tuple(roles)
        self.actor = actor
        self.status: WorkflowStatus | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="wf-header", markup=False)
            yield OptionList(id="wf-options")
            yield Static("", id="wf-guards", markup=False)
            yield Static("", id="wf-status", markup=False)

    def on_mount(self) -> None:
        raise NotImplementedError

    def _say(self, text: str) -> None:
        raise NotImplementedError

    def _load(self) -> None:
        raise NotImplementedError

    def _highlighted(self) -> TransitionOption | None:
        raise NotImplementedError

    def _show_guards(self) -> None:
        raise NotImplementedError

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        raise NotImplementedError

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        raise NotImplementedError

    def action_move(self, delta: int) -> None:
        raise NotImplementedError

    def _run(self, option: TransitionOption | None) -> None:
        raise NotImplementedError

    def action_close(self) -> None:
        raise NotImplementedError
