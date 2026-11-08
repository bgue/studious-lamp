"""The intent options of `tl record create|void` and `tl link add|retract` (P2-INT-T02, ADR-0025).

The CLI builds only the body. ``run_with_intent`` makes the two calls the API dispatcher makes
(``check_intent``, then the carrier); the checks and the stored text live in ``tl_core.intent``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

import click
import typer
from tl_core.confidentiality import viewer_for_actor
from tl_core.intent import Intent, check_intent, intent_scope
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork

_NOTE = "Intent is recorded with the event and read by nobody to decide anything."

WhyOpt = Annotated[
    str | None,
    typer.Option("--why", help=f"Why: plain text, at most 500 characters. {_NOTE}"),
]
NextOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--next",
        help="A next step, repeatable: command:target or text:<words>. " + _NOTE,
    ),
]
TowardOpt = Annotated[
    str | None,
    typer.Option(
        "--toward",
        help="What the work moves toward: target:state or target:~condition. " + _NOTE,
    ),
]
GoalRefOpt = Annotated[
    str | None,
    typer.Option("--goal-ref", help="A goal reference: a-z, 0-9, _ and -, at most 64. " + _NOTE),
]


def _next_item(item: str) -> dict[str, str]:
    if item.startswith("text:") and len(item) > len("text:"):
        return {"text": item[len("text:") :]}
    command, separator, target = item.partition(":")
    if separator and command and target:
        return {"command": command, "target": target}
    raise click.UsageError(f"--next {item!r}: expected command:target or text:<words>")


def _toward(value: str) -> dict[str, str]:
    target, separator, rest = value.partition(":")
    if separator and target and rest:
        if rest.startswith("~") and len(rest) > 1:
            return {"target": target, "condition": rest[1:]}
        if not rest.startswith("~"):
            return {"target": target, "state": rest}
    raise click.UsageError(f"--toward {value!r}: expected target:state or target:~condition")


def parse_intent_flags(
    why: str | None, next_items: Sequence[str], toward: str | None, goal_ref: str | None
) -> dict[str, Any] | None:
    """The ``intent`` of a command body from the four options; ``None`` when none is given."""
    found: dict[str, Any] = {}
    if why:
        found["why"] = why
    if next_items:
        found["next"] = [_next_item(item) for item in next_items]
    if toward is not None:
        found["toward"] = _toward(toward)
    if goal_ref is not None:
        found["goal_ref"] = goal_ref
    return found or None


def run_with_intent[C: Command, R](
    uow: UnitOfWork,
    command: C,
    handler: Callable[[UnitOfWork, C], R],
    intent: dict[str, Any] | None,
) -> R:
    """Run ``handler`` with the intent checked and carried, as the API dispatcher does.

    ``IntentInvalid`` and ``IntentReferenceUnknown`` propagate before the handler appends anything.
    """
    if intent is None:
        return handler(uow, command)
    command = command.model_copy(update={"intent": Intent.model_validate(intent)})
    command = check_intent(command, uow.conn(), viewer_for_actor(uow.conn(), command.actor))
    with intent_scope(command.intent):
        return handler(uow, command)
