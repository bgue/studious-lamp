"""Extension types in the effective schema, and records of an extension type (brief 27.3, 31; D7).

``CreateRecord.record_type = "<ns>.<Name>"`` works for an active registration and for nothing else;
a managed type takes its values as psets; the query language filters the type's pset.
"""

from __future__ import annotations

from typing import Any

import pytest
from extworld import (
    ALICE,
    LIFT,
    LIFT_PSET,
    OBSERVATION,
    OBSERVATION_PSET,
    OBSERVATION_VALUES,
    SCOPE,
    World,
)
from sqlalchemy import text
from tl_adapters.db import rebuild_projections
from tl_core.extypes import registry
from tl_core.extypes.errors import BodyNotAllowedError, BodyRequiredError, TypeNotActiveError
from tl_core.extypes.loader import default_loader
from tl_core.query import QuerySpec, parse, run_query
from tl_core.schema_provider import DirectorySchemaProvider, get_provider
from tl_core.services import psets
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.errors import (
    NoNumberingPatternError,
    PsetValidationError,
    UnknownPsetError,
    UnsupportedRecordTypeError,
)
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record, handle_update_record


def command(record_type: str, **fields: Any) -> CreateRecord:
    base: dict[str, Any] = {
        "actor": ALICE,
        "source": "test",
        "scope": SCOPE,
        "record_type": record_type,
        "title": "A record",
        "key": "X-1",
    }
    return CreateRecord(**{**base, **fields})


@pytest.fixture(autouse=True)
def forget_loaded_types() -> None:
    default_loader().forget()


# --- before and after registration --------------------------------------------------------------


def test_an_unregistered_type_is_refused_like_any_unknown_record_type(world: World) -> None:
    with (
        world.factory() as uow,
        pytest.raises(UnsupportedRecordTypeError, match="no extension type"),
    ):
        handle_create_record(
            uow, command(OBSERVATION, psets={OBSERVATION_PSET: OBSERVATION_VALUES})
        )
    with world.factory() as uow, pytest.raises(UnsupportedRecordTypeError):
        handle_create_record(uow, command("piping.Weld"))


def test_a_registered_type_creates_records(world: World) -> None:
    world.sync()
    made = world.create_observation()
    assert [e.event_type for e in made.events] == ["Record.Created", "Pset.ValuesSet"]
    assert made.version == 2 and made.key == "SO-1"
    created, values = made.events
    assert created.stream_type == OBSERVATION and created.payload["record_type"] == OBSERVATION
    assert created.payload["psets"] == {}  # the values arrive in the Pset.ValuesSet below
    assert values.payload["pset"] == OBSERVATION_PSET and values.payload["layer"] == "standard"
    assert values.payload["values"] == OBSERVATION_VALUES
    assert values.payload["effective_schema_hash"] == get_provider().effective(SCOPE).hash
    row = world.row(made.stream_id)
    assert row["type"] == OBSERVATION and row["scope"] == SCOPE and row["version"] == 2
    assert row["effective_schema_hash"] == values.payload["effective_schema_hash"]


def test_a_record_with_no_initial_values_has_one_event(world: World) -> None:
    world.sync()
    with world.factory() as uow:
        made = handle_create_record(uow, command(OBSERVATION))
    assert [e.event_type for e in made.events] == ["Record.Created"]


