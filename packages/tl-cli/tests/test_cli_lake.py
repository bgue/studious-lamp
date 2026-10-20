"""`tl lake` commands on a temporary ledger and lake (P0-I7-T20; brief 28)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pg_support import account_events
from tl_adapters.db import DbTarget
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    """A fresh ledger with two records and a fresh, empty lake directory."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(new_db()), "TL_LAKE_DIR": str(tmp_path / "lake")}
    assert run(values, "init").exit_code == 0
    for key in ("A-1", "B-1"):
        result = run(
            values, "record", "create", "--project", "P123", "--key", key, "--title", f"T {key}"
        )
        assert result.exit_code == 0, result.output
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def head(env: dict[str, str]) -> int:
    line = next(
        ln for ln in run(env, "lake", "status").stdout.splitlines() if ln.startswith("as of")
    )
    return int(line.split()[3])


def test_status_before_any_sync_says_so_and_succeeds(env: dict[str, str]) -> None:
    result = run(env, "lake", "status")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["lake not initialised: run `tl lake sync`"]


def test_sync_reports_the_range_the_snapshot_and_the_silver_rows(env: dict[str, str]) -> None:
    result = run(env, "lake", "sync")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    n = 2 + account_events(env)  # the signed-in test account of a Postgres ledger is an event too
    assert lines[0].startswith(f"synced seq 1..{n} ({n} events) in snapshot ")
    assert lines[1] == (
        "silver rows: cur_core_record 2, links 0, pset_values 0, "
        "cur_documents_document 0, cur_documents_revision 0"
    )


def test_a_second_sync_with_nothing_new_makes_no_snapshot(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "sync")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [f"lake is up to date as of seq {2 + account_events(env)}"]


def test_sync_is_incremental(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    run(env, "record", "create", "--project", "P123", "--key", "C-1", "--title", "T C-1")
    result = run(env, "lake", "sync")
    lines = result.stdout.splitlines()
    last = 3 + account_events(env)
    assert lines[0].startswith(f"synced seq {last}..{last} (1 events) in snapshot ")
    assert lines[1] == (
        "silver rows: cur_core_record 1, links 0, pset_values 0, "
        "cur_documents_document 0, cur_documents_revision 0"
    )


def test_status_after_a_sync_shows_the_as_of_seq_and_row_counts(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "status")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    n = 2 + account_events(env)
    assert lines[0].startswith(f"as of seq {n} (snapshot ")
    assert lines[1] == "syncs 1"
    assert lines[2:] == [
        "cur_core_record 2",
        "cur_documents_document 0",
        "cur_documents_revision 0",
        f"events {n}",
        "links 0",
        "pset_values 0",
    ]


def test_query_prints_a_table_and_the_as_of_line(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "query", "SELECT key, title FROM cur_core_record ORDER BY key")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[:3] == ["key | title", "A-1 | T A-1", "B-1 | T B-1"]
    assert lines[3].startswith(f"as of seq {2 + account_events(env)} (snapshot ")


def test_query_marks_nulls_and_says_when_it_truncated(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(
        env,
        "lake",
        "query",
        "--limit",
        "1",
        "SELECT key, description FROM cur_core_record ORDER BY key",
    )
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[:2] == ["key | description", "A-1 | NULL"]
    assert lines[2] == "truncated at 1 rows"
    assert lines[3].startswith(f"as of seq {2 + account_events(env)} ")


def test_query_json_prints_one_object(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "query", "--json", "SELECT count(*) AS n FROM events")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    n = 2 + account_events(env)
    assert payload["columns"] == ["n"] and payload["rows"] == [[n]]
    assert payload["as_of_seq"] == n and payload["truncated"] is False


@pytest.mark.parametrize(
    "sql",
    ["DROP TABLE events", "SELECT 1; SELECT 2", "SELECT * FROM read_csv('/etc/passwd')"],
)
def test_a_refused_query_exits_1_with_the_reason_and_changes_nothing(
    env: dict[str, str], sql: str
) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "query", sql)
    assert result.exit_code == 1
    assert result.stderr.startswith("error: refused: ")
    assert result.stdout == ""
    assert run(env, "lake", "query", "SELECT count(*) FROM events").exit_code == 0


def test_query_before_any_sync_exits_1(env: dict[str, str]) -> None:
    result = run(env, "lake", "query", "SELECT 1")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: no lake at ")


def test_tables_lists_each_table_with_its_columns(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    result = run(env, "lake", "tables")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert "events" in lines and "  seq BIGINT" in lines
    assert "cur_core_record" in lines and "  voided BOOLEAN" in lines
    assert lines.index("_tl_sync") < lines.index("cur_core_record") < lines.index("events")


def test_rebuild_needs_yes_and_then_reloads_everything(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    run(env, "record", "create", "--project", "P123", "--key", "C-1", "--title", "T C-1")
    run(env, "lake", "sync")
    refused = run(env, "lake", "rebuild")
    assert refused.exit_code == 1
    assert refused.stderr.startswith("error: rebuild deletes the lake")
    result = run(env, "lake", "rebuild", "--yes")
    assert result.exit_code == 0, result.output
    n = 3 + account_events(env)
    assert result.stdout.splitlines()[0].startswith(f"synced seq 1..{n} ({n} events) in snapshot ")
    assert run(env, "lake", "status").stdout.splitlines()[1] == "syncs 1"
    assert head(env) == n


def test_mart_ls_and_show_read_a_mart(env: dict[str, str]) -> None:
    run(env, "lake", "sync")
    empty = run(env, "lake", "mart", "ls")
    assert empty.exit_code == 0, empty.output
    assert empty.stdout.strip() == ""  # no document or schedule yet: no mart
    missing = run(env, "lake", "mart", "show", "mart_document_status")
    assert missing.exit_code == 1
    assert "no mart 'mart_document_status'" in missing.output
    refused = run(env, "lake", "mart", "show", "cur_core_record")
    assert refused.exit_code == 1 and "no mart" in refused.output


def test_mart_show_prints_the_document_status_mart(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from doccli_support import world
    from tl_core import confidentiality as cf

    made = world(env, tmp_path)
    with cf.system_view():
        made.issued_document("ISO-1")
        made.register("ISO-2", confidentiality="restricted")
        made.create_revision("ISO-2")
        made.attach("ISO-2", "A")
        made.issue("ISO-2", "A", "IFR")
    assert run(env, "lake", "sync").exit_code == 0
    listed = run(env, "lake", "mart", "ls").stdout.splitlines()
    assert "mart_document_status 1" in listed
    shown = run(env, "lake", "mart", "show", "mart_document_status")
    assert shown.exit_code == 0, shown.output
    header, row = shown.stdout.splitlines()[:2]
    assert header.startswith("scope | discipline | doc_type | status | documents")
    assert " | 1 | " in row  # the restricted document is in no count
