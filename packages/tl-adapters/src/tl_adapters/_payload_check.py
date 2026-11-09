"""Strict payload validation at append (P2-GUARD): each event payload against its generated model.

``TL_PAYLOAD_VALIDATION`` is ``off`` (default), ``collect`` or ``enforce``. ``collect`` records each
violation as ``(event_type, key, reason)`` in ``VIOLATIONS`` and logs it; the append goes on.
``enforce`` raises ``PayloadInvalid``. An event type with no payload class is reported (collect) and
never failed. The test session sets ``collect`` and writes ``VIOLATIONS`` to
``.gate/payload-violations.txt`` (root ``conftest.py``).
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

import tl_schema
from pydantic import BaseModel, ValidationError

log = logging.getLogger("tl.payload_validation")

#: ``(event_type, key, reason)`` -> number of times seen, for the whole process.
VIOLATIONS: Counter[tuple[str, str, str]] = Counter()
NO_CLASS = "no payload class"
MODES = ("off", "collect", "enforce")


class PayloadInvalid(ValueError):
    code = "payload_invalid"


def mode() -> str:
    value = os.environ.get("TL_PAYLOAD_VALIDATION", "off").strip().lower()
    return value if value in MODES else "off"


@cache
def payload_classes() -> dict[tuple[str, int], type[BaseModel] | None]:
    """``(event_type, schema_version)`` to the generated payload class, or ``None`` if absent."""
    root = Path(tl_schema.__file__).resolve().parent / "generated"
    from tl_schema.generated import models

    index = json.loads((root / "catalog" / "index.json").read_text(encoding="utf-8"))
    found: dict[tuple[str, int], type[BaseModel] | None] = {}
    for entry in index["events"]:
        cls = getattr(models, entry["payload_class"], None)
        found[(entry["event_type"], int(entry["version"]))] = (
            cls if isinstance(cls, type) and issubclass(cls, BaseModel) else None
        )
    return found


def check(event_type: str, schema_version: int, payload: dict[str, Any]) -> list[tuple[str, str]]:
    """``(key, reason)`` per violation; ``[(-, no payload class)]`` when there is no class."""
    cls = payload_classes().get((event_type, schema_version))
    if cls is None:
        return [("-", NO_CLASS)]
    try:
        cls.model_validate(payload)
    except ValidationError as exc:
        return [(".".join(str(p) for p in e["loc"]) or "-", e["type"]) for e in exc.errors()]
    return []


def validate_events(events: Iterable[Any]) -> None:
    """Apply the current mode to ``NewEvent``-like items (``event_type``, ``schema_version``,
    ``payload``). Does nothing when the mode is ``off``."""
    current = mode()
    if current == "off":
        return
    for event in events:
        problems = check(event.event_type, event.schema_version, event.payload)
        if current == "enforce":
            real = [p for p in problems if p[1] != NO_CLASS]
            if real:
                key, reason = real[0]
                raise PayloadInvalid(f"{event.event_type}: {key}: {reason}")
            continue
        for key, reason in problems:
            if VIOLATIONS[(event.event_type, key, reason)] == 0:
                log.warning("payload violation: %s %s %s", event.event_type, key, reason)
            VIOLATIONS[(event.event_type, key, reason)] += 1


def report_lines() -> list[str]:
    """Sorted ``event_type<TAB>key<TAB>reason<TAB>count`` lines."""
    return [f"{e}\t{k}\t{r}\t{n}" for (e, k, r), n in sorted(VIOLATIONS.items())]
