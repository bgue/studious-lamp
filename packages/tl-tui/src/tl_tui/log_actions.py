"""How a log shows what the server offers on a record, and runs it (P1-UX2-S3).

The server says which commands the viewer may run on a record now (``client.allowed_actions``).
This module only presents those offers: ``ACTION_UI`` maps a command name to a key, the questions
to ask first and how to build the command from the answers. An offer whose command has no entry is
not shown (it is logged once); the screen never invents an action and never decides who may do
what. The command still checks the state and the access when it runs, and a refusal goes to the
status line (``LogScreen.attempt``).

A command is built with a placeholder envelope (``ENVELOPE``); ``stamp`` puts the real actor and
scope on it just before it is sent. The table and those helpers live in ``tl_tui.action_ui`` (no
``textual``); this module re-exports them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from tl_core.actions import RecordActions
from tl_core.services.commands import Command, CommandResult
from tl_core.services.psets import SetPsetValues
from tl_mod_engineering.commands import API_COMMANDS as ENGINEERING_COMMANDS
from tl_mod_schemareg.handlers.adoption import AdoptSchemaSet

from tl_tui.action_ui import (
    ACTION_UI,
    ENVELOPE,
    ActionUi,
    Build,
    FormField,
    Prepare,
    stamp,
    without_keys,
)
from tl_tui.client import ClientInterface
from tl_tui.labels_load import forget_labels
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

log = logging.getLogger(__name__)

#: The names that moved to ``tl_tui.action_ui`` and are still importable from here.
__all__ = [
    "ACTION_UI",
    "ADD_PROPERTY_KEY",
    "ENVELOPE",
    "ActionUi",
    "Build",
    "FormField",
    "Prepare",
    "Runner",
    "add_property_actions",
    "log_actions",
    "run_module_command",
    "screen_runner",
    "stamp",
    "without_keys",
]

#: ``(label, ui, prepare)``: asks what ``ui`` asks (if anything), then sends ``prepare(values)``.
Runner = Callable[[str, "ActionUi", Prepare], None]


_ENGINEERING = frozenset(spec.model.__name__ for spec in ENGINEERING_COMMANDS)
_unknown_logged: set[str] = set()


def run_module_command(client: ClientInterface, name: str, cmd: Command) -> CommandResult:
    """Run a command of the engineering or the correspondence table (the client checks both the
    name and the access; a name in neither raises ``ForbiddenError``)."""
    done = (
        client.engineering_command(name, cmd)
        if name in _ENGINEERING
        else client.correspondence_command(name, cmd)
    )
    forget_labels(client)  # a code list, a mnemonic or a domain may have changed
    return done


def log_actions(
    offers: RecordActions,
    ui: Mapping[str, ActionUi],
    run: Runner,
    *,
    version: int | None = None,
) -> list[LogAction]:
    """One ``LogAction`` per offer that has a UI entry, in the order the server gave them.

    An offer whose command has no entry is left out (logged once per command): the screen never
    invents an action. ``run(label, ui, prepare)`` is what pressing the key does.
    """
    shown: list[LogAction] = []
    for offer in offers.actions:
        entry = ui.get(offer.command)
        if entry is None:
            if offer.command not in _unknown_logged:
                _unknown_logged.add(offer.command)
                log.info("no screen action for the offered command %s", offer.command)
            continue
        shown.append(
            LogAction(
                entry.key,
                offer.label,
                _runner_of(offer.command, offer.label, entry, offers.record_id, version, run),
            )
        )
    return shown


def _runner_of(
    command: str, label: str, entry: ActionUi, record_id: str, version: int | None, run: Runner
) -> Callable[[], None]:
    def prepare(values: dict[str, str]) -> tuple[str, Command]:
        return command, entry.build(values, record_id, version)

    def go() -> None:
        run(label, entry, prepare)

    return go


def screen_runner(
    screen: LogScreen[Any], client: ClientInterface, *, actor: str, scope: str
) -> Runner:
    """The runner of a log: asks through ``ActionFormScreen`` when the action asks anything, then
    sends the stamped command inside ``screen.attempt`` so a refusal reaches the status line."""

    def send(prepare: Prepare, values: dict[str, str]) -> None:
        name, cmd = prepare(values)
        run_module_command(client, name, stamp(cmd, actor=actor, scope=scope))

    def run(label: str, entry: ActionUi, prepare: Prepare) -> None:
        if not entry.fields and entry.confirm is None:
            send(prepare, {})  # runs inside the attempt that pressed the key
            return

        def answered(values: dict[str, str] | None) -> None:
            if values is not None:
                screen.attempt(lambda: send(prepare, values))

        screen.app.push_screen(
            ActionFormScreen(label, entry.fields, confirm=entry.confirm), answered
        )

    return run


#: The key of ``Add property`` in every log of records (``plus``: the ``+`` key).
ADD_PROPERTY_KEY = "plus"


def add_property_actions(
    screen: LogScreen[Any],
    client: ClientInterface,
    offers: RecordActions,
    *,
    actor: str,
    scope: str,
) -> list[LogAction]:
    """``[+] Add property`` for the record ``offers`` is about, unless the viewer cannot write it:
    an agent only proposes, and a voided record changes no more. The form sends nothing; its
    command goes through ``screen.attempt``, so a refusal reaches the status line."""
    if actor.startswith("agent:") or offers.state == "Void":
        return []

    def run() -> None:
        from tl_tui.widgets.add_property_form import open_add_property  # noqa: PLC0415
        from tl_tui.widgets.schema_screen import SchemaWorkbenchScreen  # noqa: PLC0415

        def write(cmd: SetPsetValues) -> None:
            client.set_pset_values(cmd)

        def send(cmd: SetPsetValues) -> None:
            screen.attempt(lambda: write(cmd))

        def workbench(package: str) -> None:
            screen.app.push_screen(SchemaWorkbenchScreen(client, scope, actor, package=package))

        def adopt(cmd: AdoptSchemaSet) -> bool:
            def run() -> None:
                client.schemareg_command("AdoptSchemaSet", cmd)
                forget_labels(client)  # an adopted package can move code lists and labels

            return screen.attempt(run)

        open_add_property(
            screen,
            client,
            scope=scope,
            record_id=offers.record_id,
            actor=actor,
            is_admin=bool(getattr(screen.app, "is_admin", False)),
            send=send,
            workbench=workbench,
            adopt=adopt,
        )

    return [LogAction(ADD_PROPERTY_KEY, "Add property", run)]
