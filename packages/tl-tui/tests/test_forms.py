"""Edit grouping and chained saves (P0-I2-T16)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient, get_path
from tl_core.ledger import ConcurrencyError
from tl_tui.forms import PsetBatch, pset_batches, save_record_edits

EDITS: dict[str, Any] = {
    "psets.valve_data.x.fat_witness_by": "@party:acme",
    "psets.valve_data.size_in": 8.0,
    "psets.prj.shutdown_tie_in.window": "SD-1",
    "psets.valve_data.seat_leakage": None,
}


def _setup() -> tuple[FakeClient, dict[str, Any]]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1002")
    assert record is not None
    return client, record


def test_pset_batches_group_by_pset_and_layer_with_relative_keys() -> None:
    client, _ = _setup()
    batches = pset_batches(client.metadata, EDITS)
    assert batches == [
        PsetBatch("valve_data", "standard", {"size_in": 8.0, "seat_leakage": None}),
        PsetBatch("valve_data", "custom", {"x.fat_witness_by": "@party:acme"}),
        PsetBatch("prj.shutdown_tie_in", "project", {"window": "SD-1"}),
    ]


@pytest.mark.parametrize(
    "path",
    [
        "psets.valve_data.nope",
        "psets.enrich.ai_classifier.valve_type",  # read-only enrichment field
        "psets.other.x",
    ],
)
def test_pset_batches_reject_unknown_and_read_only_paths(path: str) -> None:
    client, _ = _setup()
    with pytest.raises(ValueError):
        pset_batches(client.metadata, {path: "v"})


def test_save_sends_core_first_then_chained_pset_commands() -> None:
    client, record = _setup()
    outcome = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=record,
        meta=client.metadata,
        edits={"title": "Renamed", **EDITS},
    )
    assert outcome.ok and outcome.failed is None
    assert outcome.applied == [
        "core",
        "valve_data/standard",
        "valve_data/custom",
        "prj.shutdown_tie_in/project",
    ]
    assert [c.expected_version for c in client.set_pset_commands] == [
        record["version"] + 1,
        record["version"] + 2,
        record["version"] + 3,
    ]
    assert outcome.version == record["version"] + 4
    saved = client.get_record_by_id(record["id"])
    assert saved is not None
    assert saved["title"] == "Renamed" and saved["version"] == outcome.version
    assert get_path(saved["psets"], "valve_data.x.fat_witness_by") == "@party:acme"
    assert get_path(saved["psets"], "valve_data.size_in") == 8.0
    assert client.set_pset_commands[0].layer == "standard"
    assert client.set_pset_commands[0].source == "tui"


def test_save_stops_at_the_first_failure_and_reports_what_was_applied() -> None:
    client, record = _setup()

    original = client.set_pset_values
    calls = {"n": 0}

    def flaky(cmd: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConcurrencyError("someone else saved")
        return original(cmd)

    client.set_pset_values = flaky  # type: ignore[method-assign]
    outcome = save_record_edits(
        client, scope=SCOPE, actor="user:t", record=record, meta=client.metadata, edits=EDITS
    )
    assert not outcome.ok
    assert outcome.applied == ["valve_data/standard"]
    assert outcome.failed == "valve_data/custom"
    assert isinstance(outcome.error, ConcurrencyError)
    assert outcome.version == record["version"] + 1


def test_a_bad_path_sends_nothing() -> None:
    client, record = _setup()
    with pytest.raises(ValueError):
        save_record_edits(
            client,
            scope=SCOPE,
            actor="user:t",
            record=record,
            meta=client.metadata,
            edits={"title": "x", "psets.valve_data.nope": 1},
        )
    assert "update_record" not in client.calls and "set_pset_values" not in client.calls


def test_a_core_failure_stops_before_any_pset_command() -> None:
    client, record = _setup()
    record["version"] = 99  # stale
    outcome = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=record,
        meta=client.metadata,
        edits={"title": "x", **EDITS},
    )
    assert outcome.failed == "core" and outcome.applied == []
    assert client.set_pset_commands == []
