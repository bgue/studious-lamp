"""Dev resources: the event catalog and the schema graph of the core LinkML schema (brief 25.3).

Read-only resources, no tool (FANOUT D12). The catalog page, its index and one sample per event
type are read from the committed ``generated/`` files; the graph is built from the core schema
with LinkML's ``SchemaView`` on every read (nothing is cached).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from linkml_runtime.utils.schemaview import SchemaView
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from tl_schema import catalog

from tl_mcp.dev.guard import safe_child
from tl_mcp.dev.runtime import DevContext, guarded

CATALOG_DOCS_DIR = ("packages", "tl-schema", "src", "tl_schema", "generated", "docs")
CATALOG_PAGE = "event-catalog.md"
CORE_SCHEMA = ("schema", "core", "core.yaml")
CORE_SCHEMA_NAME = "tl_core"  # the name the core schema declares (`name: tl_core`)
CURRENT_STATE_TAG = "tl:current_state"
EVENT_TYPE_MAX_CHARS = 80
DESCRIPTION_MAX_CHARS = 200
SHOWN_EVENT_TYPES = 5

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _dump(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _catalog_page(repo_root: Path) -> str:
    docs = repo_root.joinpath(*CATALOG_DOCS_DIR)
    return safe_child(docs, CATALOG_PAGE, (".md",)).read_text(encoding="utf-8")


def _sample(event_type: str) -> dict[str, Any]:
    valid = catalog.event_types()
    if not event_type or len(event_type) > EVENT_TYPE_MAX_CHARS or event_type not in valid:
        shown = ", ".join(valid[:SHOWN_EVENT_TYPES])
        raise ResourceError(
            f"not a catalog event type (1 to {EVENT_TYPE_MAX_CHARS} characters); "
            f"the first valid ones are: {shown}"
        )
    return catalog.sample(event_type)


def _first_sentence(text: str | None) -> str:
    flat = " ".join((text or "").split())
    end = _SENTENCE_END.search(flat)
    sentence = flat[: end.end()] if end else flat
    if len(sentence) > DESCRIPTION_MAX_CHARS:
        sentence = sentence[: DESCRIPTION_MAX_CHARS - 3] + "..."
    return sentence


def _is_current_state(annotations: Any) -> bool:
    if CURRENT_STATE_TAG not in annotations:
        return False
    return str(annotations[CURRENT_STATE_TAG].value).lower() == "true"


def _graph(repo_root: Path) -> dict[str, Any]:
    """Classes, enums and edges of the core schema, sorted by name (see the module docstring)."""
    view = SchemaView(str(repo_root.joinpath(*CORE_SCHEMA)))
    classes = view.all_classes()
    enums = view.all_enums()
    class_names = set(classes)
    named = class_names | set(enums)

    class_docs: list[dict[str, Any]] = []
    enum_docs = [
        {
            "name": name,
            "values": sorted(str(text) for text in (enums[name].permissible_values or {})),
        }
        for name in sorted(enums)
    ]
    edges: list[dict[str, Any]] = []
    for name in sorted(classes):
        definition = classes[name]
        mixins = sorted(definition.mixins or [])
        slots = sorted(view.class_induced_slots(name), key=lambda slot: slot.name)
        class_docs.append(
            {
                "name": name,
                "is_a": definition.is_a,
                "mixins": mixins,
                "abstract": bool(definition.abstract),
                "current_state": _is_current_state(definition.annotations),
                "description": _first_sentence(definition.description),
                "slots": [
                    {
                        "name": slot.name,
                        "range": slot.range,
                        "required": bool(slot.required),
                        "multivalued": bool(slot.multivalued),
                    }
                    for slot in slots
                ],
            }
        )
        if definition.is_a:
            edges.append({"from": name, "to": definition.is_a, "kind": "is_a", "slot": None})
        for mixin in mixins:
            edges.append({"from": name, "to": mixin, "kind": "mixin", "slot": None})
        # Range edges come from the slots a class declares itself, so an inherited slot is drawn
        # once, from the class that declares it.
        for slot_name in sorted(view.class_slots(name, direct=True)):
            induced = view.induced_slot(slot_name, name)
            if induced.range in named:
                edges.append(
                    {"from": name, "to": induced.range, "kind": "range", "slot": slot_name}
                )

    return {
        "schema": CORE_SCHEMA_NAME,
        "classes": class_docs,
        "enums": enum_docs,
        "edges": edges,
    }


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.resource(
        "tl://dev/event-catalog",
        name="event_catalog",
        title="Event catalog (page)",
        description="The generated event catalog page: every event type that can reach a webhook.",
        mime_type="text/markdown",
    )
    def event_catalog() -> str:
        with guarded(ctx, "resource.event_catalog", error=ResourceError):
            return _catalog_page(ctx.repo_root)

    @server.resource(
        "tl://dev/event-catalog/index",
        name="event_catalog_index",
        title="Event catalog (index)",
        description="The catalog entries in event-type order (event_type, ce_type, schema, ...).",
        mime_type="application/json",
    )
    def event_catalog_index() -> str:
        with guarded(ctx, "resource.event_catalog_index", error=ResourceError):
            return _dump(catalog.index())

    @server.resource(
        "tl://dev/event-sample/{event_type}",
        name="event_sample",
        title="Event sample",
        description="One sample per event type: {payload, envelope} (a delta-mode CloudEvent).",
        mime_type="application/json",
    )
    def event_sample(event_type: str) -> str:
        with guarded(ctx, "resource.event_sample", {"event_type": event_type}, error=ResourceError):
            return _dump(_sample(event_type))

    @server.resource(
        "tl://dev/schema-graph",
        name="schema_graph",
        title="Schema graph (core)",
        description="Classes, enums and edges (is_a, mixin, range) of the core LinkML schema.",
        mime_type="application/json",
    )
    def schema_graph() -> str:
        with guarded(ctx, "resource.schema_graph", error=ResourceError):
            return _dump(_graph(ctx.repo_root))
