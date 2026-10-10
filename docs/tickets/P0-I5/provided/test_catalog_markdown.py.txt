"""The Markdown page of the event catalog (P0-I5-T21)."""

from __future__ import annotations

import copy
import json
import re

import pytest
from tl_schema.catalog_markdown import render_catalog_markdown
from tl_schema.catalog_types import EventTypeInfo


def make(
    event_type: str, title: str, properties: dict[str, object], required: list[str]
) -> EventTypeInfo:
    ce_type = f"tl.core.{event_type}.v1"
    return EventTypeInfo(
        event_type=event_type,
        version=1,
        ce_type=ce_type,
        title=title,
        description=f"{title} Extra sentence.",
        payload_class=event_type.replace(".", "") + "Payload",
        payload_schema={"type": "object", "properties": properties, "required": required},
        envelope_schema={"type": "object"},
        sample_payload={},
        sample_envelope={"type": ce_type, "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", "tlseq": 5},
    )


CREATED = make(
    "Record.Created",
    "A record was created.",
    {
        "title": {"type": "string", "description": "Title of the record."},
        "psets": {"description": "Initial values | keyed by pset.\nSecond line."},
        "description": {"type": ["string", "null"]},
        "confidence": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    ["title"],
)
TRANSITIONED = make("Workflow.Transitioned", "A record moved to another state.", {}, [])


def test_the_page_starts_with_the_title_and_the_intro() -> None:
    page = render_catalog_markdown([CREATED, TRANSITIONED])
    lines = page.split("\n")
    assert lines[0] == "# Throughline event catalog"
    assert lines[1] == ""
    assert "CloudEvents 1.0" in lines[2] and "Standard Webhooks" in lines[2]
    assert "`thin`, `delta` and `full`" in lines[2]
    assert "dedupe on the event `id`" in lines[2]
    assert page.endswith("\n") and not page.endswith("\n\n")


def test_the_title_is_a_parameter() -> None:
    assert render_catalog_markdown([CREATED], title="My events").startswith("# My events\n")


def test_the_index_lists_every_event_type_sorted_with_anchor_links() -> None:
    page = render_catalog_markdown([TRANSITIONED, CREATED])
    assert "## Event types\n\n| Event type | CloudEvents type | Summary |\n|---|---|---|\n" in page
    first = (
        "| [`Record.Created`](#recordcreated) | `tl.core.Record.Created.v1` | "
        "A record was created. |"
    )
    second = (
        "| [`Workflow.Transitioned`](#workflowtransitioned) | "
        "`tl.core.Workflow.Transitioned.v1` | A record moved to another state. |"
    )
    assert page.index(first) < page.index(second)


def test_each_event_type_has_a_section_named_by_its_type_with_the_facts() -> None:
    page = render_catalog_markdown([CREATED, TRANSITIONED])
    assert page.index("\n## Record.Created\n") < page.index("\n## Workflow.Transitioned\n")
    section = page.split("\n## Record.Created\n")[1].split("\n## Workflow.Transitioned\n")[0]
    assert section.startswith("\nA record was created. Extra sentence.\n")
    assert "- CloudEvents type: `tl.core.Record.Created.v1`" in section
    assert "- Ledger payload class: `RecordCreatedPayload`" in section
    assert "- Version: 1" in section


def test_the_anchor_of_a_heading_matches_the_index_link() -> None:
    page = render_catalog_markdown([CREATED, TRANSITIONED])
    for heading in re.findall(r"^## (\w+\.\w+)$", page, flags=re.M):
        assert f"(#{heading.replace('.', '').lower()})" in page


def test_the_field_table_is_sorted_and_derives_type_required_and_description() -> None:
    page = render_catalog_markdown([CREATED])
    table = page.split("### Payload fields\n\n")[1].split("\n\n")[0].split("\n")
    assert table[0] == "| Field | Type | Required | Description |"
    assert table[1] == "|---|---|---|---|"
    assert table[2:] == [
        "| `confidence` | number or null | no |  |",
        "| `description` | string or null | no |  |",
        "| `psets` | any | no | Initial values \\| keyed by pset. Second line. |",
        "| `title` | string | yes | Title of the record. |",
    ]


def test_an_event_without_fields_says_so() -> None:
    page = render_catalog_markdown([TRANSITIONED])
    assert "### Payload fields\n\nNo fields.\n" in page


def test_the_sample_is_pretty_printed_sorted_json_in_a_fence() -> None:
    page = render_catalog_markdown([CREATED])
    block = page.split("### Sample delivered event\n\n```json\n")[1].split("\n```")[0]
    assert json.loads(block) == CREATED.sample_envelope
    assert block == json.dumps(CREATED.sample_envelope, indent=2, sort_keys=True)


def test_an_empty_catalog_has_a_page_with_no_table() -> None:
    page = render_catalog_markdown([])
    assert "## Event types\n\nNo event types.\n" in page
    assert "|---|" not in page


def test_the_output_is_deterministic_independent_of_order_and_leaves_inputs_alone() -> None:
    before = copy.deepcopy(CREATED)
    assert render_catalog_markdown([CREATED, TRANSITIONED]) == render_catalog_markdown(
        [TRANSITIONED, CREATED]
    )
    assert CREATED == before


def test_a_duplicate_event_type_is_refused() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        render_catalog_markdown([CREATED, CREATED])
