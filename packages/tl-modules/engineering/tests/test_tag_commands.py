"""Tag commands against a real ledger on every adapter (T06, T08): create, class, supersession."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import as_json, seed_registry
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import Event
from tl_core.services.commands import CommandResult
from tl_core.services.errors import (
    DuplicateKeyError,
    GuardFailedError,
    NoChangesError,
    ReservedKeyError,
    UnknownPsetError,
)
from tl_core.services.psets import SetPsetValues, conformance, handle_set_pset_values
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_engineering import registry
from tl_mod_engineering.errors import (
    InvalidTagNumberError,
    RegistryScopeError,
    TagClassNotFoundError,
    TagNotFoundError,
    TagSupersededError,
)
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    MergeTags,
    ReclassifyTag,
    RecordTag,
    RenameTag,
    SplitTag,
    handle_create_tag,
    handle_merge_tags,
    handle_reclassify_tag,
    handle_record_tag,
    handle_rename_tag,
    handle_split_tag,
)

pytestmark = pytest.mark.usefixtures("fixture_schemas")

BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    return db


def create(db: DbTarget, number: str = "47-FV-1001", **more: Any) -> CommandResult:
    fields: dict[str, Any] = {"number": number, "class_code": "ControlValve", "service": "Feed gas"}
    fields.update(more)
    with open_uow(db) as uow:
        return handle_create_tag(uow, CreateTag(**{**BASE, **fields}))


def tag(db: DbTarget, number: str) -> registry.TagRow:
    with open_uow(db, readonly=True) as uow:
        found = registry.find_tag(uow.conn(), "project:P123", number)
    assert found is not None
    return found


def scalar(db: DbTarget, sql: str, **params: Any) -> Any:
    with open_uow(db, readonly=True) as uow:
        return uow.conn().execute(text(sql), params).scalar_one()


def count(db: DbTarget, table: str = "cur_core_record") -> int:
    return int(scalar(db, f"SELECT COUNT(*) FROM {table}"))


def set_values(
    db: DbTarget, made: CommandResult, pset: str, layer: str = "standard", **values: Any
) -> Any:
    with open_uow(db) as uow:
        row = registry.get_tag(uow.conn(), made.stream_id)
        assert row is not None
        return handle_set_pset_values(
            uow,
            SetPsetValues(
                **BASE,
                stream_id=made.stream_id,
                expected_version=row.version,
                pset=pset,
                layer=layer,  # type: ignore[arg-type]
                values=values,
            ),
        )


def transition(db: DbTarget, made: CommandResult, name: str) -> Any:
    with open_uow(db) as uow:
        row = registry.get_tag(uow.conn(), made.stream_id)
        assert row is not None
        return handle_transition_workflow(
            uow,
            TransitionWorkflow(
                **BASE, stream_id=made.stream_id, expected_version=row.version, transition=name
            ),
        )


# --- create --------------------------------------------------------------------------------------


def test_create_parses_the_number_and_binds_the_class(ledger: DbTarget) -> None:
    made = create(ledger)
    assert made.key == "47-FV-1001" and made.version == 2
    assert [e.event_type for e in made.events] == ["Record.Created", "Tag.Defined"]
    row = tag(ledger, "47-FV-1001")
    assert (row.id, row.class_code, row.title) == (made.stream_id, "ControlValve", "Feed gas")
    assert (row.area, row.mnemonic, row.sequence) == ("47", "FV", 1001)
    assert row.segments == {"area": "47", "mnemonic": "FV", "seq": "1001"}
    assert (row.pattern_code, row.number_status, row.violations, row.origin) == (
        "tag",
        "ok",
        [],
        "created",
    )
    payload = made.events[1].payload
    assert payload["bound_psets"] == ["valve_data"] and payload["supersedes"] == []
    assert row.conformance == "nonconformant"  # valve_data is required by the class and empty
    assert payload["effective_schema_hash"]


def test_the_class_requirement_shows_in_the_live_conformance_report(ledger: DbTarget) -> None:
    made = create(ledger)
    with open_uow(ledger, readonly=True) as uow:
        report = conformance(uow, made.stream_id)
    assert report.status == "nonconformant"
    assert [(i.path, i.rule) for i in report.issues] == [
        ("psets.valve_data", "class_required"),
        ("psets.valve_data.manufacturer", "required_in_state"),
    ]
    plain = create(ledger, "10-PT-0001", class_code=None)
    with open_uow(ledger, readonly=True) as uow:
        assert conformance(uow, plain.stream_id).status == "ok"
    assert tag(ledger, "10-PT-0001").class_code is None


def test_initial_values_are_written_and_make_the_tag_conform(ledger: DbTarget) -> None:
    made = create(ledger, psets={"valve_data": {"size_in": 4, "manufacturer": "Acme"}})
    assert [e.event_type for e in made.events] == [
        "Record.Created",
        "Tag.Defined",
        "Pset.ValuesSet",
    ]
    assert tag(ledger, "47-FV-1001").conformance == "ok"
    assert tag(ledger, "47-FV-1001").psets == {"valve_data": {"size_in": 4, "manufacturer": "Acme"}}


def test_a_pset_the_class_does_not_bind_is_refused_and_the_tag_is_not_created(
    ledger: DbTarget,
) -> None:
    with pytest.raises(UnknownPsetError):
        create(ledger, psets={"safety_data": {"sil_rating": 2}})
    assert (
        count(ledger) == count(ledger, "cur_core_record")
        and count(ledger, "cur_engineering_tag") == 0
    )


def test_a_number_that_breaks_the_pattern_is_refused_with_every_problem(ledger: DbTarget) -> None:
    before = count(ledger)
    with pytest.raises(InvalidTagNumberError) as raised:
        create(ledger, "47-XX-1")
    assert [(i["segment"], i["rule"]) for i in raised.value.issues] == [
        ("seq", "sequence"),
        ("mnemonic", "unknown_mnemonic"),
        ("mnemonic", "class_mnemonic"),  # a warning: it is listed but does not refuse
    ]
    assert "'XX' is not a registered mnemonic" in str(raised.value)
    assert "usually identify" not in str(raised.value)  # only errors are in the message
    assert count(ledger) == before


def test_the_record_policy_keeps_a_bad_number_as_a_violation(ledger: DbTarget) -> None:
    with open_uow(ledger) as uow:
        handle_record_tag(uow, RecordTag(**BASE, number="LEGACY-7"), origin="import")
    row = tag(ledger, "LEGACY-7")
    assert (row.number_status, row.origin, row.segments, row.area) == (
        "violation",
        "import",
        {},
        None,
    )
    assert [v["rule"] for v in row.violations] == ["pattern"]


def test_a_class_that_does_not_usually_use_the_prefix_is_a_warning_only(ledger: DbTarget) -> None:
    create(ledger, "47-FV-1002", class_code="ManualValve")
    row = tag(ledger, "47-FV-1002")
    assert row.number_status == "ok"
    assert [(v["rule"], v["level"]) for v in row.violations] == [("class_mnemonic", "warning")]


def test_create_refuses_what_it_cannot_accept(ledger: DbTarget) -> None:
    create(ledger)
    with pytest.raises(DuplicateKeyError):
        create(ledger)
    with pytest.raises(TagClassNotFoundError, match="Nope"):
        create(ledger, "47-FV-1003", class_code="Nope")
    with pytest.raises(RegistryScopeError, match="belong to a project"):
        with open_uow(ledger) as uow:
            handle_create_tag(
                uow,
                CreateTag(actor="user:u", source="test", scope="company", number="47-FV-1004"),
            )
    assert count(ledger, "cur_engineering_tag") == 1


def test_without_a_registry_pattern_any_number_is_accepted(db: DbTarget) -> None:
    made = create(db, "WHATEVER-1", class_code=None)
    row = tag(db, "WHATEVER-1")
    assert (row.pattern_code, row.number_status, row.segments) == (None, "ok", {})
    assert made.version == 2


def test_a_typed_tag_number_may_hold_a_slash_but_not_an_at_sign(db: DbTarget) -> None:
    """Every key a module builds holds ``@``, so a typed number without one cannot collide."""
    made = create(db, "MP/12/FV-1", class_code=None)
    assert made.key == "MP/12/FV-1" and tag(db, "MP/12/FV-1").number_status == "ok"
    with pytest.raises(ReservedKeyError):
        create(db, "47-FV@1002", class_code=None)
    assert count(db, "cur_engineering_tag") == 1


# --- the class drives the workflow ----------------------------------------------------------------


def test_a_tag_cannot_start_design_until_its_class_psets_conform(ledger: DbTarget) -> None:
    made = create(ledger)
    with pytest.raises(GuardFailedError, match="conformance"):
        transition(ledger, made, "design")
    set_values(ledger, made, "valve_data", size_in=4, body_material="CS", manufacturer="Acme")
    transition(ledger, made, "design")
    assert tag(ledger, "47-FV-1001").status == "Design"


def test_retiring_a_class_does_not_unbind_its_psets_from_existing_tags(ledger: DbTarget) -> None:
    from tl_mod_engineering.binding import bound_psets

    made = create(ledger)
    with open_uow(ledger) as uow:
        uow.append(
            stream_id="C-ControlValve",
            stream_type="engineering.TagClass",
            scope="company",
            expected_version=2,
            events=[_new("TagClass.Closed", {"lifecycle": "retired", "reason": "r"})],
            actor="user:u",
            source="test",
            correlation_id="c",
        )
    with open_uow(ledger, readonly=True) as uow:
        assert bound_psets(uow.conn(), "engineering.Tag", made.stream_id) == ("valve_data",)
        assert bound_psets(uow.conn(), "core.Record", made.stream_id) == ()
    with pytest.raises(TagClassNotFoundError):
        create(ledger, "47-FV-1005")


def _new(event_type: str, payload: dict[str, Any]) -> Any:
    from tl_core.ledger import NewEvent

    return NewEvent(event_type=event_type, payload=payload)


# --- reclassify ----------------------------------------------------------------------------------


def test_reclassify_changes_the_class_and_recomputes_conformance(ledger: DbTarget) -> None:
    made = create(ledger, "47-FV-1001", class_code=None)
    assert tag(ledger, "47-FV-1001").conformance == "ok"
    with open_uow(ledger) as uow:
        changed = handle_reclassify_tag(
            uow,
            ReclassifyTag(**BASE, stream_id=made.stream_id, class_code="ControlValve", reason="r"),
        )
    (event,) = changed.events
    assert event.payload["from_class"] is None and event.payload["to_class"] == "ControlValve"
    assert event.payload["bound_psets"] == ["valve_data"]
    row = tag(ledger, "47-FV-1001")
    assert (row.class_code, row.conformance, row.version) == ("ControlValve", "nonconformant", 3)


def test_reclassify_refuses_the_same_class_an_unknown_class_and_an_unknown_tag(
    ledger: DbTarget,
) -> None:
    made = create(ledger)

    def go(stream_id: str, code: str) -> None:
        with open_uow(ledger) as uow:
            handle_reclassify_tag(
                uow, ReclassifyTag(**BASE, stream_id=stream_id, class_code=code, reason="r")
            )

    with pytest.raises(NoChangesError):
        go(made.stream_id, "ControlValve")
    with pytest.raises(TagClassNotFoundError):
        go(made.stream_id, "Nope")
    with pytest.raises(TagNotFoundError):
        go("nope", "ManualValve")


# --- rename, split, merge ------------------------------------------------------------------------


def events_of(db: DbTarget, stream_id: str) -> list[Event]:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.read_stream(stream_id)


def test_rename_creates_a_superseding_tag_with_the_same_class_and_values(ledger: DbTarget) -> None:
    old = create(ledger, psets={"valve_data": {"size_in": 4, "manufacturer": "Acme"}})
    set_values(ledger, old, "valve_data", "custom", **{"x.fat_witness_by": "J. Smith"})
    with open_uow(ledger) as uow:
        new = handle_rename_tag(
            uow,
            RenameTag(
                **BASE, stream_id=old.stream_id, new_number="47-FV-1002", reason="P&ID rev 3"
            ),
        )
    fresh = tag(ledger, "47-FV-1002")
    assert (fresh.id, fresh.class_code, fresh.title, fresh.origin) == (
        new.stream_id,
        "ControlValve",
        "Feed gas",
        "rename",
    )
    assert fresh.psets["valve_data"] == {
        "size_in": 4,
        "manufacturer": "Acme",
        "x": {"fat_witness_by": "J. Smith"},
    }
    defined = next(e for e in new.events if e.event_type == "Tag.Defined")
    assert defined.payload["supersedes"] == [old.stream_id]
    gone = tag(ledger, "47-FV-1001")
    assert gone.status == "Superseded"
    superseded = [e for e in events_of(ledger, old.stream_id) if e.event_type == "Tag.Superseded"]
    assert [e.payload for e in superseded] == [
        {"operation": "rename", "superseded_by": [new.stream_id], "reason": "P&ID rev 3"}
    ]
    link = scalar(
        ledger,
        "SELECT relation FROM cur_links WHERE from_id = :new AND to_id = :old",
        new=new.stream_id,
        old=old.stream_id,
    )
    assert link == "supersedes"
    correlations = {e.correlation_id for e in events_of(ledger, old.stream_id)[-2:]}
    assert correlations == {events_of(ledger, new.stream_id)[0].correlation_id}


def test_a_superseded_tag_takes_no_more_changes(ledger: DbTarget) -> None:
    old = create(ledger)
    with open_uow(ledger) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old.stream_id, new_number="47-FV-1002", reason="r")
        )
    with pytest.raises(TagSupersededError, match="Superseded"):
        with open_uow(ledger) as uow:
            handle_reclassify_tag(
                uow,
                ReclassifyTag(
                    **BASE, stream_id=old.stream_id, class_code="ManualValve", reason="r"
                ),
            )
    with pytest.raises(TagSupersededError):
        with open_uow(ledger) as uow:
            handle_rename_tag(
                uow, RenameTag(**BASE, stream_id=old.stream_id, new_number="47-FV-1009", reason="r")
            )


def test_a_rename_that_cannot_work_writes_nothing(ledger: DbTarget) -> None:
    old = create(ledger)
    create(ledger, "47-FV-1002")
    before = count(ledger)

    def rename(number: str) -> None:
        with open_uow(ledger) as uow:
            handle_rename_tag(
                uow, RenameTag(**BASE, stream_id=old.stream_id, new_number=number, reason="r")
            )

    with pytest.raises(NoChangesError):
        rename("47-FV-1001")
    with pytest.raises(DuplicateKeyError):
        rename("47-FV-1002")
    with pytest.raises(InvalidTagNumberError):
        rename("47-ZZ-1")
    assert count(ledger) == before and tag(ledger, "47-FV-1001").status is None


def test_split_makes_several_tags_that_all_supersede_the_old_one(ledger: DbTarget) -> None:
    old = create(ledger, psets={"valve_data": {"size_in": 4}})
    with open_uow(ledger) as uow:
        made = handle_split_tag(
            uow,
            SplitTag(
                **BASE,
                stream_id=old.stream_id,
                new_numbers=["47-FV-1002", "47-FV-1003"],
                reason="r",
            ),
        )
    assert [m.key for m in made] == ["47-FV-1002", "47-FV-1003"]
    assert all(tag(ledger, m.key or "").origin == "split" for m in made)
    superseded = [e for e in events_of(ledger, old.stream_id) if e.event_type == "Tag.Superseded"]
    assert [e.payload["superseded_by"] for e in superseded] == [[m.stream_id for m in made]]
    assert tag(ledger, "47-FV-1001").status == "Superseded"
    assert count(ledger, "cur_links") == 2
    with pytest.raises(NoChangesError):
        with open_uow(ledger) as uow:
            handle_split_tag(
                uow,
                SplitTag(
                    **BASE,
                    stream_id=made[0].stream_id,
                    new_numbers=["47-FV-1004", "47-FV-1004"],
                    reason="r",
                ),
            )


def test_merge_makes_one_tag_from_several_taking_the_first_ones_values(ledger: DbTarget) -> None:
    first = create(ledger, psets={"valve_data": {"size_in": 4}})
    second = create(ledger, "47-FV-1002", service="Other", psets={"valve_data": {"size_in": 6}})
    with open_uow(ledger) as uow:
        merged = handle_merge_tags(
            uow,
            MergeTags(
                **BASE,
                stream_ids=[first.stream_id, second.stream_id],
                new_number="47-FV-1009",
                reason="r",
            ),
        )
    row = tag(ledger, "47-FV-1009")
    assert (row.id, row.title, row.origin) == (merged.stream_id, "Feed gas", "merge")
    assert row.psets["valve_data"]["size_in"] == 4
    assert [tag(ledger, n).status for n in ("47-FV-1001", "47-FV-1002")] == ["Superseded"] * 2
    assert count(ledger, "cur_links") == 2
    with pytest.raises(NoChangesError):
        with open_uow(ledger) as uow:
            handle_merge_tags(
                uow,
                MergeTags(**BASE, stream_ids=[row.id, row.id], new_number="47-FV-1010", reason="r"),
            )


def test_blank_reasons_are_refused() -> None:
    from pydantic import ValidationError

    for build in (
        lambda: RenameTag(**BASE, stream_id="x", new_number="n", reason=" "),
        lambda: SplitTag(**BASE, stream_id="x", new_numbers=["a", "b"], reason=""),
        lambda: MergeTags(**BASE, stream_ids=["a", "b"], new_number="n", reason=" "),
        lambda: ReclassifyTag(**BASE, stream_id="x", class_code="c", reason=" "),
    ):
        with pytest.raises(ValidationError):
            build()
    with pytest.raises(ValidationError):
        SplitTag(**BASE, stream_id="x", new_numbers=["a"], reason="r")


# --- the ledger is the truth ---------------------------------------------------------------------


def test_a_rebuild_of_the_projections_gives_the_same_tags(ledger: DbTarget) -> None:
    old = create(ledger, psets={"valve_data": {"size_in": 4}})
    create(ledger, "10-PT-0001", class_code=None)
    with open_uow(ledger) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old.stream_id, new_number="47-FV-1002", reason="r")
        )

    def snapshot() -> Any:
        with open_uow(ledger, readonly=True) as uow:
            conn = uow.conn()
            tags = [
                tuple(r)
                for r in conn.execute(text("SELECT * FROM cur_engineering_tag ORDER BY id"))
            ]
            record = [
                tuple(r)
                for r in conn.execute(
                    text(
                        "SELECT id, status, conformance, version, last_seq "
                        "FROM cur_core_record ORDER BY id"
                    )
                )
            ]
        return tags, record

    before = snapshot()
    rebuild_projections(ledger)
    assert snapshot() == before
    assert (
        as_json(
            scalar(
                ledger, "SELECT segments_json FROM cur_engineering_tag WHERE number = '10-PT-0001'"
            )
        )["seq"]
        == "0001"
    )


# --- who can write what: the origin is the server's, a recorded violation is a separate command ---


def test_a_create_command_has_no_origin_and_no_pattern_policy() -> None:
    for extra in ({"origin": "import"}, {"pattern_policy": "record"}):
        with pytest.raises(ValidationError, match="Extra inputs"):
            CreateTag.model_validate({**BASE, "number": "47-FV-1001", **extra})
    with pytest.raises(ValidationError, match="Extra inputs"):
        RecordTag.model_validate({**BASE, "number": "LEGACY-1", "origin": "import"})


def test_record_tag_keeps_a_bad_number_and_says_created_unless_the_service_says_import(
    ledger: DbTarget,
) -> None:
    with open_uow(ledger) as uow:
        handle_record_tag(uow, RecordTag(**BASE, number="LEGACY-8"))
    assert (tag(ledger, "LEGACY-8").number_status, tag(ledger, "LEGACY-8").origin) == (
        "violation",
        "created",
    )
    with pytest.raises(InvalidTagNumberError):
        create(ledger, "LEGACY-9")  # the ordinary command still refuses it


def test_the_commands_bound_their_lists_mappings_and_texts() -> None:
    from tl_mod_engineering.limits import MAX_ITEMS, MAX_NUMBER, MAX_PROPERTIES, MAX_PSETS

    ids = [f"id{n}" for n in range(MAX_ITEMS + 1)]
    with pytest.raises(ValidationError, match="at most 500"):
        MergeTags(**BASE, stream_ids=ids, new_number="47-FV-1001", reason="r")
    with pytest.raises(ValidationError, match="at most 500"):
        SplitTag(**BASE, stream_id="x", new_numbers=ids, reason="r")
    with pytest.raises(ValidationError, match="at most 50"):
        CreateTag(**BASE, number="47-FV-1001", psets={f"p{n}": {} for n in range(MAX_PSETS + 1)})
    wide = {"valve_data": {f"k{n}": 1 for n in range(MAX_PROPERTIES + 1)}}
    with pytest.raises(ValidationError, match="more than 200 properties"):
        CreateTag(**BASE, number="47-FV-1001", psets=wide)
    with pytest.raises(ValidationError, match="at most 128"):
        CreateTag(**BASE, number="9" * (MAX_NUMBER + 1))
