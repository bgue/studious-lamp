"""No client, rule or mapping writes the `enrich` or `src` layer through a record command
(second security review, finding 1).

`SetPsetValues` has always refused the roots; `CreateRecord.psets` and `UpdateRecord.changes
["psets"]` did not, so any person, rule step or inbound mapping could forge an enrichment value.
The check is in the two services, so every entry point is covered: this file drives the services,
a rule, a mapping, the API and an agent's proposal.
"""

from __future__ import annotations

from typing import Any

import pytest
from intworld import PERSON, SCOPE, World
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.errors import LayerError
from tl_core.services.records import handle_create_record, handle_update_record

FORGED = {"enrich.doc_classifier": {"doc_type": "DRW"}}


@pytest.mark.parametrize("name", ["enrich.doc_classifier", "enrich", "src.import", "src"])
def test_create_record_refuses_a_pset_under_a_read_only_root(world: World, name: str) -> None:
    with pytest.raises(LayerError), world.factory() as uow:
        handle_create_record(
            uow,
            CreateRecord(
                actor=PERSON, source="test", scope=SCOPE, record_type="core.Record",
                title="T", key="X-1", psets={name: {"a": 1}},
            ),
        )  # fmt: skip
    assert world.rows("SELECT 1 FROM cur_core_record") == []


def test_create_record_still_takes_an_ordinary_pset(world: World) -> None:
    with world.factory() as uow:
        handle_create_record(
            uow,
            CreateRecord(
                actor=PERSON, source="test", scope=SCOPE, record_type="core.Record",
                title="T", key="X-1", psets={"nde": {"a": 1}},
            ),
        )  # fmt: skip
    assert len(world.rows("SELECT 1 FROM cur_core_record")) == 1


def update(world: World, record_id: str, psets: dict[str, Any]) -> None:
    with world.factory() as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor=PERSON, source="test", scope=SCOPE, stream_id=record_id,
                expected_version=1, changes={"psets": psets},
            ),
        )  # fmt: skip


def test_update_record_refuses_to_add_or_change_a_read_only_pset(world: World) -> None:
    record_id = world.record("X-1")
    with pytest.raises(LayerError):
        update(world, record_id, FORGED)
    update(world, record_id, {"nde": {"a": 1}})  # an ordinary pset is still fine
    with pytest.raises(LayerError):
        update(world, record_id, {"nde": {"a": 1}, "src.import": {"b": 2}})


def test_a_rule_step_cannot_forge_an_enrichment(world: World) -> None:
    rule_id = world.create_rule(
        then=[
            {
                "command": "CreateRecord",
                "args": {"record_type": "core.Record", "title": "T", "key": "F-1", "psets": FORGED},
            }
        ]
    )
    world.revise_rule(rule_id, {"mode": "act"})
    world.switch_rule(rule_id, on=True)
    world.post("go #safety")
    world.worker().run_until_idle()
    assert world.rows("SELECT 1 FROM cur_core_record WHERE key = 'F-1'") == []
    assert [f["outcome"] for f in world.firings()] == ["refused"]


def test_an_inbound_mapping_cannot_forge_an_enrichment(world: World) -> None:
    mapping = (
        '{"command": "CreateRecord", "args": {"record_type": "core.Record", "title": "T", '
        '"key": "F-2", "psets": {"enrich.doc_classifier": {"doc_type": "DRW"}}}}'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["CreateRecord"])
    world.deliver(made.endpoint_id, {})
    world.inbound_runner().run_until_idle()
    [row] = world.deliveries()
    assert row["state"] == "failed"
    assert world.rows("SELECT 1 FROM cur_core_record WHERE key = 'F-2'") == []
