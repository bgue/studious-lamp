"""The restricted JSONata runtime ``jsonata-restricted@1`` (FANOUT D5; ADR-0017).

``MappingRuntime`` of the contract. Two halves:

**check** (an endpoint stores a mapping only when it returns nothing). The expression is parsed
**in the child of the envelope, never in the server**, and its syntax tree is walked against an
allow-list of node types (``inbound.profile``), which refuses function definitions and lambdas,
regular expressions, partial application, variable binding, transforms, descendants and parent
references, and any function not in ``MAPPING_ALLOWED_FUNCTIONS`` (``$eval``, ``$now``,
``$millis``, ``$random``, ``$match``, ``$replace``, ``$sift``, ``$each``, ``$map`` and the other
higher-order functions among them). The expression is at most ``profile.CHECK_MAX_CHARS`` long
and its tree ``MAX_AST_NODES`` nodes. A result is cached by the hash of the expression.

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

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any, cast

from pydantic import ValidationError

from tl_core.derivation.envelope import Breach, run_in_envelope
from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    MAPPING_ALLOWED_FUNCTIONS,
    MAPPING_LANGUAGE,
    MAPPING_MAX_COMMANDS,
    MAPPING_MAX_DEPTH,
    MAPPING_MAX_MEMORY_BYTES,
    MAPPING_MAX_OUTPUT_BYTES,
    MAPPING_MAX_SECONDS,
    MAPPING_TIMEBOX_MS,
    MappedCommand,
    MappingOutcome,
    Problem,
)
from tl_core.integration.inbound.profile import CHECK_MAX_CHARS

CHILD_ENTRY = "tl_core.integration.inbound.mapping_child:evaluate_entry"
#: A payload larger than this is not given to a mapping (the route's own cap is lower).
MAX_PAYLOAD_BYTES = 1024 * 1024
_NOT_JSON = Problem(code="not_json", message="The payload is not JSON.")
#: Authoring checks already made, by the hash of the expression (the answer depends on nothing
#: else). A bounded cache: a mapping is checked when it is stored, and again only if it changes.
_CHECKED: OrderedDict[str, list[Problem]] = OrderedDict()
_CHECK_CACHE_SIZE = 256
_CHECK_LOCK = threading.Lock()


class JsonataRestricted:
    """``MappingRuntime`` for ``jsonata-restricted@1``.

    The server never parses an expression: ``check`` and ``evaluate`` both hand it to the child of
    the ADR-0014 envelope, which parses it, walks its tree against the profile
    (``inbound.profile``) and, for ``evaluate``, runs it. Only the length is judged here.
    """

    language = MAPPING_LANGUAGE

    def check(self, expression: str) -> list[Problem]:
        if len(expression) > CHECK_MAX_CHARS:
            return [_problem("too_long", f"A mapping is at most {CHECK_MAX_CHARS} characters.")]
        key = hashlib.sha256(expression.encode("utf-8", errors="replace")).hexdigest()
        with _CHECK_LOCK:
            cached = _CHECKED.get(key)
            if cached is not None:
                _CHECKED.move_to_end(key)
                return list(cached)
        try:
            answer = self._child({"mode": "check", "expression": expression}, b"{}")
        except Breach:
            return [_problem("too_complex", "The expression took too long to check.")]
        body = _json(answer)
        problems = [_problem(str(p[0]), str(p[1])) for p in body.get("problems", []) if len(p) == 2]
        if body.get("status") not in ("ok", "refused"):
            return [_problem("engine_error", "The mapping engine failed.")]
        with _CHECK_LOCK:
            _CHECKED[key] = problems
            while len(_CHECKED) > _CHECK_CACHE_SIZE:
                _CHECKED.popitem(last=False)
        return list(problems)

    def evaluate(self, expression: str, payload: Any) -> MappingOutcome:
        if len(expression) > CHECK_MAX_CHARS:
            return MappingOutcome(status="error", problems=self.check(expression))
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
            answer = self._child(header, data)
        except Breach:
            return MappingOutcome(
                status="limit", problems=[_problem("limit", "The mapping used too much time.")]
            )
        return self._outcome(answer)

    @staticmethod
    def _child(header: dict[str, Any], data: bytes) -> bytes:
        return run_in_envelope(
            CHILD_ENTRY,
            {**header, "allowed": sorted(MAPPING_ALLOWED_FUNCTIONS)},
            data,
            timeout_s=MAPPING_MAX_SECONDS,
            memory_limit_mb=MAPPING_MAX_MEMORY_BYTES // (1024 * 1024),
            max_answer=MAPPING_MAX_OUTPUT_BYTES + 4096,
        ).payload

    @staticmethod
    def _outcome(raw: bytes) -> MappingOutcome:
        body = _json(raw)
        if not body:
            return MappingOutcome(
                status="error", problems=[_problem("engine_error", "The mapping engine failed.")]
            )
        status = body.get("status")
        if status == "refused":
            refused = [_problem(str(p[0]), str(p[1])) for p in _pairs(body.get("problems"))]
            return MappingOutcome(status="error", problems=refused)
        if status == "limit":
            return MappingOutcome(
                status="limit", problems=[_problem("limit", "The mapping used too much.")]
            )
        if status != "ok":
            code = str(body.get("code", ""))[:16]
            suffix = f" ({code})" if code else ""
            return MappingOutcome(
                status="error",
                problems=[_problem("mapping_error", f"The mapping failed{suffix}.")],
            )
        result: Any = body.get("result")
        items: list[Any]
        if result is None:
            items = []
        elif isinstance(result, dict):
            items = [result]
        elif isinstance(result, list):
            items = list(cast("list[Any]", result))
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
                return _invalid(
                    f"Command {position}: {first_error(exc, MappedCommand.model_fields)}"
                )
        return MappingOutcome(status="ok", commands=commands)


def _problem(code: str, message: str) -> Problem:
    return Problem(code=code, message=message)


def _pairs(value: Any) -> list[list[Any]]:
    """The ``[code, message]`` pairs of an answer, whatever else it holds."""
    if not isinstance(value, list):
        return []
    items = cast("list[Any]", value)
    return [
        cast("list[Any]", p)
        for p in items
        if isinstance(p, list) and len(cast("list[Any]", p)) == 2
    ]


def _json(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    return cast("dict[str, Any]", body) if isinstance(body, dict) else {}


def _invalid(message: str) -> MappingOutcome:
    return MappingOutcome(
        status="invalid_output", problems=[_problem("invalid_output", message[:200])]
    )
