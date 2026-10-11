"""The object-backed body store: validate, store once by hash, verify on read, quarantine.

Brief 31.2 and 31.4; FANOUT D10. Runs on each adapter.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from extworld import ALICE, LIFT, LIFT_BODY, LIFT_PSET, OBSERVATION, SCOPE, World
from sqlalchemy import text
from tl_adapters.db import rebuild_projections
from tl_core.extypes import body
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyQuarantinedError,
    BodyValidationError,
)
from tl_core.extypes.loader import default_loader
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySpec, parse, run_query
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.errors import RecordNotFoundError, RecordVoidedError
from tl_core.services.records import handle_void_record


@pytest.fixture(autouse=True)
def forget_loaded_types() -> None:
    default_loader().forget()


def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def stored(world: World, record_id: str) -> dict[str, Any]:
    with world.factory(readonly=True) as uow:
        return body.load_body(uow.conn(), world.store, stream_id=record_id)


def by_index(world: World, query: str) -> list[str]:
    with world.factory(readonly=True) as uow:
        spec = QuerySpec(scope=SCOPE, where=parse(query), order_by=[("key", "asc")])
        return [r["key"] for r in run_query(uow, spec)]


def store_again(world: World, record_id: str, new_body: dict[str, Any], **kw: Any) -> Any:
    with world.factory() as uow:
        return body.store_body(
            uow, world.store, stream_id=record_id, body=new_body, actor=ALICE, source="test", **kw
        )


# --- create and store -----------------------------------------------------------------------------


def test_create_stores_the_body_as_a_content_addressed_object(world: World) -> None:
    world.sync()
    made = world.create_lift()
    assert [e.event_type for e in made.events] == [
        "Record.Created",
        "Record.BodyStored",
        "Pset.ValuesSet",
    ]
    assert made.version == 3
    data = canonical(LIFT_BODY)
    digest = hashlib.sha256(data).hexdigest()
    stored_event = made.events[1]
    pointer = stored_event.payload["pointer"]
    assert pointer == {
        "uri": f"records/{LIFT}/{made.stream_id}/{digest}.json",
        "hash": digest,
        "size": len(data),
        "schema_hash": world.types()[0].registration.schema_hash,
    }
    assert stored_event.payload["previous_hash"] is None
    assert stored_event.payload["stream_id"] == made.stream_id
    assert world.object_path(made.stream_id).read_bytes() == data
    assert "crew" not in json.dumps(stored_event.payload)  # the body is never in the ledger


def test_only_the_index_fields_are_copied_into_the_pset(world: World) -> None:
    world.sync()
    made = world.create_lift()
    psets = json.loads(world.row(made.stream_id)["psets_json"])
    assert psets == {
        LIFT_PSET: {
            "crane": "CR-12",
            "lift_date": "2026-11-03",
            "load_tonnes": 42.5,
            "risk_class": "medium",
        }
    }
    values = made.events[2].payload
    assert values["pset"] == LIFT_PSET and values["layer"] == "standard"
    assert set(values["values"]) == {"crane", "lift_date", "load_tonnes", "risk_class"}
    assert values["units"] == {"load_tonnes": "t"}


def test_index_fields_filter_and_other_fields_do_not(world: World) -> None:
    world.sync()
    world.create_lift("LP-1")
    world.create_lift(
        "LP-2", {**LIFT_BODY, "risk_class": "high", "crane": "CR-07", "load_tonnes": 180}
    )
    assert by_index(world, f"psets.{LIFT_PSET}.risk_class:high") == ["LP-2"]
    assert by_index(world, f"psets.{LIFT_PSET}.crane:CR-12") == ["LP-1"]
    assert by_index(world, f"psets.{LIFT_PSET}.load_tonnes>100") == ["LP-2"]
    # the method statement is in the body only
    assert by_index(world, f"psets.{LIFT_PSET}.method_statement~lift") == []


def test_the_body_reads_back_verified(world: World) -> None:
    world.sync()
    made = world.create_lift()
    assert stored(world, made.stream_id) == LIFT_BODY


def test_a_new_body_is_a_new_object_and_the_old_one_stays(world: World) -> None:
    world.sync()
    made = world.create_lift()
    first_path = world.object_path(made.stream_id)
    changed = {**LIFT_BODY, "risk_class": "high", "load_tonnes": 99}
    pointer = store_again(world, made.stream_id, changed)
    second_path = world.object_path(made.stream_id)
    assert first_path != second_path and first_path.is_file() and second_path.is_file()
    assert stored(world, made.stream_id) == changed
    events = world.stream(made.stream_id)
    assert [e.event_type for e in events] == [
        "Record.Created",
        "Record.BodyStored",
        "Pset.ValuesSet",
        "Record.BodyStored",
        "Pset.ValuesSet",
    ]
    assert events[3].payload["previous_hash"] == made.events[1].payload["pointer"]["hash"]
    assert events[3].payload["pointer"]["hash"] == pointer.hash
    assert events[4].payload["values"] == {"risk_class": "high", "load_tonnes": 99}
    assert by_index(world, f"psets.{LIFT_PSET}.risk_class:high") == ["LP-1"]


def test_a_change_to_a_non_indexed_field_writes_no_pset_event(world: World) -> None:
    world.sync()
    made = world.create_lift()
    store_again(world, made.stream_id, {**LIFT_BODY, "method_statement": "A new method."})
    types = [e.event_type for e in world.stream(made.stream_id)]
    assert types[-1] == "Record.BodyStored" and types.count("Pset.ValuesSet") == 1


def test_removing_an_optional_index_field_unsets_the_pset_value(world: World) -> None:
    world.edit(
        world.package(),
        "type.yaml",
        "      load_tonnes:\n        range: float\n        required: true",
        "      load_tonnes:\n        range: float",
    )
    world.sync()
    made = world.create_lift()
    without = {k: v for k, v in LIFT_BODY.items() if k != "load_tonnes"}
    store_again(world, made.stream_id, without)
    last = world.stream(made.stream_id)[-1]
    assert last.event_type == "Pset.ValuesSet" and last.payload["values"] == {"load_tonnes": None}
    psets = json.loads(world.row(made.stream_id)["psets_json"])
    assert "load_tonnes" not in psets[LIFT_PSET]
    assert by_index(world, f"psets.{LIFT_PSET}.load_tonnes>0") == []


def test_a_required_field_cannot_be_removed(world: World) -> None:
    world.sync()
    made = world.create_lift()
    without = {k: v for k, v in LIFT_BODY.items() if k != "crane"}
    with pytest.raises(BodyValidationError):
        store_again(world, made.stream_id, without)


def test_the_pointer_table_counts_versions(world: World) -> None:
    world.sync()
    made = world.create_lift()
    store_again(world, made.stream_id, {**LIFT_BODY, "load_tonnes": 50})
    with world.factory(readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text("SELECT * FROM cur_core_record_body WHERE record_id = :i"),
                {"i": made.stream_id},
            )
            .mappings()
            .one()
        )
        pointer = body.body_pointer(uow.conn(), made.stream_id)
    assert row["body_versions"] == 2 and row["type_name"] == LIFT and row["scope"] == SCOPE
    assert pointer is not None and pointer.hash == row["hash"] and pointer.size == row["body_size"]


def test_storing_the_same_body_again_appends_nothing(world: World) -> None:
    world.sync()
    made = world.create_lift()
    head = world.head()
    pointer = store_again(world, made.stream_id, dict(LIFT_BODY))
    assert world.head() == head
    assert pointer.hash == made.events[1].payload["pointer"]["hash"]


def test_key_order_does_not_change_the_hash(world: World) -> None:
    world.sync()
    made = world.create_lift()
    head = world.head()
    reordered = dict(reversed(list(LIFT_BODY.items())))
    store_again(world, made.stream_id, reordered)
    assert world.head() == head


# --- validation -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"risk_class": "extreme"}, "risk_class"),
        ({"load_tonnes": "heavy"}, "load_tonnes"),
        ({"load_tonnes": -5}, "load_tonnes"),
        ({"crane": "crane 12"}, "crane"),
        ({"lift_date": "yesterday"}, "lift_date"),
        ({"crew": "A. Okafor"}, "crew"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_an_invalid_body_is_refused_before_anything_is_written(
    world: World, change: dict[str, Any], fragment: str
) -> None:
    world.sync()
    head = world.head()
    objects_before = sorted(world.store.iter_keys())
    with world.factory() as uow, pytest.raises(BodyValidationError) as caught:
        body.create_extension_record(
            uow,
            world.store,
            CreateRecord(
                actor=ALICE, source="t", scope=SCOPE, record_type=LIFT, title="x", key="K"
            ),
            {**LIFT_BODY, **change},
        )
    assert any(fragment in issue for issue in caught.value.issues)
    assert world.head() == head
    assert sorted(world.store.iter_keys()) == objects_before  # no object was put


def test_a_missing_required_field_is_named(world: World) -> None:
    world.sync()
    made = world.create_lift()
    with pytest.raises(BodyValidationError) as caught:
        store_again(world, made.stream_id, {"crane": "CR-12"})
    assert any("lift_date" in issue and "required" in issue for issue in caught.value.issues)


def test_an_oversized_body_is_refused(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    world.sync()
    made = world.create_lift()
    monkeypatch.setattr(body, "MAX_BODY_BYTES", 50)
    with pytest.raises(BodyValidationError, match="bytes"):
        store_again(world, made.stream_id, {**LIFT_BODY, "method_statement": "x" * 100})


def test_a_failed_validation_on_update_leaves_the_old_body(world: World) -> None:
    world.sync()
    made = world.create_lift()
    with pytest.raises(BodyValidationError):
        store_again(world, made.stream_id, {**LIFT_BODY, "risk_class": "extreme"})
    assert stored(world, made.stream_id) == LIFT_BODY
    assert len(world.stream(made.stream_id)) == 3


# --- what may have a body ---------------------------------------------------------------


def test_only_object_backed_records_have_a_body(world: World) -> None:
    world.sync()
    managed = world.create_observation()
    with pytest.raises(BodyNotAllowedError, match="no body"):
        store_again(world, managed.stream_id, {"a": 1})
    with world.factory() as uow, pytest.raises(BodyNotAllowedError, match="managed"):
        body.create_extension_record(
            uow,
            world.store,
            CreateRecord(
                actor=ALICE, source="t", scope=SCOPE, record_type=OBSERVATION, title="x", key="K"
            ),
            {"a": 1},
        )


def test_a_core_record_has_no_body(world: World) -> None:
    from tl_core.services.records import handle_create_record

    with world.factory() as uow:
        plain = handle_create_record(
            uow,
            CreateRecord(
                actor=ALICE,
                source="t",
                scope=SCOPE,
                record_type="core.Record",
                title="p",
                key="P-1",
            ),
        )
    with pytest.raises(BodyNotAllowedError):
        store_again(world, plain.stream_id, {})


def test_the_initial_values_of_an_object_backed_record_come_from_the_body(world: World) -> None:
    world.sync()
    head = world.head()
    with world.factory() as uow, pytest.raises(BodyNotAllowedError, match="not from psets"):
        body.create_extension_record(
            uow,
            world.store,
            CreateRecord(
                actor=ALICE,
                source="t",
                scope=SCOPE,
                record_type=LIFT,
                title="x",
                key="K",
                psets={LIFT_PSET: {"crane": "CR-1"}},
            ),
            dict(LIFT_BODY),
        )
    assert world.head() == head


def test_unknown_and_voided_records_are_refused(world: World) -> None:
    world.sync()
    with pytest.raises(RecordNotFoundError):
        store_again(world, "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", dict(LIFT_BODY))
    made = world.create_lift()
    with world.factory() as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor=ALICE,
                source="t",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                reason="duplicate",
            ),
        )
    with pytest.raises(RecordVoidedError):
        store_again(world, made.stream_id, {**LIFT_BODY, "load_tonnes": 1})


def test_expected_version_guards_against_a_lost_update(world: World) -> None:
    world.sync()
    made = world.create_lift()
    store_again(
        world, made.stream_id, {**LIFT_BODY, "load_tonnes": 50}, expected_version=made.version
    )
    with pytest.raises(ConcurrencyError):  # the editor still has the old version
        store_again(
            world, made.stream_id, {**LIFT_BODY, "load_tonnes": 60}, expected_version=made.version
        )
    assert stored(world, made.stream_id)["load_tonnes"] == 50


# --- verified reads and quarantine ---------------------------------------------------------------


def corrupt(world: World, record_id: str) -> None:
    world.object_path(record_id).write_bytes(b'{"crane":"CR-99"}')


def test_a_damaged_object_is_never_returned(world: World) -> None:
    world.sync()
    made = world.create_lift()
    corrupt(world, made.stream_id)
    with pytest.raises(BodyHashMismatchError) as caught:
        stored(world, made.stream_id)
    error = caught.value
    assert error.record_id == made.stream_id and error.actual is not None
    assert error.expected == made.events[1].payload["pointer"]["hash"]


def test_same_size_damage_is_caught_by_the_hash(world: World) -> None:
    world.sync()
    made = world.create_lift()
    path = world.object_path(made.stream_id)
    original = path.read_bytes()
    path.write_bytes(original.replace(b"CR-12", b"CR-13"))
    assert len(path.read_bytes()) == len(original)
    with pytest.raises(BodyHashMismatchError, match="hash differs"):
        stored(world, made.stream_id)


def test_a_missing_object_is_a_mismatch_with_no_actual_hash(world: World) -> None:
    world.sync()
    made = world.create_lift()
    world.object_path(made.stream_id).unlink()
    with pytest.raises(BodyHashMismatchError, match="object missing") as caught:
        stored(world, made.stream_id)
    assert caught.value.actual is None


def test_an_object_grown_past_its_size_is_read_only_a_little_past_it(world: World) -> None:
    world.sync()
    made = world.create_lift()
    path = world.object_path(made.stream_id)
    size = path.stat().st_size
    path.write_bytes(path.read_bytes() + b" " * 10_000_000)
    with pytest.raises(BodyHashMismatchError, match=f"{size + 1} bytes found"):
        stored(world, made.stream_id)


def test_a_record_without_a_body_has_no_body_to_load(world: World) -> None:
    world.sync()
    managed = world.create_observation()
    with pytest.raises(BodyNotFoundError):
        stored(world, managed.stream_id)


def test_read_body_quarantines_the_record_and_the_next_read_fails_fast(world: World) -> None:
    world.sync()
    made = world.create_lift()
    assert body.read_body(world.factory, world.store, stream_id=made.stream_id) == LIFT_BODY
    corrupt(world, made.stream_id)
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    with world.factory(readonly=True) as uow:
        (entry,) = body.list_body_quarantine(uow.conn())
    assert entry.record_id == made.stream_id and entry.type_name == LIFT and entry.scope == SCOPE
    assert entry.reason == "hash mismatch" and entry.actual_hash is not None
    assert entry.expected_hash == made.events[1].payload["pointer"]["hash"]
    # the second read does not touch the object at all
    world.object_path(made.stream_id).write_bytes(canonical(LIFT_BODY))  # fixed, but not rechecked
    with pytest.raises(BodyQuarantinedError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)


def test_a_missing_object_is_quarantined_with_that_reason(world: World) -> None:
    world.sync()
    made = world.create_lift()
    world.object_path(made.stream_id).unlink()
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    with world.factory(readonly=True) as uow:
        (entry,) = body.list_body_quarantine(uow.conn())
    assert entry.reason == "object missing" and entry.actual_hash is None


def test_quarantine_is_recorded_even_though_the_failing_read_rolls_back(world: World) -> None:
    world.sync()
    made = world.create_lift()
    corrupt(world, made.stream_id)
    with pytest.raises(BodyHashMismatchError):
        with world.factory(readonly=True) as uow:  # a caller reading in its own unit of work
            body.load_body(uow.conn(), world.store, stream_id=made.stream_id)
    with world.factory(readonly=True) as uow:
        assert body.list_body_quarantine(uow.conn()) == []  # load_body alone records nothing
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    with world.factory(readonly=True) as uow:
        assert len(body.list_body_quarantine(uow.conn())) == 1


def test_recheck_lifts_the_quarantine_once_the_object_is_sound(world: World) -> None:
    world.sync()
    made = world.create_lift()
    path = world.object_path(made.stream_id)
    good = path.read_bytes()
    path.write_bytes(b"broken")
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    assert body.recheck_body(world.factory, world.store, stream_id=made.stream_id) is False
    with world.factory(readonly=True) as uow:
        assert len(body.list_body_quarantine(uow.conn())) == 1
    path.write_bytes(good)
    assert body.recheck_body(world.factory, world.store, stream_id=made.stream_id) is True
    with world.factory(readonly=True) as uow:
        assert body.list_body_quarantine(uow.conn()) == []
    assert body.read_body(world.factory, world.store, stream_id=made.stream_id) == LIFT_BODY


def test_storing_the_body_again_heals_a_damaged_object_and_lifts_the_quarantine(
    world: World,
) -> None:
    world.sync()
    made = world.create_lift()
    corrupt(world, made.stream_id)
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    head = world.head()
    store_again(world, made.stream_id, dict(LIFT_BODY))
    assert world.head() == head  # no new event: the same body
    assert body.read_body(world.factory, world.store, stream_id=made.stream_id) == LIFT_BODY
    with world.factory(readonly=True) as uow:
        assert body.list_body_quarantine(uow.conn()) == []


def test_a_new_body_replaces_a_quarantined_one(world: World) -> None:
    world.sync()
    made = world.create_lift()
    corrupt(world, made.stream_id)
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=made.stream_id)
    changed = {**LIFT_BODY, "load_tonnes": 77}
    store_again(world, made.stream_id, changed)
    assert body.read_body(world.factory, world.store, stream_id=made.stream_id) == changed


def test_a_quarantine_marks_only_the_hash_it_was_found_for(world: World) -> None:
    world.sync()
    made = world.create_lift()
    corrupt(world, made.stream_id)
    err = None
    try:
        with world.factory(readonly=True) as uow:
            body.load_body(uow.conn(), world.store, stream_id=made.stream_id)
    except BodyHashMismatchError as exc:
        err = exc
    assert err is not None
    changed = {**LIFT_BODY, "load_tonnes": 77}
    store_again(
        world, made.stream_id, changed
    )  # a newer body arrives before the failure is recorded
    body._record_quarantine(world.factory, err)  # type: ignore[attr-defined]
    with world.factory(readonly=True) as uow:
        assert body.list_body_quarantine(uow.conn()) == []


def test_a_rebuild_keeps_the_quarantine_and_rebuilds_the_pointers(world: World) -> None:
    world.sync()
    made = world.create_lift()
    other = world.create_lift("LP-2", {**LIFT_BODY, "crane": "CR-02"})
    corrupt(world, other.stream_id)
    with pytest.raises(BodyHashMismatchError):
        body.read_body(world.factory, world.store, stream_id=other.stream_id)

    def pointers() -> list[Any]:
        with world.factory(readonly=True) as uow:
            return [
                tuple(r)
                for r in uow.conn().execute(
                    text("SELECT * FROM cur_core_record_body ORDER BY record_id")
                )
            ]

    before = pointers()
    rebuild_projections(world.db)
    assert pointers() == before and len(before) == 2
    with world.factory(readonly=True) as uow:
        assert [e.record_id for e in body.list_body_quarantine(uow.conn())] == [other.stream_id]
    assert stored(world, made.stream_id) == LIFT_BODY


def test_the_object_key_is_safe_for_every_backend(world: World) -> None:
    from tl_core.files.keys import check_key

    world.sync()
    made = world.create_lift()
    with world.factory(readonly=True) as uow:
        pointer = body.body_pointer(uow.conn(), made.stream_id)
    assert pointer is not None
    assert check_key(pointer.uri) == pointer.uri
    assert pointer.uri.startswith(f"records/{LIFT}/{made.stream_id}/") and pointer.uri.endswith(
        ".json"
    )
