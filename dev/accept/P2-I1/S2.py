"""Acceptance for P2-I1-S2: awp schema, CWP workflow, numbering pattern, standards edition.
Exit 0, one ``PASS <check>`` line per check, then ``S2 ok``. SQLite only; no network.

Run: ``uv run python dev/accept/P2-I1/S2.py``.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.workflow.loader import load_workflow
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
GENERATED = ROOT / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"

# Written from the spec (m3-wbs-cwp.md section 2), not read from the generated files.
RECORD_CLASSES = {
    "awp.WBSNode": "none",
    "awp.PathOfConstruction": "none",
    "awp.CWA": "none",
    "awp.CWP": "draft_only",
    "awp.EWPRef": "none",
    "awp.PWPRef": "none",
}
TABLES = {
    "cur_awp_wbs_node",
    "cur_awp_wbs_allocation",
    "cur_awp_path",
    "cur_awp_path_step",
    "cur_awp_cwa",
    "cur_awp_cwp",
    "cur_awp_cwp_allocation",
    "cur_awp_ewp_ref",
    "cur_awp_pwp_ref",
    "cur_awp_rollup",
}
COMMODITIES = [
    "piping",
    "structural-steel",
    "concrete",
    "civil-earthworks",
    "electrical",
    "instrumentation",
    "mechanical-equipment",
    "insulation",
    "painting",
]
STATES = [
    "Planned",
    "In development",
    "Released for IWP development",
    "Executing",
    "Complete",
    "Closed",
    "Void",
]
NO_CARD = {
    "WBSNode.Defined",
    "WBSNode.Revised",
    "WBSNode.Retired",
    "WBSNode.CostCodesMapped",
    "WBSNode.BudgetRolledUp",
    "PathOfConstruction.Defined",
    "PathOfConstruction.Resequenced",
    "CWP.AllocatedToWbs",
}
CARD = {
    "CWA.Defined",
    "CWA.Revised",
    "CWA.Retired",
    "CWP.Defined",
    "CWP.Revised",
    "CWP.Released",
    "EWPRef.Defined",
    "EWPRef.Updated",
    "PWPRef.Defined",
    "PWPRef.Updated",
}


def passed(name: str) -> None:
    print(f"PASS {name}")


def need(condition: bool, what: str) -> None:
    if not condition:
        print(f"FAIL {what}")
        sys.exit(1)


def record_types() -> None:
    for record_type, offline in RECORD_CLASSES.items():
        need(record_type in TYPE_LABELS, f"{record_type} is in TYPE_LABELS")
        need(OFFLINE_CLASSES.get(record_type) == offline, f"{record_type} offline class {offline}")
    passed("six record types in TYPE_LABELS and OFFLINE_CLASSES with the table's classes")


def ddl_tables() -> None:
    conn = sqlite3.connect(":memory:")
    for name in sorted(TABLES):
        path = GENERATED / "ddl" / "sqlite" / f"{name}.sql"
        need(path.is_file(), f"generated DDL {name}.sql exists")
        conn.executescript(path.read_text(encoding="utf-8"))
    found = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    need(TABLES <= found, f"tables created: missing {sorted(TABLES - found)}")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cur_awp_cwp)")}
    need(
        {"discipline", "budget_hours", "quantities_json", "contractor_text"} <= cols, "cwp columns"
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cur_awp_rollup)")}
    need(
        {"subject_id", "line", "cost_code_id", "measure", "value", "as_of_seq", "run_id"} <= cols,
        "rollup columns",
    )
    passed("child and rollup tables exist in the generated SQLite DDL")


def commodity_list(doc: Any) -> None:
    codes = [v.code for v in doc.code_lists["Commodity"].values]
    need(codes == COMMODITIES, f"Commodity values in order: {codes}")
    need(doc.code_lists["Commodity"].value_list_policy == "extensible", "Commodity is extensible")
    need(set(doc.code_lists) == {"Commodity", "PathReason", "ConstraintType"}, "three code lists")
    need(len(doc.code_lists["PathReason"].values) == 7, "PathReason holds seven values")
    need(len(doc.code_lists["ConstraintType"].values) == 8, "ConstraintType holds eight values")
    passed("Commodity holds the nine values in order")


def standards_load_twice(work: Path) -> None:
    db = as_target(str(work / "std.db"))
    create_schema(db)
    std = FIXTURES / "standards"
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        doc = load_standards_file(std / "co.acme.awp@1.0.0.yaml")
        commodity_list(doc)
        reports = []
        for _ in range(2):
            with open_uow(db) as uow:
                reports.append(load_standards(uow, doc, actor="user:seed", source="test"))
    need(
        reports[0].created == 3 + 9 + 7 + 8, f"first load adds 27 entries, got {reports[0].created}"
    )
    need(reports[1].created == 0 and reports[1].skipped == 27, "second load adds no entry")
    passed("loading co.acme.awp@1.0.0 twice: the second load adds no entry")


def workflow() -> None:
    wf = load_workflow(FIXTURES / "workflows" / "awp-cwp.yaml")
    need([s.name for s in wf.states] == STATES, "seven states, Void last")
    need(wf.initial_state == "Planned" and wf.record_type == "awp.CWP", "initial state and type")
    moves = {(f, t.to) for t in wf.transitions for f in t.from_states}
    need(("Closed", "Void") not in moves, "Closed is terminal")
    need(not any(f == "Closed" for f, _ in moves), "nothing leaves Closed")
    need(not any(f == "Void" for f, _ in moves), "nothing leaves Void")
    need(("Released for IWP development", "In development") in moves, "return move")
    need(("Complete", "Executing") in moves, "reopen move")
    need(all((s, "Void") in moves for s in STATES[:5]), "every state but Closed can be voided")
    need(all(not t.guards for t in wf.transitions), "no guard (no roles guard)")
    passed("workflow awp-cwp loads with the seven states and Void")


def numbering(work: Path) -> None:
    pattern = load_numbering(FIXTURES / "numbering" / "patterns.yaml").get("awp.CWP")
    need(pattern is not None, "awp.CWP pattern exists")
    assert pattern is not None
    need(
        pattern.template == "{project}-{type}-{discipline}-{seq:4}" and pattern.gap_free, "template"
    )
    db = as_target(str(work / "num.db"))
    create_schema(db)
    keys = []
    for discipline in ("PIP", "PIP", "CIV"):
        with open_uow(db) as uow:
            values = segment_values(pattern, "project:P123", {"discipline": discipline})
            alloc = allocate_key(
                uow,
                pattern=pattern,
                scope="project:P123",
                values=values,
                record_id=None,
                record_type="awp.CWP",
                actor="user:seed",
                source="test",
            )
            keys.append(alloc.key)
    need(keys == ["P123-CWP-PIP-0001", "P123-CWP-PIP-0002", "P123-CWP-CIV-0001"], f"keys {keys}")
    passed("CWP pattern allocates P123-CWP-PIP-0001, -0002 and P123-CWP-CIV-0001")


def events() -> None:
    doc = yaml.safe_load((SCHEMA / "modules" / "awp" / "events.yaml").read_text(encoding="utf-8"))
    by_type: dict[str, dict[str, Any]] = {}
    for name, cls in doc["classes"].items():
        event_type = (cls.get("annotations") or {}).get("tl:event_type")
        need(event_type is not None, f"{name} has tl:event_type")
        by_type[event_type] = cls
    need(
        set(by_type) == NO_CARD | CARD,
        f"event set differs: {sorted(set(by_type) ^ (NO_CARD | CARD))}",
    )
    index = json.loads((GENERATED / "catalog" / "index.json").read_text(encoding="utf-8"))
    listed = json.dumps(index)
    for event_type, cls in by_type.items():
        policy = (cls.get("attributes") or {}).get("feed_policy")
        if event_type in NO_CARD:
            need(
                policy is not None
                and policy.get("equals_string") == "none"
                and policy.get("required"),
                f"{event_type} carries feed_policy none",
            )
        else:
            need(policy is None, f"{event_type} makes an ordinary card (no feed_policy)")
        need(f'"{event_type}"' in listed, f"{event_type} is in the generated catalog")
    passed("every awp event has a tl:event_type and the feed policy of the list")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        record_types()
        ddl_tables()
        standards_load_twice(work)
        workflow()
        numbering(work)
        events()
    print("S2 ok")


main()
