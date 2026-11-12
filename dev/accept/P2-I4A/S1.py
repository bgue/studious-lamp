"""Acceptance for P2-I4A-S1: the requisitions schema, fixtures and module spec.
Exit 0, one ``PASS <check>`` line per check, final ``S1 ok``.

Expectations are written from the S1 piece spec, not read from the generated files.
SQLite only; every check is dialect-neutral. Run: ``uv run python dev/accept/P2-I4A/S1.py``.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import yaml
from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.auth.access_words import load_access_words, table_word
from tl_core.ledger import NewEvent
from tl_core.modules import load_modules
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.util import new_ulid
from tl_core.workflow.loader import load_workflow
from tl_schema import generate
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS
from tl_schema.registry import load_package

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
MODULE = SCHEMA / "modules" / "requisitions"

KINDS = {
    "requisitions.LaborRequisition": ("labor", "cur_requisitions_labor_requisition", "LAB"),
    "requisitions.MaterialRequisition": (
        "material",
        "cur_requisitions_material_requisition",
        "MAT",
    ),
    "requisitions.GeneralRequisition": ("general", "cur_requisitions_general_requisition", "GEN"),
    "requisitions.ScaffoldRequest": ("scaffold", "cur_requisitions_scaffold_request", "SCF"),
}
WORK_ORDER = "requisitions.WorkOrder"
TABLES = [v[1] for v in KINDS.values()] + ["cur_requisitions_work_order"]
OFFLINE = {t: "draft_only" for t in KINDS} | {WORK_ORDER: "none"}
# Event type -> (feed rule, valid-time slot). Rule: none (silenced), card (a card), None (generic).
EVENTS: dict[str, tuple[str | None, bool]] = {
    "Requisition.Raised": (None, True),
    "Requisition.Revised": ("none", True),
    "Requisition.Approved": ("card", True),
    "Requisition.Rejected": ("card", True),
    "Requisition.Cancelled": (None, True),
    "Requisition.Fulfilled": (None, True),
    "WorkOrder.Opened": ("none", True),
    "WorkOrder.Scheduled": (None, True),
    "WorkOrder.Assigned": ("none", True),
    "WorkOrder.Started": (None, True),
    "WorkOrder.Completed": ("card", True),
    "WorkOrder.Closed": (None, True),
}
WORDS = {
    "requisitions.view": "read",
    "requisitions.raise": "user",
    "requisitions.edit": "user",
    "requisitions.cancel": "user",
    "requisitions.approve": "controller",
    "requisitions.reject": "controller",
    "requisitions.schedule": "controller",
    "requisitions.assign": "controller",
    "requisitions.start": "user",
    "requisitions.complete": "user",
    "requisitions.close": "controller",
    "requisitions.fulfil": "user",
}
REQ_STATES = [
    "Requested",
    "Approved",
    "Scheduled",
    "In progress",
    "Done",
    "Closed",
    "Rejected",
    "Cancelled",
]
REQ_MOVES = {
    ("Requested", "Approved"),
    ("Approved", "Scheduled"),
    ("Scheduled", "In progress"),
    ("In progress", "Done"),
    ("Done", "Closed"),
    ("Requested", "Rejected"),
    ("Requested", "Cancelled"),
    ("Approved", "Cancelled"),
}
WO_STATES = ["Open", "Scheduled", "In progress", "Done", "Closed", "Cancelled"]
WO_MOVES = {
    ("Open", "Scheduled"),
    ("Scheduled", "In progress"),
    ("In progress", "Done"),
    ("Done", "Closed"),
    ("Open", "Cancelled"),
    ("Scheduled", "Cancelled"),
}


def _moves(definition: object) -> set[tuple[str, str]]:
    return {(s, t.to) for t in definition.transitions for s in t.from_states}  # type: ignore[attr-defined]


def check_types() -> None:
    for record_type in OFFLINE:
        assert record_type in TYPE_LABELS, record_type
    assert TYPE_LABELS["requisitions.LaborRequisition"] == "Labour requisition"
    found = {k: v for k, v in OFFLINE_CLASSES.items() if k.startswith("requisitions.")}
    assert found == OFFLINE, found


def check_ddl() -> None:
    ddl = generate.GENERATED_DIR / "ddl"
    for dialect in ("sqlite", "postgres"):
        for table in TABLES:
            assert (ddl / dialect / f"{table}.sql").is_file(), f"{dialect}: {table}"
    assert not list((ddl / "sqlite").glob("cur_requisitions_requisition.sql")), "base has a table"
    connection = sqlite3.connect(":memory:")
    try:
        for table in TABLES:
            connection.executescript((ddl / "sqlite" / f"{table}.sql").read_text(encoding="utf-8"))
        names = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    assert set(TABLES) <= names, set(TABLES) - names


def check_workflows() -> None:
    folder = FIXTURES / "workflows"
    for record_type, (kind, _, _) in KINDS.items():
        d = load_workflow(folder / f"requisitions-requisition-{kind}.yaml")
        assert d.record_type == record_type and d.initial_state == "Requested"
        assert d.state_names() == REQ_STATES
        assert _moves(d) == REQ_MOVES, sorted(_moves(d))
        terminal = {s for s in d.state_names() if not d.transitions_from(s)}
        assert terminal == {"Closed", "Rejected", "Cancelled"}, terminal
        assert ("Approved", "Closed") not in _moves(d)
        assert not [g for t in d.transitions for g in t.guards], "a requisition move is gated"
    wo = load_workflow(folder / "requisitions-work-order.yaml")
    assert wo.record_type == WORK_ORDER and wo.initial_state == "Open"
    assert wo.state_names() == WO_STATES
    assert _moves(wo) == WO_MOVES, sorted(_moves(wo))
    assert ("Open", "Done") not in _moves(wo)
    terminal = {s for s in wo.state_names() if not wo.transitions_from(s)}
    assert terminal == {"Closed", "Cancelled"}, terminal


def check_numbering() -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    expected = {t: f"{{project}}-REQ-{code}-{{seq:4}}" for t, (_, _, code) in KINDS.items()}
    expected[WORK_ORDER] = "{project}-WO-{seq:4}"
    chosen = {}
    for record_type, template in expected.items():
        pattern = patterns.find("project:P123", record_type)
        assert pattern is not None and pattern.gap_free is True, record_type
        assert pattern.template == template, (record_type, pattern.template)
        chosen[record_type] = pattern
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        keys: dict[str, list[str]] = {t: [] for t in expected}
        # interleaved, so independent counters show
        for _ in range(2):
            for record_type, pattern in chosen.items():
                with open_uow(target) as uow:
                    keys[record_type].append(
                        allocate_key(
                            uow,
                            pattern=pattern,
                            scope="project:P123",
                            values=segment_values(pattern, "project:P123"),
                            record_id=None,
                            record_type=record_type,
                            actor="user:seed",
                            source="accept",
                            correlation_id=new_ulid(),
                        ).key
                    )
    for record_type, template in expected.items():
        want = [
            template.replace("{project}", "P123").replace("{seq:4}", n) for n in ("0001", "0002")
        ]
        assert keys[record_type] == want, (record_type, keys[record_type])


def check_constraint_opt_in() -> None:
    folder = FIXTURES / "workflows"
    gated = []
    for path in sorted(folder.glob("requisitions-*.yaml")):
        d = load_workflow(path)
        for t in d.transitions:
            for g in t.guards:
                gated.append((d.record_type, t.name, g.kind, getattr(g, "phase", None)))
    assert gated == [(WORK_ORDER, "start", "no_open_blocking_constraints", "start")], gated


def check_crane_lift() -> None:
    package = load_package(FIXTURES / "co.acme.engineering@3.2.0.yaml")
    pset = package.psets["crane_lift"]
    assert "requisitions.GeneralRequisition" in pset.applies_to, pset.applies_to
    assert set(pset.properties) == {"load_t", "radius_m", "boom_m", "lift_date", "plan_reference"}
    standards = yaml.safe_load(
        (FIXTURES / "standards" / "co.acme.awp@1.0.0.yaml").read_text("utf-8")
    )
    values = [v["code"] for v in standards["code_lists"]["GeneralRequisitionType"]["values"]]
    assert values == ["crane_lift", "hot_work_support", "other"], values


def check_events() -> None:
    by_type: dict[str, dict[str, object]] = {}
    for name in ("events.yaml",):
        document = yaml.safe_load((MODULE / name).read_text(encoding="utf-8"))
        for definition in document["classes"].values():
            annotations = definition.get("annotations") or {}
            assert "tl:event_type" in annotations, definition
            by_type[annotations["tl:event_type"]] = definition
    assert set(by_type) == set(EVENTS), sorted(set(by_type) ^ set(EVENTS))
    for event_type, (rule, _) in EVENTS.items():
        attributes = by_type[event_type]["attributes"]  # type: ignore[index]
        policy = attributes.get("feed_policy")  # type: ignore[union-attr]
        if rule == "none":
            assert policy and policy["equals_string"] == "none", event_type
        elif rule == "card":
            assert policy and policy["equals_string"] == "full", event_type
        else:
            assert policy is None, event_type
        at = attributes["at"]  # type: ignore[index]
        assert at["annotations"]["tl:valid_time"] == "at", event_type
    for event_type in ("WorkOrder.Started", "WorkOrder.Completed"):
        assert by_type[event_type]["attributes"]["at"]["required"] is True  # type: ignore[index]
    for event_type in (e for e in EVENTS if e.startswith("WorkOrder.")):
        assert by_type[event_type]["attributes"]["requisition_id"]["required"] is True  # type: ignore[index]
    index = (generate.GENERATED_DIR / "catalog" / "index.json").read_text(encoding="utf-8")
    for event_type in EVENTS:
        assert f'"event_type": "{event_type}"' in index, event_type


def check_words() -> None:
    words = load_access_words()
    for word, expected in WORDS.items():
        assert word in words, word
        assert words[word] == expected and table_word(word) == expected, word
    assert sorted(w for w in words if w.startswith("requisitions.")) == sorted(WORDS)


def check_module_spec() -> None:
    specs = {s.name: s for s in load_modules()}
    spec = specs["requisitions"]
    assert spec.record_types == frozenset(OFFLINE), spec.record_types
    names = [p.name for p in spec.projectors()]
    assert names == ["requisitions_requisition", "requisitions_work_order"], names
    assert not spec.command_words


def _raised(kind: str) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": kind,
        "subject": f"A {kind} request",
        "requester": "user:ana",
        "priority": "high",
        "need_by": "2026-11-20",
        "location_text": "Unit 4",
        "for_record_id": new_ulid(),
        "at": "2026-11-02T08:00:00Z",
    }
    extra: dict[str, dict[str, object]] = {
        "labor": {
            "craft": "Pipefitter",
            "classification": "Journeyman",
            "headcount": 6,
            "start_date": "2026-11-02",
            "end_date": "2026-11-13",
            "shift": "Day",
            "requirements": "Own tools",
        },
        "material": {
            "from_location_id": new_ulid(),
            "lines": [{"item_id": new_ulid(), "qty": "4", "uom": "EA", "fulfilled_qty": "0"}],
        },
        "general": {"general_type": "crane_lift"},
        "scaffold": {
            "purpose": "Access to tie-in",
            "elevation": "+4.5",
            "gridline": "C-4",
            "length_m": "6.0",
            "width_m": "1.2",
            "height_m": "5.5",
            "load_class": "light",
            "duration_days": 14,
        },
    }
    return base | extra[kind]


def check_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        ids: dict[str, str] = {}
        for record_type, (kind, table, _) in KINDS.items():
            payload = _raised(kind)
            stream = new_ulid()
            ids[record_type] = stream
            with open_uow(target) as uow:
                uow.append(
                    stream_id=stream,
                    stream_type=record_type,
                    scope="project:P123",
                    expected_version=0,
                    events=[
                        NewEvent(
                            event_type="Record.Created",
                            payload={
                                "record_type": record_type,
                                "key": f"P123-REQ-{kind[:3].upper()}-0001",
                                "title": str(payload["subject"]),
                                "description": None,
                                "psets": {},
                            },
                        ),
                        NewEvent(event_type="Requisition.Raised", payload=payload),
                    ],
                    actor="user:ana",
                    source="accept",
                    correlation_id=new_ulid(),
                )
            with open_uow(target, readonly=True) as uow:
                row = (
                    uow.conn()
                    .execute(text(f"SELECT * FROM {table} WHERE id = :i"), {"i": stream})
                    .mappings()
                    .one()
                )
            assert row["kind"] == kind and row["subject"] == payload["subject"], kind
            assert row["priority"] == "high" and row["for_record_id"] == payload["for_record_id"]
            assert row["approved_by"] is None and row["work_order_id"] is None
        with open_uow(target, readonly=True) as uow:
            labor = (
                uow.conn()
                .execute(text("SELECT headcount, craft FROM cur_requisitions_labor_requisition"))
                .one()
            )
            assert tuple(labor) == (6, "Pipefitter"), tuple(labor)
            lines = (
                uow.conn()
                .execute(text("SELECT lines_json FROM cur_requisitions_material_requisition"))
                .scalar_one()
            )
            assert '"qty":"4"' in str(lines), lines
            days = (
                uow.conn()
                .execute(text("SELECT duration_days FROM cur_requisitions_scaffold_request"))
                .scalar_one()
            )
            assert int(days) == 14
            general = (
                uow.conn()
                .execute(text("SELECT general_type FROM cur_requisitions_general_requisition"))
                .scalar_one()
            )
            assert general == "crane_lift"
        # approval and the work order
        labor_id = ids["requisitions.LaborRequisition"]
        wo_id = new_ulid()
        with open_uow(target) as uow:
            uow.append(
                stream_id=wo_id,
                stream_type=WORK_ORDER,
                scope="project:P123",
                expected_version=0,
                events=[
                    NewEvent(
                        event_type="Record.Created",
                        payload={
                            "record_type": WORK_ORDER,
                            "key": "P123-WO-0001",
                            "title": "WO",
                            "description": None,
                            "psets": {},
                        },
                    ),
                    NewEvent(
                        event_type="WorkOrder.Opened",
                        payload={
                            "requisition_id": labor_id,
                            "work_kind": "labour",
                            "at": "2026-11-02T09:00:00Z",
                        },
                    ),
                ],
                actor="user:sam",
                source="accept",
                correlation_id=new_ulid(),
            )
            uow.append(
                stream_id=labor_id,
                stream_type="requisitions.LaborRequisition",
                scope="project:P123",
                expected_version=2,
                events=[
                    NewEvent(
                        event_type="Requisition.Approved",
                        payload={
                            "approved_by": "user:sam",
                            "work_order_id": wo_id,
                            "at": "2026-11-02T09:00:00Z",
                        },
                    )
                ],
                actor="user:sam",
                source="accept",
                correlation_id=new_ulid(),
            )
            uow.append(
                stream_id=wo_id,
                stream_type=WORK_ORDER,
                scope="project:P123",
                expected_version=2,
                events=[
                    NewEvent(
                        event_type="WorkOrder.Started",
                        payload={"requisition_id": labor_id, "at": "2026-11-03T07:00:00Z"},
                    ),
                    NewEvent(
                        event_type="WorkOrder.Completed",
                        payload={
                            "requisition_id": labor_id,
                            "at": "2026-11-13T15:00:00Z",
                            "hours_actual": "96.0",
                        },
                    ),
                ],
                actor="user:ana",
                source="accept",
                correlation_id=new_ulid(),
            )
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            approved = conn.execute(
                text(
                    "SELECT approved_by, approved_at, work_order_id "
                    "FROM cur_requisitions_labor_requisition WHERE id = :i"
                ),
                {"i": labor_id},
            ).one()
            assert tuple(approved) == ("user:sam", "2026-11-02T09:00:00Z", wo_id), tuple(approved)
            order = conn.execute(
                text(
                    "SELECT requisition_id, work_kind, actual_start, actual_finish, hours_actual "
                    "FROM cur_requisitions_work_order"
                )
            ).one()
            assert tuple(order) == (labor_id, "labour", "2026-11-03", "2026-11-13", "96.0"), tuple(
                order
            )
            version = conn.execute(
                text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": labor_id}
            ).scalar_one()
            assert int(version) == 3, version


CHECKS: list[tuple[str, Callable[[], None]]] = [
    (
        "five types in TYPE_LABELS and OFFLINE_CLASSES (four draft_only, work order none)",
        check_types,
    ),
    ("five tables in the generated DDL of both dialects, none for the base", check_ddl),
    (
        "both workflows load; terminal states; Approved -> Closed and Open -> Done refused",
        check_workflows,
    ),
    ("five gap-free patterns allocate -0001, -0002, one counter per kind", check_numbering),
    ("one constraint opt-in guard: work order start, phase start", check_constraint_opt_in),
    ("crane_lift pset binds to GeneralRequisition; GeneralRequisitionType list", check_crane_lift),
    ("twelve events with tl:event_type, feed policy and valid-time tag", check_events),
    ("twelve access words resolve to their table words", check_words),
    ("module spec loads through tl_core.modules", check_module_spec),
    (
        "a requisition of each kind and a work order round-trip through the projectors",
        check_round_trip,
    ),
]


def main() -> int:
    for name, check in CHECKS:
        try:
            check()
        except AssertionError as error:
            print(f"FAIL {name}: {error}")
            return 1
        print(f"PASS {name}")
    print("S1 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
