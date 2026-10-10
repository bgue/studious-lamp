"""`tl restore --from-archive DIR --db TARGET` (P0-I7-T04)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.archivestore import FsArchiveStore
from tl_adapters.db import make_engine, read_tx
from tl_adapters.sqlite.engine import make_engine as sqlite_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_cli.main import app
from tl_core.archive import load_public_key, seal_segment, verify_archive, write_keypair
from tl_core.ledger import NewEvent
from typer.testing import CliRunner

runner = CliRunner()


def add_events(db: Path, count: int) -> None:
    engine = sqlite_engine(db)
    try:
        ledger = SqliteLedger(engine)
        ledger.create_schema()
        for n in range(1, count + 1):
            ledger.append(
                stream_id=f"s-{n}",
                stream_type="test.Thing",
                scope=("company", "project:P1")[n % 2],
                expected_version=0,
                events=[NewEvent(event_type="Thing.Created", payload={"n": n, "t": "café"})],
                actor="user:u-1",
                source="test",
                correlation_id=f"c-{n}",
            )
    finally:
        engine.dispose()


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.db = tmp_path / "tl.db"
        self.archive = tmp_path / "archive"
        self.key = tmp_path / "keys" / "archive-signing.key"
        self.env = {"TL_DB": str(self.db), "TL_ENV": "dev"}
        add_events(self.db, 10)
        signer = write_keypair(self.key)
        store = FsArchiveStore(self.archive)
        engine = sqlite_engine(self.db)
        try:
            while True:
                with read_tx(engine) as conn:
                    if seal_segment(conn, store, signer, max_events=4) is None:
                        break
        finally:
            engine.dispose()

    @property
    def pub(self) -> Path:
        return self.key.with_suffix(".pub")

    def run(self, *args: str):  # noqa: ANN201
        return runner.invoke(app, list(args), env=self.env)

    def restore(self, target: str):  # noqa: ANN201
        return self.run(
            "restore",
            "--from-archive",
            str(self.archive),
            "--db",
            target,
            "--public-key",
            str(self.pub),
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def event_rows(db: Path) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
    finally:
        conn.close()


def test_restore_into_a_new_sqlite_file_reproduces_every_event(
    world: World, tmp_path: Path
) -> None:
    target = tmp_path / "new" / "restored.db"  # the parent directory does not exist yet
    result = world.restore(str(target))
    assert result.exit_code == 0, result.output
    assert result.exception is None
    first, second = result.stdout.splitlines()
    assert first == f"restored 10 events from 3 segments into {target} (last seq 10)"
    assert re.fullmatch(
        r"verify \d+\.\d\ds, insert \d+\.\d\ds, rebuild \d+\.\d\ds, total \d+\.\d\ds", second
    )
    assert event_rows(target) == event_rows(world.db)  # every column, verbatim


def test_a_restored_database_verifies_against_the_archive(world: World, tmp_path: Path) -> None:
    target = tmp_path / "restored.db"
    assert world.restore(str(target)).exit_code == 0
    engine = sqlite_engine(target)
    try:
        with read_tx(engine) as conn:
            issues = verify_archive(
                FsArchiveStore(world.archive), public_key=load_public_key(world.pub), conn=conn
            )
    finally:
        engine.dispose()
    assert issues == []


def test_restore_refuses_a_database_that_has_events_and_changes_nothing(
    world: World,
) -> None:
    before = event_rows(world.db)
    result = world.restore(str(world.db))
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error:" in result.stderr and "not empty" in result.stderr
    assert result.stdout == ""
    assert event_rows(world.db) == before


def test_restore_from_a_tampered_archive_prints_the_divergence_and_creates_no_database(
    world: World, tmp_path: Path
) -> None:
    ndjson = world.archive / "segments" / "000000000005-000000000008" / "events.ndjson"
    ndjson.chmod(0o644)
    ndjson.write_bytes(ndjson.read_bytes().replace(b'"n":6', b'"n":9', 1))
    target = tmp_path / "restored.db"
    result = world.restore(str(target))
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.stdout.splitlines() == [
        "divergence: file_hash segment=000000000005-000000000008 seq=5: "
        "events.ndjson differs from its hash"
    ]
    assert "error: the archive does not verify" in result.stderr
    assert not target.exists()


def test_restore_needs_an_archive_and_a_readable_public_key(world: World, tmp_path: Path) -> None:
    target = str(tmp_path / "r.db")
    missing = world.run(
        "restore",
        "--from-archive",
        str(tmp_path / "nope"),
        "--db",
        target,
        "--public-key",
        str(world.pub),
    )
    assert missing.exit_code == 1 and "error: no archive at" in missing.stderr
    no_key = world.run(
        "restore",
        "--from-archive",
        str(world.archive),
        "--db",
        target,
        "--public-key",
        str(tmp_path / "absent.pub"),
    )
    assert no_key.exit_code == 1 and "error: cannot read the public key" in no_key.stderr
    assert not Path(target).exists()


def test_both_options_are_required(world: World) -> None:
    assert world.run("restore", "--db", "x.db").exit_code == 2
    assert world.run("restore", "--from-archive", str(world.archive)).exit_code == 2


@pytest.mark.requires_postgres
def test_restore_into_an_empty_postgres_schema_hides_the_password(world: World, pg_db: str) -> None:
    result = world.restore(pg_db)
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert result.stdout.splitlines()[0].startswith("restored 10 events from 3 segments into ")
    assert "postgres:postgres@" not in result.output and "postgres:***@" in result.output
    engine = make_engine(pg_db)
    try:
        with read_tx(engine) as conn:
            hashes = [r[0] for r in conn.execute(text("SELECT hash FROM events ORDER BY seq"))]
    finally:
        engine.dispose()
    assert hashes == [row[16] for row in event_rows(world.db)]


def test_schema_warnings_go_to_stderr_after_the_two_summary_lines(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tl_cli.restore as restore_module
    from tl_adapters.restore import RestoreResult

    def fake(*args: object, **kwargs: object) -> RestoreResult:
        return RestoreResult(
            events=1,
            segments=1,
            last_seq=1,
            verify_seconds=0.0,
            insert_seconds=0.0,
            rebuild_seconds=0.0,
            total_seconds=0.0,
            warnings=("scope project:P1: schemas differ", "scope company: schemas differ"),
        )

    monkeypatch.setattr(restore_module, "restore_from_archive", fake)
    result = world.restore(str(tmp_path / "w.db"))
    assert result.exit_code == 0, result.output
    assert len(result.stdout.splitlines()) == 2
    assert result.stderr.splitlines() == [
        "warning: scope project:P1: schemas differ",
        "warning: scope company: schemas differ",
    ]
