"""dev/release/starter.sh on the core section of P200 in tmp_path (P2-REL-T04).

Runs the real demo-project recipe into a temporary ledger (local SQLite, no network) and checks the
archive's members, START.txt and SHA256SUMS line.
"""

from __future__ import annotations

import hashlib
import subprocess
import tarfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "release" / "starter.sh"
DEMO_PASSWORD = "p200-demo-pass"
DEMO_ACCOUNT = "mokafor"
TRY_IT_SECRET = "throughline-try-it-p200-not-a-secret"


def _version() -> str:
    data = tomllib.loads((REPO / "packages" / "tl-cli" / "pyproject.toml").read_text("utf-8"))
    return str(data["project"]["version"])


def test_starter_bundle_members_and_start_txt(tmp_path: Path) -> None:
    version = _version()
    result = subprocess.run(
        ["bash", str(SCRIPT), "--sections", "core", "--out", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]

    name = f"starter-p200-{version}.tar.gz"
    tarball = tmp_path / name
    assert tarball.is_file()

    with tarfile.open(tarball, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        # Exactly the three items: the ledger, the schema directory and START.txt. Nothing else.
        assert "ledger/p200.db" in names
        assert "START.txt" in names
        assert "schema" in names
        allowed = {"ledger/p200.db", "START.txt", "schema"}
        for member in members:
            inside_schema = member.name.startswith("schema/")
            assert member.name in allowed or inside_schema, f"unexpected member {member.name}"
            assert not member.issym() and not member.islnk(), f"link member {member.name}"
        start = archive.extractfile("START.txt")
        assert start is not None
        text = start.read().decode("utf-8")

    # The demo account and its password are there; the only secret is the documented try-it value.
    assert DEMO_ACCOUNT in text
    assert DEMO_PASSWORD in text
    assert text.count(DEMO_PASSWORD) == 1
    assert f"TL_OBJECT_SECRET={TRY_IT_SECRET}" in text
    lowered = text.lower()
    for word in ("token", "hash", "argon", "session"):
        assert word not in lowered, f"START.txt mentions {word}"
    assert len(text.splitlines()) <= 25

    # SHA256SUMS carries the archive's own digest.
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    sums = (tmp_path / "SHA256SUMS").read_text("utf-8").splitlines()
    assert [line for line in sums if line.endswith(f"  {name}")] == [f"{digest}  {name}"]
