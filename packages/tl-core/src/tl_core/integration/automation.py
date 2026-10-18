"""Building and running the commands automation produces (FANOUT D3; ADR-0017).

A rule step, an inbound mapping and an enricher all end the same way: a command name and static
arguments become a command model with the **server's** fields on it, and the command runs through
the injected :class:`~tl_core.integration.contract.CommandRunner` as a service actor. This module is
that one path, so each engine gets the same four checks:

a. the command is one automation may run (``AUTOMATION_COMMANDS``);
b. it is in the record's own list (a rule's steps, an endpoint's ``allowed_commands``);
c. the declared access covers what the command needs (``access_covers``; a command nobody
   declared an access for is refused);
d. the command's own model validation, and later the handler's allow-lists and guards, run as for
   any client.

``actor``, ``source``, ``scope``, ``correlation_id`` and ``causation_id`` are set here from
:class:`ServerFields`; arguments that name one are refused, never ignored. A link is written with
the engine's own system link source through the narrow ``system_source`` keyword, never through
``by_module`` (which also lifts the module allow-list).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from tl_core.integration.actor_access import require_access
from tl_core.integration.contract import (
    AUTOMATION_COMMANDS,
    INBOUND_MAX_JSON_DEPTH,
    SERVER_SET_FIELDS,
    AutomationAccess,
    CommandRunner,
    PlannedCommand,
    Problem,
    access_covers,
)
from tl_core.integration.errors import CommandAccessError
from tl_core.links.vocabulary import LinkSource
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import (
    AddLink,
    SuggestLink,
    handle_add_link,
    handle_suggest_link,
)
from tl_core.uow import UnitOfWork

MAX_PROBLEM_CHARS = 200


@dataclass(frozen=True)
class ServerFields:
    """The fields the server sets on a command automation runs."""

    actor: str
    source: str
    scope: str
    correlation_id: str
    causation_id: str | None


@dataclass(frozen=True)
class Planned:
    """A built command (``None`` when it was refused) and how a preview shows it."""

    command: Command | None
    planned: PlannedCommand


def names_server_field(value: Any, depth: int = 0) -> str | None:
    """The first server-set field name used as a key anywhere in ``value`` (a bounded walk)."""
    if depth > INBOUND_MAX_JSON_DEPTH:
        return "<too deep>"
    if isinstance(value, dict):
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            if key in SERVER_SET_FIELDS:
                return str(key)  # pyright: ignore[reportUnknownArgumentType]
            found = names_server_field(item, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            found = names_server_field(item, depth + 1)
            if found is not None:
                return found
    return None


def first_error(exc: ValidationError) -> str:
    """The first validation error as ``field: message`` (never the input value)."""
    errors = exc.errors(include_input=False, include_url=False, include_context=False)
    if not errors:
        return "the command is not valid"
    first = errors[0]
    where = ".".join(str(part) for part in first["loc"]) or "command"
    return f"{where}: {first['msg']}"[:MAX_PROBLEM_CHARS]


def plan_command(
    runner: CommandRunner,
    name: str,
    args: dict[str, Any],
    fields: ServerFields,
    *,
    declared: AutomationAccess,
    allowed: Collection[str],
    link_source: LinkSource,
) -> Planned:
    """Build one command and say whether it may run. Nothing is run or written."""

    def refuse(code: str, message: str, access: Any = None) -> Planned:
        return Planned(
            None,
            PlannedCommand(
                command_type=name,
                command={},
                access=access,
                permitted=False,
                summary=name,
                problem=Problem(code=code, message=message[:MAX_PROBLEM_CHARS]),
            ),
        )

    if name not in AUTOMATION_COMMANDS or name not in allowed:
        return refuse("command_not_allowed", f"{name} is not in this automation's list.")
    model = runner.model_of(name)
    needed = runner.access_of(name)
    if model is None:
        return refuse("unknown_command", f"{name} is not a command of this server.")
    if not access_covers(declared, needed):
        what = needed or "an access nobody declared"
        return refuse(
            "access_denied", f"{name} needs {what}; this automation holds {declared}.", needed
        )
    named = names_server_field(args)
    if named is not None:
        return refuse("server_field", f"The server sets {named}; the arguments may not.", needed)
    unknown = sorted(set(args) - set(model.model_fields))
    if unknown:
        return refuse("unknown_field", f"{name} has no field {', '.join(unknown)[:80]}.", needed)
    values = dict(args)
    if issubclass(model, AddLink):
        if values.get("link_source", link_source) != link_source:
            return refuse("link_source", f"Links made here have the source {link_source}.", needed)
        values["link_source"] = link_source
    try:
        command = model.model_validate(
            {
                **values,
                "actor": fields.actor,
                "source": fields.source,
                "scope": fields.scope,
                "correlation_id": fields.correlation_id,
                "causation_id": fields.causation_id,
            }
        )
    except ValidationError as exc:
        return refuse("invalid_command", first_error(exc), needed)
    return Planned(
        command,
        PlannedCommand(
            command_type=name,
            command=command.model_dump(mode="json", exclude={"actor"}),
            access=needed,
            permitted=True,
            summary=f"{name} in {fields.scope}",
        ),
    )


def run_automation_command(
    runner: CommandRunner,
    uow: UnitOfWork,
    command: Command,
    *,
    link_source: LinkSource,
    declared: AutomationAccess,
) -> CommandResult:
    """Run a command built by :func:`plan_command`. Raises what the handler raises.

    The command's access is checked twice and fails closed: against the access this automation was
    declared (``user`` or ``controller``, never ``admin``), and, in the runner, against what the
    command's own actor holds in the ledger (``actor_access``). A link goes through the handler's
    narrow ``system_source`` keyword, so the module allow-lists and guards still apply; the runner's
    check is made here for those two. An action is invoked through the runner, so ``holds`` comes
    from the actor's resolved access.
    """
    name = type(command).__name__
    needed = runner.access_of(name)
    if not access_covers(declared, needed):
        raise CommandAccessError(f"{name} needs more access than this automation was declared")
    if isinstance(command, SuggestLink | AddLink):
        require_access(uow.conn(), command.actor, needed, name)
        if isinstance(command, SuggestLink):
            return handle_suggest_link(uow, command, system_source=link_source)
        return handle_add_link(uow, command, system_source=link_source)
    return runner.run(uow, command)
