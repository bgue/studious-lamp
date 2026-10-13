"""`tl doc import` on a temporary ledger (P1-I2-T12d): preview, apply, refusals."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from doccli_support import admin_session, docs_env, load_document_standards, world
from engcli_support import ordinary_env
from tl_adapters.db import DbTarget
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = str(ROOT / "dev" / "seed" / "templates" / "document-register-dms-export.yaml")
SAMPLE = str(ROOT / "dev" / "seed" / "legacy" / "dms-document-register.csv")

runner = CliRunner()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = docs_env(new_db, monkeypatch)
    load_document_standards(values)
    return values


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def do_import(env: dict[str, str], *more: str, file: str = SAMPLE, ok: bool = True) -> RunResult:
    args = ("doc", "import", file, "--project", "P123", "--mapping", TEMPLATE)
    return run(env, *args, *more, ok=ok)


def register(env: dict[str, str]) -> list[str]:
    return run(env, "doc", "ls", "--project", "P123").stdout.splitlines()


def test_the_preview_says_what_would_happen_and_writes_nothing(env: dict[str, str]) -> None:
    out = do_import(env).stdout.splitlines()
    assert out[0] == "import dms-document-register dms-document-register.csv into project P123"
    assert out[1] == "new=9  exists=0  invalid=7"
    assert out[2] == "+ ISO-0101  ISO  Isometric, line 47-P-101"
    assert out[10] == "+ CAL-0007  CAL  Pipe stress calculation line 47-P-101"
    assert out[11].startswith("! line 11: the number appears again; first on line 2")
    assert "! line 14: DISCIPLINE: 'WELDING' is not one of the mapped values" in out
    assert "! line 16: the title is blank" in out
    assert out[-1] == "dry run: nothing written; add --apply to write"
    assert register(env) == []


def test_apply_is_for_an_admin_and_refuses_a_file_with_invalid_rows(
    env: dict[str, str], tmp_path: Path
) -> None:
    if admin_session(env):
        refused = do_import(ordinary_env(env, tmp_path), "--apply", ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    whole = do_import(env, "--apply", ok=False)
    assert "7 row(s) cannot be imported" in whole.stderr
    assert register(env) == []


def test_skip_invalid_registers_the_valid_rows_and_a_second_run_finds_them(
    env: dict[str, str],
) -> None:
    admin_session(env)
    done = do_import(env, "--apply", "--skip-invalid", "--job", "dms-2024")
    assert done.stdout.splitlines()[-1] == "applied dms-2024: registered=9  skipped=7"
    listing = register(env)
    assert len(listing) == 9 and listing[0].startswith("CAL-0007  Registered  -  CAL  STR")
    shown = run(env, "doc", "show", "ISO-0101", "--project", "P123").stdout
    assert "title: Isometric, line 47-P-101" in shown and "originator: Acme Piping" in shown
    again = do_import(env).stdout.splitlines()
    assert again[1] == "new=0  exists=9  invalid=7" and "= ISO-0101" in again


def test_a_bad_mapping_a_missing_file_and_a_wrong_file_are_errors(
    env: dict[str, str], tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not\n- a mapping\n", encoding="utf-8")
    result = run(env, "doc", "import", SAMPLE, "--project", "P123", "--mapping", str(bad), ok=False)
    assert result.stderr.strip() == "error: bad.yaml: a mapping template must be a YAML mapping"
    missing = do_import(env, file=str(tmp_path / "nope.csv"), ok=False)
    assert missing.exit_code != 0
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("DOC NO,TITLE\nISO-1,x\n", encoding="utf-8")
    result = do_import(env, file=str(wrong), ok=False)
    assert result.stderr.startswith("error: the file lacks the column(s): DOC TYPE")


def test_the_registered_documents_are_the_modules_own(env: dict[str, str], tmp_path: Path) -> None:
    admin_session(env)
    do_import(env, "--apply", "--skip-invalid")
    made = world(env, tmp_path)
    assert made.document("SPC-0003").doc_type == "SPC"
    assert made.document("SPC-0003").revision_scheme == "numeric"  # the company rule for specs
