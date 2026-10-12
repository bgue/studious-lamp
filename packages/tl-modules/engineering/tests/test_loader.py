"""Loading the acme standards document into a real ledger on every adapter (P1-I1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_mod_engineering import registry
from tl_mod_engineering.document import StandardsDoc, load_standards_file, parse_standards
from tl_mod_engineering.errors import InvalidPatternError, StandardsLoadError
from tl_mod_engineering.handlers.standards import RegisterCodeList, handle_register_code_list
from tl_mod_engineering.handlers.tags import CreateTag, handle_create_tag
from tl_mod_engineering.loader import LoadReport, load_standards, plan_load
from tl_mod_engineering.names import COMPANY

pytestmark = pytest.mark.usefixtures("fixture_schemas")

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)
SMALL = """
standards: co.small.standards
version: 1.0.0
description: A small edition.
owner: engineering
code_lists:
  Area:
    label: Area
    definition: Plant areas.
    value_list_policy: extensible
    values:
      - {code: "20", label: Process}
      - {code: "10", label: Utilities}
mnemonics:
  - {code: FV, label: Flow control valve}
numbering_patterns:
  - code: tag
    label: Tag
    definition: Tag numbers.
    record_type: engineering.Tag
    template: "{area}-{mnemonic}-{seq:4}"
    segments:
      area: {role: area, list: Area}
      mnemonic: {role: mnemonic, registry: mnemonic}
      seq: {role: sequence}
tag_classes:
  - code: ControlValve
    label: Control valve
    definition: A valve that modulates flow.
    family: valve
    required_psets: [valve_data]
    mnemonics: [FV]