def test_the_index_values_are_pset_values_the_query_language_filters(world: World) -> None:
    world.sync()
    world.create_observation("SO-1", severity="high")
    world.create_observation("SO-2", severity="low", category="good_practice")
    world.create_observation("SO-3", severity="high", category="unsafe_act")

    def found(query: str) -> list[str]:
        with world.factory(readonly=True) as uow:
            spec = QuerySpec(scope=SCOPE, where=parse(query), order_by=[("key", "asc")])
            return [r["key"] for r in run_query(uow, spec)]

    assert found(f"psets.{OBSERVATION_PSET}.severity:high") == ["SO-1", "SO-3"]
    assert found(f"psets.{OBSERVATION_PSET}.category:good_practice") == ["SO-2"]
    assert found(f"type:{OBSERVATION} psets.{OBSERVATION_PSET}.severity:high") == ["SO-1", "SO-3"]
    with world.factory(readonly=True) as uow:
        count = (
            uow.conn()
            .execute(
                text("SELECT COUNT(*) FROM cur_pset_values WHERE pset = :p"),
                {"p": OBSERVATION_PSET},
            )
            .scalar_one()
        )
    assert count == 3 * 4


def test_a_project_scope_and_the_company_scope_both_see_the_type(world: World) -> None:
    world.sync()
    for scope in ("company", SCOPE, "project:P9"):
        schema = get_provider().effective(scope)
        pset = schema.psets[OBSERVATION_PSET]
        assert pset.applies_to == [OBSERVATION] and pset.package == OBSERVATION
        assert pset.version == "1.0.0"
        assert [p.name for p in schema.for_record_type(OBSERVATION)] == [OBSERVATION_PSET]


def test_the_effective_schema_is_unchanged_when_no_type_is_registered(world: World) -> None:
    plain = DirectorySchemaProvider().effective(SCOPE)
    assert get_provider().effective(SCOPE).hash == plain.hash
    world.sync()
    registered = get_provider().effective(SCOPE)
    assert registered.hash != plain.hash
    assert {p.name for p in registered.packages} >= {LIFT, OBSERVATION}


def test_the_form_metadata_of_a_type_lists_its_pset_fields(world: World) -> None:
    world.sync()
    with world.factory(readonly=True) as uow:
        managed = psets.form_metadata(uow, SCOPE, OBSERVATION)
        backed = psets.form_metadata(uow, SCOPE, LIFT)
    (group,) = managed.psets
    assert group.name == OBSERVATION_PSET
    assert [f.path.rsplit(".", 1)[1] for f in group.fields] == [
        "observed_on",
        "category",
        "severity",
        "location",
        "narrative",
        "immediate_action",
    ]
    kinds = {f.path.rsplit(".", 1)[1]: f.kind for f in group.fields}
    assert kinds["observed_on"] == "date" and kinds["severity"] == "enum"
    assert kinds["narrative"] == "text"
    (lift_group,) = backed.psets  # an object-backed type exposes its index fields only
    assert [f.path.rsplit(".", 1)[1] for f in lift_group.fields] == [
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
    ]


# --- values on create ----------------------------------------------------------------------------


def test_a_wrong_type_of_value_is_refused_and_nothing_is_written(world: World) -> None:
    world.sync()
    head = world.head()
    with world.factory() as uow, pytest.raises(PsetValidationError) as caught:
        handle_create_record(
            uow, command(OBSERVATION, psets={OBSERVATION_PSET: {"observed_on": 5}})
        )
    assert any("observed_on" in issue for issue in caught.value.issues)
    assert world.head() == head


def test_an_unknown_property_and_an_unknown_pset_are_refused(world: World) -> None:
    world.sync()
    with world.factory() as uow, pytest.raises(PsetValidationError):
        handle_create_record(uow, command(OBSERVATION, psets={OBSERVATION_PSET: {"colour": "red"}}))
    with world.factory() as uow, pytest.raises(UnknownPsetError, match="valve_data"):
        handle_create_record(uow, command(OBSERVATION, psets={"valve_data": {"size_in": 2}}))


def test_a_value_outside_its_list_is_stored_and_shows_as_conformance(world: World) -> None:
    world.sync()
    made = world.create_observation(severity="catastrophic")
    assert made.events[1].payload["conformance"] != "ok"
    with world.factory(readonly=True) as uow:
        report = psets.conformance(uow, made.stream_id)
    assert [i.rule for i in report.issues] == ["value_list"]


