"""The outbox projector: one row per event, subjects, changes, determinism, atomicity."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tl_adapters.sqlite.uow import open_uow, rebuild_projections
from tl_core.projection.defaults import default_registry
from world import SCOPE, World

OUTBOX_SQL = "SELECT * FROM outbox_events ORDER BY seq"


def data(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row["data_json"])


def test_the_outbox_is_registered_last_and_sees_every_event_type() -> None:
    registry = default_registry()
    names = [p.name for p in registry.all()]
    assert names[-1] == "outbox"
    # The feed projector also sees every event (it makes event cards) and is registered just before.
    assert [p.name for p in registry.for_event("Something.Unheard")] == ["feed", "outbox"]
    assert names.index("core_record") < names.index("outbox")


def test_every_event_gets_exactly_one_row_with_the_event_facts(world: World) -> None:
    rid = world.record("P1-0001", title="Gate valve")
    world.retitle(rid, "Gate valve 47", version=1)
    rows = world.query(OUTBOX_SQL)
    events = world.query(
        "SELECT seq, event_id, event_type, stream_version FROM events ORDER BY seq"
    )
    assert [r["seq"] for r in rows] == [e["seq"] for e in events]
    assert [r["event_id"] for r in rows] == [e["event_id"] for e in events]
    first, second = rows
    assert (first["event_type"], first["scope"], first["subject_id"]) == (
        "Record.Created",
        SCOPE,
        rid,
    )
    assert (first["subject_type"], first["subject_key"], first["subject_version"]) == (
        "core.Record",
        "P1-0001",
        1,
    )
    assert first["recorded_at"].endswith("+00:00")
    assert json.loads(second["changed_fields_json"]) == ["title"]
    assert data(second)["changes"] == {"title": ["Gate valve", "Gate valve 47"]}
    assert data(second)["origin"]["version"] == 2
    assert data(second)["detail"] == {"changes": {"title": ["Gate valve", "Gate valve 47"]}}


def test_a_rolled_back_transaction_leaves_no_outbox_row(world: World) -> None:
    with pytest.raises(RuntimeError), world.factory() as uow:
        uow.append(
            stream_id="S1",
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=0,
            events=[_new("Record.Created", {"record_type": "t", "key": "K", "title": "T"})],
            actor="user:a",
            source="test",
            correlation_id="c",
        )
        raise RuntimeError("refuse the command")
    assert world.query("SELECT * FROM outbox_events") == []


def _new(event_type: str, payload: dict[str, Any]) -> Any:
    from tl_core.ledger import NewEvent

    return NewEvent(event_type=event_type, payload=payload)


def test_a_link_event_is_about_the_record_at_its_from_end(world: World) -> None:
    a, b = world.record("P1-A"), world.record("P1-B")
    link = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"
    world.append(
        "Link.Added",
        {"from_ref": a, "to_ref": b, "relation": "raised_against", "source": "manual"},
        stream_id=link,
        stream_type="core.Link",
    )
    world.append("Link.Verified", {}, stream_id=link, stream_type="core.Link")
    added, verified = world.query(OUTBOX_SQL)[-2:]
    for row in (added, verified):
        assert row["subject_id"] == a
        assert row["stream_id"] == link
        assert json.loads(row["related_ids_json"]) == [b]
        assert json.loads(row["link_relations_json"]) == ["raised_against"]
        assert row["subject_key"] == "P1-A"
        assert data(row)["links"] == [{"rel": "raised_against", "id": b}]


def test_a_file_event_is_about_the_record_of_the_file_and_carries_its_slot(world: World) -> None:
    rid = world.record("P1-F")
    fid = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8"
    world.append(
        "File.Uploaded",
        {
            "file_id": fid,
            "record_id": rid,
            "slot": "mtr",
            "revision": 1,
            "sha256": "a" * 64,
            "size": 3,
            "content_type": "text/plain",
            "filename": "m.txt",
            "status": "quarantined",
            "deduplicated": False,
        },
        stream_id=fid,
        stream_type="core.File",
    )
    world.append(
        "File.Processed",
        {"file_id": fid, "status": "available", "report": {}, "supersedes": []},
        stream_id=fid,
        stream_type="core.File",
    )
    uploaded, processed = world.query(OUTBOX_SQL)[-2:]
    for row in (uploaded, processed):
        assert row["subject_id"] == rid
        assert row["file_slot"] == "mtr"


def test_pset_values_are_flattened_to_dotted_paths(world: World) -> None:
    rid = world.record("P1-P")
    world.append(
        "Pset.ValuesSet",
        {
            "pset": "valve_data",
            "layer": "standard",
            "values": {"size_in": 4, "rating": {"class": 150}},
            "effective_schema_hash": "h",
        },
        stream_id=rid,
    )
    row = world.query(OUTBOX_SQL)[-1]
    assert json.loads(row["changed_fields_json"]) == [
        "psets.valve_data.rating.class",
        "psets.valve_data.size_in",
    ]
    assert data(row)["changes"]["psets.valve_data.size_in"] == [None, 4]


def test_a_workflow_transition_records_both_states_and_a_status_change(world: World) -> None:
    rid = world.record("P1-W")
    world.append(
        "Workflow.Transitioned",
        {
            "workflow": "doc",
            "workflow_version": 1,
            "from_state": "InReview",
            "to_state": "Issued",
            "transition": "issue",
        },
        stream_id=rid,
    )
    row = world.query(OUTBOX_SQL)[-1]
    assert (row["from_state"], row["to_state"]) == ("InReview", "Issued")
    assert data(row)["changes"] == {"status": ["InReview", "Issued"]}


def test_hashtags_are_collected_without_the_hash_sign(world: World) -> None:
    world.append("Feed.Posted", {"post_id": "p", "body": "x", "hashtags": ["#safety", "qa"]})
    assert json.loads(world.query(OUTBOX_SQL)[-1]["hashtags_json"]) == ["safety", "qa"]


def test_rebuilding_the_outbox_from_the_ledger_reproduces_the_rows(world: World) -> None:
    rid = world.record("P1-R")
    world.retitle(rid, "Renamed", version=1)
    world.append("Feed.Posted", {"post_id": "p", "body": "x", "hashtags": ["a"]})
    before = world.query(OUTBOX_SQL)
    replayed = rebuild_projections(world.path, types=["outbox"])
    assert replayed == len(before)
    assert world.query(OUTBOX_SQL) == before


def test_an_update_that_changes_psets_lists_leaf_paths(world: World) -> None:
    rid = world.record("P1-U")
    world.append(
        "Record.Updated",
        {"changes": {"psets": [{"a": {"x": 1, "y": 2}}, {"a": {"x": 1, "y": 3}, "b": 5}]}},
        stream_id=rid,
    )
    row = world.query(OUTBOX_SQL)[-1]
    assert data(row)["changes"] == {"psets.a.y": [2, 3], "psets.b": [None, 5]}


def test_open_uow_writes_outbox_rows_too(world: World) -> None:
    rid = world.record("P1-O")
    with open_uow(world.path, readonly=True) as uow:
        rows = uow.ledger.read_after(0)
    assert len(rows) == 1 and rid
