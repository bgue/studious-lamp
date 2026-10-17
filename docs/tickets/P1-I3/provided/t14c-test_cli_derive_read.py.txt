"""`tl derive show|report|rows|diff|check|validate` (P1-I3-T14c). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import (
    FACTORY,
    KEY,
    ROWS,
    as_admin,
    csv_file,
    derive_env,
    runtime,
    schema_file,
    seed,
)
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult

P = ["--project", "P123"]
BAD = [*ROWS[:2], ("47-HV-2001", "Vent", "XX", "2")]  # an unknown type on row 3
CHANGED = [ROWS[0], ("47-FV-1002", "Return", "HV", "8"), ("47-PSV-3001", "Relief", "PSV", "1")]


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[dict[str, str]]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    made = seed(values, tmp_path)
    with runtime(made):
        as_admin(values)
        schema = str(schema_file(tmp_path))
        assert tl(values, "derive", "schema", "register", schema, "--company").exit_code == 0
        yield values


def derive(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "derive", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def run_pass(env: dict[str, str], tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """Open (once), attach a CSV, extract and validate it."""
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    derive(env, "content", KEY, str(csv_file(tmp_path, rows, f"p{len(rows)}{rows[-1][0]}.csv")), *P)
    derive(env, "start", KEY, *P)
    derive(env, "worker", "--once", "--factory", FACTORY)


def test_show_lists_state_passes_and_the_running_job(env: dict[str, str], tmp_path: Path) -> None:
    run_pass(env, tmp_path, ROWS)
    lines = derive(env, "show", KEY, *P).stdout.splitlines()
    assert lines[:5] == [
        f"derived {KEY}",
        "state Valid",
        "source src.doc.ISD-001@A",
        "schema instrument-index@1.0.0",
        "method manual",
    ]
    assert "published -" in lines
    assert [line for line in lines if line.startswith("pass ")] == [
        "pass 1  fake  ok  rows 3  validation valid  errors 0"
    ]
    derive(env, "validate", KEY, *P)  # queues a job: show names it
    assert any(
        line.startswith("job ") and line.endswith(" queued")
        for line in derive(env, "show", KEY, *P).stdout.splitlines()
    )


def test_report_prints_the_issues_and_strict_fails_on_invalid(
    env: dict[str, str], tmp_path: Path
) -> None:
    run_pass(env, tmp_path, BAD)
    out = derive(env, "report", KEY, *P).stdout.splitlines()
    assert out[0] == f"report {KEY} pass 1 against instrument-index@1.0.0: invalid"
    assert out[1] == "rows checked 3  with errors 1  errors 1  warnings 0"
    assert out[2].startswith("error row 3 column type ")
    assert "XX" in out[2]
    derive(env, "report", KEY, *P, "--strict", ok=False)
    one = derive(env, "report", KEY, *P, "--limit", "1").stdout.splitlines()
    assert len(one) == 3


def test_report_before_any_pass_is_an_error(env: dict[str, str]) -> None:
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    assert "no extracted data yet" in derive(env, "report", KEY, *P, ok=False).output
    assert "no extracted data yet" in derive(env, "rows", KEY, *P, ok=False).output


def test_rows_pages_the_extracted_cells(env: dict[str, str], tmp_path: Path) -> None:
    run_pass(env, tmp_path, ROWS)
    out = derive(env, "rows", KEY, *P, "--limit", "2").stdout.splitlines()
    assert out[0] == "columns tag service type size_in"
    assert out[1] == "1  47-FV-1001 | Feed | CV | 4"
    assert out[2] == "2  47-FV-1002 | Return | HV | 6"
    assert out[3] == "showing 1-2 of 3"
    rest = derive(env, "rows", KEY, *P, "--offset", "2").stdout.splitlines()
    assert rest[1] == "3  47-HV-2001 | Vent | PSV | 2" and rest[-1] == "showing 3-3 of 3"


def test_diff_compares_a_pass_with_the_one_before(env: dict[str, str], tmp_path: Path) -> None:
    run_pass(env, tmp_path, ROWS)
    assert "no earlier data" in derive(env, "diff", KEY, *P, ok=False).output
    derive(env, "content", KEY, str(csv_file(tmp_path, CHANGED, "changed.csv")), *P)
    derive(env, "start", KEY, *P)
    derive(env, "worker", "--once", "--factory", FACTORY)
    out = derive(env, "diff", KEY, *P).stdout.splitlines()
    assert out[0] == "added 1  removed 1  changed 1  unchanged 1"
    assert "+ 47-PSV-3001" in out and "- 47-HV-2001" in out
    assert "~ 47-FV-1002: size_in 6 -> 8" in out
    wrong = derive(env, "diff", KEY, *P, "--against", "sideways", ok=False)
    assert "--against must be previous_pass or previous_revision" in wrong.output


def test_check_validates_now_and_stores_nothing(env: dict[str, str], tmp_path: Path) -> None:
    run_pass(env, tmp_path, ROWS)
    own = derive(env, "check", KEY, *P).stdout.splitlines()
    assert own[0] == f"check {KEY} pass 1 against instrument-index@1.0.0: valid"
    other = schema_file(
        tmp_path,
        semver="2.0.0",
        mapping=None,
        target_kind=None,
        json_schema={
            "type": "object",
            "required": ["tag"],
            "properties": {"tag": {"type": "string", "pattern": "^ZZ"}},
        },
    )
    assert tl(env, "derive", "schema", "register", str(other), "--company").exit_code == 0
    out = derive(env, "check", KEY, *P, "--schema", "instrument-index@2.0.0").stdout
    assert "against instrument-index@2.0.0: invalid" in out
    derive(env, "check", KEY, *P, "--schema", "instrument-index@2.0.0", "--strict", ok=False)
    assert "pass 1  fake  ok  rows 3  validation valid" in derive(env, "show", KEY, *P).stdout
    assert derive(env, "jobs", *P, "--state", "queued").stdout.strip() == ""


def test_validate_queues_a_job_and_the_worker_keeps_the_report(
    env: dict[str, str], tmp_path: Path
) -> None:
    run_pass(env, tmp_path, ROWS)
    queued = derive(env, "validate", KEY, *P).stdout.strip()
    assert queued.startswith("queued ") and queued.endswith(f" for {KEY}")
    ran = derive(env, "worker", "--once", "--factory", FACTORY).stdout.splitlines()
    assert ran[0].endswith(" validate done")


def test_an_unknown_key_is_named(env: dict[str, str]) -> None:
    out = derive(env, "show", "ISD-009@A/none", *P, ok=False)
    assert "no derived document 'ISD-009@A/none'" in out.output


def test_validate_cannot_act_as_someone_else(env: dict[str, str], tmp_path: Path) -> None:
    from tl_adapters.db import as_target, is_postgres

    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs one admin in on Postgres")
    run_pass(env, tmp_path, ROWS)
    prod = env | {"TL_ENV": "prod"}  # a setup where nobody may act as someone else
    refused = tl(prod, "derive", "validate", KEY, *P, "--actor", "user:ceo")
    assert refused.exit_code == 1 and "is not the signed-in user" in refused.output
    assert derive(env, "jobs", *P, "--state", "queued").stdout.strip() == ""
