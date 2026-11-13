"""Acceptance for P2-I5-S1: rules of credit as package content, weekly plan, progress, closeout
fields, words, settings. Exit 0, one ``PASS <check>`` line per check, then ``S1 ok``. SQLite only;
no network.

Run: ``uv run python dev/accept/P2-I5/S1.py``.
"""

from __future__ import annotations

import sqlite3
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, text
from tl_core.auth.access_words import load_access_words, table_word
from tl_core.files.slots import parse_file_slots
from tl_core.ledger import Event
from tl_core.settings.registry import get_definition
from tl_core.settings.values import InvalidSettingValueError, normalise
from tl_core.workflow.loader import load_workflow
from tl_mod_awp.projectors.iwp import IwpProjector
from tl_mod_awp.projectors.progress import ProgressProjector
from tl_mod_awp.projectors.week import WeekProjector
from tl_mod_schemareg.analysis import lint_errors, parse_content
from tl_mod_schemareg.errors import InvalidSchemaPackageError
from tl_schema.registry import load_package, parse_package

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
AWP = SCHEMA / "modules" / "awp"
GENERATED = ROOT / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"
PACKAGE = FIXTURES / "packages" / "co.acme.awp@1.1.0.yaml"

# Written from the spec (docs/tickets/P2-I5/S1-schema-and-package.md), not from generated files.
TABLES = ("cur_awp_weekly_plan", "cur_awp_week_commitment", "cur_awp_iwp_progress")
NO_CARD = {
    "WeeklyPlan.Opened",
    "WeeklyPlan.IwpCommitted",
    "WeeklyPlan.OutcomeRecorded",
    "IWP.Started",
    "IWP.ProgressRecorded",
    "IWP.FieldCompleted",
    "Cwp.PartyAssigned",
    "Cwp.SubcontractProgressRecorded",
}
CARD = {"WeeklyPlan.Closed", "IWPCloseout.Recorded"}
AT_EVENTS = {"IWP.Started", "IWP.FieldCompleted", "IWP.ProgressRecorded"}
WORDS = {
    "awp.week.plan": "user",
    "awp.week.commit": "user",
    "awp.week.close": "controller",
    "awp.progress.record": "user",
    "awp.closeout.record": "user",
    "awp.closeout.close": "controller",
    "awp.subcontract.assign": "controller",
    "awp.subcontract.progress": "user",
    "awp.worker.run": "controller",
    "core.constraint.waive": "controller",
}
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
IWP = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1"
PLAN = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P0"


def passed(name: str) -> None:
    print(f"PASS {name}")


def need(condition: bool, what: str) -> None:
    if not condition:
        print(f"FAIL {what}")
        sys.exit(1)


def ddl_tables() -> None:
    conn = sqlite3.connect(":memory:")
    for name in (*TABLES, "cur_awp_iwp_closeout", "cur_awp_cwp"):
        conn.executescript((GENERATED / "ddl" / "sqlite" / f"{name}.sql").read_text("utf-8"))
        need(conn.execute(f"SELECT count(*) FROM {name}").fetchone() == (0,), f"{name} exists")
    closeout = {r[1] for r in conn.execute("PRAGMA table_info(cur_awp_iwp_closeout)")}
    need({"redlines_file_id", "closed_by", "closed_at"} <= closeout, "closeout fields")
    need("assigned_party" in {r[1] for r in conn.execute("PRAGMA table_info(cur_awp_cwp)")}, "cwp")
    passed("every table exists in the generated DDL; the closeout and CWP fields are columns")


def workflow() -> None:
    plan = load_workflow(FIXTURES / "workflows" / "awp-weekly-plan.yaml")
    moves = {(f, t.to) for t in plan.transitions for f in t.from_states}
    need(plan.record_type == "awp.WeeklyPlan" and plan.initial_state == "Draft", "plan workflow")
    need(not any(f == "Closed" for f, _ in moves), "Closed is final")
    need(("Draft", "Committed") in moves and ("Committed", "Closed") in moves, "plan moves")
    need(("Draft", "Closed") not in moves, "Draft -> Closed is refused")
    passed("the weekly plan workflow loads; Closed is final; Draft -> Closed is refused")


