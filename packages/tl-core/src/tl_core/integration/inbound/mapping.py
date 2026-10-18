"""The restricted JSONata runtime ``jsonata-restricted@1`` (FANOUT D5; ADR-0017).

``MappingRuntime`` of the contract. Two halves:

**check** (an endpoint stores a mapping only when it returns nothing). The expression is parsed
with the library and its syntax tree is walked against an allow-list of node types, which refuses
function definitions and lambdas, regular expressions, partial application, variable binding,
transforms, descendants and parent references, and any function not in
``MAPPING_ALLOWED_FUNCTIONS`` (``$eval``, ``$now``, ``$millis``, ``$random``, ``$match``,
``$replace``, ``$sift``, ``$each``, ``$map`` and the other higher-order functions among them). The
expression is at most ``MAPPING_MAX_EXPRESSION_CHARS`` long; the walk is bounded in nodes and depth.

**evaluate** (per delivery). The expression runs in the ADR-0014 envelope
(``tl_core.derivation.envelope``, never a copy): a fresh interpreter with a scrubbed environment,
``RLIMIT_AS`` of ``MAPPING_MAX_MEMORY_BYTES``, a wall clock of ``MAPPING_MAX_SECONDS`` and the
process group killed on a breach, with the library's own time box (``MAPPING_TIMEBOX_MS``,
``MAPPING_MAX_DEPTH``) inside. The payload goes in as JSON; the answer comes back as JSON bytes at
most ``MAPPING_MAX_OUTPUT_BYTES`` and is parsed here, never unpickled, into a ``MappingOutcome``.
A breach is ``limit``; a library error is ``error`` with its JSONata code and a fixed text.

JSONata has no input or output function. The limits do not confine the filesystem or the network of
the child (ADR-0014 known limit; the risk register covers both uses).
"""

# jsonata-python ships no type information; its objects are untyped here.
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportArgumentType=false

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from jsonata import Jsonata
from jsonata.parser import Parser
from pydantic import ValidationError

from tl_core.derivation.envelope import Breach, run_in_envelope
from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    MAPPING_ALLOWED_FUNCTIONS,
    MAPPING_LANGUAGE,
    MAPPING_MAX_COMMANDS,
    MAPPING_MAX_DEPTH,
    MAPPING_MAX_EXPRESSION_CHARS,
    MAPPING_MAX_MEMORY_BYTES,
    MAPPING_MAX_OUTPUT_BYTES,
    MAPPING_MAX_SECONDS,
    MAPPING_TIMEBOX_MS,
    MappedCommand,
    MappingOutcome,
    Problem,
)

CHILD_ENTRY = "tl_core.integration.inbound.mapping_child:evaluate_entry"
#: A payload larger than this is not given to a mapping (the route's own cap is lower).
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_AST_NODES = 5_000
MAX_AST_DEPTH = 200
#: Node types of the syntax tree a mapping may use. Everything else is refused by name.
ALLOWED_NODE_TYPES = frozenset(
    {
        "unary",  # an object or array constructor, or a minus sign
        "binary",
        "path",
        "name",
        "number",
        "string",
        "value",  # true, false, null
        "variable",
        "function",
        "condition",
        "filter",
        "block",  # parentheses
        "wildcard",
        "apply",  # a ~> $f()
        "sort",
        "group",
    }
)
_NOT_JSON = Problem(code="not_json", message="The payload is not JSON.")


def _node_children(node: Parser.Symbol) -> Iterator[Parser.Symbol]:
    """Every syntax node directly under ``node`` (the library keeps them in many fields)."""
    for value in vars(node).values():
        yield from _symbols(value, 0)


def _symbols(value: Any, depth: int) -> Iterator[Parser.Symbol]:
    if isinstance(value, Parser.Symbol):
        yield value
    elif isinstance(value, list | tuple) and depth < 4:
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            yield from _symbols(item, depth + 1)


def _problem(code: str, message: str) -> Problem:
    return Problem(code=code, message=message)


def syntax_problems(tree: Parser.Symbol) -> list[Problem]:
    """The reasons a syntax tree is outside the profile (the first few, deduplicated)."""
    problems: dict[str, Problem] = {}
    stack: list[tuple[Parser.Symbol, int]] = [(tree, 0)]
    seen = 0
    while stack:
        node, depth = stack.pop()
        seen += 1
        if seen > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            problems["size"] = _problem("too_complex", "The expression is too large or too deep.")
            break
        kind = str(node.type)
        if kind not in ALLOWED_NODE_TYPES:
            problems[f"node:{kind}"] = _problem(
                "not_allowed", f"{_describe(kind)} is not allowed in a mapping."
            )
            continue
        if kind == "function":
            name = _called(node)
            if name is None or f"${name}" not in MAPPING_ALLOWED_FUNCTIONS:
                shown = "that function" if name is None else f"${name[:40]}"
                problems[f"fn:{name}"] = _problem(
                    "function_not_allowed", f"{shown} is not allowed in a mapping."
                )
                continue
        elif kind == "variable":
            name = str(node.value)
            if name not in ("", "$") and f"${name}" not in MAPPING_ALLOWED_FUNCTIONS:
                problems[f"var:{name}"] = _problem(
                    "variable_not_allowed", f"${name[:40]} is not allowed in a mapping."
                )
                continue
        stack.extend((child, depth + 1) for child in _node_children(node))
    return list(problems.values())[:10]


