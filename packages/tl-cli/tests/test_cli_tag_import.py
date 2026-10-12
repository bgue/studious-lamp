"""`tl tag import`: preview and apply a legacy tag list on a temporary ledger (P1-I1-T10c)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from tl_adapters.db import DbTarget, is_postgres
from tl_cli.main import app
from tl_mod_engineering.testing import seed_registry
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()

MAPPING = {
    "name": "instrument-index",
    "description": "A test export of the incumbent system.",
    "columns": [
        {"column": "TAG NO", "to": "number"},
        {"column": "SERVICE", "to": "service"},
        {"column": "CLASS", "to": "class", "values": {"CV": "ControlValve", "MV": "ManualValve"}},
        {"column": "SIZE", "to": "psets.valve_data.size_in", "type": "decimal"},
        {"column": "MFR", "to": "psets.valve_data.manufacturer"},
    ],
}
HEADER = "TAG NO,SERVICE,CLASS,SIZE,MFR\n"
FILE = HEADER + (
    "47-FV-1001,Feed gas,CV,4,Acme\n"
    "47-FV-1002,Fuel gas,CV,6,\n"
    "10-PT-0001,Pressure,,,\n"
    "LEGACY-1,Old line,MV,,\n"
)


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    target = new_db()
    values = {"TL_DB": str(target)}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    seed_registry(target)
    return values


@pytest.fixture
def mapping(tmp_path: Path) -> Path:
    path = tmp_path / "mapping.yaml"
    path.write_text(yaml.safe_dump(MAPPING), encoding="utf-8")
    return path


def write(tmp_path: Path, content: str, name: str = "tags.csv") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def tl(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def imp(env: dict[str, str], file: Path, mapping: Path, *more: str) -> RunResult:
    return tl(
        env, "tag", "import", str(file), "--mapping", str(mapping), "--project", "P123", *more
    )


def ok(result: RunResult) -> list[str]:
    assert result.exception is None, result.exception
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def listed(env: dict[str, str]) -> list[str]:
    return ok(tl(env, "tag", "ls", "--project", "P123"))


def test_without_apply_it_prints_the_plan_and_writes_nothing(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    lines = ok(imp(env, write(tmp_path, FILE), mapping))
    assert lines == [
        "import instrument-index tags.csv into project P123",
        "new=4  changed=0  unchanged=0  removed=0  invalid=0",
        "+ 47-FV-1001  ControlValve  Feed gas",
        "+ 47-FV-1002  ControlValve  Fuel gas",
        "+ 10-PT-0001  -  Pressure",
        "+ LEGACY-1  ManualValve  Old line",
        "dry run: nothing written; add --apply to write",
    ]
    assert listed(env) == []


def test_apply_creates_the_tags_and_keeps_a_bad_number_as_a_violation(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    lines = ok(imp(env, write(tmp_path, FILE), mapping, "--apply"))
    assert lines[1] == "new=4  changed=0  unchanged=0  removed=0  invalid=0"
    assert lines[-1] == "applied tags: created=4  changed=0  skipped=0"
    assert len(listed(env)) == 4
    shown = ok(tl(env, "tag", "show", "LEGACY-1", "--project", "P123"))
    assert "number_status: violation" in shown and "origin: import" in shown
    valve = ok(tl(env, "tag", "show", "47-FV-1001", "--project", "P123"))
    assert (
        "class: ControlValve" in valve
        and 'psets: {"valve_data":{"manufacturer":"Acme","size_in":4' in valve[-1]
    )


def test_a_second_import_of_the_same_file_changes_nothing(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    file = write(tmp_path, FILE)
    ok(imp(env, file, mapping, "--apply"))
    again = ok(imp(env, file, mapping, "--apply"))
    assert again[1] == "new=0  changed=0  unchanged=4  removed=0  invalid=0"
    assert again[-1] == "applied tags: created=0  changed=0  skipped=0"


def test_the_plan_shows_each_changed_field_and_the_tags_the_file_lacks(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    ok(imp(env, write(tmp_path, FILE), mapping, "--apply"))
    newer = write(
        tmp_path,
        HEADER
        + "47-FV-1001,Feed gas to flare,MV,8,Acme\n10-PT-0001,Pressure,,,\n47-FV-1005,New,CV,,\n",
        "newer.csv",
    )
    lines = ok(imp(env, newer, mapping))
    assert lines[1] == "new=1  changed=1  unchanged=1  removed=2  invalid=0"
    assert lines[2:-1] == [
        "+ 47-FV-1005  ControlValve  New",
        '~ 47-FV-1001  class: "ControlValve" -> "ManualValve"; service: "Feed gas" -> '
        '"Feed gas to flare"; psets.valve_data.size_in: 4 -> 8',
        "- 47-FV-1002",
        "- LEGACY-1",
    ]
    applied = ok(imp(env, newer, mapping, "--apply", "--job", "J7"))
    assert applied[-1] == "applied J7: created=1  changed=1  skipped=0"
    assert "class: ManualValve" in ok(tl(env, "tag", "show", "47-FV-1001", "--project", "P123"))
    assert len(listed(env)) == 5  # the tags the file lacks are still there


def test_invalid_rows_are_listed_and_stop_an_apply_unless_skipped(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    broken = write(tmp_path, FILE + ",No number,CV,,\n47-FV-1003,Bad,CV,wide,\n", "broken.csv")
    lines = ok(imp(env, broken, mapping))
    assert lines[1] == "new=4  changed=0  unchanged=0  removed=0  invalid=2"
    assert lines[-3].startswith("! line 6: the tag number is blank")
    assert lines[-2].startswith("! line 7: ")
    refused = imp(env, broken, mapping, "--apply")
    assert refused.exit_code == 1 and "Traceback" not in refused.output
    assert refused.stderr.splitlines()[0] == (
        "error: 2 row(s) cannot be imported; fix them or skip them"
    )
    assert refused.stderr.splitlines()[1] == "  - line 6: the tag number is blank"
    assert listed(env) == []
    done = ok(imp(env, broken, mapping, "--apply", "--skip-invalid"))
    assert done[-1] == "applied broken: created=4  changed=0  skipped=2"
    assert len(listed(env)) == 4


def test_a_row_the_module_refuses_names_its_line_and_nothing_is_written(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    sizes = HEADER + "47-FV-1001,Feed gas,CV,4,Acme\n47-FV-1002,Fuel gas,CV,6,\n"
    first = write(tmp_path, sizes.replace("CV,6,", "CV,,"), "ok.csv")
    ok(imp(env, first, mapping, "--apply"))
    rows = HEADER + "47-FV-1003,New,CV,,\n47-FV-1001,Feed gas,CV,4,Acme\n"
    spec = yaml.safe_load(mapping.read_text())
    spec["columns"][2]["values"]["XX"] = "NoSuchClass"
    mapping.write_text(yaml.safe_dump(spec), encoding="utf-8")
    bad = write(tmp_path, rows + "47-FV-1004,Bad class,XX,,\n", "bad.csv")
    result = imp(env, bad, mapping, "--apply")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: line 4 (47-FV-1004): ")
    assert "NoSuchClass" in result.stderr
    assert len(listed(env)) == 2


def test_it_names_a_file_or_mapping_it_cannot_use(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    gone = imp(env, tmp_path / "missing.csv", mapping)
    assert gone.exit_code == 1 and gone.stderr.startswith("error: missing.csv: cannot read file")
    lacking = write(tmp_path, "TAG NO,SERVICE\n47-FV-1001,Feed gas\n", "short.csv")
    result = imp(env, lacking, mapping)
    assert result.exit_code == 1
    assert result.stderr.startswith("error: the file lacks the column(s): CLASS, SIZE, MFR")
    nomap = imp(env, write(tmp_path, FILE), tmp_path / "none.yaml")
    assert nomap.exit_code == 1 and "none.yaml: cannot read file" in nomap.stderr


def test_the_source_of_the_events_names_the_job(
    env: dict[str, str], mapping: Path, tmp_path: Path
) -> None:
    if is_postgres(env["TL_DB"]):
        pytest.skip("reads the SQLite file directly")
    import sqlite3

    ok(imp(env, write(tmp_path, FILE), mapping, "--apply", "--job", "J42"))
    with sqlite3.connect(env["TL_DB"]) as conn:
        found = conn.execute(
            "SELECT DISTINCT source FROM events WHERE event_type = 'Tag.Defined'"
        ).fetchall()
    assert found == [("import:J42",)]
