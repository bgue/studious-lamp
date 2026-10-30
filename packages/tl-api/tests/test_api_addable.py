"""``GET /records/{id}/addable-properties``, ad-hoc custom fields and adopting a set (P1-UX3 r4).

The parity the owner asked for: what the TUI form offers, the API offers, and an ad-hoc custom
field goes through the same ``SetPsetValues`` route with the same validation. The hidden world of
ADR-0016 (``test_api_actions``) proves a hidden record is a missing one for the read and for the
write, whatever the name of the field.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness import Harness
from test_api_actions import FAKE_ID, World, world  # noqa: F401  (fixtures)
from test_api_schedule import Cast
from tl_api.client import ApiClient
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import PsetValidationError, RecordNotFoundError
from tl_core.services.psets import SetPsetValues
from tl_mod_correspondence.confseed import TOKENS
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.testing import next_version

PKG = "co.acme.engineering"
SCOPE = "project:P123"
BASE: dict[str, Any] = {"source": "test", "scope": "company"}
NEW_SET = "inspection_data"


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def add_optional_pset(data: dict[str, Any]) -> None:
    """A new optional set for every record: no project has it until it adopts the package."""
    data["psets"][NEW_SET] = {
        "label": "Inspection data",
        "description": "Inspection data example set (round 4 test).",
        "applies_to": ["core.Record"],
        "enforcement": "advisory",
        "adoption": "optional",
        "custom_section": {"allowed": False},
        "properties": {
            "inspected_on": {"label": "Inspected on", "description": "Date.", "range": "date"},
        },
    }


def command(api: ApiClient, model: type, **fields: Any) -> Any:  # type: ignore[type-arg]
    return api.schemareg_command(model.__name__, model(actor="user:x", **BASE, **fields))


def publish_new_set(cast: Cast) -> None:
    bob, boss = cast.api("bob"), cast.api("boss")
    content = next_version(PKG, "3.3.0", add_optional_pset)
    package_id = command(bob, DraftSchemaPackage, content=content).stream_id
    command(bob, AnalyseSchemaPackage, package_id=package_id)
    command(bob, SubmitSchemaPackage, package_id=package_id)
    command(boss, ApproveSchemaPackage, package_id=package_id)
    command(boss, PublishSchemaPackage, package_id=package_id)


def put(api: ApiClient, record: Any, pset: str, values: dict[str, Any], layer: str) -> Any:
    return api.set_pset_values(
        SetPsetValues(
            actor="user:x",
            source="test",
            scope=SCOPE,
            stream_id=record.stream_id,
            expected_version=api.get_record_by_id(record.stream_id)["version"],  # type: ignore[index]
            pset=pset,
            layer=layer,  # type: ignore[arg-type]
            values=values,
        )
    )


# --- the read ------------------------------------------------------------------------------


def test_the_read_lists_what_a_record_lacks_and_each_sets_custom_rule(
    harness: Harness, cast: Cast
) -> None:
    record = harness.create_record("ADD-1", "A valve")
    found = cast.api("bob").addable_properties(record.stream_id)
    assert found.record_id == record.stream_id and found.scope == SCOPE and found.can_write
    sizes = [p for p in found.standard if (p.pset, p.property) == ("valve_data", "size_in")]
    assert len(sizes) == 1
    size = sizes[0]
    assert size.label and size.type == "decimal" and size.unit and size.layer == "standard"
    assert size.path == "psets.valve_data.size_in" and size.set_label
    enum = next(p for p in found.standard if p.type == "enum")
    assert enum.values and enum.code_list
    rule = next(r for r in found.custom if r.pset == "valve_data")
    assert (rule.allowed, rule.max_properties, rule.used) == (True, 10, 0)
    assert "fat_witness_by" in rule.declared
    locked = [r for r in found.custom if not r.allowed]
    assert all(r.max_properties is None for r in locked)
    assert found.name_rule


def test_a_value_removes_the_property_and_a_custom_field_counts_as_used(
    harness: Harness, cast: Cast
) -> None:
    bob = cast.api("bob")
    record = harness.create_record("ADD-2", "A valve")
    put(bob, record, "valve_data", {"size_in": 4}, "standard")
    put(bob, record, "valve_data", {"x.inspector_note": "ok", "x.lead_days": 14}, "custom")
    found = bob.addable_properties(record.stream_id)
    assert ("valve_data", "size_in") not in {(p.pset, p.property) for p in found.standard}
    assert next(r for r in found.custom if r.pset == "valve_data").used == 2


def test_an_agent_can_read_but_not_write_nor_adopt(harness: Harness, cast: Cast) -> None:
    record = harness.create_record("ADD-3", "A valve")
    agent = cast.agent.get(f"/records/{record.stream_id}/addable-properties")
    assert agent.status_code == 200
    assert agent.json()["can_write"] is False and agent.json()["write_refusal"]
    assert all(s["can_adopt"] is False for s in agent.json()["adoptable"])


def test_a_missing_record_is_404_and_no_token_is_401(harness: Harness, cast: Cast) -> None:
    assert cast.clients["bob"].get(f"/records/{FAKE_ID}/addable-properties").status_code == 404
    with pytest.raises(RecordNotFoundError):
        cast.api("bob").addable_properties(FAKE_ID)
    record = harness.create_record("ADD-4", "A valve")
    anonymous = cast.anonymous.get(f"/records/{record.stream_id}/addable-properties")
    assert anonymous.status_code == 401


def test_the_route_is_in_the_contract(harness: Harness) -> None:
    spec = harness.app.openapi()
    op = spec["paths"]["/records/{record_id}/addable-properties"]["get"]
    assert op["operationId"] == "get_record_addable_properties"
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AddableProperties"
    )
    assert {"AddableProperties", "AddableProperty", "AdoptableSet", "CustomRule"} <= set(
        spec["components"]["schemas"]
    )


# --- ad-hoc custom fields over the same route ------------------------------------------------


@pytest.mark.parametrize(
    "key", ["x.Bad", "x.1st", "x.has space", "x." + "a" * 41, "x.x", "x.prj_a", "x.size_in"]
)
def test_a_bad_name_is_a_422_pset_validation(harness: Harness, cast: Cast, key: str) -> None:
    record = harness.create_record("ADD-5", "A valve")
    body = {
        "scope": SCOPE,
        "stream_id": record.stream_id,
        "expected_version": 1,
        "pset": "valve_data",
        "layer": "custom",
        "values": {key: "v"},
    }
    refused = cast.clients["bob"].post("/commands/SetPsetValues", json=body)
    assert refused.status_code == 422 and refused.json()["error"] == "pset_validation"
    with pytest.raises(PsetValidationError):
        put(cast.api("bob"), record, "valve_data", {key: "v"}, "custom")


def test_an_ad_hoc_field_over_the_limit_is_refused(harness: Harness, cast: Cast) -> None:
    bob = cast.api("bob")
    record = harness.create_record("ADD-6", "A valve")
    put(bob, record, "valve_data", {f"x.f{i}": i for i in range(10)}, "custom")
    with pytest.raises(PsetValidationError):
        put(bob, record, "valve_data", {"x.eleventh": 1}, "custom")
    full = bob.addable_properties(record.stream_id)
    rule = next(r for r in full.custom if r.pset == "valve_data")
    assert rule.used == rule.max_properties == 10


def test_a_good_ad_hoc_field_is_one_event_and_is_text_unless_a_number(
    harness: Harness, cast: Cast
) -> None:
    record = harness.create_record("ADD-7", "A valve")
    done = put(cast.api("bob"), record, "valve_data", {"x.note": "n", "x.days": 3}, "custom")
    assert done.events[0].payload["values"] == {"x.note": "n", "x.days": 3}


# --- a hidden record is a missing record -----------------------------------------------------


def test_the_read_and_the_write_on_a_hidden_record_read_like_a_missing_one(world: World) -> None:  # noqa: F811
    ids = world.hidden.ids
    for who, kinds in {
        "bob": ["restricted", "privileged", "commercial", "secret_rfi"],
        "boss": ["privileged", "secret_rfi"],
    }.items():
        client = world.client(who)
        missing = client.get(f"/records/{FAKE_ID}/addable-properties")
        assert missing.status_code == 404
        for kind in kinds:
            hidden = client.get(f"/records/{ids[kind]}/addable-properties")
            assert hidden.status_code == 404
            assert hidden.text.replace(ids[kind], FAKE_ID) == missing.text, (who, kind)
            assert sorted(hidden.headers) == sorted(missing.headers), (who, kind)
            for token in TOKENS.values():
                assert token not in hidden.text
            # the write names the same record: a good name and a bad one answer alike
            answers = set()
            for key in ("x.good_name", "x.Bad Name", "x.prj_a"):
                body = {
                    "scope": "project:P123",
                    "stream_id": ids[kind],
                    "expected_version": 1,
                    "pset": "valve_data",
                    "layer": "custom",
                    "values": {key: "v"},
                }
                refused = client.post("/commands/SetPsetValues", json=body)
                assert refused.status_code == 404, (who, kind, key)
                answers.add(refused.text.replace(ids[kind], FAKE_ID))
            assert len(answers) == 1, (who, kind)


# --- adopting a set ---------------------------------------------------------------------------


def test_an_unadopted_optional_set_is_offered_and_only_a_superuser_may_adopt_it(
    harness: Harness, cast: Cast
) -> None:
    publish_new_set(cast)
    record = harness.create_record("ADD-8", "A valve")
    bob, boss = cast.api("bob"), cast.api("boss")
    as_bob = bob.addable_properties(record.stream_id)
    offered = [s for s in as_bob.adoptable if s.pset == NEW_SET]
    assert len(offered) == 1
    sheet = offered[0]
    assert (sheet.package, sheet.version, sheet.project) == (PKG, "3.3.0", "P123")
    assert sheet.command == "AdoptSchemaPackage" and sheet.can_adopt is False
    assert sheet.needs == "Needs a superuser to adopt this set for P123"
    assert [p.property for p in sheet.properties] == ["inspected_on"]
    assert NEW_SET not in {p.pset for p in as_bob.standard}
    assert [s.can_adopt for s in boss.addable_properties(record.stream_id).adoptable] == [True]
    with pytest.raises(ForbiddenError):  # the same access rule on the command itself
        command(bob, AdoptSchemaPackage, project="P123", package=PKG, version="3.3.0")
    command(boss, AdoptSchemaPackage, project="P123", package=PKG, version="3.3.0")
    after = bob.addable_properties(record.stream_id)
    assert after.adoptable == []
    assert [(p.pset, p.property, p.type) for p in after.standard if p.pset == NEW_SET] == [
        (NEW_SET, "inspected_on", "date")
    ]
    put(
        bob, record, NEW_SET, {"inspected_on": "2026-10-30"}, "standard"
    )  # the value can be entered
