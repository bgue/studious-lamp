"""Acceptance for P2-I2-C1: core constraint schema (ADR-0024). SQLite only; no network.

Exit 0, one ``PASS <check>`` line per check, then ``C1 ok``.
Run: ``uv run python dev/accept/P2-I2/C1.py``.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.auth.access_words import load_access_words
from tl_core.links.vocabulary import default_vocabulary
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.workflow.definition import NoOpenBlockingConstraintsGuard
from tl_core.workflow.loader import WorkflowError, load_workflow, parse_workflow
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
GENERATED = ROOT / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"

# Written from the spec (docs/tickets/P2-I2/C1-core-constraint-schema.md), not from generated files.
COLUMNS = {
    "subject_id", "phase", "severity", "category", "owner", "description_text", "source",
    "check_name", "suppress_hash", "clear_reason", "target_kind", "target_id", "target_ref_type",
    "target_ref_text", "effective_at", "due_at", "cleared_at", "cleared_by",
}  # fmt: skip
EVENTS = {"Constraint.Raised", "Constraint.Assigned", "Constraint.Cleared", "Constraint.Withdrawn"}
CWP_GUARDED = {"start_execution", "complete"}
IWP_GUARDED = {"ready": "ready", "start": None, "complete": None}


def need(condition: bool, what: str) -> None:
    if not condition:
        print(f"FAIL {what}")
        sys.exit(1)


def passed(name: str) -> None:
    print(f"PASS {name}")


def labels() -> None:
    need("core.Constraint" in TYPE_LABELS, "core.Constraint is in TYPE_LABELS")
    need(OFFLINE_CLASSES.get("core.Constraint") == "draft_only", "core.Constraint is draft_only")
    need("awp.Constraint" not in TYPE_LABELS, "awp.Constraint is not in TYPE_LABELS")
    need("awp.Constraint" not in OFFLINE_CLASSES, "awp.Constraint is not in OFFLINE_CLASSES")
    passed("core.Constraint in TYPE_LABELS and OFFLINE_CLASSES (draft_only); no awp.Constraint")


def table() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript((GENERATED / "ddl/sqlite/cur_core_constraint.sql").read_text("utf-8"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cur_core_constraint)")}
    need(COLUMNS <= cols, f"missing columns {sorted(COLUMNS - cols)}")
    need("facts_hash" not in cols, "no facts_hash column")
    need(not (GENERATED / "ddl/sqlite/cur_awp_constraint.sql").exists(), "awp table is gone")
    passed("cur_core_constraint has the spec's columns and no facts_hash")


def events() -> None:
    doc = yaml.safe_load((SCHEMA / "core" / "constraint.yaml").read_text("utf-8"))
    found = [(c.get("annotations") or {}).get("tl:event_type") for c in doc["classes"].values()]
    found = [f for f in found if f]
    need(set(found) == EVENTS and len(found) == 4, f"event types {found}")
    listed = (GENERATED / "catalog" / "index.json").read_text("utf-8")
    need(all(f'"{e}"' in listed for e in EVENTS), "events are in the generated catalog")
    for p in (SCHEMA / "modules" / "awp").glob("*.yaml"):
        need("Constraint." not in p.read_text("utf-8"), f"no constraint event left in {p.name}")
    passed("the four events load with tl:event_type, are in the catalog, and left awp")


def workflow() -> None:
    wf = load_workflow(FIXTURES / "workflows" / "core-constraint.yaml")
    need(wf.record_type == "core.Constraint" and wf.initial_state == "Open", "record type, start")
    moves = {(f, t.to) for t in wf.transitions for f in t.from_states}
    need(not any(f in ("Cleared", "Withdrawn") for f, _ in moves), "Cleared, Withdrawn terminal")
    need({("Open", "Assigned"), ("Assigned", "Cleared"), ("Open", "Cleared")} <= moves, "clears")
    need({("Open", "Withdrawn"), ("Assigned", "Withdrawn")} <= moves, "withdraws")
    need(all(not t.guards for t in wf.transitions), "no guards")
    need(not (FIXTURES / "workflows" / "awp-constraint.yaml").exists(), "awp workflow is gone")
    passed("core-constraint workflow loads; Cleared and Withdrawn are terminal")


def numbering(work: Path) -> None:
    pattern = load_numbering(FIXTURES / "numbering" / "patterns.yaml").get("core.Constraint")
    need(pattern is not None and pattern.gap_free, "core.Constraint pattern, gap-free")
    need(load_numbering(FIXTURES / "numbering" / "patterns.yaml").get("awp.Constraint") is None,
         "no awp.Constraint pattern")  # fmt: skip
    assert pattern is not None
    db = as_target(str(work / "n.db"))
    create_schema(db)
    keys = []
    for _ in range(2):
        with open_uow(db) as uow:
            alloc = allocate_key(
                uow,
                pattern=pattern,
                scope="project:P123",
                values=segment_values(pattern, "project:P123", {}),
                record_id=None,
                record_type="core.Constraint",
                actor="user:seed",
                source="test",
            )
            keys.append(alloc.key)
    need(keys == ["P123-CON-0001", "P123-CON-0002"], f"keys {keys}")
    passed("numbering allocates P123-CON-0001 and -0002")


def relation() -> None:
    vocab = default_vocabulary()
    need("targets" in vocab, "targets in the vocabulary")
    rel, inverse = vocab.resolve("targets")
    need(
        rel.inverse_code == "targeted_by"
        and not inverse
        and vocab.label("targets", "out") == "targets",
        "targets label",
    )
    inv, inverse = vocab.resolve("targeted_by")
    need(inverse and inv.code == "targets", "targeted_by resolves to targets")
    need(vocab.label("targets", "in") == "targeted by", "targeted by label")
    passed("targets and targeted_by resolve in the vocabulary")


def words() -> None:
    table = load_access_words()
    need(table.get("core.constraint.edit") == "user", "core.constraint.edit is user")
    need(table.get("core.constraint.view") == "read", "core.constraint.view is read")
    need("awp.constraint.edit" not in table, "awp.constraint.edit is gone")
    passed("core.constraint.edit (user) and .view (read) exist; awp.constraint.edit does not")


def guards() -> None:
    def kinds(name: str) -> dict[str, str | None]:
        wf = load_workflow(FIXTURES / "workflows" / name)
        out: dict[str, str | None] = {}
        for t in wf.transitions:
            for g in t.guards:
                need(isinstance(g, NoOpenBlockingConstraintsGuard), f"{name}/{t.name}: guard kind")
                out[t.name] = g.phase  # type: ignore[union-attr]
        return out

    need(kinds("awp-cwp.yaml") == dict.fromkeys(CWP_GUARDED), "CWP guards on two transitions")
    need(kinds("awp-iwp.yaml") == IWP_GUARDED, "IWP guards; phase ready on ready only")
    for name in ("core-constraint.yaml", "awp-scope-item.yaml"):
        need(kinds(name) == {}, f"{name} has no guard")
    passed("the guard loads on CWP start_execution, complete and IWP ready, start, complete only")


def bad_phase() -> None:
    text = (FIXTURES / "workflows" / "awp-iwp.yaml").read_text("utf-8")
    bad = text.replace("phase: ready", "phase: Ready-Now", 1)
    need(bad != text, "the YAML has a phase to break")
    try:
        parse_workflow(bad, source="bad.yaml")
    except WorkflowError as exc:
        need("phase" in str(exc), f"the refusal names the phase: {exc}")
    else:
        need(False, "a bad phase is refused")
    passed("a workflow with a bad phase is refused by the loader")


if __name__ == "__main__":
    labels()
    table()
    events()
    workflow()
    with tempfile.TemporaryDirectory() as tmp:
        numbering(Path(tmp))
    relation()
    words()
    guards()
    bad_phase()
    print("C1 ok")
