"""The child side of a mapping evaluation (FANOUT D5): runs inside ``run_in_envelope``.

``evaluate_entry`` is the entry point the envelope calls in a fresh interpreter with a scrubbed
environment, a memory limit and a wall clock. It imports the standard library, ``jsonata`` and
``inbound.profile`` (which imports only those). It checks the expression against the profile
before it runs anything, reads the payload from the data block, evaluates with the library's own
time box and depth bound, and answers a tag and JSON bytes that the parent parses with ``json``
(nothing is unpickled). The JSONata library has no input or output function, and the profile
refuses ``$eval``; the limits do not confine the filesystem or the network (ADR-0014 known limit).
"""

# jsonata-python ships no type information; its objects are untyped here.
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportArgumentType=false

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

TAG_RESULT = b"M"


def _answer(body: dict[str, Any]) -> tuple[bytes, bytes]:
    return TAG_RESULT, json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def evaluate_entry(header: Mapping[str, Any], data: bytes) -> tuple[bytes, bytes]:
    """Evaluate ``header["expression"]`` over the JSON in ``data``.

    The answer is one of ``{"status": "ok", "result": ...}``, ``{"status": "error", "code": ...}``
    (a JSONata error: only its code) or ``{"status": "limit"}`` (the library's time or depth box,
    or an output over ``max_output``).
    """
    from jsonata import Jsonata, jexception

    from tl_core.integration.inbound.profile import check_expression

    # The profile is checked here, in the child, before anything is evaluated: the parent never
    # parses an expression. ``mode`` "check" is the authoring check and evaluates nothing.
    problems = check_expression(str(header["expression"]), header["allowed"])
    if problems or header.get("mode") == "check":
        return _answer(
            {"status": "refused" if problems else "ok", "problems": [list(p) for p in problems]}
        )
    try:
        payload = json.loads(data)
        expression = Jsonata(
            str(header["expression"]),
            timeout=int(header["timebox_ms"]),
            stack=int(header["max_depth"]),
        )
        result = expression.evaluate(payload)
    except jexception.JException as exc:
        code = str(getattr(exc, "error", "") or "")
        if code in ("D1012", "U1001"):  # evaluation timeout; stack overflow
            return _answer({"status": "limit"})
        return _answer({"status": "error", "code": code[:16]})
    except RecursionError:
        return _answer({"status": "limit"})
    except (ValueError, TypeError):
        return _answer({"status": "error", "code": "invalid_input"})
    try:
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return _answer({"status": "error", "code": "not_json"})
    if len(text.encode()) > int(header["max_output"]):
        return _answer({"status": "limit"})
    return TAG_RESULT, ('{"status":"ok","result":' + text + "}").encode()
