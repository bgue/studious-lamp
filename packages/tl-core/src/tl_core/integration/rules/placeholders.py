"""``${binding}`` placeholders in the string arguments of a rule step (FANOUT D7).

A rule's arguments are static JSON. Their strings may hold ``${name}`` for a name in
``RULE_BINDINGS`` (``subject_key``, ``event_id`` ...); the worker fills them from the event and its
subject record with ``string.Template.safe_substitute`` and nothing else: never ``str.format`` (no
attribute access), never ``eval``. A bound value is inserted once; what it contains is not read
again, so a record title that says ``${event_actor}`` stays that text.

Two checks:

* :func:`check_template` runs when a rule is stored. It refuses a name outside ``RULE_BINDINGS``
  and a lone ``$`` (write ``$$`` for a dollar sign), so a typo is found at authoring, not at 3 a.m.
* :func:`substitute` runs per event. A bound value longer than ``RULE_MAX_BINDING_CHARS``, or
  arguments that grow past ``RULE_MAX_ARGS_BYTES``, make the step refused; nothing is cut.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from string import Template
from typing import Any

from tl_core.integration.contract import (
    INBOUND_MAX_JSON_DEPTH,
    RULE_BINDINGS,
    RULE_MAX_ARGS_BYTES,
    RULE_MAX_BINDING_CHARS,
    Problem,
)

MAX_NODES = 2_000


def _names(text: str) -> tuple[list[str], bool]:
    """The placeholder names in ``text`` and whether a stray ``$`` is there."""
    names: list[str] = []
    stray = False
    for match in Template.pattern.finditer(text):
        if match.group("invalid") is not None:
            stray = True
        name = match.group("named") or match.group("braced")
        if name is not None:
            names.append(name)
    return names, stray


def _walk_strings(value: Any, depth: int, budget: list[int]) -> list[str]:
    """Every string value of ``value`` (keys are not templates); raises ``ValueError`` if the
    structure is deeper than ``INBOUND_MAX_JSON_DEPTH`` or holds more than ``MAX_NODES`` values."""
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > INBOUND_MAX_JSON_DEPTH:
        raise ValueError("the arguments are too large or too deep")
    if isinstance(value, str):
        return [value]
    found: list[str] = []
    if isinstance(value, dict):
        for item in value.values():  # pyright: ignore[reportUnknownVariableType]
            found.extend(_walk_strings(item, depth + 1, budget))
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            found.extend(_walk_strings(item, depth + 1, budget))
    return found


def check_template(args: dict[str, Any]) -> list[Problem]:
    """Problems with the placeholders of ``args`` (empty means they may be stored)."""
    try:
        texts = _walk_strings(args, 0, [0])
    except ValueError:
        return [Problem(code="args_too_large", message="The step's arguments are too large.")]
    problems: list[Problem] = []
    for text in texts:
        names, stray = _names(text)
        if stray:
            problems.append(
                Problem(code="bad_placeholder", message="A lone $ is not allowed; write $$.")
            )
        for name in names:
            if name not in RULE_BINDINGS:
                problems.append(
                    Problem(
                        code="unknown_binding",
                        message=f"${{{name[:40]}}} is not a binding. Use one of: "
                        f"{', '.join(sorted(RULE_BINDINGS))}.",
                    )
                )
    try:
        size = len(json.dumps(args, sort_keys=True, separators=(",", ":")).encode())
    except (TypeError, ValueError, OverflowError, RecursionError):
        return [
            *problems,
            Problem(code="args_not_json", message="A step's arguments must be JSON."),
        ]
    if size > RULE_MAX_ARGS_BYTES:
        problems.append(
            Problem(
                code="args_too_large",
                message=f"A step's arguments are over {RULE_MAX_ARGS_BYTES} bytes.",
            )
        )
    return problems


def substitute(
    args: dict[str, Any], bindings: Mapping[str, str]
) -> tuple[dict[str, Any], Problem | None]:
    """``args`` with every placeholder in a string value filled from ``bindings``.

    Returns the new arguments and no problem, or the unchanged arguments and the reason the step
    must be refused. A name that is not bound is left as it is (``safe_substitute``): the check at
    authoring time is what keeps such names out.
    """
    for name, value in bindings.items():
        if name in RULE_BINDINGS and len(value) > RULE_MAX_BINDING_CHARS:
            return args, Problem(
                code="binding_too_long",
                message=f"{name} is longer than {RULE_MAX_BINDING_CHARS} characters.",
            )

    def fill(value: Any, depth: int) -> Any:
        if depth > INBOUND_MAX_JSON_DEPTH:
            raise ValueError("too deep")
        if isinstance(value, str):
            return Template(value).safe_substitute(bindings)
        if isinstance(value, dict):
            return {name: fill(item, depth + 1) for name, item in value.items()}  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, list):
            return [fill(item, depth + 1) for item in value]  # pyright: ignore[reportUnknownVariableType]
        return value

    try:
        filled: dict[str, Any] = fill(args, 0)
    except ValueError:
        return args, Problem(code="args_too_large", message="The step's arguments are too deep.")
    try:
        size = len(json.dumps(filled, sort_keys=True, separators=(",", ":")).encode())
    except (TypeError, ValueError, OverflowError, RecursionError):
        return args, Problem(code="args_not_json", message="The step's arguments are not JSON.")
    if size > RULE_MAX_ARGS_BYTES:
        return args, Problem(
            code="args_too_large",
            message=f"A step's arguments grew past {RULE_MAX_ARGS_BYTES} bytes.",
        )
    return filled, None
