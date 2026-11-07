"""Acceptance for P2-I2-S1: awp schema part 2 (IWP, scope item, constraint, closeout, readiness, events).
Exit 0, one ``PASS <check>`` line per check, then ``S1 ok``. SQLite only; no network.

Run: ``uv run python dev/accept/P2-I2/S1.py``.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflow
from tl_mod_awp.facts import MAX_SCOPE_IDS, SCOPE_TOO_LARGE, iwp_facts
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_schema.generated.type_labels import TYPE_LABELS

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
GENERATED = ROOT / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"

# Written from the spec (docs/tickets/P2-I2/S1-schema-part2.md), not read from the generated files.
RECORD_CLASSES = {
    "awp.IWP": "draft_only",
    "awp.ScopeItem": "draft_only",
    "awp.Constraint": "draft_only",
    "awp.IWPCloseout": "none",
}
TABLES = {
    "cur_awp_iwp",
    "cur_awp_scope_item",
    "cur_awp_constraint",
    "cur_awp_iwp_closeout",
    "cur_awp_readiness",
    "cur_awp_readiness_check",
}
NO_CARD = {
    "IWP.ReadinessEvaluated",
    "ScopeItem.Created",
    "ScopeItem.Revised",
    "IWP.ScopeAdded",
    "IWP.ScopeRemoved",
}
CARD = {
    "IWP.Created",
    "IWP.Revised",
    "IWP.DocumentPinned",
    "IWP.Split",
    "IWP.SignedOff",
    "IWP.Issued",
    "IWP.Held",
    "IWP.HoldReleased",
    "Constraint.Raised",
    "Constraint.Assigned",
    "Constraint.Cleared",
    "IWP.Ready",
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
    passed("four record types in TYPE_LABELS and OFFLINE_CLASSES with the table's classes")


def ddl_tables() -> None:
    conn = sqlite3.connect(":memory:")
    for name in sorted(TABLES):
        path = GENERATED / "ddl" / "sqlite" / f"{name}.sql"
        need(path.is_file(), f"generated DDL {name}.sql exists")
        conn.executescript(path.read_text(encoding="utf-8"))
    found = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    need(TABLES <= found, f"tables created: missing {sorted(TABLES - found)}")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cur_awp_readiness_check)")}
    need({"iwp_id", "name", "state", "count_ok", "resolve_via_json"} <= cols, "check columns")
    passed("the six tables exist in the generated SQLite DDL")


def workflows() -> None:
    iwp = load_workflow(FIXTURES / "workflows" / "awp-iwp.yaml")
    moves = {(f, t.to) for t in iwp.transitions for f in t.from_states}
    for final in ("Closed", "Split", "Cancelled"):
        need(not any(f == final for f, _ in moves), f"nothing leaves {final}")
    need(("On hold", "Ready") not in moves, "On hold -> Ready is refused")
    need(("On hold", "Constraint check") in moves, "On hold -> Constraint check")
    need(("Ready", "Constraint check") in moves, "Ready -> Constraint check")
    need(all(not t.guards for t in iwp.transitions), "the IWP workflow has no guard")
    item = load_workflow(FIXTURES / "workflows" / "awp-scope-item.yaml")
    moves = {(f, t.to) for t in item.transitions for f in t.from_states}
    need(not any(f in ("Verified", "Void") for f, _ in moves), "Verified and Void are final")
    need(("Installed", "Planned") in moves and ("Verified", "Void") not in moves, "scope moves")
    con = load_workflow(FIXTURES / "workflows" / "awp-constraint.yaml")
    moves = {(f, t.to) for t in con.transitions for f in t.from_states}
    need(not any(f in ("Cleared", "Void") for f, _ in moves), "Cleared and Void are final")
    need(("Open", "Cleared") in moves and ("Cleared", "Void") not in moves, "constraint moves")
    passed("the three workflows load; terminal states as stated; On hold -> Ready is refused")


def allocate(work: Path, pattern_id: str, record_type: str, supplied: list[dict[str, str]]) -> Any:
    pattern = load_numbering(FIXTURES / "numbering" / "patterns.yaml").get(pattern_id)
    need(pattern is not None, f"{pattern_id} pattern exists")
    assert pattern is not None
    db = as_target(str(work / f"{pattern_id}.db"))
    create_schema(db)
    keys = []
    for given in supplied:
        with open_uow(db) as uow:
            values = segment_values(pattern, "project:P123", given)
            alloc = allocate_key(
                uow,
                pattern=pattern,
                scope="project:P123",
                values=values,
                record_id=None,
                record_type=record_type,
                actor="user:seed",
                source="test",
            )
            keys.append(alloc.key)
    return pattern, keys


def numbering(work: Path) -> None:
    pattern, keys = allocate(
        work, "awp.IWP", "awp.IWP", [{"discipline": d} for d in ("PIP", "PIP", "CIV")]
    )
    need(pattern.gap_free, "IWP pattern is gap-free")
    need(keys == ["P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"], f"keys {keys}")
    passed("IWP pattern allocates P123-IWP-PIP-0001, -0002 and P123-IWP-CIV-0001")
    pattern, keys = allocate(work, "awp.ScopeItem", "awp.ScopeItem", [{}, {}])
    need(not pattern.gap_free, "scope item pattern is not gap-free")
    need(keys == ["P123-SCI-000001", "P123-SCI-000002"], f"keys {keys}")
    passed("scope item pattern allocates P123-SCI-000001 and -000002")


def events() -> None:
    doc = yaml.safe_load((SCHEMA / "modules" / "awp" / "iwp_events.yaml").read_text("utf-8"))
    by_type: dict[str, dict[str, Any]] = {}
    for name, cls in doc["classes"].items():
        event_type = (cls.get("annotations") or {}).get("tl:event_type")
        need(event_type is not None, f"{name} has tl:event_type")
        by_type[event_type] = cls
    need(set(by_type) == NO_CARD | CARD, f"event set: {sorted(set(by_type) ^ (NO_CARD | CARD))}")
    listed = (GENERATED / "catalog" / "index.json").read_text(encoding="utf-8")
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
    passed("every IWP event has a tl:event_type and the feed policy of the list")


def expected_link() -> None:
    doc = yaml.safe_load((SCHEMA / "modules" / "awp" / "iwp.yaml").read_text("utf-8"))
    expects = doc["classes"]["IWP"]["annotations"]["tl:expects_link"]
    need(len(expects) == 1, "one expected link")
    e = expects[0]
    need(
        (e["relation"], e["direction"], e["by_state"], e["target_type"])
        == ("requires", "out", "Issued", "permit.PermitToWork"),
        f"expected link {e}",
    )
    text = (FIXTURES / "workflows" / "awp-iwp.yaml").read_text("utf-8")
    need("expected_links" not in yaml.safe_load(text).get("transitions", []).__str__(), "no guard")
    passed("the IWP class expects the permit to work by Issued; the workflow has no guard")


def facts(work: Path) -> None:
    db = as_target(str(work / "facts.db"))
    create_schema(db)
    iwp = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1"
    with open_uow(db) as uow:
        conn = uow.conn()
        # No projector writes these tables yet (S2, S5), so the generated DDL creates the IWP table.
        ddl = (GENERATED / "ddl" / "sqlite" / "cur_awp_iwp.sql").read_text(encoding="utf-8")
        for statement in ddl.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            "INSERT INTO cur_core_record (id, key, type, scope, title, version, last_seq, "
            "created_at, updated_at) VALUES (?, 'P123-IWP-PIP-0001', 'awp.IWP', 'project:P123', "
            "'t', 1, 1, 'x', 'x')",
            (iwp,),
        )
        conn.exec_driver_sql(
            "INSERT INTO cur_awp_iwp (id, scope, discipline, planned_start, foreman, "
            "estimated_hours, last_seq) VALUES (?, 'project:P123', 'PIP', '2026-11-02', "
            "'user:ana', '12.5', 1)",
            (iwp,),
        )

        def contain(n: int) -> None:
            for i in range(n):
                rid = f"R{i:025d}"
                kind = "awp.ScopeItem" if i % 3 else "engineering.Tag"
                conn.exec_driver_sql(
                    "INSERT INTO cur_core_record (id, key, type, scope, title, version, last_seq, "
                    "created_at, updated_at) VALUES (?, ?, ?, 'project:P123', 't', 1, 1, 'x', 'x')",
                    (rid, f"K{i}", kind),
                )
                conn.exec_driver_sql(
                    "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, source, "
                    "created_by, created_at, updated_at, version, last_seq) VALUES (?, "
                    "'project:P123', ?, ?, 'contains', 'manual', 'user:x', 'x', 'x', 1, 1)",
                    (f"L{i:025d}", iwp, rid),
                )

        contain(3)
        got = iwp_facts(conn, iwp)
        need(got.status == "Draft" and got.key == "P123-IWP-PIP-0001", "status and key")
        need(got.estimated_hours == 12.5 and got.foreman == "user:ana", "typed fields")
        need(sum(len(v) for v in got.scope_ids.values()) == 3, f"three ids: {got.scope_ids}")
        need(set(got.scope_ids) == {"awp.ScopeItem", "engineering.Tag"}, "by record type")
        passed("iwp_facts returns three contains links by record type, status Draft")
        conn.exec_driver_sql("DELETE FROM cur_links")
        conn.exec_driver_sql("DELETE FROM cur_core_record WHERE id != ?", (iwp,))
        contain(MAX_SCOPE_IDS)
        need(sum(len(v) for v in iwp_facts(conn, iwp).scope_ids.values()) == MAX_SCOPE_IDS, "cap")
        conn.exec_driver_sql("DELETE FROM cur_links")
        conn.exec_driver_sql("DELETE FROM cur_core_record WHERE id != ?", (iwp,))
        contain(MAX_SCOPE_IDS + 1)
        try:
            iwp_facts(conn, iwp)
        except ValueError as exc:
            need(str(exc) == SCOPE_TOO_LARGE, f"fixed text, got {exc}")
        else:
            need(False, "5001 ids raise ValueError")
    passed("iwp_facts with 5 001 contains links raises the fixed ValueError")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        record_types()
        ddl_tables()
        workflows()
        numbering(work)
        events()
        expected_link()
        facts(work)
    print("S1 ok")


main()
