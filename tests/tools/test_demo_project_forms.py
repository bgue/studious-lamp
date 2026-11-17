"""The forms section of the demo project (V3-F1a; reference ticket T09).

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``), as
``test_demo_project_permits.py`` does. The generator is SQLite only, so these tests do not run on
Postgres.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = "core,forms"

#: The state of each submission in the order they were made, as ``forms.FINAL`` fixes it (the
#: Voided one is a voided record, the Discarded one and the drafts have no key).
FINAL = (
    "Submitted", "Submitted", "Submitted", "Submitted", "Accepted", "Accepted", "Accepted",
    "Accepted", "Returned", "Returned", "Voided", "Draft", "Draft", "Discarded", "Submitted",
)  # fmt: skip

SUBMISSIONS = (
    "SELECT r.id AS id, r.key AS key, COALESCE(r.status, 'Draft') AS status, r.voided AS voided, "
    "s.author AS author, s.reviewed_by AS reviewed_by, s.void_reason AS void_reason, "
    "s.answer_class AS answer_class, s.submitted_on AS submitted_on "
    "FROM cur_core_record r JOIN cur_forms_submission s ON s.id = r.id "
    "ORDER BY r.created_at, r.id"
)


@dataclass(frozen=True)
class Run:
    db: Path
    stdout: str
    returncode: int


def generate(db: Path, objects: Path, sections: str) -> Run:
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [
            sys.executable, "-m", "dev.seed.demo_project", "--db", str(db),
            "--objects", str(objects), "--sections", sections,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )  # fmt: skip
    return Run(db, done.stdout, done.returncode)


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-forms")
    made = {
        "main": generate(base / "main.db", base / "objects-main", SECTIONS),
        "again": generate(base / "again.db", base / "objects-again", SECTIONS),
        "without": generate(base / "without.db", base / "objects-without", "core"),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_four_templates_are_published(runs: dict[str, Run]) -> None:
    found = rows(
        runs["main"].db,
        "SELECT r.key AS key, r.status AS status, t.answer_class AS cls, t.content_hash AS h "
        "FROM cur_core_record r JOIN cur_forms_template t ON t.id = r.id ORDER BY r.key",
    )
    assert [f["key"] for f in found] == ["TPL-0001", "TPL-0002", "TPL-0003", "TPL-0004"]
    assert all(f["status"] == "Published" and f["h"] for f in found)
    assert [f["cls"] for f in found] == [None, None, "restricted", "privileged"]


def test_the_submissions_by_state(runs: dict[str, Run]) -> None:
    found = rows(runs["main"].db, SUBMISSIONS)
    assert [f["status"] for f in found] == list(FINAL)
    assert sum(1 for f in found if f["voided"]) == 1


def test_a_reviewer_is_never_the_author_and_the_void_has_a_reason(runs: dict[str, Run]) -> None:
    found = rows(runs["main"].db, SUBMISSIONS)
    for f in found:
        if f["status"] in ("Accepted", "Returned"):
            assert f["reviewed_by"] and f["reviewed_by"] != f["author"]
    voided = [f for f in found if f["status"] == "Voided"]
    assert len(voided) == 1 and voided[0]["void_reason"]


def test_drafts_have_no_number_and_the_rest_have_unique_keys(runs: dict[str, Run]) -> None:
    found = rows(runs["main"].db, SUBMISSIONS)
    for f in found:
        if f["status"] in ("Draft", "Discarded"):
            assert f["key"] is None and f["submitted_on"] is None
    keys = [str(f["key"]) for f in found if f["key"]]
    assert len(keys) == len(set(keys)) == 12
    assert keys == [f"P200-FRM-{n:04d}" for n in range(1, 13)]


def test_one_submission_is_privileged_and_the_default_viewer_reads_the_rest_but_drafts(
    runs: dict[str, Run],
) -> None:
    db = runs["main"].db
    assert [f["answer_class"] for f in rows(db, SUBMISSIONS)].count("privileged") == 1
    with open_uow(db, readonly=True) as uow:
        visible, extra = cf.not_hidden_each("s.id", cf.LOWEST)
        shown = (
            uow.conn()
            .execute(text(f"SELECT count(*) FROM cur_forms_submission s WHERE {visible}"), extra)
            .scalar_one()
        )
    # 15 submissions less the 2 drafts (author only), the 3 restricted ones (hazard assessments:
    # Submitted, Accepted, Discarded) and the privileged one: 9 (the voided one counts here; the
    # views leave a voided record out themselves)
    assert shown == 9


def test_no_event_of_the_section_holds_a_secret(runs: dict[str, Run]) -> None:
    found = rows(
        runs["main"].db,
        "SELECT payload FROM events WHERE event_type LIKE 'Template.%' "
        "OR event_type LIKE 'Submission.%'",
    )
    assert found
    for event in found:
        body = str(event["payload"]).lower()
        assert "password" not in body and "token" not in body


def test_the_section_line_is_printed(runs: dict[str, Run]) -> None:
    assert any(line.startswith("forms: 19 records, ") for line in runs["main"].stdout.splitlines())


def test_two_runs_with_one_seed_agree(runs: dict[str, Run]) -> None:
    def fingerprint(db: Path) -> str:
        found = rows(
            db,
            "SELECT s.author AS a, s.submitted_on AS d, COALESCE(r.key, '') AS k, "
            "COALESCE(r.status, '') AS st, s.answers_json AS j FROM cur_forms_submission s "
            "JOIN cur_core_record r ON r.id = s.id ORDER BY r.created_at, r.id",
        )
        lines = [f"{f['a']}|{f['d']}|{f['k']}|{f['st']}|{f['j']}" for f in found]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    assert fingerprint(runs["main"].db) == fingerprint(runs["again"].db)


def test_without_forms_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def per_type(db: Path) -> dict[str, int]:
        found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
        return {
            str(r["type"]): int(str(r["n"]))
            for r in found
            if not str(r["type"]).startswith("forms.")
        }

    assert per_type(runs["main"].db) == per_type(runs["without"].db)
