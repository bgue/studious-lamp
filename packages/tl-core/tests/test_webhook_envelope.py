"""The CloudEvents envelope, payload modes and the confidentiality seam."""

from __future__ import annotations

import json

import pytest
from tl_core.webhooks.envelope import (
    OpenPolicy,
    build_envelope,
    effective_mode,
    rfc3339,
    to_body,
)
from tl_core.webhooks.rows import OutboxRow
from tl_core.webhooks.uris import UriConfig, ce_type, urn

RID = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
OTHER = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
URIS = UriConfig("https://tl.example.com", "acme")


def row(**kw: object) -> OutboxRow:
    base = {
        "seq": 48211933,
        "event_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
        "scope": "project:P123",
        "event_type": "Workflow.Transitioned",
        "stream_id": RID,
        "stream_type": "core.Record",
        "stream_version": 7,
        "subject_id": RID,
        "subject_type": "core.Record",
        "subject_key": "47-1234-W012",
        "subject_version": 7,
        "actor": "user:jsmith",
        "recorded_at": "2026-10-09T03:14:07.000000+00:00",
        "correlation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
        "data": {
            "origin": {"id": RID, "key": "47-1234-W012", "type": "core.Record", "version": 7},
            "changes": {"status": ["FitUp", "Welded"]},
            "links": [],
            "detail": {"from_state": "FitUp", "to_state": "Welded"},
        },
    }
    base.update(kw)
    return OutboxRow(**base)  # type: ignore[arg-type]


def test_naming_and_uris_follow_the_brief() -> None:
    assert ce_type("Record.Created") == "tl.core.Record.Created.v1"
    assert ce_type("Pset.ValuesSet", 2) == "tl.core.Pset.ValuesSet.v2"
    assert urn(RID) == f"urn:tl:{RID}"
    assert URIS.source("project:P123") == "https://tl.example.com/c/acme/p/P123"
    assert URIS.source("company") == "https://tl.example.com/c/acme"
    assert (
        URIS.record_uri("project:P123", "core.Record", "47-1234-W012", RID, 7)
        == "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7"
    )
    assert URIS.record_uri("company", None, None, RID).endswith(f"/r/core.Record/{RID}")
    with pytest.raises(ValueError):
        ce_type("lower.case")


def test_thin_carries_the_envelope_and_origin_only() -> None:
    envelope = build_envelope(row(), "thin", URIS)
    assert envelope["specversion"] == "1.0"
    assert envelope["type"] == "tl.core.Workflow.Transitioned.v1"
    assert envelope["time"] == "2026-10-09T03:14:07.000000Z"
    assert envelope["subject"] == f"urn:tl:{RID}"
    assert envelope["tlseq"] == 48211933 and envelope["tlstreamversion"] == 7
    assert envelope["tlactor"] == "user:jsmith"
    assert envelope["datacontenttype"] == "application/json"
    assert set(envelope["data"]) == {"origin"}
    origin = envelope["data"]["origin"]
    assert origin["id"] == f"urn:tl:{RID}" and origin["version"] == 7
    assert origin["uri"].endswith("/r/core.Record/47-1234-W012@v7")


def test_delta_adds_changes_links_and_detail_full_adds_the_record() -> None:
    links = [{"rel": "belongs_to", "id": OTHER, "type": "core.Record", "key": "47-1234-S03"}]
    delta = build_envelope(row(), "delta", URIS, links=links)
    assert delta["data"]["changes"] == {"status": ["FitUp", "Welded"]}
    assert delta["data"]["detail"]["to_state"] == "Welded"
    assert delta["data"]["links"] == [
        {
            "rel": "belongs_to",
            "id": f"urn:tl:{OTHER}",
            "type": "core.Record",
            "key": "47-1234-S03",
            "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-S03",
        }
    ]
    assert "record" not in delta["data"]
    full = build_envelope(row(), "full", URIS, links=links, record={"id": RID, "version": 7})
    assert full["data"]["record"] == {"id": RID, "version": 7}


def test_a_subject_without_a_version_falls_back_to_the_stream_version() -> None:
    envelope = build_envelope(row(subject_version=None), "thin", URIS)
    assert envelope["data"]["origin"]["version"] == 7


def test_the_body_is_canonical_json_and_stable() -> None:
    envelope = build_envelope(row(), "delta", URIS)
    body = to_body(envelope)
    assert body == to_body(json.loads(body))
    assert " " not in body.split('"detail"')[0].replace('"user:jsmith"', "")
    assert body.startswith('{"data":')


def test_rfc3339_normalises_the_offset() -> None:
    assert rfc3339("2026-10-09T03:14:07.123456+00:00") == "2026-10-09T03:14:07.123456Z"
    assert rfc3339("2026-10-09T05:14:07.000000+02:00") == "2026-10-09T03:14:07.000000Z"


class ForceThin:
    def forced_mode(self, row: OutboxRow, requested: str) -> str:
        return "thin"

    def allows(self, row: OutboxRow, owner: str) -> bool:
        return True


class Raiser:
    def forced_mode(self, row: OutboxRow, requested: str) -> str:
        return "full"

    def allows(self, row: OutboxRow, owner: str) -> bool:
        return True


def test_the_confidentiality_seam_can_lower_but_never_raise_the_mode() -> None:
    assert effective_mode(OpenPolicy(), row(), "full") == "full"
    assert effective_mode(ForceThin(), row(), "full") == "thin"  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="never raise"):
        effective_mode(Raiser(), row(), "thin")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown payload mode"):
        effective_mode(OpenPolicy(), row(), "huge")
