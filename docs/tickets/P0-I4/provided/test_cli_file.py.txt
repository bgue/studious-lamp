"""`tl file put|get|ls` end to end on a temporary ledger and an fs object store (P0-I4-T24)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
PDF = b"%PDF-1.7 first report"
PDF2 = b"%PDF-1.7 second report"


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def fields(result: RunResult) -> dict[str, str]:
    """The `name value` lines of a command's output."""
    found: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, value = line.partition(" ")
        found[name] = value
    return found


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    env = {
        "TL_DB": str(tmp_path / "tl.db"),
        "TL_OBJECT_ROOT": str(tmp_path / "objects"),
        "TL_ENV": "dev",
        "TL_SCHEMA_DIR": str(Path(__file__).resolve().parents[3] / "schema" / "fixtures"),
    }
    assert run(env, "init").exit_code == 0
    created = run(env, "record", "create", "--project", "P123", "--key", "REC-1", "--title", "R")
    assert created.exit_code == 0, created.output
    return env


def make(tmp_path: Path, name: str, body: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(body)
    return path


def put(env: dict[str, str], path: Path, *extra: str) -> RunResult:
    return run(env, "file", "put", str(path), "--project", "P123", "--record", "REC-1", *extra)


def ls_rows(env: dict[str, str], *extra: str) -> list[list[str]]:
    result = run(env, "file", "ls", "--project", "P123", "--record", "REC-1", *extra)
    assert result.exit_code == 0, result.output
    return [line.split("\t") for line in result.stdout.splitlines()]


def test_put_prints_the_result_and_ls_lists_it(env: dict[str, str], tmp_path: Path) -> None:
    result = put(env, make(tmp_path, "mtr.pdf", PDF), "--slot", "report")
    assert result.exit_code == 0, result.output
    out = fields(result)
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", out["file"])
    assert (out["slot"], out["revision"], out["status"], out["size"]) == (
        "report",
        "1",
        "available",
        str(len(PDF)),
    )
    assert out["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert out["deduplicated"] == "false"
    assert "already attached" not in result.stdout
    assert ls_rows(env) == [[out["file"], "report", "1", "available", str(len(PDF)), "mtr.pdf"]]
    assert (tmp_path / "objects").is_dir()


def test_putting_the_same_bytes_again_attaches_nothing_new(
    env: dict[str, str], tmp_path: Path
) -> None:
    path = make(tmp_path, "mtr.pdf", PDF)
    first = fields(put(env, path, "--slot", "report"))
    again = put(env, path, "--slot", "report")
    assert again.exit_code == 0, again.output
    assert "already attached" in again.stdout
    assert fields(again)["file"] == first["file"]
    assert len(ls_rows(env, "--all")) == 1


def test_a_new_revision_supersedes_the_old_one_in_a_one_slot(
    env: dict[str, str], tmp_path: Path
) -> None:
    first = fields(put(env, make(tmp_path, "r1.pdf", PDF), "--slot", "report"))
    second = fields(put(env, make(tmp_path, "r2.pdf", PDF2), "--slot", "report"))
    assert second["revision"] == "2"
    current = ls_rows(env)
    assert [row[0] for row in current] == [second["file"]]
    everything = ls_rows(env, "--all")
    assert [(row[0], row[2], row[3]) for row in everything] == [
        (first["file"], "1", "superseded"),
        (second["file"], "2", "available"),
    ]


def test_ls_can_filter_by_slot_and_shows_generic_attachments(
    env: dict[str, str], tmp_path: Path
) -> None:
    put(env, make(tmp_path, "r.pdf", PDF), "--slot", "report")
    put(env, make(tmp_path, "pic.jpg", b"\xff\xd8 jpeg"), "--slot", "photo")
    generic = fields(put(env, make(tmp_path, "notes.txt", b"notes")))
    assert generic["slot"] == "-"
    assert {row[1] for row in ls_rows(env)} == {"report", "photo", "-"}
    assert [row[1] for row in ls_rows(env, "--slot", "photo")] == ["photo"]


def test_the_content_type_is_guessed_and_can_be_overridden(
    env: dict[str, str], tmp_path: Path
) -> None:
    refused = put(env, make(tmp_path, "r.txt", PDF), "--slot", "report")
    assert refused.exit_code == 1 and "text/plain" in refused.stderr  # guessed from .txt
    accepted = put(
        env, make(tmp_path, "r.txt", PDF), "--slot", "report", "--content-type", "application/pdf"
    )
    assert accepted.exit_code == 0, accepted.output


def test_get_writes_identical_bytes_and_protects_existing_files(
    env: dict[str, str], tmp_path: Path
) -> None:
    uploaded = fields(put(env, make(tmp_path, "mtr.pdf", PDF), "--slot", "report"))
    out = tmp_path / "copy.pdf"
    result = run(env, "file", "get", uploaded["file"], "--project", "P123", "--out", str(out))
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == PDF
    assert fields(result)["sha256"] == hashlib.sha256(PDF).hexdigest()
    again = run(env, "file", "get", uploaded["file"], "--project", "P123", "--out", str(out))
    assert again.exit_code == 1 and "--force" in again.stderr
    out.write_bytes(b"old")
    forced = run(
        env, "file", "get", uploaded["file"], "--project", "P123", "--out", str(out), "--force"
    )
    assert forced.exit_code == 0 and out.read_bytes() == PDF


def test_get_refuses_and_removes_a_corrupt_object(env: dict[str, str], tmp_path: Path) -> None:
    uploaded = fields(put(env, make(tmp_path, "mtr.pdf", PDF), "--slot", "report"))
    stored = next(p for p in (tmp_path / "objects").rglob("*") if p.is_file())
    stored.write_bytes(b"%PDF-1.7 tampered!!!!")
    out = tmp_path / "copy.pdf"
    result = run(env, "file", "get", uploaded["file"], "--project", "P123", "--out", str(out))
    assert result.exit_code == 1 and "SHA-256" in result.stderr
    assert not out.exists()


def test_errors_are_printed_with_exit_code_one(env: dict[str, str], tmp_path: Path) -> None:
    path = make(tmp_path, "r.pdf", PDF)
    unknown_slot = put(env, path, "--slot", "nope")
    assert unknown_slot.exit_code == 1 and unknown_slot.stderr.startswith("error: ")
    no_record = run(env, "file", "put", str(path), "--project", "P123", "--record", "NOPE")
    assert no_record.exit_code == 1 and "NOPE" in no_record.stderr
    no_file = run(
        env,
        "file",
        "get",
        "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "--project",
        "P123",
        "--out",
        str(tmp_path / "x"),
    )
    assert no_file.exit_code == 1 and no_file.stderr.startswith("error: ")
    no_list = run(env, "file", "ls", "--project", "P123", "--record", "NOPE")
    assert no_list.exit_code == 1 and "NOPE" in no_list.stderr
    assert not (tmp_path / "x").exists()


def test_an_unconfigured_secret_is_an_error_not_a_crash(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_ENV", raising=False)
    monkeypatch.delenv("TL_OBJECT_SECRET", raising=False)
    result = put(env | {"TL_ENV": ""}, make(tmp_path, "r.pdf", PDF), "--slot", "report")
    assert result.exit_code == 1 and "TL_OBJECT_SECRET" in result.stderr
