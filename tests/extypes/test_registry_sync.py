"""Registry sync: register, quarantine, idempotence and conflict detection (brief 31.1; D8, D9).

Runs on each adapter (the ``world`` fixture uses ``new_db``).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from extworld import ALICE, LIFT, OBSERVATION, World
from sqlalchemy import text
from tl_adapters.db import rebuild_projections
from tl_core.extypes import registry
from tl_core.extypes.errors import TypeNotActiveError, UnknownTypeError
from tl_core.extypes.registry import scan
from tl_core.extypes.types import TypeIssue


def refs(views: list[Any]) -> list[str]:
    return [v.registration.type_ref for v in views]


def rows(world: World) -> list[dict[str, Any]]:
    with world.factory(readonly=True) as uow:
        found = (
            uow.conn()
            .execute(text("SELECT * FROM cur_core_type_registration ORDER BY type_ref"))
            .mappings()
            .all()
        )
        return [dict(r) for r in found]


# --- scan -----------------------------------------------------------------------------------------


def test_scan_finds_package_directories_sorted(world: World) -> None:
    found = [p.relative_to(world.root.resolve()).as_posix() for p in scan(world.root)]
    assert found == ["co.acme/LiftPlan/1.0.0", "co.acme/SafetyObservation/1.0.0"]


def test_scan_ignores_hidden_directories_and_does_not_enter_a_package(
    world: World, tmp_path: Path
) -> None:
    hidden = world.root / ".git" / "co.x" / "Y" / "1.0.0"
    hidden.mkdir(parents=True)
    (hidden / "type.yaml").write_text("x: 1\n")
    nested = world.package() / "templates" / "inner"
    nested.mkdir(parents=True)
    (nested / "type.yaml").write_text("x: 1\n")
    found = [p.relative_to(world.root.resolve()).as_posix() for p in scan(world.root)]
    assert found == ["co.acme/LiftPlan/1.0.0", "co.acme/SafetyObservation/1.0.0"]


def test_scan_finds_a_directory_that_only_has_a_lock_and_a_missing_root_is_empty(
    world: World, tmp_path: Path
) -> None:
    lonely = world.root / "co.acme" / "Lonely" / "1.0.0"
    lonely.mkdir(parents=True)
    (lonely / "type.lock").write_text('{"files": {}}')
    assert lonely.resolve() in scan(world.root)
    assert scan(tmp_path / "nowhere") == []


# --- registering ---------------------------------------------------------------------------------


def test_sync_registers_every_valid_package_with_one_event_each(world: World) -> None:
    views = world.sync()
    assert refs(views) == ["co.acme.LiftPlan@1.0.0", "co.acme.SafetyObservation@1.0.0"]
    events = world.type_events()
    assert [e.event_type for e in events] == ["TypeRegistration.Registered"] * 2
    first = events[0]
    assert first.stream_id == "type:co.acme.LiftPlan@1.0.0"
    assert first.stream_type == "core.TypeRegistration"
    assert first.scope == "company" and first.actor == ALICE and first.source == "test"
    payload = first.payload
    assert payload["status"] == "active" and payload["owner"] == ALICE
    assert payload["storage_mode"] == "object-backed"
    assert payload["index_fields"] == ["lift_date", "crane", "load_tonnes", "risk_class"]
    assert payload["location_uri"] == world.package().resolve().as_uri()
    assert {v.registration.status for v in world.types()} == {"active"}


def test_the_registration_row_holds_metadata_only(world: World) -> None:
    world.sync()
    lift = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert lift["type_name"] == LIFT and lift["pset"] == "co_acme_lift_plan"
    assert lift["status"] == "active" and lift["storage_mode"] == "object-backed"
    assert json.loads(lift["index_fields_json"]) == [
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
    ]
    assert lift["report_json"] is None and lift["conflict_hash"] is None
    assert lift["first_seq"] == lift["last_seq"] and lift["version_n"] == 1


def test_sync_is_idempotent_it_appends_nothing_the_second_time(world: World) -> None:
    world.sync()
    head = world.head()
    assert world.sync() == []
    assert world.head() == head


def test_a_third_sync_after_a_quarantine_is_also_silent(world: World) -> None:
    world.package().joinpath("examples", "bad.json").write_text("{}")
    world.relock(world.package())
    world.sync()
    head = world.head()
    assert world.sync() == [] and world.sync() == []
    assert world.head() == head


def test_sync_of_an_empty_or_missing_root_registers_nothing(world: World, tmp_path: Path) -> None:
    from tl_core.extypes import registry as reg

    assert reg.sync(world.factory, tmp_path / "empty", actor=ALICE, source="test") == []


# --- quarantine -----------------------------------------------------------------------------------


def test_an_invalid_package_is_quarantined_with_its_report_and_the_others_register(
    world: World,
) -> None:
    (world.package() / "examples" / "bad.json").write_text("{}")
    world.relock(world.package())
    views = world.sync()
    by_ref = {v.registration.type_ref: v.registration.status for v in views}
    assert by_ref == {
        "co.acme.LiftPlan@1.0.0": "quarantined",
        "co.acme.SafetyObservation@1.0.0": "active",
    }
    with world.factory(readonly=True) as uow:
        entries = registry.list_quarantined(uow.conn())
    assert [e.type_ref for e in entries] == ["co.acme.LiftPlan@1.0.0"]
    entry = entries[0]
    assert entry.status == "quarantined" and entry.registered_hash is None
    assert {(i.kind, i.path) for i in entry.report} == {("example", "examples/bad.json")}
    quarantined = [e for e in world.type_events() if e.event_type == "TypeRegistration.Quarantined"]
    assert len(quarantined) == 1
    assert quarantined[0].payload["content_hash"] == entry.content_hash


def test_a_quarantined_row_has_no_owner_storage_mode_or_schema_hash(world: World) -> None:
    (world.package() / "examples" / "bad.json").write_text("{}")
    world.relock(world.package())
    world.sync()
    row = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert row["status"] == "quarantined"
    assert row["owner"] is None and row["storage_mode"] is None and row["schema_hash"] is None
    assert row["pset"] == "co_acme_lift_plan" and row["type_name"] == LIFT
    view = next(v for v in world.types("quarantined"))
    assert view.registration.owner == "" and view.registration.index_fields == []


def test_fixing_a_quarantined_package_registers_it(world: World) -> None:
    bad = world.package() / "examples" / "bad.json"
    bad.write_text("{}")
    world.relock(world.package())
    world.sync()
    bad.unlink()
    world.relock(world.package())
    views = world.sync()
    assert refs(views) == ["co.acme.LiftPlan@1.0.0"]
    assert views[0].registration.status == "active"
    lift = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert (
        lift["report_json"] is None
        and lift["version_n"] == 2
        and lift["first_seq"] < lift["last_seq"]
    )


def test_a_second_different_failure_updates_the_report(world: World) -> None:
    pkg = world.package()
    (pkg / "examples" / "bad.json").write_text("{}")
    world.relock(pkg)
    world.sync()
    (pkg / "examples" / "bad.json").write_text('{"crane": "x"}')
    world.relock(pkg)
    assert refs(world.sync()) == ["co.acme.LiftPlan@1.0.0"]
    with world.factory(readonly=True) as uow:
        (entry,) = registry.list_quarantined(uow.conn())
    assert any("crane" in i.detail for i in entry.report)


def test_a_path_that_is_not_a_package_path_is_quarantined_under_a_stand_in_ref(
    world: World,
) -> None:
    stray = world.root / "Stray"
    shutil.copytree(world.package(), stray)
    views = world.sync()
    assert "invalid:Stray" in refs(views)
    stray_view = next(v for v in views if v.registration.type_ref == "invalid:Stray")
    assert stray_view.registration.status == "quarantined"
    events = [e for e in world.type_events() if e.stream_id == "type:invalid:Stray"]
    assert [e.event_type for e in events] == ["TypeRegistration.Quarantined"]
    head = world.head()
    assert world.sync() == [] and world.head() == head


def test_directory_backed_storage_is_quarantined_as_unsupported(world: World) -> None:
    world.edit(
        world.package(),
        "type.yaml",
        "tl:storage_mode: object-backed",
        "tl:storage_mode: directory-backed",
    )
    world.sync()
    with world.factory(readonly=True) as uow:
        (entry,) = registry.list_quarantined(uow.conn())
    assert [i.kind for i in entry.report] == ["unsupported"]


# --- conflicts ------------------------------------------------------------------------------------


def test_editing_a_registered_version_is_a_conflict_and_the_registration_stays(
    world: World,
) -> None:
    world.sync()
    registered = {r["type_ref"]: r for r in rows(world)}
    world.edit(world.package(), "README.md", "planned crane lift", "planned crane lift (edited)")
    views = world.sync()
    assert refs(views) == ["co.acme.LiftPlan@1.0.0"]
    now = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    before = registered["co.acme.LiftPlan@1.0.0"]
    assert now["status"] == "active"
    assert now["content_hash"] == before["content_hash"]  # unchanged: the old version stands
    assert now["conflict_hash"] is not None and now["conflict_hash"] != now["content_hash"]
    report = [TypeIssue.model_validate(i) for i in json.loads(now["report_json"])]
    assert report[0].kind == "conflict" and "new version" in report[0].detail
    assert world.types("active")[0].registration.content_hash == before["content_hash"]


def test_a_refused_change_is_reported_once(world: World) -> None:
    world.sync()
    world.edit(world.package(), "README.md", "planned crane lift", "planned crane lift (edited)")
    world.sync()
    head = world.head()
    assert world.sync() == [] and world.head() == head


def test_a_conflict_lists_in_the_quarantine_report_with_both_hashes(world: World) -> None:
    world.sync()
    original = world.types("active")[0].registration.content_hash
    world.edit(world.package(), "README.md", "planned crane lift", "planned crane lift (edited)")
    world.sync()
    with world.factory(readonly=True) as uow:
        (entry,) = registry.list_quarantined(uow.conn())
    assert entry.status == "active" and entry.registered_hash == original
    assert entry.content_hash != original


def test_reverting_the_files_clears_the_conflict(world: World) -> None:
    world.sync()
    readme = world.package() / "README.md"
    original = readme.read_text()
    world.edit(world.package(), "README.md", "planned crane lift", "planned crane lift (edited)")
    world.sync()
    readme.write_text(original)
    world.relock(world.package())
    assert refs(world.sync()) == ["co.acme.LiftPlan@1.0.0"]
    now = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert now["conflict_hash"] is None and now["report_json"] is None and now["status"] == "active"
    with world.factory(readonly=True) as uow:
        assert registry.list_quarantined(uow.conn()) == []
    head = world.head()
    assert world.sync() == [] and world.head() == head


def test_a_conflicting_change_that_is_also_invalid_still_keeps_the_registration(
    world: World,
) -> None:
    world.sync()
    (world.package() / "examples" / "bad.json").write_text("{}")
    world.relock(world.package())
    world.sync()
    now = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert now["status"] == "active"
    kinds = [i["kind"] for i in json.loads(now["report_json"])]
    assert kinds[0] == "conflict" and "example" in kinds


def test_a_new_version_registers_beside_the_old_one(world: World) -> None:
    world.sync()
    newer = world.root / "co.acme" / "LiftPlan" / "1.1.0"
    shutil.copytree(world.package(), newer)
    world.edit(newer, "README.md", "planned crane lift", "planned crane lift, v1.1")
    views = world.sync()
    assert refs(views) == ["co.acme.LiftPlan@1.1.0"]
    with world.factory(readonly=True) as uow:
        versions = [v.registration.version for v in registry.versions_of(uow.conn(), LIFT)]
        current = registry.current_type(uow.conn(), LIFT)
    assert versions == ["1.0.0", "1.1.0"]
    assert current is not None and current.registration.version == "1.1.0"


def test_versions_sort_numerically_not_as_text(world: World) -> None:
    world.sync()
    for version in ("1.2.0", "1.10.0"):
        copy = world.root / "co.acme" / "LiftPlan" / version
        shutil.copytree(world.package(), copy)
        world.edit(copy, "README.md", "planned crane lift", f"planned crane lift {version}")
    world.sync()
    with world.factory(readonly=True) as uow:
        current = registry.current_type(uow.conn(), LIFT)
    assert current is not None and current.registration.version == "1.10.0"


def test_two_types_whose_names_give_the_same_pset_conflict(world: World) -> None:
    world.sync()
    twin = world.root / "co.acme" / "LiftPlan" / "2.0.0"
    shutil.copytree(world.package(), twin)  # same type name: a version, not a clash
    other_ns = world.root / "co.acme.lift" / "Plan" / "1.0.0"  # its pset is co_acme_lift_plan too
    shutil.copytree(world.package(), other_ns)
    world.edit(other_ns, "type.yaml", "  LiftPlan:\n    is_a", "  Plan:\n    is_a")
    world.edit(
        other_ns, "workflow.yaml", "record_type: co.acme.LiftPlan", "record_type: co.acme.lift.Plan"
    )
    world.edit(
        other_ns, "settings.yaml", "co.acme.lift_plan.max_load_tonnes", "co.acme.lift.plan.max"
    )
    world.edit(other_ns, "settings.yaml", "owner: co.acme.LiftPlan", "owner: co.acme.lift.Plan")
    views = world.sync()
    statuses = {v.registration.type_ref: v.registration.status for v in views}
    assert statuses["co.acme.LiftPlan@2.0.0"] == "active"
    assert statuses["co.acme.lift.Plan@1.0.0"] == "quarantined"
    with world.factory(readonly=True) as uow:
        entries = {e.type_ref: e for e in registry.list_quarantined(uow.conn())}
    report = entries["co.acme.lift.Plan@1.0.0"].report
    assert [i.kind for i in report] == ["conflict"]
    assert "co.acme.LiftPlan" in report[0].detail


# --- deprecation ----------------------------------------------------------------------------------


def test_deprecate_marks_a_version_and_appends_one_event(world: World) -> None:
    world.sync()
    with world.factory() as uow:
        view = registry.deprecate_type(
            uow, type_ref="co.acme.LiftPlan@1.0.0", reason="superseded", actor=ALICE, source="test"
        )
    assert view.registration.status == "deprecated"
    events = [e for e in world.type_events() if e.event_type == "TypeRegistration.Deprecated"]
    assert len(events) == 1 and events[0].payload == {
        "type_ref": "co.acme.LiftPlan@1.0.0",
        "reason": "superseded",
    }
    row = next(r for r in rows(world) if r["type_ref"] == "co.acme.LiftPlan@1.0.0")
    assert row["reason"] == "superseded"
    head = world.head()
    assert world.sync() == [] and world.head() == head  # deprecation survives a sync


def test_a_deprecated_version_is_not_registered_again_by_a_later_sync(world: World) -> None:
    world.sync()
    with world.factory() as uow:
        registry.deprecate_type(
            uow, type_ref="co.acme.LiftPlan@1.0.0", reason="old", actor=ALICE, source="test"
        )
    world.sync()
    assert world.types("deprecated")[0].registration.type_ref == "co.acme.LiftPlan@1.0.0"


def test_deprecate_refuses_unknown_blank_and_not_active(world: World) -> None:
    world.sync()
    with world.factory() as uow, pytest.raises(UnknownTypeError):
        registry.deprecate_type(
            uow, type_ref="co.acme.Nope@1.0.0", reason="x", actor=ALICE, source="test"
        )
    with world.factory() as uow, pytest.raises(UnknownTypeError):
        registry.deprecate_type(uow, type_ref="nonsense", reason="x", actor=ALICE, source="test")
    with world.factory() as uow, pytest.raises(Exception, match="reason"):
        registry.deprecate_type(
            uow, type_ref="co.acme.LiftPlan@1.0.0", reason="  ", actor=ALICE, source="test"
        )
    with world.factory() as uow:
        registry.deprecate_type(
            uow, type_ref="co.acme.LiftPlan@1.0.0", reason="old", actor=ALICE, source="test"
        )
    with world.factory() as uow, pytest.raises(TypeNotActiveError):
        registry.deprecate_type(
            uow, type_ref="co.acme.LiftPlan@1.0.0", reason="again", actor=ALICE, source="test"
        )


# --- reading --------------------------------------------------------------------------------------


def test_list_types_filters_by_status_and_get_type_reads_one(world: World) -> None:
    (world.package(OBSERVATION) / "examples" / "bad.json").write_text("{}")
    world.relock(world.package(OBSERVATION))
    world.sync()
    assert [v.registration.type_ref for v in world.types("active")] == ["co.acme.LiftPlan@1.0.0"]
    assert [v.registration.type_ref for v in world.types("quarantined")] == [
        "co.acme.SafetyObservation@1.0.0"
    ]
    assert world.types("deprecated") == []
    assert len(world.types()) == 2
    with world.factory(readonly=True) as uow:
        found = registry.get_type(uow.conn(), "co.acme.LiftPlan@1.0.0")
        missing = registry.get_type(uow.conn(), "co.acme.Nope@1.0.0")
    assert found is not None and found.seq > 0 and missing is None


# --- replay ---------------------------------------------------------------------------------------


def test_rebuilding_the_projections_gives_the_same_registry_rows(world: World) -> None:
    pkg = world.package()
    (pkg / "examples" / "bad.json").write_text("{}")
    world.relock(pkg)
    world.sync()
    (pkg / "examples" / "bad.json").unlink()
    world.relock(pkg)
    world.sync()  # quarantined, then registered
    world.edit(pkg, "README.md", "planned crane lift", "planned crane lift (edited)")
    world.sync()  # a conflict
    with world.factory() as uow:
        registry.deprecate_type(
            uow,
            type_ref="co.acme.SafetyObservation@1.0.0",
            reason="old",
            actor=ALICE,
            source="test",
        )
    before = rows(world)
    rebuild_projections(world.db)
    assert rows(world) == before
    assert [r["status"] for r in before] == ["active", "deprecated"]


def test_the_registry_itself_catches_a_pset_clash_a_provider_does_not_know_about(
    world: World,
) -> None:
    from tl_core.schema_provider import DirectorySchemaProvider

    plain = DirectorySchemaProvider()  # knows no extension types, so its schema has no clash
    registry.sync(world.factory, world.root, actor=ALICE, source="test", provider=plain)
    other_ns = world.root / "co.acme.lift" / "Plan" / "1.0.0"
    shutil.copytree(world.package(), other_ns)
    world.edit(other_ns, "type.yaml", "  LiftPlan:\n    is_a", "  Plan:\n    is_a")
    world.edit(other_ns, "workflow.yaml", "co.acme.LiftPlan", "co.acme.lift.Plan")
    world.edit(
        other_ns, "settings.yaml", "co.acme.lift_plan.max_load_tonnes", "co.acme.lift.plan.max"
    )
    world.edit(other_ns, "settings.yaml", "owner: co.acme.LiftPlan", "owner: co.acme.lift.Plan")
    registry.sync(world.factory, world.root, actor=ALICE, source="test", provider=plain)
    with world.factory(readonly=True) as uow:
        entries = {e.type_ref: e for e in registry.list_quarantined(uow.conn())}
    report = entries["co.acme.lift.Plan@1.0.0"].report
    assert [i.kind for i in report] == ["conflict"]
    assert "pset name is already used by co.acme.LiftPlan" in report[0].detail


# --- review fixes: one bad package, lost races, single read, deprecation -------------------


def test_one_package_that_blows_up_is_quarantined_and_the_others_still_register(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.extypes.compile import compile_type as real

    def flaky(package: Path, coords: Any, **kwargs: Any) -> Any:
        if coords.name == "LiftPlan":
            raise FileNotFoundError("vanished while reading")
        return real(package, coords, **kwargs)

    monkeypatch.setattr("tl_core.extypes.validate.compile_type", flaky)
    views = world.sync()
    assert {v.registration.type_ref: v.registration.status for v in views} == {
        "co.acme.LiftPlan@1.0.0": "quarantined",
        "co.acme.SafetyObservation@1.0.0": "active",
    }
    with world.factory(readonly=True) as uow:
        (entry,) = registry.list_quarantined(uow.conn())
    assert [(i.kind, i.path) for i in entry.report] == [("compile", None)]
    assert "FileNotFoundError" in entry.report[0].detail


def test_a_url_import_is_quarantined_without_stopping_the_run(world: World) -> None:
    world.edit(
        world.package(),
        "type.yaml",
        "  - throughline/core/extension\n",
        "  - throughline/core/extension\n  - http://127.0.0.1:9/evil\n",
    )
    views = world.sync()
    assert {v.registration.type_ref: v.registration.status for v in views} == {
        "co.acme.LiftPlan@1.0.0": "quarantined",
        "co.acme.SafetyObservation@1.0.0": "active",
    }


def test_sync_reads_each_package_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from tl_core.extypes.validate import describe_package as real

    calls: list[Path] = []

    def counting(path: Path, root: Path | None = None) -> Any:
        calls.append(path)
        return real(path, root)

    monkeypatch.setattr("tl_core.extypes.registry.describe_package", counting)
    monkeypatch.setattr("tl_core.extypes.validate.describe_package", counting)
    world.sync()
    assert len(calls) == 2  # one per package, not one more for the validation


class _LosesOnce:
    """A unit-of-work factory whose first write fails like the loser of a race."""

    def __init__(self, inner: Any, failures: int) -> None:
        self.inner = inner
        self.failures = failures
        self.attempts = 0

    def __call__(self, readonly: bool = False) -> Any:
        manager = self.inner(readonly=readonly)
        if readonly:
            return manager
        return _Wrapped(manager, self)


class _Wrapped:
    def __init__(self, manager: Any, owner: _LosesOnce) -> None:
        self.manager, self.owner = manager, owner

    def __enter__(self) -> Any:
        uow = self.manager.__enter__()
        owner = self.owner
        real_append = uow.append

        def append(**kwargs: Any) -> Any:
            owner.attempts += 1
            if owner.attempts <= owner.failures:
                from tl_core.ledger import ConcurrencyError

                raise ConcurrencyError("expected version 0, stream is at 1")
            return real_append(**kwargs)

        uow.append = append
        return uow

    def __exit__(self, *exc: Any) -> Any:
        return self.manager.__exit__(*exc)


def test_the_loser_of_a_race_retries_once_and_registers(world: World) -> None:
    loser = _LosesOnce(world.factory, failures=1)
    views = registry.sync(loser, world.root, actor=ALICE, source="test")
    assert {v.registration.status for v in views} == {"active"} and len(views) == 2
    assert loser.attempts == 3  # one failed append, its retry, and the second package


def test_a_package_that_keeps_losing_is_left_for_the_next_run_and_does_not_abort(
    world: World,
) -> None:
    loser = _LosesOnce(world.factory, failures=2)
    assert len(registry.sync(loser, world.root, actor=ALICE, source="test")) == 1
    assert len(world.sync()) == 1  # the next run registers the one that kept losing
    assert {v.registration.status for v in world.types()} == {"active"}


def test_deprecate_tells_the_provider_after_the_commit(world: World) -> None:
    world.sync()
    before = registry.changes()
    with pytest.raises(UnknownTypeError):
        registry.deprecate(
            world.factory, type_ref="co.acme.Nope@1.0.0", reason="x", actor=ALICE, source="test"
        )
    assert registry.changes() == before  # a refusal changes nothing
    registry.deprecate(
        world.factory, type_ref=f"{LIFT}@1.0.0", reason="old", actor=ALICE, source="test"
    )
    assert registry.changes() == before + 1


def test_deprecate_type_inside_the_callers_unit_of_work_does_not_bump(world: World) -> None:
    world.sync()
    before = registry.changes()
    with world.factory() as uow:
        registry.deprecate_type(
            uow, type_ref=f"{LIFT}@1.0.0", reason="old", actor=ALICE, source="test"
        )
    assert registry.changes() == before


def test_reverting_a_conflict_on_a_deprecated_version_clears_it_and_keeps_it_deprecated(
    world: World,
) -> None:
    world.sync()
    registry.deprecate(
        world.factory, type_ref=f"{LIFT}@1.0.0", reason="superseded", actor=ALICE, source="test"
    )
    readme = world.package() / "README.md"
    original = readme.read_text()
    world.edit(world.package(), "README.md", "planned crane lift", "planned crane lift (edited)")
    world.sync()
    now = next(r for r in rows(world) if r["type_ref"] == f"{LIFT}@1.0.0")
    assert now["status"] == "deprecated" and now["conflict_hash"] is not None
    readme.write_text(original)
    world.relock(world.package())
    assert refs(world.sync()) == [f"{LIFT}@1.0.0"]
    now = next(r for r in rows(world) if r["type_ref"] == f"{LIFT}@1.0.0")
    assert now["status"] == "deprecated" and now["reason"] == "superseded"
    assert now["conflict_hash"] is None and now["report_json"] is None
    with world.factory(readonly=True) as uow:
        assert registry.list_quarantined(uow.conn()) == []
    before = rows(world)
    rebuild_projections(world.db)
    assert rows(world) == before
