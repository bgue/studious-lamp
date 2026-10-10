"""`tl archive keygen|seal|verify` (P0-I7-T03)."""

from __future__ import annotations

import hashlib
import re
import stat
from pathlib import Path

import pytest
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_cli.main import app
from tl_core.ledger import NewEvent
from typer.testing import CliRunner

runner = CliRunner()
SEG1 = "000000000001-000000000004"
SEG2 = "000000000005-000000000008"
SEG3 = "000000000009-000000000010"


def add_events(db: Path, start: int, count: int) -> None:
    engine = make_engine(db)
    try:
        ledger = SqliteLedger(engine)
        ledger.create_schema()
        for n in range(start, start + count):
            ledger.append(
                stream_id=f"s-{n}",
                stream_type="test.Thing",
                scope=("company", "project:P1")[n % 2],
                expected_version=0,
                events=[NewEvent(event_type="Thing.Created", payload={"n": n})],
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

    @property
    def pub(self) -> Path:
        return self.key.with_suffix(".pub")

    def run(self, *args: str, extra_env: dict[str, str] | None = None):  # noqa: ANN201
        return runner.invoke(app, list(args), env={**self.env, **(extra_env or {})})

    def manifest_sha(self, segment: str) -> str:
        data = (self.archive / "segments" / segment / "manifest.json").read_bytes()
        return hashlib.sha256(data).hexdigest()

    def seal(self, *more: str):  # noqa: ANN201
        return self.run(
            "archive", "seal", "--archive", str(self.archive), "--key", str(self.key), *more
        )

    def verify(self, *more: str):  # noqa: ANN201
        return self.run(
            "archive",
            "verify",
            "--archive",
            str(self.archive),
            "--public-key",
            str(self.pub),
            *more,
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


@pytest.fixture
def sealed(world: World) -> World:
    add_events(world.db, 1, 10)
    assert world.run("archive", "keygen", "--key", str(world.key)).exit_code == 0
    result = world.seal("--max-events", "4")
    assert result.exit_code == 0, result.output
    return world


def tamper(path: Path, old: bytes, new: bytes) -> None:
    path.chmod(0o644)  # archive files are read-only
    path.write_bytes(path.read_bytes().replace(old, new, 1))


def test_keygen_writes_a_private_key_and_a_public_key_and_refuses_to_replace(
    world: World,
) -> None:
    result = world.run("archive", "keygen", "--key", str(world.key))
    assert result.exit_code == 0, result.output
    assert result.exception is None
    first, second = result.stdout.splitlines()
    match = re.fullmatch(
        rf"wrote private key {re.escape(str(world.key))} \(key id ([0-9a-f]{{16}})\)", first
    )
    assert match, first
    assert second == f"wrote public key {world.pub}"
    assert stat.S_IMODE(world.key.stat().st_mode) == 0o600
    assert len(world.pub.read_text().strip()) == 64

    again = world.run("archive", "keygen", "--key", str(world.key))
    assert again.exit_code == 1
    assert isinstance(again.exception, SystemExit)
    assert "error:" in again.stderr and "refusing to replace" in again.stderr
    assert again.stdout == ""

    forced = world.run("archive", "keygen", "--key", str(world.key), "--force")
    assert forced.exit_code == 0, forced.output
    assert match.group(1) not in forced.stdout  # a new key has a new id


def test_seal_writes_segments_then_reports_nothing_new_then_continues(sealed: World) -> None:
    assert sorted(p.name for p in (sealed.archive / "segments").iterdir()) == [SEG1, SEG2, SEG3]
    again = sealed.seal("--max-events", "4")
    assert again.exit_code == 0, again.output
    assert again.stdout.splitlines() == [
        "nothing new to seal; archive is at seq 10",
        f"record outside the archive: last_seq 10 manifest_sha256 {sealed.manifest_sha(SEG3)}",
    ]

    add_events(sealed.db, 11, 3)
    more = sealed.seal("--max-events", "4")
    assert more.exit_code == 0 and more.exception is None
    assert more.stdout.splitlines() == [
        "sealed segment 000000000011-000000000013 (3 events, seq 11..13)",
        "sealed 1 segments; archive is at seq 13",
        "record outside the archive: last_seq 13 manifest_sha256 "
        + sealed.manifest_sha("000000000011-000000000013"),
    ]


def test_the_first_seal_prints_one_line_per_segment_and_a_summary(world: World) -> None:
    add_events(world.db, 1, 10)
    world.run("archive", "keygen", "--key", str(world.key))
    result = world.seal("--max-events", "4")
    assert result.exit_code == 0 and result.exception is None
    assert result.stdout.splitlines() == [
        f"sealed segment {SEG1} (4 events, seq 1..4)",
        f"sealed segment {SEG2} (4 events, seq 5..8)",
        f"sealed segment {SEG3} (2 events, seq 9..10)",
        "sealed 3 segments; archive is at seq 10",
        f"record outside the archive: last_seq 10 manifest_sha256 {world.manifest_sha(SEG3)}",
    ]


def test_seal_without_a_key_or_a_ledger_exits_1(world: World) -> None:
    add_events(world.db, 1, 2)
    no_key = world.seal()
    assert no_key.exit_code == 1 and isinstance(no_key.exception, SystemExit)
    assert f"error: no signing key at {world.key}" in no_key.stderr
    assert not world.archive.exists()

    world.run("archive", "keygen", "--key", str(world.key))
    world.db.unlink()
    no_db = world.seal()
    assert no_db.exit_code == 1 and isinstance(no_db.exception, SystemExit)
    assert f"error: no ledger at {world.db}" in no_db.stderr
    assert not world.db.exists()


def test_the_archive_directory_can_come_from_the_environment(world: World) -> None:
    add_events(world.db, 1, 3)
    world.run("archive", "keygen", "--key", str(world.key))
    result = world.run(
        "archive",
        "seal",
        "--key",
        str(world.key),
        extra_env={"TL_ARCHIVE_DIR": str(world.archive)},
    )
    assert result.exit_code == 0, result.output
    assert (world.archive / "segments").is_dir()


def test_verify_an_intact_archive(sealed: World) -> None:
    result = sealed.verify()
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert result.stdout.splitlines() == ["verified 3 segments, seq 1..10 (10 events)"]

    deep = sealed.verify("--deep", "--db", str(sealed.db))
    assert deep.exit_code == 0, deep.output
    assert deep.stdout.splitlines() == [
        "verified 3 segments, seq 1..10 (10 events)",
        f"database {sealed.db} agrees up to seq 10",
    ]


def test_verify_an_empty_archive(world: World) -> None:
    world.archive.mkdir()
    world.run("archive", "keygen", "--key", str(world.key))
    result = world.verify()
    assert result.exit_code == 0 and result.exception is None
    assert result.stdout.splitlines() == ["verified 0 segments (the archive is empty)"]


def test_verify_reports_the_first_divergence_and_exits_1(sealed: World) -> None:
    tamper(sealed.archive / "segments" / SEG2 / "events.ndjson", b'"n":6', b'"n":9')
    result = sealed.verify()
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.stdout.splitlines() == [
        f"divergence: file_hash segment={SEG2} seq=5: events.ndjson differs from its hash"
    ]


def test_verify_all_reports_one_divergence_per_broken_segment(sealed: World) -> None:
    tamper(sealed.archive / "segments" / SEG1 / "events.ndjson", b'"n":2', b'"n":9')
    (sealed.archive / "segments" / SEG3 / "events.parquet").unlink()
    first_only = sealed.verify()
    assert len(first_only.stdout.splitlines()) == 1
    both = sealed.verify("--all")
    assert both.exit_code == 1
    lines = both.stdout.splitlines()
    assert [line.split()[1:3] for line in lines] == [
        ["file_hash", f"segment={SEG1}"],
        ["missing_file", f"segment={SEG3}"],
    ]
    assert lines[1].endswith("seq=-: events.parquet is missing")


def test_verify_with_another_key_reports_a_signature_divergence(
    sealed: World, tmp_path: Path
) -> None:
    other = tmp_path / "other" / "k.key"
    assert sealed.run("archive", "keygen", "--key", str(other)).exit_code == 0
    result = sealed.run(
        "archive",
        "verify",
        "--archive",
        str(sealed.archive),
        "--public-key",
        str(other.with_suffix(".pub")),
    )
    assert result.exit_code == 1
    assert result.stdout.startswith(f"divergence: signature segment={SEG1} ")


def test_verify_against_a_database_with_other_history_reports_db_mismatch(
    sealed: World, tmp_path: Path
) -> None:
    other = tmp_path / "other.db"
    add_events(other, 100, 10)
    result = sealed.verify("--db", str(other))
    assert result.exit_code == 1
    assert result.stdout.startswith(f"divergence: db_mismatch segment={SEG1} seq=1: ")


def test_verify_needs_an_archive_and_a_readable_public_key(world: World, sealed: World) -> None:
    missing = world.run("archive", "verify", "--archive", str(world.archive / "nope"))
    assert missing.exit_code == 1 and "error: no archive at" in missing.stderr
    no_key = world.run(
        "archive",
        "verify",
        "--archive",
        str(world.archive),
        "--public-key",
        str(world.archive / "absent.pub"),
    )
    assert no_key.exit_code == 1 and "error: cannot read the public key" in no_key.stderr


def test_verify_catches_dropped_trailing_segments_with_the_recorded_seq_and_manifest(
    sealed: World,
) -> None:
    recorded = sealed.manifest_sha(SEG3)
    ok = sealed.verify("--expect-last-seq", "10", "--expect-manifest", recorded)
    assert ok.exit_code == 0, ok.output
    assert ok.stdout.splitlines() == ["verified 3 segments, seq 1..10 (10 events)"]

    seg3 = sealed.archive / "segments" / SEG3
    for name in ("events.ndjson", "events.parquet", "manifest.json"):
        (seg3 / name).chmod(0o644)
        (seg3 / name).unlink()
    seg3.rmdir()
    assert sealed.verify().exit_code == 0  # nothing inside the archive shows the loss
    short = sealed.verify("--expect-last-seq", "10")
    assert short.exit_code == 1 and isinstance(short.exception, SystemExit)
    assert short.stdout.splitlines() == [
        "divergence: seq_gap segment=- seq=9: the archive ends at seq 8 but the record says it "
        "reached 10: trailing segments are missing"
    ]
    wrong = sealed.verify("--expect-manifest", recorded)
    assert wrong.exit_code == 1
    assert wrong.stdout.startswith(
        "divergence: manifest_chain segment=- seq=-: the recorded manifest "
    )
