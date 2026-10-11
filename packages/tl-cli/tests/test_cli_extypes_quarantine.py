"""`tl types quarantine ls|recheck` on a temporary ledger and object store (P0-I8-T26)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_cli.main import app
from tl_core.extypes import body, registry
from tl_core.extypes.errors import BodyHashMismatchError
from tl_core.extypes.lock import write_lock
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CreateRecord
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan"
SCOPE = "project:P123"
BODY: dict[str, Any] = {
    "crane": "CR-12",
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "risk_class": "medium",
}


class Env:
    def __init__(self, tmp_path: Path, db: DbTarget) -> None:
        self.db = db
        self.root = tmp_path / "types"
        self.objects = tmp_path / "objects"
        self.env = {"TL_DB": str(self.db), "TL_OBJECT_ROOT": str(self.objects), "TL_ENV": "dev"}
        self.store = FsObjectStore(self.objects, secret=b"x")

    def run(self, *args: str) -> RunResult:
        return runner.invoke(app, list(args), env=self.env)

    def factory(self, readonly: bool = False) -> Any:
        return open_uow(self.db, readonly=readonly)

    def make_lift(self, key: str = "LP-1") -> str:
        cmd = CreateRecord(
            actor="user:alice", source="test", scope=SCOPE, record_type=LIFT, title="Lift", key=key
        )
        with self.factory() as uow:
            return body.create_extension_record(uow, self.store, cmd, dict(BODY)).stream_id

    def object_file(self, record_id: str) -> Path:
        with self.factory(readonly=True) as uow:
            pointer = body.body_pointer(uow.conn(), record_id)
        assert pointer is not None
        return self.store.path_for(pointer.uri)


@pytest.fixture
def env(
    tmp_path: Path, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Env]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    built = Env(tmp_path, new_db())
    shutil.copytree(TYPES, built.root)
    with use_provider(DirectorySchemaProvider()):
        assert built.run("init").exit_code == 0
        yield built


def test_the_quarantine_group_is_under_types() -> None:
    helped = runner.invoke(app, ["types", "quarantine", "--help"]).stdout
    assert "ls" in helped and "recheck" in helped


def test_ls_says_so_when_nothing_is_quarantined(env: Env) -> None:
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    result = env.run("types", "quarantine", "ls")
    assert result.exit_code == 0 and result.exception is None
    assert result.stdout.splitlines() == ["nothing quarantined"]


def test_ls_lists_a_quarantined_version_with_its_issues(env: Env) -> None:
    package = env.root / "co.acme" / "LiftPlan" / "1.0.0"
    (package / "examples" / "bad.json").write_text("{}")
    write_lock(package)
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    result = env.run("types", "quarantine", "ls")
    assert result.exit_code == 0 and result.exception is None
    lines = result.stdout.splitlines()
    assert lines[0] == f"type {LIFT}@1.0.0 quarantined"
    assert all(line.startswith("  example examples/bad.json: ") for line in lines[1:])
    assert len(lines) >= 2


def test_ls_lists_a_conflict_with_both_hashes(env: Env) -> None:
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    package = env.root / "co.acme" / "LiftPlan" / "1.0.0"
    (package / "README.md").write_text("edited\n")
    write_lock(package)
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    lines = env.run("types", "quarantine", "ls").stdout.splitlines()
    assert lines[0].startswith(f"type {LIFT}@1.0.0 conflict (registered ")
    assert ", files " in lines[0] and lines[0].endswith(")")
    assert lines[1].startswith("  conflict -: ")


def test_ls_lists_a_record_whose_body_failed_verification(env: Env) -> None:
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    record_id = env.make_lift()
    env.object_file(record_id).write_bytes(b"broken")
    with pytest.raises(BodyHashMismatchError):  # read_body quarantines, then raises
        body.read_body(env.factory, env.store, stream_id=record_id)
    assert env.run("types", "quarantine", "ls").stdout.splitlines() == [
        f"body {record_id} {LIFT} hash mismatch"
    ]


def test_recheck_restores_a_body_once_the_object_is_sound(env: Env) -> None:
    registry.sync(env.factory, env.root, actor="user:ops", source="test")
    record_id = env.make_lift()
    path = env.object_file(record_id)
    good = path.read_bytes()
    path.write_bytes(b"broken")
    with pytest.raises(BodyHashMismatchError):
        body.read_body(env.factory, env.store, stream_id=record_id)
    failing = env.run("types", "quarantine", "recheck", record_id)
    assert failing.exit_code == 1 and failing.stdout.splitlines() == [f"still failing {record_id}"]
    path.write_bytes(good)
    fixed = env.run("types", "quarantine", "recheck", record_id)
    assert fixed.exit_code == 0 and fixed.exception is None
    assert fixed.stdout.splitlines() == [f"restored {record_id}"]
    assert env.run("types", "quarantine", "ls").stdout.splitlines() == ["nothing quarantined"]


def test_recheck_of_a_record_without_a_body_is_an_error(env: Env) -> None:
    result = env.run("types", "quarantine", "recheck", "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5")
    assert (
        result.exit_code == 1 and "error: " in result.stderr and "no stored body" in result.stderr
    )


def test_recheck_without_an_object_store_is_an_error(env: Env) -> None:
    env.env["TL_OBJECT_STORE"] = "s3"
    result = env.run("types", "quarantine", "recheck", "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5")
    assert result.exit_code == 1 and "TL_S3_BUCKET" in result.stderr
