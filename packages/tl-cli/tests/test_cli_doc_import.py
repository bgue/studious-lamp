"""`tl doc import` on a temporary ledger (P1-I2-T12e): preview, apply, refusals, limits."""

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


def test_a_user_can_preview_but_cannot_apply_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path
) -> None:
    """A bulk write into the controlled register is the admin's (ADR-0011), like `tl tag import`."""
    if not admin_session(env):
        return  # on Postgres the test session is already an admin: there is no user to refuse
    user = ordinary_env(env, tmp_path)
    preview = do_import(user)
    assert preview.stdout.splitlines()[1] == "new=9  exists=0  invalid=7"
    for flags in (("--apply",), ("--apply", "--skip-invalid")):  # skip-invalid is no way round
        refused = do_import(user, *flags, ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    assert register(env) == []
    assert "dms-document-register" not in run(env, "doc", "ls", "--project", "P123").stdout


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


HEAD = (
    "DOC NO,TITLE,DOC TYPE,DISCIPLINE,ORIGINATOR,REV,STATUS,REV DATE,FILE PATH,CHECKED BY,REMARKS\n"
)


def small_file(tmp_path: Path, *rows: str, name: str = "small.csv") -> str:
    path = tmp_path / name
    path.write_text(HEAD + "".join(rows), encoding="utf-8")
    return str(path)


def line(number: str, title: str = "A title") -> str:
    return f"{number},{title},ISOMETRIC,PIPING,Acme Piping,A,IFR,2024-01-01,,,\n"


def test_what_apply_would_refuse_is_invalid_in_the_preview_and_skip_invalid_imports_the_rest(
    env: dict[str, str], tmp_path: Path
) -> None:
    admin_session(env)
    file = small_file(tmp_path, line("ISO-0201", "t" * 600), line("ISO-0202"))
    out = do_import(env, file=file).stdout.splitlines()
    assert out[1] == "new=1  exists=0  invalid=1"
    assert out[-2].startswith("! line 2: title: ") and out[-1].startswith("dry run")
    assert "+ ISO-0202  ISO  A title" in out
    done = do_import(env, "--apply", "--skip-invalid", file=file)
    assert done.stdout.splitlines()[-1].endswith("registered=1  skipped=1")
    assert [row.split("  ")[0] for row in register(env)] == ["ISO-0202"]


def test_a_control_character_is_an_invalid_row_and_never_printed(
    env: dict[str, str], tmp_path: Path
) -> None:
    file = small_file(
        tmp_path, line("ISO-0\x00301"), line("ISO-0302", "Ti\x00tle"), line("ISO-0303")
    )
    out = do_import(env, file=file).stdout
    assert "\x00" not in out
    lines = out.splitlines()
    assert lines[1] == "new=1  exists=0  invalid=2"
    assert "! line 2: DOC NO: holds a control character" in lines
    assert "! line 3: TITLE: holds a control character; the title is blank" in lines


def test_a_file_with_more_than_a_thousand_rows_is_refused_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path
) -> None:
    admin_session(env)
    rows = [line(f"ISO-{n:04d}") for n in range(1001)]
    file = small_file(tmp_path, *rows, name="many.csv")
    for flags in ((), ("--apply",)):
        refused = do_import(env, *flags, file=file, ok=False)
        assert refused.stderr.strip() == (
            "error: the file has more than 1000 rows; an import takes at most 1000, so split it"
        )
    assert register(env) == []


def test_a_file_over_five_mebibytes_is_refused_before_it_is_read(
    env: dict[str, str], tmp_path: Path
) -> None:
    big = tmp_path / "big.csv"
    with big.open("wb") as handle:
        handle.truncate(5 * 1024 * 1024 + 1)
    refused = do_import(env, file=str(big), ok=False)
    assert refused.stderr.startswith("error: big.csv: the file is 5242881 bytes; an import takes")
    assert "at most 5 MiB" in refused.stderr
