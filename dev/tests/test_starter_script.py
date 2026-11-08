"""dev/release/starter.sh on the core and documents sections of P200 in tmp_path (P2-REL-T04).

Runs the real demo-project recipe into a temporary ledger and object store (local SQLite and the fs
store, no network). Checks the archive's listing, that every document blob the ledger references is
in the bundle, START.txt and the SHA256SUMS line.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import tarfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "release" / "starter.sh"
DEMO_PASSWORD = "p200-demo-pass"
DEMO_ACCOUNT = "mokafor"
TRY_IT_SECRET = "throughline-try-it-p200-not-a-secret"
DB_MEMBER = "ledger/p200.db"
FILES_MEMBER = "ledger/files"


def _version() -> str:
    data = tomllib.loads((REPO / "packages" / "tl-cli" / "pyproject.toml").read_text("utf-8"))
    return str(data["project"]["version"])


def _blob_members(db: Path) -> set[str]:
    """Archive member names of the blobs the ledger's attachments point at (status available)."""
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT DISTINCT sha256 FROM cur_files WHERE status = 'available'"
        ).fetchall()
    members: set[str] = set()
    for (digest,) in rows:
        hex_digest = str(digest).lower()
        members.add(f"{FILES_MEMBER}/sha256/{hex_digest[:2]}/{hex_digest[2:4]}/{hex_digest}")
    return members


def test_starter_bundle_members_and_start_txt(tmp_path: Path) -> None:
    version = _version()
    result = subprocess.run(
        ["bash", str(SCRIPT), "--sections", "core,documents", "--out", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]

    name = f"starter-p200-{version}.tar.gz"
    tarball = tmp_path / name
    assert tarball.is_file()

    with tarfile.open(tarball, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        # Top level: the ledger (with its object store), the schema directory and START.txt only.
        assert {member_name.split("/")[0] for member_name in names} == {
            "ledger",
            "schema",
            "START.txt",
        }
        assert DB_MEMBER in names
        assert FILES_MEMBER in names
        assert "schema" in names
        assert "START.txt" in names
        allowed = {DB_MEMBER, FILES_MEMBER, "schema", "START.txt"}
        for member in members:
            inside_schema = member.name.startswith("schema/")
            inside_files = member.name.startswith(f"{FILES_MEMBER}/")
            assert member.name in allowed or inside_schema or inside_files, (
                f"unexpected member {member.name}"
            )
            assert not member.issym() and not member.islnk(), f"link member {member.name}"
        start = archive.extractfile("START.txt")
        assert start is not None
        text = start.read().decode("utf-8")
        archive.extract(DB_MEMBER, path=tmp_path / "extract", filter="data")

    # Every blob the ledger's documents point at is in the bundle.
    blobs = _blob_members(tmp_path / "extract" / DB_MEMBER)
    assert blobs, "the documents section left no attachment with bytes in the ledger"
    missing = sorted(blobs - set(names))
    assert not missing, (
        f"{len(missing)} referenced blobs are missing from the bundle, e.g. {missing[:3]}"
    )

    # The demo account and its password are there; the only secret is the documented try-it value.
    assert DEMO_ACCOUNT in text
    assert DEMO_PASSWORD in text
    assert text.count(DEMO_PASSWORD) == 1
    assert f"TL_OBJECT_SECRET={TRY_IT_SECRET}" in text
    assert "TL_PROJECT=P200" in text
    lowered = text.lower()
    for word in ("token", "hash", "argon", "session"):
        assert word not in lowered, f"START.txt mentions {word}"
    assert len(text.splitlines()) <= 25

    # SHA256SUMS carries the archive's own digest.
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    sums = (tmp_path / "SHA256SUMS").read_text("utf-8").splitlines()
    assert [line for line in sums if line.endswith(f"  {name}")] == [f"{digest}  {name}"]
