"""The module seam of the core (ADR-0010): specs, module records, bound psets, numbering patterns.

A fake module stands in for a real one: it provides the record type ``fake.Thing`` and binds the
pset ``valve_data`` to the records whose key starts with ``B``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.ledger import Event, NewEvent
from tl_core.modules import (
    ModuleLoadError,
    ModuleSpec,
    bound_psets,
    is_module_record_type,
    load_modules,
    module_record_types,
    use_modules,
)
from tl_core.numbering.config import (
    NumberingPattern,
    NumberingRegistry,
    numbering_for,
    use_numbering,
)
from tl_core.projection.defaults import default_registry
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_core.services.errors import (
    DuplicateKeyError,
    NoNumberingPatternError,
    UnknownPsetError,
    UnsupportedRecordTypeError,
)
from tl_core.services.psets import SetPsetValues, conformance, handle_set_pset_values
from tl_core.services.records import create_module_record
from tl_core.util import new_ulid

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
THING = "fake.Thing"


class FakeProjector:
    name = "fake_thing"
    handles = frozenset({"Thing.Defined"})

    def ddl(self, dialect: str) -> list[str]:
        return []

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


def binds_valve_data_to_b_keys(
    conn: Connection, record_type: str, record_id: str
) -> tuple[str, ...]:
    key = conn.execute(
        text("SELECT key FROM cur_core_record WHERE id = :id"), {"id": record_id}
    ).scalar_one()
    return ("valve_data",) if str(key).startswith("B") else ()


def registered_patterns(conn: Connection) -> Sequence[NumberingPattern]:
    return [
        NumberingPattern(
            id="fake:thing",
            record_type=THING,
            template="{project}-{type}-{seq:3}",
            type_code="THG",
            scope="project:*",
        )
    ]


def fake_spec(**more: Any) -> ModuleSpec:
    return ModuleSpec(
        name="fake",
        record_types=frozenset({THING}),
        projectors=lambda: [FakeProjector()],
        bound_psets=binds_valve_data_to_b_keys,
        **more,
    )


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture(autouse=True)
def fake_module() -> Iterator[None]:
    with use_modules(
        [
            fake_spec(
                numbering_patterns=registered_patterns,
                generic_commands={THING: frozenset({"SetPsetValues"})},
            )
        ]
    ):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    path = new_db()
    create_schema(path)
    return path


def command() -> Command:
    return Command(actor="user:u", source="test", scope=SCOPE)


def make_thing(db: DbTarget, key: str | None, **more: Any) -> Any:
    with open_uow(db) as uow:
        return create_module_record(
            uow, command(), record_type=THING, title="A thing", key=key, **more
        )


# --- the registry of specs ---------------------------------------------------------------------


def test_the_installed_modules_are_the_override_inside_the_block() -> None:
    assert [m.name for m in load_modules()] == ["fake"]
    assert module_record_types() == {THING}
    assert is_module_record_type(THING) and not is_module_record_type("core.Record")


def test_the_installed_modules_are_found_through_their_entry_points() -> None:
    from tl_core import modules

    found = modules._discover()  # pyright: ignore[reportPrivateUsage]
    assert [m.name for m in found] == ["documents", "engineering"]
    by_name = {m.name: m for m in found}
    assert "engineering.Tag" in by_name["engineering"].record_types
    assert "documents.Document" in by_name["documents"].record_types


def test_a_record_type_must_start_with_the_module_name() -> None:
    with pytest.raises(ModuleLoadError, match="must start with 'fake.'"):
        ModuleSpec(name="fake", record_types=frozenset({"other.Thing"}), projectors=lambda: [])


def test_module_projectors_join_the_default_registry_before_the_outbox() -> None:
    names = [p.name for p in default_registry().all()]
    assert "fake_thing" in names
    assert names.index("fake_thing") > names.index("feed")
    assert names[-1] == "outbox"
    assert "fake_thing" in [p.name for p in default_registry().for_event("Thing.Defined")]


# --- creating a module record ------------------------------------------------------------------


def test_a_module_record_is_an_envelope_row_with_the_extra_events_after_it(db: DbTarget) -> None:
    extra = NewEvent(event_type="Thing.Defined", payload={"size": 3})
    result = make_thing(db, "B-1", extra_events=[extra])
    assert [e.event_type for e in result.events] == ["Record.Created", "Thing.Defined"]
    assert result.version == 2 and result.key == "B-1"
    with open_uow(db, readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text("SELECT type, key, scope, voided FROM cur_core_record WHERE id = :id"),
                {"id": result.stream_id},
            )
            .one()
        )
    assert (row.type, row.key, row.scope, bool(row.voided)) == (THING, "B-1", SCOPE, False)


def test_a_duplicate_key_is_refused_and_writes_nothing(db: DbTarget) -> None:
    make_thing(db, "A-1")
    with pytest.raises(DuplicateKeyError):
        make_thing(db, "A-1")
    with open_uow(db, readonly=True) as uow:
        count = uow.conn().execute(text("SELECT COUNT(*) FROM cur_core_record")).scalar_one()
    assert count == 1


def test_a_type_no_module_provides_is_refused(db: DbTarget) -> None:
    with open_uow(db) as uow, pytest.raises(UnsupportedRecordTypeError):
        create_module_record(uow, command(), record_type="fake.Other", title="x", key="K")


def test_without_a_key_the_numbering_service_uses_the_pattern_the_module_holds(
    db: DbTarget,
) -> None:
    with open_uow(db, readonly=True) as uow:
        assert "fake:thing" in [p.id for p in numbering_for(uow.conn()).all()]
    first = make_thing(db, None)
    second = make_thing(db, None)
    assert (first.key, second.key) == ("P123-THG-001", "P123-THG-002")


def test_without_a_key_and_without_a_pattern_the_create_is_refused(db: DbTarget) -> None:
    with use_modules([fake_spec()]), use_numbering(NumberingRegistry()):
        with open_uow(db) as uow, pytest.raises(NoNumberingPatternError):
            create_module_record(uow, command(), record_type=THING, title="x", key=None)


# --- psets a class binds ------------------------------------------------------------------------


def set_valve_data(db: DbTarget, record_id: str, version: int, **values: Any) -> Any:
    with open_uow(db) as uow:
        return handle_set_pset_values(
            uow,
            SetPsetValues(
                actor="user:u",
                source="test",
                scope=SCOPE,
                stream_id=record_id,
                expected_version=version,
                pset="valve_data",
                layer="standard",
                values=values,
            ),
        )


def test_a_bound_pset_can_be_written_on_a_module_record(db: DbTarget) -> None:
    thing = make_thing(db, "B-1")
    written = set_valve_data(db, thing.stream_id, thing.version, size_in=4, manufacturer="Acme")
    assert written.events[0].event_type == "Pset.ValuesSet"
    assert written.events[0].payload["conformance"] == "ok"


def test_the_same_pset_is_refused_when_the_class_does_not_bind_it(db: DbTarget) -> None:
    thing = make_thing(db, "A-1")
    with pytest.raises(UnknownPsetError, match="does not apply"):
        set_valve_data(db, thing.stream_id, thing.version, size_in=4)


def test_conformance_counts_a_bound_pset_without_values_as_missing(db: DbTarget) -> None:
    bound = make_thing(db, "B-1")
    plain = make_thing(db, "A-1")
    with open_uow(db, readonly=True) as uow:
        report = conformance(uow, bound.stream_id)
        clean = conformance(uow, plain.stream_id)
    assert report.status == "nonconformant"
    assert [i.rule for i in report.issues] == ["class_required", "required_in_state"]
    assert clean.status == "ok" and clean.issues == []


def test_bound_psets_of_a_type_no_module_binds_are_empty(db: DbTarget) -> None:
    with open_uow(db, readonly=True) as uow:
        assert bound_psets(uow.conn(), "core.Record", new_ulid()) == ()


# --- a module that cannot load ------------------------------------------------------------------


class FakeEntry:
    def __init__(self, name: str, loaded: Any) -> None:
        self.name = name
        self._loaded = loaded

    def load(self) -> Any:
        if isinstance(self._loaded, Exception):
            raise self._loaded
        return self._loaded


def discover_with(monkeypatch: pytest.MonkeyPatch, *entries: FakeEntry) -> Any:
    from tl_core import modules

    monkeypatch.setattr(modules, "entry_points", lambda group: list(entries))
    return modules._discover()  # pyright: ignore[reportPrivateUsage]


def test_discovery_returns_the_specs_sorted_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    other = ModuleSpec(name="aaa", record_types=frozenset({"aaa.X"}), projectors=lambda: [])
    found = discover_with(
        monkeypatch,
        FakeEntry("fake", lambda: fake_spec()),
        FakeEntry("aaa", lambda: other),
    )
    assert [m.name for m in found] == ["aaa", "fake"]


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([FakeEntry("fake", RuntimeError("boom"))], "cannot be loaded: boom"),
        ([FakeEntry("fake", lambda: "not a spec")], "must return a ModuleSpec"),
        ([FakeEntry("other", lambda: fake_spec())], "returned a spec named 'fake'"),
    ],
)
def test_a_module_that_does_not_load_is_a_loud_error(
    monkeypatch: pytest.MonkeyPatch, entries: list[FakeEntry], message: str
) -> None:
    with pytest.raises(ModuleLoadError, match=message):
        discover_with(monkeypatch, *entries)


def test_two_modules_may_not_claim_one_record_type(monkeypatch: pytest.MonkeyPatch) -> None:
    clash = ModuleSpec(name="aaa", record_types=frozenset({"aaa.X"}), projectors=lambda: [])
    object.__setattr__(clash, "record_types", frozenset({THING}))
    with pytest.raises(ModuleLoadError, match="claimed by"):
        discover_with(
            monkeypatch,
            FakeEntry("aaa", lambda: clash),
            FakeEntry("fake", lambda: fake_spec()),
        )


# --- generic commands on module records (ADR-0010 addendum) -------------------------------------


def test_a_module_type_allows_no_generic_command_unless_its_spec_lists_it(db: DbTarget) -> None:
    from tl_core.modules import GENERIC_COMMANDS, require_generic_command

    made = make_thing(db, "B-1")
    with pytest.raises(UnsupportedRecordTypeError, match="UpdateRecord cannot change a fake.Thing"):
        require_generic_command(THING, "UpdateRecord")
    assert made is not None
    require_generic_command("core.Record", "UpdateRecord")  # not a module type: untouched
    with use_modules([fake_spec(generic_commands={THING: frozenset({"SetPsetValues"})})]):
        require_generic_command(THING, "SetPsetValues")
        with pytest.raises(UnsupportedRecordTypeError):
            require_generic_command(THING, "UpdateRecord")
    assert {"UpdateRecord", "SetPsetValues", "VoidRecord", "AddLink"} <= GENERIC_COMMANDS


def test_the_generic_write_commands_refuse_a_module_record(db: DbTarget) -> None:
    from tl_core.services.commands import UpdateRecord, VoidRecord
    from tl_core.services.links import AddLink, handle_add_link
    from tl_core.services.records import handle_update_record, handle_void_record
    from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow

    thing = make_thing(db, "B-1")
    other = make_thing(db, "B-2")
    base: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": SCOPE}
    refused: list[Callable[[Any], Any]] = [
        lambda uow: handle_update_record(
            uow,
            UpdateRecord(
                **base, stream_id=thing.stream_id, expected_version=1, changes={"title": "x"}
            ),
        ),
        lambda uow: handle_void_record(
            uow,
            VoidRecord(**base, stream_id=thing.stream_id, expected_version=1, reason="r"),
        ),
        lambda uow: handle_set_pset_values(
            uow,
            SetPsetValues(
                **base,
                stream_id=thing.stream_id,
                expected_version=1,
                pset="valve_data",
                layer="standard",
                values={"manufacturer": "Acme"},
            ),
        ),
        lambda uow: handle_transition_workflow(
            uow,
            TransitionWorkflow(
                **base, stream_id=thing.stream_id, expected_version=1, transition="submit"
            ),
        ),
        lambda uow: handle_add_link(
            uow, AddLink(**base, from_id=thing.stream_id, to_id=other.stream_id)
        ),
    ]
    with use_modules([fake_spec(numbering_patterns=registered_patterns)]):  # allows nothing
        for run in refused:
            with pytest.raises(UnsupportedRecordTypeError, match="fake.Thing"):
                with open_uow(db) as uow:
                    run(uow)


def test_a_spec_cannot_allow_what_is_not_a_generic_command_or_not_its_type() -> None:
    with pytest.raises(ModuleLoadError, match="not a generic command"):
        fake_spec(generic_commands={THING: frozenset({"DropTable"})})
    with pytest.raises(ModuleLoadError, match="not one of its record types"):
        fake_spec(generic_commands={"fake.Other": frozenset({"UpdateRecord"})})