def test_missing_required_values_show_as_conformance(world: World) -> None:
    world.sync()
    with world.factory() as uow:
        made = handle_create_record(
            uow, command(OBSERVATION, psets={OBSERVATION_PSET: {"location": "Gate 4"}})
        )
    assert made.events[1].payload["conformance"] != "ok"


def test_a_key_is_needed_when_the_type_has_no_numbering_pattern(world: World) -> None:
    world.sync()
    with world.factory() as uow, pytest.raises(NoNumberingPatternError):
        handle_create_record(uow, command(OBSERVATION, key=None))


def test_a_duplicate_key_is_refused_like_for_any_record(world: World) -> None:
    from tl_core.services.errors import DuplicateKeyError

    world.sync()
    world.create_observation("SO-1")
    with pytest.raises(DuplicateKeyError):
        world.create_observation("SO-1")


# --- object-backed types need their body ----------------------------------------------------------


def test_handle_create_record_refuses_an_object_backed_type(world: World) -> None:
    world.sync()
    head = world.head()
    with world.factory() as uow, pytest.raises(BodyRequiredError, match="object-backed"):
        handle_create_record(uow, command(LIFT))
    assert world.head() == head


# --- deprecated, unavailable, drifted ------------------------------------------------------------


def test_a_deprecated_type_takes_no_new_instances_but_old_ones_stay_editable(world: World) -> None:
    world.sync()
    made = world.create_observation()
    with world.factory() as uow:
        registry.deprecate_type(
            uow, type_ref=f"{OBSERVATION}@1.0.0", reason="old", actor=ALICE, source="test"
        )
    with world.factory() as uow, pytest.raises(TypeNotActiveError, match="deprecated"):
        handle_create_record(uow, command(OBSERVATION, key="SO-2"))
    with world.factory() as uow:
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=ALICE,
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                pset=OBSERVATION_PSET,
                layer="standard",
                values={"severity": "low"},
            ),
        )
    assert OBSERVATION_PSET in get_provider().effective(SCOPE).psets  # still validates old records


def test_a_quarantined_type_is_not_in_the_schema(world: World) -> None:
    (world.package(OBSERVATION) / "examples" / "bad.json").write_text("{}")
    world.relock(world.package(OBSERVATION))
    world.sync()
    assert OBSERVATION_PSET not in get_provider().effective(SCOPE).psets
    with world.factory() as uow, pytest.raises(UnsupportedRecordTypeError):
        handle_create_record(uow, command(OBSERVATION))


def test_a_type_whose_files_changed_after_registering_is_unavailable(world: World) -> None:
    world.sync()
    world.create_observation()
    default_loader().forget()  # a fresh process reads the files again
    (world.package(OBSERVATION) / "README.md").write_text("changed behind the registry's back\n")
    world.source.invalidate()
    with world.factory() as uow, pytest.raises(TypeNotActiveError, match="changed since"):
        handle_create_record(uow, command(OBSERVATION, key="SO-2"))
    assert OBSERVATION_PSET not in get_provider().effective(SCOPE).psets
    assert "changed since" in world.source.unavailable()[f"{OBSERVATION}@1.0.0"]
    # the records already made are still there and readable
    assert world.row(_first_record(world))["type"] == OBSERVATION


def _first_record(world: World) -> str:
    with world.factory(readonly=True) as uow:
        return str(uow.conn().execute(text("SELECT id FROM cur_core_record LIMIT 1")).scalar_one())


def test_restoring_the_files_makes_the_type_available_again(world: World) -> None:
    world.sync()
    readme = world.package(OBSERVATION) / "README.md"
    original = readme.read_text()
    default_loader().forget()
    readme.write_text("changed\n")
    world.source.invalidate()
    assert OBSERVATION_PSET not in get_provider().effective(SCOPE).psets
    readme.write_text(original)
    world.source.invalidate()
    assert OBSERVATION_PSET in get_provider().effective(SCOPE).psets


