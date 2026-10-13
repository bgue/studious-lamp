"""`tl doc rendition add|replace-signed|ls` on a temporary ledger (P1-I2-T09c).

Documents and revisions are made with the module's own test world (`doccli_support.world`); the
files are uploaded and registered by the commands under test.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from doccli_support import admin_session, docs_env, world
from engcli_support import ordinary_env
from tl_adapters.db import DbTarget
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = docs_env(new_db, monkeypatch)
    values["TL_OBJECT_ROOT"] = str(tmp_path / "cli-objects")
    return values


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def rendition(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "doc", "rendition", *args, ok=ok)


def make(tmp_path: Path, name: str, body: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(body)
    return path


def listing(env: dict[str, str], *more: str, code: str = "A") -> list[list[str]]:
    out = rendition(env, "ls", "ISO-1234", code, "--project", "P123", *more).stdout
    return [line.split("  ") for line in out.splitlines()]


def sha12(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()[:12]


def add(env: dict[str, str], path: Path, *more: str, code: str = "A", ok: bool = True) -> RunResult:
    return rendition(env, "add", "ISO-1234", code, str(path), "--project", "P123", *more, ok=ok)


@pytest.fixture
def draft(env: dict[str, str], tmp_path: Path) -> dict[str, str]:
    """ISO-1234 with a draft revision A and no file."""
    made = world(env, tmp_path)
    made.register("ISO-1234")
    made.create_revision("ISO-1234")
    return env


# --- add and ls -----------------------------------------------------------------------------------


def test_add_uploads_the_file_and_registers_it_as_a_rendition(
    draft: dict[str, str], tmp_path: Path
) -> None:
    body = b"%PDF-1.7 isometric sheet A"
    path = make(tmp_path, "sheet-A.pdf", body)
    result = add(draft, path, "--kind", "pdf", "--pages", "3")
    out = result.stdout.splitlines()
    assert out[0] == "attached pdf sheet-A.pdf to ISO-1234@A"
    assert out[1].startswith("rendition ") and len(out[1].split()[1]) == 26
    assert listing(draft) == [["pdf", "sheet-A.pdf", f"{len(body)}B", "3p", sha12(body), "current"]]


def test_a_newer_pdf_replaces_the_older_and_all_shows_both(
    draft: dict[str, str], tmp_path: Path
) -> None:
    first, second = b"%PDF-1.7 one", b"%PDF-1.7 two, longer"
    add(draft, make(tmp_path, "one.pdf", first), "--kind", "pdf")
    add(draft, make(tmp_path, "two.pdf", second), "--kind", "pdf", "--pages", "5")
    assert listing(draft) == [["pdf", "two.pdf", f"{len(second)}B", "5p", sha12(second), "current"]]
    assert listing(draft, "--all") == [
        ["pdf", "one.pdf", f"{len(first)}B", "-p", sha12(first), "replaced"],
        ["pdf", "two.pdf", f"{len(second)}B", "5p", sha12(second), "current"],
    ]


def test_a_native_file_and_a_markup_are_renditions_of_their_own_kind(
    draft: dict[str, str], tmp_path: Path
) -> None:
    add(draft, make(tmp_path, "sheet.dwg", b"DWG native"), "--kind", "native")
    add(draft, make(tmp_path, "red.pdf", b"%PDF markup"), "--kind", "markup")
    kinds = [row[0] for row in listing(draft)]
    assert kinds == ["markup", "native"]


def test_a_bad_kind_a_missing_revision_and_a_repeated_file_are_errors(
    draft: dict[str, str], tmp_path: Path
) -> None:
    path = make(tmp_path, "sheet.pdf", b"%PDF-1.7 x")
    bad = add(draft, path, "--kind", "scan", ok=False)
    assert bad.stderr.strip() == "error: kind must be one of native, pdf, markup, signed"
    ghost = add(draft, path, "--kind", "pdf", code="Z", ok=False)
    assert ghost.stderr.strip() == "error: no revision 'Z' of ISO-1234"
    add(draft, path, "--kind", "pdf")
    again = add(draft, path, "--kind", "pdf", ok=False)
    assert again.stderr.startswith("error: ")
    assert len(listing(draft, "--all")) == 1


def test_an_issued_revision_takes_no_new_pdf_but_takes_a_signed_copy(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")
    late = add(env, make(tmp_path, "late.pdf", b"%PDF-1.7 late"), "--kind", "pdf", ok=False)
    assert late.stderr.startswith("error: ")
    assert [row[0] for row in listing(env)] == ["pdf"]
    add(env, make(tmp_path, "signed.pdf", b"%PDF-1.7 signed"), "--kind", "signed")
    assert [row[0] for row in listing(env)] == ["pdf", "signed"]


# --- replace-signed -------------------------------------------------------------------------------


def test_the_signed_copy_is_written_once_and_an_admin_replaces_it(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")
    first, second = b"%PDF-1.7 signed one", b"%PDF-1.7 signed two"
    add(env, make(tmp_path, "s1.pdf", first), "--kind", "signed")
    again = add(env, make(tmp_path, "s2.pdf", second), "--kind", "signed", ok=False)
    assert "already has a signed copy" in again.stderr
    args = ("replace-signed", "ISO-1234", "A", str(make(tmp_path, "s2.pdf", second)))
    args += ("--project", "P123", "--reason", "the first scan was cut off")
    if admin_session(env):
        refused = rendition(ordinary_env(env, tmp_path), *args, ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    done = rendition(env, *args)
    assert done.stdout.splitlines()[0] == "replaced the signed copy of ISO-1234@A with s2.pdf"
    signed = [row for row in listing(env, "--all") if row[0] == "signed"]
    assert [(row[1], row[5]) for row in signed] == [("s1.pdf", "replaced"), ("s2.pdf", "current")]


def test_replace_signed_needs_a_signed_copy_to_replace(env: dict[str, str], tmp_path: Path) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")
    admin_session(env)
    path = make(tmp_path, "s.pdf", b"%PDF-1.7 s")
    args = ("replace-signed", "ISO-1234", "A", str(path), "--project", "P123", "--reason", "x")
    result = rendition(env, *args, ok=False)
    assert result.stderr.startswith("error: ")
    assert [row[0] for row in listing(env)] == ["pdf"]