def package() -> None:
    doc = load_package(PACKAGE)
    need(doc.key() == "co.acme.awp@1.1.0" and lint_errors(doc) == [], "package passes the lint")
    piping = next(r for r in doc.rules_of_credit if r.commodity == "piping")
    need(sum(s.weight for s in piping.steps) == 100, "piping sums to 100")
    passed("co.acme.awp@1.1.0 passes the package lint and its piping entry sums to 100")
    raw: dict[str, Any] = yaml.safe_load(PACKAGE.read_text("utf-8"))
    for step, weight in zip(raw["rules_of_credit"][0]["steps"], (30, 60, 20), strict=True):
        step["weight"] = weight
    bad = parse_package(yaml.safe_dump(raw), source="bad")
    messages = [i.message for i in lint_errors(bad)]
    need(
        messages == ["rules_of_credit: weights of piping do not sum to 100"],
        "weights 30/60/20 are refused with the fixed message",
    )
    passed("weights 30/60/20 are refused with the fixed message")
    big = PACKAGE.read_text("utf-8") + "# " + "x" * (300 * 1024) + "\n"
    try:
        parse_content(big)
        need(False, "a 300 KiB file is refused")
    except InvalidSchemaPackageError:
        pass
    try:
        parse_content(PACKAGE.read_text("utf-8") + "\x00")
        need(False, "a NUL byte is refused")
    except InvalidSchemaPackageError:
        pass
    passed("a 300 KiB file and a NUL byte are refused")


def settings() -> None:
    rules = get_definition("awp.rules_of_credit.set")
    need(normalise(rules, "co.acme.awp@1.1.0") == "co.acme.awp@1.1.0", "package@version")
    need(normalise(rules, "") == "", "empty is allowed")
    try:
        normalise(rules, "co acme")
        need(False, "'co acme' is refused")
    except InvalidSettingValueError:
        pass
    passed("the setting accepts co.acme.awp@1.1.0 and refuses 'co acme'")
    need(get_definition("awp.pack.pdf").default is False, "awp.pack.pdf defaults off")
    passed("awp.pack.pdf defaults off")
    landing = get_definition("tui.landing")
    need(landing.default == "default", "tui.landing default")
    need(normalise(landing, "iwp_mine") == "iwp_mine", "iwp_mine accepted")
    try:
        normalise(landing, "x")
        need(False, "'x' is refused")
    except InvalidSettingValueError:
        pass
    passed("tui.landing accepts iwp_mine and refuses x")


def events() -> None:
    found: dict[str, dict[str, Any]] = {}
    for name in ("iwp_events.yaml", "week_events.yaml"):
        for cls in yaml.safe_load((AWP / name).read_text("utf-8"))["classes"].values():
            event_type = (cls.get("annotations") or {}).get("tl:event_type")
            if event_type in NO_CARD | CARD:
                found[event_type] = cls
    need(set(found) == NO_CARD | CARD, "every new event has tl:event_type")
    for event_type, cls in found.items():
        policy = (cls.get("attributes") or {}).get("feed_policy")
        if event_type in NO_CARD:
            need(policy is not None and policy.get("equals_string") == "none", f"{event_type} none")
        else:
            need(policy is None, f"{event_type} makes a feed card")
        tagged = [
            n
            for n, a in cls["attributes"].items()
            if (a.get("annotations") or {}).get("tl:valid_time")
        ]
        need(len(tagged) == 1, f"{event_type} tags one slot with tl:valid_time")
        if event_type in AT_EVENTS:
            need(tagged == ["at"], f"{event_type}.at is valid time")
    passed(
        "every event has tl:event_type and the stated feed policy; the `at` fields are valid time"
    )