def test_a_package_directory_that_vanished_makes_the_type_unavailable(world: World) -> None:
    import shutil

    world.sync()
    default_loader().forget()
    shutil.rmtree(world.package(OBSERVATION))
    world.source.invalidate()
    with world.factory() as uow, pytest.raises(TypeNotActiveError, match="missing"):
        handle_create_record(uow, command(OBSERVATION))


def test_a_type_is_loaded_once_not_on_every_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tl_core.extypes.compile as compile_module

    world.sync()
    calls: list[str] = []
    real = compile_module.compile_type

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("compile")
        return real(*args, **kwargs)

    monkeypatch.setattr("tl_core.extypes.loader.compile_type", counting)
    default_loader().forget()
    for index in range(5):
        world.create_observation(f"SO-{index}")
    assert len(calls) == 2  # one compile per registered type, however many records


# --- the provider's polling ---------------------------------------------------------------------


def test_another_process_registering_shows_after_the_polling_interval(world: World) -> None:
    from tl_core.extypes.provider import LedgerExtensionSource

    clock = {"now": 0.0}
    source = LedgerExtensionSource(world.factory, ttl=5.0, clock=lambda: clock["now"])
    first = source.token()
    # simulate a write by another process: events appended without this process' bump
    import tl_core.extypes.registry as reg

    before = reg.changes()
    world.sync()
    reg._changes = before  # type: ignore[attr-defined]  # pretend the bump never happened here
    assert source.token() == first  # cached: the interval has not passed
    clock["now"] = 6.0
    assert source.token() != first


def test_a_registration_made_in_this_process_shows_at_once(world: World) -> None:
    from tl_core.extypes.provider import LedgerExtensionSource

    clock = {"now": 0.0}
    source = LedgerExtensionSource(world.factory, ttl=3600.0, clock=lambda: clock["now"])
    first = source.token()
    world.sync()
    assert source.token() != first


def test_a_ledger_without_the_registry_tables_has_no_types(tmp_path: Any) -> None:
    from tl_adapters.db import make_uow_factory
    from tl_core.extypes.provider import LedgerExtensionSource

    path = tmp_path / "old.db"
    from tl_adapters.sqlite.uow import open_uow

    with open_uow(path) as uow:  # a database that has the events table but not the registry's
        uow.conn().execute(text("SELECT 1"))
    factory = make_uow_factory(path)
    try:
        source = LedgerExtensionSource(factory, ttl=0.0)
        assert source.token().startswith("none") and source.documents() == []
    finally:
        factory.dispose()


# --- an object-backed type's index fields are copies of its body ------------------------


def test_index_fields_of_an_object_backed_record_cannot_be_written_directly(world: World) -> None:
    world.sync()
    made = world.create_lift()
    with world.factory() as uow, pytest.raises(BodyNotAllowedError, match="copied from the body"):
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=ALICE,
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                pset=LIFT_PSET,
                layer="standard",
                values={"crane": "CR-99"},
            ),
        )
    with world.factory() as uow, pytest.raises(BodyNotAllowedError):
        handle_update_record(
            uow,
            UpdateRecord(
                actor=ALICE,
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                changes={"psets": {LIFT_PSET: {"crane": "CR-99"}}},
            ),
        )
    # the title is the record's own and stays editable
    with world.factory() as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor=ALICE,
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                changes={"title": "Renamed"},
            ),
        )
    assert world.row(made.stream_id)["title"] == "Renamed"


def test_a_managed_records_psets_can_be_updated(world: World) -> None:
    world.sync()
    made = world.create_observation()
    with world.factory() as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor=ALICE,
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=made.version,
                changes={"psets": {OBSERVATION_PSET: {"severity": "low"}}},
            ),
        )


# --- replay ---------------------------------------------------------------------------------------


