# pyright: basic
"""Event catalog generator (brief 18.3): from LinkML event classes to schemas, samples and docs.

Input: the classes in ``schema/core/events.yaml`` that carry the annotation
``tl:event_type`` (``tl:event_version``, ``tl:sample_changes`` and ``tl:sample_links`` are
optional). Output, all deterministic and committed under ``generated/``:

* ``catalog/schemas/<Type>.v<N>.json``: JSON Schema (2020-12) of the CloudEvent a subscriber
  receives for that event type: ``type`` fixed to ``tl.core.<Type>.v<N>``, ``data.detail``
  described by the payload class (payloads are open: extra keys are allowed, new optional fields
  are additive).
* ``catalog/samples/<Type>.v<N>.json``: ``{"payload": ..., "envelope": ...}``, a sample ledger
  payload (the class ``examples`` value) and the delta-mode envelope built from it. Both validate
  against the schemas; the contract tests check that.
* ``catalog/index.json``: the event types in order, with file names.
* ``catalog/asyncapi.json``: the AsyncAPI 3 document (``catalog_asyncapi``).
* ``docs/event-catalog.md``: the browsable page (``catalog_markdown``).

The LinkML ``Any`` type (a JSON column) becomes "any JSON value" in the schemas, arrays included.
"""

from __future__ import annotations

import copy
import json
import re
from contextlib import chdir
from pathlib import Path
from typing import Any

from linkml.generators.jsonschemagen import JsonSchemaGenerator
from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.catalog_asyncapi import asyncapi_document
from tl_schema.catalog_markdown import render_catalog_markdown
from tl_schema.catalog_types import EventTypeInfo

ROOT_SCHEMA = "core.yaml"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_HOST = "https://tl.example.com"
SAMPLE_IDS = {
    "event": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
    "record": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
    "correlation": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
}


class CatalogError(ValueError):
    """The event classes cannot be turned into a catalog."""


def _annotation(element: Any, tag: str) -> str | None:
    annotations = element.annotations
    if not annotations or tag not in annotations:
        return None
    return str(annotations[tag].value)


def ce_type(event_type: str, version: int) -> str:
    return f"tl.core.{event_type}.v{version}"


def file_stem(event_type: str, version: int) -> str:
    return f"{event_type}.v{version}"


def _inline_any(node: Any) -> Any:
    """Replace ``$ref: Any`` by "any JSON value" (``{}``) and collapse ``anyOf [any, null]``."""
    if isinstance(node, list):
        return [_inline_any(item) for item in node]
    if not isinstance(node, dict):
        return node
    if node.get("$ref") == "#/$defs/Any":
        return {}
    out = {key: _inline_any(value) for key, value in node.items()}
    options = out.get("anyOf")
    if isinstance(options, list) and any(option == {} for option in options):
        out.pop("anyOf")
    return out


def _first_sentence(text: str) -> str:
    flat = " ".join(text.split())
    match = re.match(r"^(.*?[.!?])(?:\s|$)", flat)
    return match.group(1) if match else flat