def _called(node: Parser.Symbol) -> str | None:
    """The name of the function a call node calls, when it calls a named one."""
    procedure = getattr(node, "procedure", None)
    if isinstance(procedure, Parser.Symbol) and str(procedure.type) == "variable":
        return str(procedure.value)
    return None


_DESCRIPTIONS = {
    "lambda": "A function definition",
    "regex": "A regular expression",
    "partial": "Partial application",
    "bind": "Binding a variable",
    "transform": "A transform",
    "descendant": "The ** operator",
    "parent": "The % operator",
    "focus": "The @ operator",
    "index": "The # operator",
}


def _describe(kind: str) -> str:
    return _DESCRIPTIONS.get(kind, f"A {kind[:20]} expression")


class JsonataRestricted:
    """``MappingRuntime`` for ``jsonata-restricted@1``."""

    language = MAPPING_LANGUAGE

    def check(self, expression: str) -> list[Problem]:
        if len(expression) > MAPPING_MAX_EXPRESSION_CHARS:
            return [
                _problem(
                    "too_long", f"A mapping is at most {MAPPING_MAX_EXPRESSION_CHARS} characters."
                )
            ]
        if not expression.strip() or "\x00" in expression:
            return [_problem("empty", "A mapping is not empty and holds no NUL.")]
        try:
            tree = Jsonata(expression).ast
        except RecursionError:
            return [_problem("too_complex", "The expression is nested too deeply.")]
        except Exception as exc:  # the library's own error: its code, never the expression
            code = str(getattr(exc, "error", "") or "")[:16]
            suffix = f" ({code})" if code else ""
            return [_problem("syntax", f"The expression does not parse{suffix}.")]
        return syntax_problems(tree)

    def evaluate(self, expression: str, payload: Any) -> MappingOutcome:
        refused = self.check(expression)
        if refused:
            return MappingOutcome(status="error", problems=refused)
        try:
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        except (TypeError, ValueError, RecursionError, OverflowError):
            return MappingOutcome(status="error", problems=[_NOT_JSON])
        if len(data) > MAX_PAYLOAD_BYTES:
            return MappingOutcome(
                status="limit", problems=[_problem("limit", "The payload is too large to map.")]
            )
        header = {
            "expression": expression,
            "timebox_ms": MAPPING_TIMEBOX_MS,
            "max_depth": MAPPING_MAX_DEPTH,
            "max_output": MAPPING_MAX_OUTPUT_BYTES,
        }
        try:
            answer = run_in_envelope(
                CHILD_ENTRY,
                header,
                data,
                timeout_s=MAPPING_MAX_SECONDS,
                memory_limit_mb=MAPPING_MAX_MEMORY_BYTES // (1024 * 1024),
                max_answer=MAPPING_MAX_OUTPUT_BYTES + 4096,
            )
        except Breach:
            return MappingOutcome(
                status="limit", problems=[_problem("limit", "The mapping used too much time.")]
            )
        return self._outcome(answer.payload)

    @staticmethod
    def _outcome(raw: bytes) -> MappingOutcome:
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            return MappingOutcome(
                status="error", problems=[_problem("engine_error", "The mapping engine failed.")]
            )
        status = body.get("status") if isinstance(body, dict) else None  # pyright: ignore[reportUnknownMemberType]
        if status == "limit":
            return MappingOutcome(
                status="limit", problems=[_problem("limit", "The mapping used too much.")]
            )
        if status != "ok":
            code = str(body.get("code", ""))[:16] if isinstance(body, dict) else ""  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            suffix = f" ({code})" if code else ""
            return MappingOutcome(
                status="error",
                problems=[_problem("mapping_error", f"The mapping failed{suffix}.")],
            )
        result = body.get("result")  # pyright: ignore[reportUnknownMemberType]
        items: list[Any]
        if result is None:
            items = []
        elif isinstance(result, dict):
            items = [result]
        elif isinstance(result, list):
            items = list(result)  # pyright: ignore[reportUnknownArgumentType]
        else:
            return _invalid("The mapping must give commands, not a bare value.")
        if len(items) > MAPPING_MAX_COMMANDS:
            return MappingOutcome(
                status="limit",
                problems=[
                    _problem("limit", f"At most {MAPPING_MAX_COMMANDS} commands per delivery.")
                ],
            )
        commands: list[MappedCommand] = []
        for position, item in enumerate(items, start=1):
            try:
                commands.append(MappedCommand.model_validate(item))
            except ValidationError as exc:
                return _invalid(f"Command {position}: {first_error(exc)}")
        return MappingOutcome(status="ok", commands=commands)


def _invalid(message: str) -> MappingOutcome:
    return MappingOutcome(
        status="invalid_output", problems=[_problem("invalid_output", message[:200])]
    )
