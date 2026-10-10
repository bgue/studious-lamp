"""Read the committed event catalog at runtime (``generated/catalog``).

The catalog is generated from LinkML by ``tl_schema.generators.catalog`` and committed, so the
runtime reads files instead of loading LinkML: ``tl webhook test`` sends a catalog sample, the
contract tests validate delivered events against the schemas.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast


def _read(relative: str) -> Any:
    resource = files("tl_schema.generated").joinpath("catalog", *relative.split("/"))
    return json.loads(resource.read_text(encoding="utf-8"))


def index() -> list[dict[str, Any]]:
    """The catalog entries in event-type order (``event_type``, ``ce_type``, ``schema``, ...)."""
    return cast("list[dict[str, Any]]", _read("index.json")["events"])


def event_types() -> list[str]:
    return [str(entry["event_type"]) for entry in index()]


def _entry(event_type: str) -> dict[str, Any]:
    for entry in index():
        if entry["event_type"] == event_type:
            return entry
    raise KeyError(f"no such event type in the catalog: {event_type}")


def envelope_schema(event_type: str) -> dict[str, Any]:
    """JSON Schema of the CloudEvent delivered for ``event_type``."""
    return cast("dict[str, Any]", _read(str(_entry(event_type)["schema"])))


def sample(event_type: str) -> dict[str, Any]:
    """``{"payload": <ledger payload>, "envelope": <delta-mode CloudEvent>}`` for ``event_type``."""
    return cast("dict[str, Any]", _read(str(_entry(event_type)["sample"])))


def asyncapi() -> dict[str, Any]:
    return cast("dict[str, Any]", _read("asyncapi.json"))