def test_rebuilding_the_projections_gives_the_same_records_and_pset_values(world: World) -> None:
    world.sync()
    world.create_observation("SO-1")
    world.create_observation("SO-2", severity="low")
    world.create_lift("LP-1")

    def snapshot() -> tuple[list[Any], list[Any]]:
        with world.factory(readonly=True) as uow:
            records = [
                tuple(r)
                for r in uow.conn().execute(
                    text(
                        "SELECT id, key, type, scope, version, last_seq, psets_json, "
                        "effective_schema_hash, conformance FROM cur_core_record ORDER BY id"
                    )
                )
            ]
            values = [
                tuple(r)
                for r in uow.conn().execute(
                    text(
                        "SELECT record_id, path, pset, value_text, value_num, last_seq "
                        "FROM cur_pset_values ORDER BY record_id, path"
                    )
                )
            ]
            return records, values

    before = snapshot()
    rebuild_projections(world.db)
    assert snapshot() == before
    assert len(before[0]) == 3 and len(before[1]) == 4 + 4 + 4


# --- review fix: the loader re-verifies without a restart ---------------------------------


def test_an_edited_package_becomes_unavailable_without_forgetting_the_loader(
    world: World,
) -> None:
    from tl_core.extypes.loader import TypeLoader

    world.sync()
    (view,) = [v for v in world.types() if v.registration.name == "SafetyObservation"]
    clock = {"now": 0.0}
    loader = TypeLoader(reverify=1.0, clock=lambda: clock["now"])
    assert loader.load(view.registration).__class__.__name__ == "LoadedType"
    (world.package(OBSERVATION) / "README.md").write_text("changed behind the registry's back\n")
    clock["now"] = 0.5  # inside the interval: the cached type is served, no hashing
    assert loader.load(view.registration).__class__.__name__ == "LoadedType"
    clock["now"] = 1.5
    result = loader.load(view.registration)
    assert result.__class__.__name__ == "Unavailable"
    assert "changed since" in result.reason  # type: ignore[union-attr]
    # and it stays unavailable, then returns when the files do
    assert loader.load(view.registration).__class__.__name__ == "Unavailable"


def test_a_deleted_package_becomes_unavailable_without_forgetting_the_loader(
    world: World,
) -> None:
    import shutil

    from tl_core.extypes.loader import TypeLoader

    world.sync()
    (view,) = [v for v in world.types() if v.registration.name == "SafetyObservation"]
    clock = {"now": 0.0}
    loader = TypeLoader(reverify=1.0, clock=lambda: clock["now"])
    assert loader.load(view.registration).__class__.__name__ == "LoadedType"
    shutil.rmtree(world.package(OBSERVATION))
    clock["now"] = 2.0
    result = loader.load(view.registration)
    assert result.__class__.__name__ == "Unavailable" and "missing" in result.reason  # type: ignore[union-attr]


def test_the_default_loader_notices_an_edit_when_the_interval_has_passed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.sync()
    world.create_observation("SO-1")  # loads and caches the type
    (world.package(OBSERVATION) / "README.md").write_text("changed\n")
    import time

    loader = default_loader()
    monkeypatch.setattr(loader, "_clock", lambda: time.monotonic() + 5.0)
    with world.factory() as uow, pytest.raises(TypeNotActiveError, match="changed since"):
        handle_create_record(uow, command(OBSERVATION, key="SO-2"))


def test_a_retired_version_says_deprecated_even_when_its_files_changed(world: World) -> None:
    world.sync()
    with world.factory() as uow:
        registry.deprecate_type(
            uow, type_ref=f"{OBSERVATION}@1.0.0", reason="old", actor=ALICE, source="test"
        )
    package = world.package(OBSERVATION)
    world.edit(package, "README.md", "Example", "Edited example")
    default_loader().forget()
    with world.factory() as uow, pytest.raises(TypeNotActiveError, match="is deprecated"):
        handle_create_record(uow, command(OBSERVATION, key="SO-9"))