def _resolve(defs: dict[str, Any], name: str) -> dict[str, Any]:
    """A class from ``$defs`` with every nested class definition inlined."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/") and ref != "#/$defs/Any":
            merged = walk(copy.deepcopy(defs[ref.removeprefix("#/$defs/")]))
            merged.update({k: walk(v) for k, v in node.items() if k != "$ref"})
            return merged
        return {key: walk(value) for key, value in node.items()}

    return _inline_any(walk(copy.deepcopy(defs[name])))


def _open(schema: dict[str, Any]) -> dict[str, Any]:
    schema = copy.deepcopy(schema)
    schema.pop("examples", None)
    schema["additionalProperties"] = True
    return schema


def build_events(schema_dir: Path) -> list[EventTypeInfo]:
    """The catalog entries, sorted by event type. Runs inside ``schema_dir``."""
    with chdir(schema_dir):
        view = SchemaView(ROOT_SCHEMA)
        defs = json.loads(JsonSchemaGenerator(ROOT_SCHEMA).serialize())["$defs"]
        found: list[EventTypeInfo] = []
        for class_name in sorted(view.all_classes()):
            definition: Any = view.get_class(class_name)
            event_type = _annotation(definition, "tl:event_type")
            if event_type is None:
                continue
            version = int(_annotation(definition, "tl:event_version") or "1")
            examples: Any = definition.examples
            if not examples:
                raise CatalogError(f"{class_name}: an event class needs an `examples` sample")
            sample_payload = json.loads(examples[0].value)
            payload_schema = _open(_resolve(defs, class_name))
            title = _first_sentence(str(definition.description))
            changes = json.loads(_annotation(definition, "tl:sample_changes") or "{}")
            links = json.loads(_annotation(definition, "tl:sample_links") or "[]")
            envelope_schema = _envelope_schema(defs, event_type, version, payload_schema)
            found.append(
                EventTypeInfo(
                    event_type=event_type,
                    version=version,
                    ce_type=ce_type(event_type, version),
                    title=title,
                    description=" ".join(str(definition.description).split()),
                    payload_class=class_name,
                    payload_schema=payload_schema,
                    envelope_schema=envelope_schema,
                    sample_payload=sample_payload,
                    sample_envelope=_sample_envelope(
                        event_type, version, sample_payload, changes, links
                    ),
                )
            )
    names = [e.event_type for e in found]
    if len(set(names)) != len(names):
        raise CatalogError("two event classes declare the same tl:event_type")
    return sorted(found, key=lambda e: e.event_type)


def _envelope_schema(
    defs: dict[str, Any], event_type: str, version: int, payload_schema: dict[str, Any]
) -> dict[str, Any]:
    schema = _resolve(defs, "CloudEvent")
    properties = schema["properties"]
    properties["type"] = {**properties["type"], "const": ce_type(event_type, version)}
    properties["dataschema"] = {
        **properties["dataschema"],
        "const": f"{SCHEMA_HOST}/schema/events/{event_type}/{version}",
    }
    data = properties["data"]
    data["additionalProperties"] = True
    detail = copy.deepcopy(payload_schema)
    detail["description"] = properties["data"]["properties"]["detail"].get("description", "")
    data["properties"]["detail"] = detail
    schema.pop("examples", None)
    ordered = {
        "$schema": DRAFT,
        "$id": f"{SCHEMA_HOST}/schema/events/{event_type}/{version}",
        "title": ce_type(event_type, version),
    }
    ordered.update(schema)
    return ordered


def _sample_envelope(
    event_type: str,
    version: int,
    payload: dict[str, Any],
    changes: dict[str, Any],
    links: list[dict[str, Any]],
) -> dict[str, Any]:
    record = SAMPLE_IDS["record"]
    base = f"{SCHEMA_HOST}/c/acme/p/P123"
    return {
        "specversion": "1.0",
        "id": SAMPLE_IDS["event"],
        "source": base,
        "type": ce_type(event_type, version),
        "time": "2026-10-09T03:14:07.000000Z",
        "subject": f"urn:tl:{record}",
        "dataschema": f"{SCHEMA_HOST}/schema/events/{event_type}/{version}",
        "datacontenttype": "application/json",
        "tlseq": 48211933,
        "tlstreamversion": 7,
        "tlcorrelationid": SAMPLE_IDS["correlation"],
        "tlactor": "user:jsmith",
        "data": {
            "origin": {
                "id": f"urn:tl:{record}",
                "key": "47-1234-W012",
                "type": "core.Record",
                "uri": f"{base}/r/core.Record/47-1234-W012@v7",
                "version": 7,
                "api": f"{SCHEMA_HOST}/api/v1/p/P123/records/{record}",
            },
            "changes": changes,
            "links": links,
            "detail": payload,
        },
    }


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def generate_from(schema_dir: Path) -> dict[str, str]:
    events = build_events(schema_dir)
    files: dict[str, str] = {}
    index: list[dict[str, Any]] = []
    for event in events:
        stem = file_stem(event.event_type, event.version)
        files[f"catalog/schemas/{stem}.json"] = _dump(event.envelope_schema)
        files[f"catalog/samples/{stem}.json"] = _dump(
            {"payload": event.sample_payload, "envelope": event.sample_envelope}
        )
        index.append(
            {
                "event_type": event.event_type,
                "version": event.version,
                "ce_type": event.ce_type,
                "title": event.title,
                "payload_class": event.payload_class,
                "schema": f"schemas/{stem}.json",
                "sample": f"samples/{stem}.json",
            }
        )
    files["catalog/index.json"] = _dump({"events": index})
    files["catalog/asyncapi.json"] = _dump(asyncapi_document(events))
    files["docs/event-catalog.md"] = render_catalog_markdown(events)
    return files


def generate(schema_dir: Path) -> dict[str, str]:
    """Entry point used by ``tl_schema.generate``."""
    return generate_from(schema_dir)
