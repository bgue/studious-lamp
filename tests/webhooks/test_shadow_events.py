"""The proposal of a shadow enrichment value carries the value: no webhook gets it (second
security review, re-check finding 1)."""

from __future__ import annotations

import json
from typing import Any

from world import World

STREAM = "core.EnrichmentValue"


def proposal(state: str) -> dict[str, Any]:
    return {
        "value_id": "V1",
        "target": {"id": "r1", "record_type": "core.Record"},
        "property_path": "enrich.e.p",
        "value": "alpha",
        "enricher": "e",
        "enricher_version": "1",
        "confidence": 0.5,
        "inputs": [],
        "model_ref": None,
        "produced_at": "2026-10-19T00:00:00Z",
        "acceptance_state": state,
    }


def test_a_shadow_proposal_is_never_sent_and_a_proposed_one_is(world: World) -> None:
    sid = world.subscribe(filter={"event_types": ["Enrichment.*"]}).subscription_id
    world.append(
        "Enrichment.Proposed", proposal("shadow"), stream_id="V-SHADOW", stream_type=STREAM
    )
    world.append(
        "Enrichment.Proposed", proposal("proposed"), stream_id="V-OPEN", stream_type=STREAM
    )
    world.dispatcher().run_until_idle()
    rows = world.query("SELECT body FROM wh_delivery WHERE subscription_id = :s", s=sid)
    assert len(rows) == 1
    assert "V-SHADOW" not in json.dumps(rows, default=str)
    assert "V-OPEN" in str(rows[0]["body"])


def test_a_replay_does_not_send_it_either(world: World) -> None:
    sid = world.subscribe(filter={"event_types": ["Enrichment.*"]}, mode="full").subscription_id
    world.append(
        "Enrichment.Proposed", proposal("shadow"), stream_id="V-SHADOW", stream_type=STREAM
    )
    world.dispatcher().replay(sid, 0, 10_000)
    assert world.query("SELECT 1 FROM wh_delivery WHERE subscription_id = :s", s=sid) == []
