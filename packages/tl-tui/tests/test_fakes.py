"""The fake behaves like the real client where screens rely on it (P0-I2-T11)."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from fakes import SCOPE, FakeClient, get_path
from tl_core.ledger import ConcurrencyError
from tl_core.services.psets import SetPsetValues
from tl_tui.client import ClientInterface


def _cmd(
    record_id: str,
    version: int,
    pset: str,
    layer: Literal["standard", "custom", "project"],
    values: dict[str, Any],
) -> SetPsetValues:
    return SetPsetValues(
        actor="user:t",
        source="tui",
        scope=SCOPE,
        stream_id=record_id,
        expected_version=version,
        pset=pset,
        layer=layer,
        values=values,
    )


def test_fake_satisfies_protocol_and_seeds_three_valves() -> None:
    client: ClientInterface = FakeClient.with_valve_example()
    rows = client.list_records(SCOPE)
    assert [r["key"] for r in rows] == ["FV-1001", "FV-1002", "FV-1003"]
    assert [r["conformance"] for r in rows] == ["ok", "warning", "nonconformant"]


def test_set_pset_values_nests_custom_keys_and_bumps_version() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1002")
    assert record is not None
    result = client.set_pset_values(
        _cmd(record["id"], record["version"], "valve_data", "custom", {"x.fat_witness_by": "@p"})
    )
    assert result.version == record["version"] + 1
    updated = client.get_record_by_id(record["id"])
    assert updated is not None
    assert get_path(updated["psets"], "valve_data.x.fat_witness_by") == "@p"
    last = client.history(record["id"])[-1]
    assert last.event_type == "Pset.ValuesSet"
    assert last.payload["effective_schema_hash"] == client.metadata.effective_schema_hash


def test_stale_version_raises_concurrency_error() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    with pytest.raises(ConcurrencyError):
        client.set_pset_values(_cmd(record["id"], 99, "valve_data", "standard", {"size_in": 1.0}))


def test_conformance_levels_follow_the_fake_rules() -> None:
    client = FakeClient.with_valve_example()
    full = client.get_record(SCOPE, "FV-1002")
    bare = client.get_record(SCOPE, "FV-1003")
    assert full is not None and bare is not None
    report = client.conformance(full["id"])
    assert report.status == "warning"
    assert [i.path for i in report.issues] == ["psets.valve_data.seat_leakage"]
    bad = client.conformance(bare["id"])
    assert bad.status == "nonconformant"
    assert {i.rule for i in bad.issues} == {"required_in_state"}
