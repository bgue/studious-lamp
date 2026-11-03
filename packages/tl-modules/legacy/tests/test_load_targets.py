"""Load targets found by entry point (W0-B2): registry, refusals, scope and the mapping form."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from tl_adapters.db import open_uow
from tl_core.modules import ModuleLoadError
from tl_core.util import new_ulid
from tl_mod_legacy.errors import LoadRefusedError, MappingProblemError
from tl_mod_legacy.model import Grid, LoaderDef, use_loaders
from tl_mod_legacy.targets import (
    LOAD_TARGET_ENTRY_POINT,
    MappingTarget,
    Target,
    TargetLoadError,
    check_scope,
    documents_target,
    installed_targets,
    load_targets,
    mapping_target,
    tags_target,
    target_for,
    use_targets,
)
from tl_mod_legacy.testing import ADMIN, PROJECT, LegacyWorld, tag_csv

COMPANY = "company"
COLUMNS = {"Name": "title", "Notes": "description"}


def mapping(kind: str = "costcodes", **extra: Any) -> Target:
    options: dict[str, Any] = {
        "module": "cost",
        "record_type": "cost.CostCode",
        "key_column": "Code",
        "columns": COLUMNS,
    }
    return mapping_target(kind, **{**options, **extra})


class Entry:
    """The members of an ``EntryPoint`` that ``load_targets`` uses."""

    def __init__(self, name: str, factory: Callable[[], Any], value: str = "x:y") -> None:
        self.name = name
        self.value = value
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


def entry(name: str, **extra: Any) -> Entry:
    return Entry(name, lambda: mapping(name, **extra))


#: The built-ins of the legacy package and the three targets of the materials package (P2-I3 S2).
INSTALLED_BY = {
    "documents": ("legacy", "project"),
    "materials_item_master": ("materials", "company"),
    "materials_location": ("materials", "project"),
    "materials_po_line": ("materials", "project"),
    "tags": ("legacy", "project"),
}
INSTALLED = list(INSTALLED_BY)


def load(*entries: Entry) -> dict[str, Target]:
    return load_targets(entries)  # type: ignore[arg-type]


# --- the registry -------------------------------------------------------------------------------


def test_the_group_name_is_the_documented_one() -> None:
    assert LOAD_TARGET_ENTRY_POINT == "throughline.load_targets"


def test_the_installed_targets_are_the_built_ins_and_the_materials_targets() -> None:
    found = installed_targets()
    assert list(found) == INSTALLED
    for kind, target in found.items():
        assert (target.kind, target.module, target.scope) == (kind, *INSTALLED_BY[kind])
        assert isinstance(target, Target)
    assert list(load_targets()) == list(found)


def test_the_two_built_in_factories_return_targets_of_their_own_kind() -> None:
    assert tags_target().kind == "tags" and documents_target().kind == "documents"


def test_a_plugin_is_found_and_the_result_is_sorted() -> None:
    assert list(load(entry("zeta"), entry("alpha"))) == ["alpha", "zeta"]
    assert load() == {}


def test_a_duplicate_name_is_a_module_load_error() -> None:
    with pytest.raises(ModuleLoadError, match="declared twice") as caught:
        load(entry("same"), Entry("same", lambda: mapping("same"), value="other:y"))
    assert isinstance(caught.value, TargetLoadError)
    assert "'same'" in str(caught.value) and LOAD_TARGET_ENTRY_POINT in str(caught.value)


def test_a_plugin_that_fails_to_load_is_refused_with_the_exception_type_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> Any:
        raise RuntimeError("secret internals hunter2")

    with caplog.at_level(logging.WARNING), pytest.raises(TargetLoadError) as caught:
        load(Entry("broken", broken))
    assert "'broken'" in str(caught.value) and "RuntimeError" in str(caught.value)
    assert "hunter2" not in str(caught.value) and "hunter2" in caplog.text


@pytest.mark.parametrize("produced", [None, "text", 3, object()])
def test_a_plugin_that_returns_no_target_is_refused(produced: Any) -> None:
    with pytest.raises(TargetLoadError, match="must return a Target"):
        load(Entry("odd", lambda: produced))


def test_a_target_named_differently_from_its_entry_point_is_refused() -> None:
    with pytest.raises(TargetLoadError, match="same name"):
        load(Entry("one", lambda: mapping("other")))


def test_a_target_with_a_scope_outside_project_and_company_is_refused() -> None:
    bad = mapping("odd")
    bad.scope = "everywhere"  # type: ignore[assignment]
    with pytest.raises(TargetLoadError, match="scope project or company"):
        load(Entry("odd", lambda: bad))


@pytest.mark.parametrize("bad", ["", "Upper", "1st", "has-dash", "has space", "_x"])
def test_a_bad_entry_point_name_is_refused_before_it_is_loaded(bad: str) -> None:
    def never() -> Any:
        raise AssertionError("loaded a misnamed plugin")

    with pytest.raises(TargetLoadError, match="must match"):
        load(Entry(bad, never))


def test_an_unknown_target_is_refused_and_the_known_ones_are_listed() -> None:
    with pytest.raises(LoadRefusedError) as caught:
        target_for("nope")
    assert "'nope'" in str(caught.value) and f"known: {', '.join(INSTALLED)}" in str(caught.value)


def test_with_none_installed_the_refusal_says_so() -> None:
    with use_targets({}), pytest.raises(LoadRefusedError, match="none installed"):
        target_for("tags")


def test_use_targets_replaces_the_registry_for_the_block_only() -> None:
    mine = mapping("mine")
    with use_targets({"mine": mine}):
        assert target_for("mine") is mine
        assert list(installed_targets()) == ["mine"]
        with pytest.raises(LoadRefusedError):
            target_for("tags")
    assert list(installed_targets()) == INSTALLED


# --- scope --------------------------------------------------------------------------------------


def test_a_project_target_loads_into_a_project_and_refuses_the_company() -> None:
    target = target_for("tags")
    check_scope(target, PROJECT)
    with pytest.raises(LoadRefusedError, match="loads into a project.*--project"):
        check_scope(target, COMPANY)


def test_a_company_target_loads_into_the_company_and_refuses_a_project() -> None:
    target = mapping("registry", scope="company")
    check_scope(target, COMPANY)
    with pytest.raises(LoadRefusedError, match="loads into the company.*--company"):
        check_scope(target, PROJECT)


def test_a_project_target_with_a_malformed_scope_is_refused() -> None:
    with pytest.raises(LoadRefusedError):
        check_scope(target_for("tags"), "site:S1")


def test_opening_a_run_for_a_project_target_with_the_company_scope_is_refused(
    world: LegacyWorld,
) -> None:
    runs_before = len(world.runs())
    with pytest.raises(LoadRefusedError, match="--project"):
        world.service.open(COMPANY, "test-tags", "tags.csv", tag_csv(2), actor=ADMIN)
    assert len(world.runs()) == runs_before


def test_opening_a_run_with_an_unregistered_target_is_refused(world: LegacyWorld) -> None:
    with use_targets({"documents": documents_target()}):  # no `tags`
        with pytest.raises(LoadRefusedError, match="no load target 'tags'"):
            world.open("test-tags", "tags.csv", tag_csv(2))
    assert world.runs() == []


def test_opening_a_run_for_a_company_target_with_a_project_scope_is_refused(
    world: LegacyWorld,
) -> None:
    loader = LoaderDef(
        name="test-cc",
        system="cost",
        table="codes",
        target="registry",
        description="Company cost codes.",
        mapping_text="",
        file_types=("csv",),
    )
    with use_targets({"registry": mapping("registry", scope="company")}):
        with use_loaders({"test-cc": loader}):
            with pytest.raises(LoadRefusedError, match="--company"):
                world.open("test-cc", "codes.csv", b"Code,Name\nC1,One\n")
    assert world.runs() == []


# --- the mapping form ---------------------------------------------------------------------------


def test_a_mapping_target_describes_itself() -> None:
    target = mapping("costcodes")
    assert isinstance(target, MappingTarget) and isinstance(target, Target)
    assert (target.kind, target.module, target.scope) == ("costcodes", "cost", "project")
    assert target.record_type == "cost.CostCode" and target.key_column == "Code"
    assert target.columns == COLUMNS
    assert mapping("c2", scope="company").scope == "company"


@pytest.mark.parametrize("bad", ["", "Upper", "1st", "has-dash", "has space"])
def test_a_mapping_target_needs_a_plain_name(bad: str) -> None:
    with pytest.raises(ValueError, match="must match"):
        mapping(bad)


def test_a_mapping_target_scope_is_project_or_company() -> None:
    with pytest.raises(ValueError, match="project or company"):
        mapping("c", scope="site")


def test_a_mapping_may_only_fill_title_and_description() -> None:
    with pytest.raises(ValueError, match="title, description, not 'status'"):
        mapping("c", columns={"State": "status"})


def test_a_file_without_the_key_column_or_a_mapped_column_is_a_mapping_problem() -> None:
    target = mapping("costcodes")
    with open_uow_none() as conn, pytest.raises(MappingProblemError, match="no column 'Code'"):
        target.plan(conn, PROJECT, None, Grid(["Name", "Notes"], [["a", "b"]]))  # type: ignore[arg-type]
    with open_uow_none() as conn, pytest.raises(MappingProblemError, match="no column 'Notes'"):
        target.plan(conn, PROJECT, None, Grid(["Code", "Name"], [["C1", "a"]]))  # type: ignore[arg-type]


class open_uow_none:  # noqa: N801
    """A connection that must not be used: the column check comes before any read."""

    def __enter__(self) -> Any:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


GRID = Grid(
    ["Code", "Name", "Notes"],
    [
        ["C1", "Concrete", "in situ"],
        ["C2", "Steel", ""],
        ["", "No key", ""],
        ["C1", "Repeated", ""],
    ],
)


def test_a_mapping_target_plans_applies_compares_and_reverses(world: LegacyWorld) -> None:
    target = mapping("costcodes")
    correlation = f"load:{new_ulid()}"
    with open_uow(world.db, readonly=True) as uow:
        plan = target.plan(uow.conn(), PROJECT, None, GRID)  # type: ignore[arg-type]
    assert [(r.line, r.key) for r in plan.rows] == [(2, "C1"), (3, "C2")]
    assert plan.existing == []
    assert plan.invalid == [(4, "no key"), (5, "key repeated")]

    with open_uow(world.db) as uow:
        made = target.apply(
            uow,
            PROJECT,
            None,  # type: ignore[arg-type]
            plan,
            actor=ADMIN,
            source="legacy:test",
            correlation_id=correlation,
            confidentiality=None,
        )
    assert [(m.key, m.line) for m in made] == [("C1", 2), ("C2", 3)]
    stored = {
        r["key"]: r
        for r in world.rows(
            "SELECT key, title, description, type FROM cur_core_record WHERE type = :t",
            t="cost.CostCode",
        )
    }
    assert stored["C1"]["title"] == "Concrete" and stored["C1"]["description"] == "in situ"
    assert stored["C2"]["title"] == "Steel" and not stored["C2"]["description"]

    # create-only: planned again, the keys are held and nothing is new
    with open_uow(world.db, readonly=True) as uow:
        again = target.plan(uow.conn(), PROJECT, None, GRID)  # type: ignore[arg-type]
        comparison = target.compare(uow.conn(), PROJECT, None, GRID, {"C1", "C2"})  # type: ignore[arg-type]
    assert again.rows == [] and again.existing == ["C1", "C2"]
    assert comparison.valid == 2 and comparison.matched == 2 and comparison.missing == []
    assert comparison.invalid == 2

    ids = [m.record_id for m in made]
    with open_uow(world.db, readonly=True) as uow:
        reversals = target.reversals(uow.conn(), PROJECT, ids, correlation)
    assert len(reversals) == 2
    with open_uow(world.db) as uow:
        count = target.reverse(
            uow,
            PROJECT,
            ids,
            actor=ADMIN,
            source="legacy:test",
            correlation_id=correlation,
            reason="mistake",
        )
    assert count == 2
    assert all(
        bool(r["voided"])
        for r in world.rows("SELECT voided FROM cur_core_record WHERE type = :t", t="cost.CostCode")
    )
    with open_uow(world.db) as uow:  # a second reversal changes nothing
        assert (
            target.reverse(
                uow,
                PROJECT,
                ids,
                actor=ADMIN,
                source="legacy:test",
                correlation_id=correlation,
                reason="again",
            )  # fmt: skip
            == 0
        )


def test_a_mapping_without_a_title_column_uses_the_key_as_the_title(world: LegacyWorld) -> None:
    target = mapping("costcodes", columns={"Notes": "description"})
    grid = Grid(["Code", "Notes"], [["K9", "only a note"]])
    with open_uow(world.db, readonly=True) as uow:
        plan = target.plan(uow.conn(), PROJECT, None, grid)  # type: ignore[arg-type]
    with open_uow(world.db) as uow:
        target.apply(
            uow, PROJECT, None, plan,  # type: ignore[arg-type]
            actor=ADMIN, source="legacy:test", correlation_id=f"load:{new_ulid()}",
            confidentiality=None,
        )  # fmt: skip
    row = world.rows("SELECT title, description FROM cur_core_record WHERE key = 'K9'")[0]
    assert row["title"] == "K9" and row["description"] == "only a note"
