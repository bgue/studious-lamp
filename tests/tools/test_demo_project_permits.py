"""The permits section of the demo project (P2-PTW-T03).

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``), as
``test_demo_project_inspections.py`` does. The generator is SQLite only (its ``--db`` is a file
path), so these tests do not run on Postgres (L-P2-WEB1-3).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 6)  # world.TODAY: the fixed "today" of the demo project
DAY = TODAY.isoformat()
SOURCED = "core,engineering,awp,constraints"
SECTIONS = f"{SOURCED},permits"
TYPES = ("hot_work", "confined_space", "work_at_height", "excavation", "isolation", "general")
NEEDS_ISOLATION = ("confined_space", "isolation")

#: The shown state of each permit by key order, as ``dev.seed.demo_project.permits.FINAL`` fixes it.
SHOWN = (
    "Active", "Active", "Requested", "Approved", "Active", "Requested", "Active", "Suspended",
    "Active", "Approved", "Approved", "Suspended", "Lapsed", "Closed", "Rejected", "Handed back",
    "Closed", "Lapsed", "Rejected", "Cancelled",
)  # fmt: skip


@dataclass(frozen=True)
class Run:
    db: Path
    stdout: str
    returncode: int


def generate(db: Path, objects: Path, sections: str) -> Run:
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev.seed.demo_project",
            "--db",
            str(db),
            "--objects",
            str(objects),
            "--sections",
            sections,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return Run(db, done.stdout, done.returncode)


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


PERMITS = (
    "SELECT r.id AS id, r.key AS key, r.status AS status, p.permit_type AS permit_type, "
    "p.area AS area, p.holder AS holder, p.for_record_id AS for_record_id, "
    "p.requested_by AS requested_by, p.approved_by AS approved_by, p.valid_until AS valid_until, "
    "s.type AS subject_type FROM cur_core_record r JOIN cur_permits_permit p ON p.id = r.id "
    "LEFT JOIN cur_core_record s ON s.id = p.for_record_id "
    "WHERE r.type = 'permits.Permit' ORDER BY r.key"
)
ISOLATIONS = (
    "SELECT r.id AS id, r.key AS key, r.status AS status, i.energy AS energy, "
    "i.lock_number AS lock_number, i.tag_number AS tag_number, i.applied_by AS applied_by, "
    "i.verified_by AS verified_by, i.point_record_id AS point_record_id "
    "FROM cur_core_record r JOIN cur_permits_isolation i ON i.id = r.id "
    "WHERE r.type = 'permits.Isolation' ORDER BY r.key"
)
GAS_TESTS = (
    "SELECT r.key AS key, g.permit_id AS permit_id, g.taken_at AS taken_at, g.result AS result, "
    "g.id AS id, g.o2_pct AS o2, g.lel_pct AS lel, g.h2s_ppm AS h2s, g.co_ppm AS co "
    "FROM cur_core_record r JOIN cur_permits_gas_test g ON g.id = r.id "
    "WHERE r.type = 'permits.GasTest' ORDER BY r.key"
)


def shown(permit: dict[str, object]) -> str:
    """The state shown on TODAY: Lapsed is an Active permit whose ``valid_until`` is past."""
    stored = str(permit["status"] or "Requested")
    if stored == "Active" and str(permit["valid_until"])[:10] < DAY:
        return "Lapsed"
    return stored


def permits(db: Path) -> list[dict[str, object]]:
    return rows(db, PERMITS)


def isolations(db: Path) -> list[dict[str, object]]:
    return rows(db, ISOLATIONS)


def state_of(item: dict[str, object], default: str) -> str:
    return str(item["status"] or default)


def counts(items: list[dict[str, object]], column: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for item in items:
        found[str(item[column])] = found.get(str(item[column]), 0) + 1
    return found


def live_links(db: Path) -> dict[str, set[str]]:
    """Permit id -> the isolations its own events link and have not unlinked."""
    found: dict[str, set[str]] = {}
    for event in rows(
        db,
        "SELECT stream_id, event_type, payload FROM events WHERE event_type IN "
        "('Permit.IsolationLinked', 'Permit.IsolationUnlinked') ORDER BY seq",
    ):
        body = json.loads(str(event["payload"]))
        live = found.setdefault(str(event["stream_id"]), set())
        if event["event_type"] == "Permit.IsolationLinked":
            live.add(str(body["isolation_id"]))
        else:
            live.discard(str(body["isolation_id"]))
    return found


def events_of(db: Path, event_type: str) -> list[dict[str, object]]:
    found = rows(
        db, f"SELECT stream_id, payload FROM events WHERE event_type = '{event_type}' ORDER BY seq"
    )
    return [{"stream_id": e["stream_id"], **json.loads(str(e["payload"]))} for e in found]


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-permits")
    made = {
        "main": generate(base / "main.db", base / "objects-main", SECTIONS),
        "again": generate(base / "again.db", base / "objects-again", SECTIONS),
        "without": generate(base / "without.db", base / "objects-without", SOURCED),
        "bare": generate(base / "bare.db", base / "objects-bare", "core,permits"),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_the_counts_by_shown_state_and_by_type(runs: dict[str, Run]) -> None:
    items = permits(runs["main"].db)
    assert [shown(p) for p in items] == list(SHOWN)
    assert counts([{"s": shown(p)} for p in items], "s") == {
        "Requested": 2,
        "Approved": 3,
        "Active": 5,
        "Lapsed": 2,
        "Suspended": 2,
        "Handed back": 1,
        "Closed": 2,
        "Rejected": 2,
        "Cancelled": 1,
    }
    by_type = counts(items, "permit_type")
    assert set(by_type) == set(TYPES)
    assert sum(by_type.values()) == 20


def test_keys_have_no_gap(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    assert [str(p["key"]) for p in permits(db)] == [f"P200-PTW-{n:04d}" for n in range(1, 21)]
    assert [str(i["key"]) for i in isolations(db)] == [f"P200-ISL-{n:04d}" for n in range(1, 9)]
    assert [str(g["key"]) for g in rows(db, GAS_TESTS)] == [
        f"P200-GAS-{n:04d}" for n in range(1, 15)
    ]


def test_the_subjects(runs: dict[str, Run]) -> None:
    found = counts(permits(runs["main"].db), "subject_type")
    assert found == {"awp.IWP": 12, "awp.CWP": 2, "None": 6}


def test_the_isolations_by_state_and_link(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    isos = isolations(db)
    assert counts([{"s": state_of(i, "Applied")} for i in isos], "s") == {
        "Verified": 3,
        "Applied": 3,
        "Removed": 2,
    }
    assert {str(i["energy"]) for i in isos} == {"electrical", "mechanical", "process", "other"}
    assert [i["lock_number"] for i in isos] == [f"L-{n:02d}" for n in range(1, 9)]
    assert [i["tag_number"] for i in isos] == [f"T-{n:02d}" for n in range(1, 9)]
    by_permit = {str(p["id"]): p for p in permits(db)}
    state_by_iso = {str(i["id"]): state_of(i, "Applied") for i in isos}
    linked_states: dict[str, list[str]] = {}
    for permit_id, linked in live_links(db).items():
        for iso in linked:
            linked_states.setdefault(state_by_iso[iso], []).append(shown(by_permit[permit_id]))
    assert sorted(linked_states["Verified"]) == ["Active", "Active", "Suspended"]
    assert linked_states["Applied"] == ["Approved"]
    tagged = [i for i in isos if i["point_record_id"] is not None]
    assert len(tagged) == 1
    point = rows(
        db, f"SELECT type FROM cur_core_record WHERE id = '{tagged[0]['point_record_id']}'"
    )
    assert [p["type"] for p in point] == ["engineering.Tag"]


def test_an_active_permit_has_the_isolation_its_type_requires(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    state_by_iso = {str(i["id"]): state_of(i, "Applied") for i in isolations(db)}
    links = live_links(db)
    seen = 0
    for permit in permits(db):
        if (
            shown(permit) not in ("Active", "Lapsed")
            or permit["permit_type"] not in NEEDS_ISOLATION
        ):
            continue
        states = [state_by_iso[i] for i in links.get(str(permit["id"]), set())]
        assert states, permit["key"]
        assert set(states) == {"Verified"}, permit["key"]
        seen += 1
    assert seen == 2


def test_a_verifier_is_not_the_applier(runs: dict[str, Run]) -> None:
    verified = [i for i in isolations(runs["main"].db) if state_of(i, "Applied") == "Verified"]
    assert len(verified) == 3
    for item in verified:
        assert item["verified_by"] is not None
        assert item["verified_by"] != item["applied_by"], item["key"]


def test_an_approver_is_not_the_requester(runs: dict[str, Run]) -> None:
    approved = [p for p in permits(runs["main"].db) if p["approved_by"] is not None]
    assert len(approved) == 15
    for permit in approved:
        assert permit["approved_by"] != permit["requested_by"], permit["key"]


def test_a_removed_isolation_has_no_live_linked_permit(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    removed = {str(i["id"]) for i in isolations(db) if state_of(i, "Applied") == "Removed"}
    assert len(removed) == 2
    by_permit = {str(p["id"]): p for p in permits(db)}
    for permit_id, linked in live_links(db).items():
        if linked & removed:
            assert shown(by_permit[permit_id]) in ("Handed back", "Closed")


def test_the_gas_tests(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    tests = rows(db, GAS_TESTS)
    assert len(tests) == 14
    assert counts(tests, "result") == {"pass": 11, "fail": 3}
    by_permit = {str(p["id"]): p for p in permits(db)}
    for test in tests:
        permit = by_permit[str(test["permit_id"])]
        assert permit["permit_type"] in ("hot_work", "confined_space")
        assert str(test["taken_at"])[:10] <= DAY
        if permit["valid_until"] is not None:
            assert str(test["taken_at"]) < str(permit["valid_until"])
        assert 0 <= float(str(test["o2"])) <= 100
    # at least one failing test suspended its permit (the S3 rule), and says so
    stopped = [s for s in events_of(db, "Permit.Suspended") if s["gas_test_id"] is not None]
    failing = {str(t["id"]): t for t in tests if t["result"] == "fail"}
    assert len(stopped) == 1
    assert str(stopped[0]["gas_test_id"]) in failing
    assert str(failing[str(stopped[0]["gas_test_id"])]["permit_id"]) == stopped[0]["stream_id"]
    assert shown(by_permit[str(stopped[0]["stream_id"])]) == "Suspended"


def test_a_resume_event_exists_and_the_permit_is_active(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    resumed = events_of(db, "Permit.Resumed")
    assert len(resumed) == 1
    by_permit = {str(p["id"]): p for p in permits(db)}
    assert shown(by_permit[str(resumed[0]["stream_id"])]) == "Active"
    assert len(events_of(db, "Permit.Suspended")) == 3  # two shown Suspended and the resumed one


def test_the_section_line_is_printed(runs: dict[str, Run]) -> None:
    assert any(
        line.startswith("permits: 42 records, ") for line in runs["main"].stdout.splitlines()
    )


def test_two_runs_with_one_seed_agree(runs: dict[str, Run]) -> None:
    def fingerprint(db: Path) -> str:
        lines = [
            f"{p['key']}|{shown(p)}|{p['permit_type']}|{p['area']}|{p['holder']}|"
            f"{p['requested_by']}|{p['approved_by']}|{p['valid_until']}|{p['subject_type']}"
            for p in permits(db)
        ]
        lines += [
            f"{i['key']}|{state_of(i, 'Applied')}|{i['energy']}|{i['applied_by']}|"
            f"{i['verified_by']}"
            for i in isolations(db)
        ]
        lines += [
            f"{g['key']}|{g['result']}|{g['taken_at']}|{g['o2']}|{g['lel']}|{g['h2s']}|{g['co']}"
            for g in rows(db, GAS_TESTS)
        ]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    assert fingerprint(runs["main"].db) == fingerprint(runs["again"].db)


def test_without_permits_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def per_type(db: Path) -> dict[str, int]:
        found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
        counts_ = {str(r["type"]): int(str(r["n"])) for r in found}
        for kind in ("permits.Permit", "permits.Isolation", "permits.GasTest"):
            counts_.pop(kind, None)
        return counts_

    assert per_type(runs["main"].db) == per_type(runs["without"].db)
    assert permits(runs["without"].db) == []


def test_without_iwps_the_permits_name_no_record(runs: dict[str, Run]) -> None:
    bare = runs["bare"]
    assert "permits: no subjects for permits" in bare.stdout.splitlines()
    items = permits(bare.db)
    assert len(items) == 20
    assert all(p["for_record_id"] is None for p in items)
    assert len(isolations(bare.db)) == 8
    assert len(rows(bare.db, GAS_TESTS)) == 14
