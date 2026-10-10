"""`tl file reconcile` on a temporary ledger and an fs object store (P0-I4-T25). Rows of cur_files
are inserted with SQL; the store holds real bytes."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.uow import open_uow
from tl_cli.main import app
from tl_core.files import object_key
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
INSERT = text(
    "INSERT INTO cur_files (file_id, scope, record_id, slot, revision, sha256, size, content_type, "
    "filename, status, deduplicated, uploaded_by, uploaded_at, updated_at, version, last_seq) "
    "VALUES (:file_id, 'project:P123', 'REC', NULL, 1, :sha, :size, 'text/plain', 'f.txt', "
    "'available', 0, 'user:t', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 1, 1)"
)


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    env = {
        "TL_DB": str(tmp_path / "tl.db"),
        "TL_OBJECT_ROOT": str(tmp_path / "objects"),
        "TL_ENV": "dev",
    }
    assert run(env, "init").exit_code == 0
    return env


def store_of(env: dict[str, str]) -> FsObjectStore:
    # TL_ENV=dev makes the CLI sign with the public dev secret; reconcile needs no signature.
    return FsObjectStore(Path(env["TL_OBJECT_ROOT"]), secret=b"unused")


def add(env: dict[str, str], file_id: str, body: bytes, *, stored: bool = True) -> str:
    digest = hashlib.sha256(body).hexdigest()
    if stored:
        store_of(env).put(
            object_key(digest),
            io.BytesIO(body),
            size=len(body),
            sha256=digest,
            content_type="text/plain",
        )
    with open_uow(env["TL_DB"]) as uow:
        uow.conn().execute(INSERT, {"file_id": file_id, "sha": digest, "size": len(body)})
    return digest


def summary(result: RunResult) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, value = line.partition(" ")
        found.setdefault(name, value)
    return found


def test_a_clean_store_exits_zero(env: dict[str, str]) -> None:
    add(env, "F-1", b"one")
    result = run(env, "file", "reconcile")
    assert result.exit_code == 0, result.output
    assert summary(result) == {
        "checked": "1",
        "verified": "false",
        "missing": "0",
        "corrupt": "0",
        "orphans": "0",
        "staging": "0",
    }


def test_a_missing_object_is_listed_and_exits_one(env: dict[str, str]) -> None:
    digest = add(env, "F-gone", b"gone", stored=False)
    result = run(env, "file", "reconcile")
    assert result.exit_code == 1
    assert summary(result)["missing"] == "1"
    assert f"missing {digest} files=F-gone" in result.stdout.splitlines()


def test_verify_finds_corruption(env: dict[str, str]) -> None:
    digest = add(env, "F-1", b"original")
    store_of(env).path_for(object_key(digest)).write_bytes(b"tampered")
    assert run(env, "file", "reconcile").exit_code == 0  # without --verify the bytes are not read
    result = run(env, "file", "reconcile", "--verify")
    assert result.exit_code == 1
    assert summary(result)["verified"] == "true" and summary(result)["corrupt"] == "1"
    other = hashlib.sha256(b"tampered").hexdigest()
    assert f"corrupt {digest} files=F-1 sha256 is {other}" in result.stdout.splitlines()


def test_orphans_are_listed_but_do_not_fail_the_run(env: dict[str, str]) -> None:
    add(env, "F-1", b"kept")
    body = b"left over"
    orphan = object_key(hashlib.sha256(body).hexdigest())
    store_of(env).put(
        orphan,
        io.BytesIO(body),
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        content_type="text/plain",
    )
    store_of(env).put(
        "staging/abc",
        io.BytesIO(b"s"),
        size=1,
        sha256=hashlib.sha256(b"s").hexdigest(),
        content_type="text/plain",
    )
    result = run(env, "file", "reconcile")
    assert result.exit_code == 0, result.output
    assert summary(result)["orphans"] == "1" and summary(result)["staging"] == "1"
    assert f"orphan {orphan}" in result.stdout.splitlines()


def test_it_does_not_change_the_store_or_the_ledger(env: dict[str, str]) -> None:
    add(env, "F-1", b"one")
    store = store_of(env)
    before = list(store.iter_keys())
    run(env, "file", "reconcile", "--verify")
    assert list(store.iter_keys()) == before
    with open_uow(env["TL_DB"], readonly=True) as uow:
        assert uow.conn().execute(text("SELECT COUNT(*) FROM cur_files")).scalar_one() == 1


def test_an_unconfigured_secret_is_an_error(env: dict[str, str]) -> None:
    result = run(env | {"TL_ENV": ""}, "file", "reconcile")
    assert result.exit_code == 1 and "TL_OBJECT_SECRET" in result.stderr