def words() -> None:
    table = load_access_words()
    for word, expected in WORDS.items():
        need(table.get(word) == expected, f"{word} is {expected}")
        need(table_word(word) == expected, f"{word} resolves to {expected}")
    need(table["core.constraint.waive"] == "controller", "waive is controller")
    passed("every new word resolves to its table word; core.constraint.waive is controller")


def file_slots() -> None:
    pack = parse_file_slots((FIXTURES / "files" / "awp-iwp.yaml").read_text("utf-8"), source="a")
    close = parse_file_slots(
        (FIXTURES / "files" / "awp-iwp-closeout.yaml").read_text("utf-8"), source="b"
    )
    need(pack.get("awp.IWP", "pack") is not None, "pack slot")
    need(
        {s.name for s in close.for_type("awp.IWPCloseout")} == {"redlines", "actuals"},
        "closeout slots",
    )
    passed("both file-slot fixtures load")


def _event(event_type: str, stream: str, seq: int, payload: dict[str, Any]) -> Event:
    return Event(
        event_type=event_type,
        schema_version=1,
        payload=payload,
        seq=seq,
        event_id=f"e{seq}",
        stream_id=stream,
        stream_type="awp.WeeklyPlan",
        stream_version=seq,
        scope="project:P123",
        actor="user:ana",
        recorded_at=NOW,
        effective_at=NOW,
        correlation_id="c",
        causation_id=None,
        source="accept",
        prev_hash=None,
        hash="0" * 64,
    )


def projectors() -> None:
    engine = create_engine("sqlite://")
    week, progress = WeekProjector(), ProgressProjector()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE cur_core_record (id TEXT, version INT, last_seq INT, updated_at TEXT)"
            )
        )
        for stream in (PLAN, IWP):
            conn.execute(text("INSERT INTO cur_core_record VALUES (:i, 1, 0, '')"), {"i": stream})
        for projector in (week, progress, IwpProjector()):
            for statement in projector.ddl("sqlite"):
                conn.execute(text(statement))
        week.apply(
            conn,
            _event("WeeklyPlan.Opened", PLAN, 2, {"week": "2026-W45", "week_start": "2026-11-02"}),
        )
        commit = {"iwp_id": IWP, "foreman": "user:ana", "committed_hours": "40.0"}
        week.apply(conn, _event("WeeklyPlan.IwpCommitted", PLAN, 3, commit))
        outcome = {"iwp_id": IWP, "outcome": "done", "miss_reason": None}
        week.apply(conn, _event("WeeklyPlan.OutcomeRecorded", PLAN, 4, outcome))
        week.apply(conn, _event("WeeklyPlan.Closed", PLAN, 5, {"ppc": "100.0"}))
        need(
            conn.execute(text("SELECT ppc FROM cur_awp_weekly_plan")).scalar_one() == "100.0",
            "plan closed with its ppc",
        )
        need(
            conn.execute(text("SELECT outcome FROM cur_awp_week_commitment")).scalar_one()
            == "done",
            "commitment outcome",
        )
        body = {"iwp_id": IWP, "earned_pct": "42.5", "edition": "co.acme.awp@1.1.0", "at": "x"}
        progress.apply(conn, _event("IWP.ProgressRecorded", IWP, 6, body))
        need(
            conn.execute(text("SELECT earned_pct FROM cur_awp_iwp_progress")).scalar_one()
            == "42.5",
            "progress row",
        )
    passed("each projector round-trips a hand-written event")


def pack_extra() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text("utf-8"))
    awp = next(p for p in lock["package"] if p["name"] == "tl-mod-awp")
    extra = {d["name"] for d in awp["optional-dependencies"]["pack"]}
    need(extra == {"reportlab", "segno"}, "the pack extra holds reportlab and segno")
    passed("the pack extra resolves in uv.lock")


def main() -> None:
    ddl_tables()
    workflow()
    package()
    settings()
    events()
    words()
    file_slots()
    projectors()
    pack_extra()
    print("S1 ok")


if __name__ == "__main__":
    main()
