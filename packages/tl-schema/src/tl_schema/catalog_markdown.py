"""Browsable Markdown page of the event catalog (brief 18.3).

``render_catalog_markdown`` is a pure function of its ``EventTypeInfo`` inputs: the same events in
any order give the same page, and the inputs are not modified.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from tl_schema.catalog_types import EventTypeInfo

INTRO = (
    "Every ledger event type that can reach a webhook subscriber, generated from the LinkML event "
    "classes. Each event arrives as a CloudEvents 1.0 JSON message signed with Standard Webhooks "
    "headers; the payload modes are `thin`, `delta` and `full`. "
    "Receivers dedupe on the event `id`. "
    "A request sent by `tl webhook test` carries the extra header `webhook-test: 1`; real "
    "deliveries never do."
)

_INDEX_HEADER = "| Event type | CloudEvents type | Summary |"
_INDEX_RULE = "|---|---|---|"
_FIELD_HEADER = "| Field | Type | Required | Description |"
_FIELD_RULE = "|---|---|---|---|"


def render_catalog_markdown(
    events: Sequence[EventTypeInfo], *, title: str = "Throughline event catalog"
) -> str:
    """The catalog page for ``events``. Pure and deterministic. See the ticket."""
    seen: set[str] = set()
    for event in events:
        if event.event_type in seen:
            raise ValueError("duplicate event type in the catalog")
        seen.add(event.event_type)
    ordered = sorted(events, key=lambda e: e.event_type)
    lines: list[str] = [f"# {title}", "", INTRO, "", "## Event types", ""]
    if not ordered:
        lines.append("No event types.")
    else:
        lines += [_INDEX_HEADER, _INDEX_RULE]
        lines += [_index_row(event) for event in ordered]
    for event in ordered:
        lines += _section(event)
    return "\n".join(lines) + "\n"


def _anchor(event_type: str) -> str:
    return event_type.replace(".", "").lower()


def _index_row(event: EventTypeInfo) -> str:
    return (
        f"| [`{event.event_type}`](#{_anchor(event.event_type)}) | `{event.ce_type}` | "
        f"{event.title} |"
    )


def _section(event: EventTypeInfo) -> list[str]:
    rows = _field_rows(event.payload_schema)
    table = [_FIELD_HEADER, _FIELD_RULE, *rows] if rows else ["No fields."]
    sample = json.dumps(event.sample_envelope, indent=2, sort_keys=True)
    return [
        "",
        f"## {event.event_type}",
        "",
        event.description.strip(),
        "",
        f"- CloudEvents type: `{event.ce_type}`",
        f"- Ledger payload class: `{event.payload_class}`",
        f"- Version: {event.version}",
        "",
        "### Payload fields",
        "",
        *table,
        "",
        "### Sample delivered event",
        "",
        "```json",
        sample,
        "```",
    ]


def _field_rows(payload_schema: dict[str, Any]) -> list[str]:
    """One table row per property of ``payload_schema``, sorted by name."""
    raw_properties: object = payload_schema.get("properties", {})
    if not isinstance(raw_properties, dict):
        return []
    properties = cast(dict[str, Any], raw_properties)
    required = _required_names(payload_schema.get("required"))
    rows: list[str] = []
    for name in sorted(properties):
        raw_prop: object = properties[name]
        prop: dict[str, Any] = cast(dict[str, Any], raw_prop) if isinstance(raw_prop, dict) else {}
        is_required = "yes" if name in required else "no"
        rows.append(f"| `{name}` | {_type_text(prop)} | {is_required} | {_cell_text(prop)} |")
    return rows


def _required_names(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {name for name in cast(list[Any], raw) if isinstance(name, str)}


def _type_names(raw: object) -> list[str]:
    """A JSON Schema ``type``: a string, or a list of strings (non-strings are skipped)."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [name for name in cast(list[Any], raw) if isinstance(name, str)]
    return []


def _type_text(prop: dict[str, Any]) -> str:
    """The Type cell: ``type``, else the typed options of ``anyOf``, else ``any``."""
    direct = _type_names(prop.get("type"))
    if direct:
        return " or ".join(direct)
    options: object = prop.get("anyOf")
    if isinstance(options, list):
        names: list[str] = []
        for option in cast(list[Any], options):
            if isinstance(option, dict):
                names += _type_names(cast(dict[str, Any], option).get("type"))
        if names:
            return " or ".join(names)
    return "any"


def _cell_text(prop: dict[str, Any]) -> str:
    """The Description cell: whitespace collapsed to single spaces, ``|`` escaped."""
    description = prop.get("description")
    text = description if isinstance(description, str) else ""
    return " ".join(text.split()).replace("|", "\\|")
