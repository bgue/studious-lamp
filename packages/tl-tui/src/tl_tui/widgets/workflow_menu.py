"""Workflow action menu: the record's state, each transition, and why a blocked one is blocked.

(P0-I3-T15; brief 8.) Opened with `w`. The list shows every transition that starts in the record's
state with ``✓ allowed`` or ``✗ blocked``; below it the guards of the highlighted transition, each
with its message, so a blocked transition explains itself (a missing expected link, a role, a
property required in the target state). Enter runs an allowed transition through
`ClientInterface.transition`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from tl_core.services.errors import GuardFailedError
from tl_core.services.workflow import TransitionOption, TransitionWorkflow, WorkflowStatus

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.text import timestamp


def header_text(status: WorkflowStatus) -> str:
    """Two lines: ``KEY  workflow vN`` and ``State: <label>  (since <time>)``."""
    return (
        f"{status.key}  {status.workflow} v{status.workflow_version}\n"
        f"State: {status.state_label}  (since {timestamp(status.entered_at)})"
    )


def option_line(option: TransitionOption) -> str:
    """``<label> → <to state>  ✓ allowed`` or ``…  ✗ blocked``."""
    verdict = "✓ allowed" if option.allowed else "✗ blocked"
    return f"{option.label} → {option.to_state}  {verdict}"


def guard_lines(option: TransitionOption) -> list[str]:
    """One line per guard, ``  ✓ <kind>: <message>`` or ``  ✗ <kind>: <message>``; a transition
    with no guards gives ``["  (no guards)"]``."""
    if not option.guards:
        return ["  (no guards)"]
    return [f"  {'✓' if g.passed else '✗'} {g.kind}: {g.message}" for g in option.guards]


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
        self.query_one("#wf-options", OptionList).focus()
        self._load()

    def _say(self, text: str) -> None:
        self.query_one("#wf-status", Static).update(text)

    def _load(self) -> None:
        options = self.query_one("#wf-options", OptionList)
        options.clear_options()
        try:
            self.status = self.client.workflow_status(self.record["id"], roles=self.roles)
        except CLIENT_ERRORS as exc:
            self.status = None
            self.query_one("#wf-header", Static).update(str(self.record.get("key") or ""))
            self.query_one("#wf-guards", Static).update("")
            self._say(describe_error(exc))
            return
        roles = ", ".join(self.roles) or "none"
        self.query_one("#wf-header", Static).update(f"{header_text(self.status)}\nRoles: {roles}")
        for option in self.status.options:
            options.add_option(Option(Text(option_line(option)), id=option.transition))
        if self.status.options:
            options.highlighted = 0
        else:
            self.query_one("#wf-guards", Static).update("No transitions from this state")
        self._show_guards()

    def _highlighted(self) -> TransitionOption | None:
        if self.status is None:
            return None
        index = self.query_one("#wf-options", OptionList).highlighted
        if index is None or not 0 <= index < len(self.status.options):
            return None
        return self.status.options[index]

    def _show_guards(self) -> None:
        option = self._highlighted()
        if option is not None:
            self.query_one("#wf-guards", Static).update("\n".join(guard_lines(option)))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._show_guards()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._run(self._highlighted())

    def action_move(self, delta: int) -> None:
        options = self.query_one("#wf-options", OptionList)
        if delta > 0:
            options.action_cursor_down()
        else:
            options.action_cursor_up()

    def _run(self, option: TransitionOption | None) -> None:
        if option is None or self.status is None:
            return
        if not option.allowed:
            reasons = [g.message for g in option.guards if not g.passed]
            self._say("Blocked: " + "; ".join(reasons))
            return
        cmd = TransitionWorkflow(
            actor=self.actor,
            source="tui",
            scope=self.scope,
            stream_id=str(self.record["id"]),
            expected_version=self.status.version,
            transition=option.transition,
            actor_roles=list(self.roles),
        )
        try:
            self.client.transition(cmd)
        except GuardFailedError as exc:
            self._load()
            self._say(f"Blocked: {exc}")
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc))
        else:
            self.dismiss(True)

    def action_close(self) -> None:
        self.dismiss(False)