"""


@pytest.fixture(scope="module")
def acme() -> StandardsDoc:
    return load_standards_file(FIXTURE)


def run(db: DbTarget, doc: StandardsDoc, **more: str) -> LoadReport:
    with open_uow(db) as uow:
        return load_standards(uow, doc, actor="user:admin", source="test", **more)


def plan(db: DbTarget, doc: StandardsDoc) -> LoadReport:
    with open_uow(db, readonly=True) as uow:
        return plan_load(uow.conn(), doc)


def scalar(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_the_acme_edition_loads_into_an_empty_ledger(db: DbTarget, acme: StandardsDoc) -> None:
    report = run(db, acme)
    values = sum(len(c.values) for c in acme.code_lists.values())
    assert report.edition == "co.acme.standards@1.0.0"
    assert report.skipped == 0
    assert report.count("code_list", "create") == len(acme.code_lists)
    assert report.count("code_value", "create") == values
    assert report.count("mnemonic", "create") == len(acme.mnemonics)
    assert report.count("numbering_pattern", "create") == len(acme.numbering_patterns)
    assert report.count("tag_class", "create") == len(acme.tag_classes)
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        lists = registry.find_standards(conn, scope=COMPANY, kind="code_list")
        assert {row.code for row in lists} == set(acme.code_lists)
        assert {row.owner for row in lists} == {acme.owner}
        area = registry.code_values(conn, COMPANY, "Area")
        assert [v.code for v in area] == [v.code for v in acme.code_lists["Area"].values]
        assert [v.sort_order for v in area] == [10 * n for n in range(1, len(area) + 1)]
        assert registry.active_tag_class(conn, COMPANY, "SafetyValve") is not None
        assert registry.active_standard(conn, COMPANY, "numbering_pattern", "tag") is not None


def test_loading_twice_changes_nothing(db: DbTarget, acme: StandardsDoc) -> None:
    run(db, acme)
    events = scalar(db, "SELECT COUNT(*) FROM events")
    again = run(db, acme)
    assert again.created == 0
    assert again.skipped == len(plan(db, acme).items)
    assert {item.reason for item in again.items} == {"already registered", "already defined"}
    assert scalar(db, "SELECT COUNT(*) FROM events") == events


def test_the_plan_writes_nothing_and_predicts_the_load(db: DbTarget, acme: StandardsDoc) -> None:
    before = scalar(db, "SELECT COUNT(*) FROM events")
    expected = plan(db, acme)
    assert scalar(db, "SELECT COUNT(*) FROM events") == before
    assert expected.skipped == 0
    assert run(db, acme) == expected
    assert plan(db, acme).created == 0


def test_a_partly_loaded_ledger_gets_only_the_rest(db: DbTarget) -> None:
    doc = parse_standards(SMALL)
    with open_uow(db) as uow:
        handle_register_code_list(
            uow,
            RegisterCodeList(
                actor="user:admin",
                source="test",
                scope=COMPANY,
                code="Area",
                label="Area",
                edition=doc.edition,
                value_list_policy="extensible",
            ),
        )
    report = run(db, doc)
    skipped = [(i.kind, i.code) for i in report.items if i.action == "skip"]
    assert skipped == [("code_list", "Area")]
    assert report.count("code_value", "create") == 2
    with open_uow(db, readonly=True) as uow:
        assert [v.code for v in registry.code_values(uow.conn(), COMPANY, "Area")] == ["20", "10"]


def test_one_correlation_id_ties_the_whole_load_together(db: DbTarget) -> None:
    run(db, parse_standards(SMALL), correlation_id="load-1")
    assert scalar(db, "SELECT COUNT(*) FROM events WHERE correlation_id <> 'load-1'") == 0
    assert scalar(db, "SELECT COUNT(*) FROM events WHERE correlation_id = 'load-1'") > 10


def test_another_edition_of_a_loaded_standard_is_left_alone(db: DbTarget) -> None:
    run(db, parse_standards(SMALL))
    newer = parse_standards(SMALL.replace("version: 1.0.0", "version: 2.0.0"))
    report = run(db, newer)
    assert report.created == 0
    assert {item.reason for item in report.items if item.kind == "code_list"} == {
        "already registered in co.small.standards@1.0.0"
    }


def test_a_class_that_needs_a_missing_pset_stops_the_load_before_any_write(db: DbTarget) -> None:
    doc = parse_standards(SMALL.replace("[valve_data]", "[no_such_pset]"))
    with pytest.raises(StandardsLoadError) as caught:
        run(db, doc)
    assert caught.value.problems == [
        "tag class ControlValve: pset 'no_such_pset' is not in the company schema"
    ]
    assert scalar(db, "SELECT COUNT(*) FROM events") == 0


def test_a_failure_part_way_leaves_nothing_behind(db: DbTarget) -> None:
    run(db, parse_standards(SMALL))
    events = scalar(db, "SELECT COUNT(*) FROM events")
    other = parse_standards(
        SMALL.replace("co.small.standards", "co.other.standards")
        .replace("  Area:", "  Zone:")
        .replace("code: tag", "code: other")
        .replace("list: Area", "list: Zone")
        .replace("code: FV", "code: HV")
        .replace("mnemonics: [FV]", "mnemonics: [HV]")
        .replace("code: ControlValve", "code: HandValve")
    )
    with pytest.raises(InvalidPatternError, match="already numbered"):
        run(db, other)
    assert scalar(db, "SELECT COUNT(*) FROM events") == events
    with open_uow(db, readonly=True) as uow:
        assert (
            registry.find_standards(uow.conn(), scope=COMPANY, kind="code_list", code="Zone") == []
        )


def test_loaded_standards_number_and_class_a_tag(db: DbTarget, acme: StandardsDoc) -> None:
    run(db, acme)
    with open_uow(db) as uow:
        made = handle_create_tag(
            uow,
            CreateTag(
                actor="user:dev",
                source="test",
                scope="project:P123",
                number="47-FV-1001",
                class_code="ControlValve",
            ),
        )
    assert made.key == "47-FV-1001"
    with open_uow(db, readonly=True) as uow:
        tag = registry.find_tag(uow.conn(), "project:P123", "47-FV-1001")
        assert tag is not None
        assert tag.number_status == "ok"


def test_a_rebuild_of_the_projections_gives_the_same_registry(
    db: DbTarget, acme: StandardsDoc
) -> None:
    run(db, acme)

    def snapshot() -> list[tuple[object, ...]]:
        with open_uow(db, readonly=True) as uow:
            out: list[tuple[object, ...]] = []
            for table in (
                "cur_engineering_standard",
                "cur_engineering_code_value",
                "cur_engineering_tag_class",
            ):
                out += [
                    tuple(r) for r in uow.conn().execute(text(f"SELECT * FROM {table} ORDER BY id"))
                ]
            return out

    before = snapshot()
    rebuild_projections(db)
    assert snapshot() == before
