"""`tl types sync` reads "conflict" when a registered version's files were edited (T20 ruling)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_cli.main import app
from tl_core.extypes.lock import write_lock
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from typer.testing import CliRunner

runner = CliRunner()
TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan@1.0.0"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, dict[str, str]]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    root = tmp_path / "types"
    shutil.copytree(TYPES, root)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    with use_provider(DirectorySchemaProvider()):
        assert runner.invoke(app, ["init"], env=values).exit_code == 0
        yield root, values


def test_an_edit_to_a_registered_version_reads_as_a_conflict_not_as_registered(
    env: tuple[Path, dict[str, str]],
) -> None:
    root, values = env
    first = runner.invoke(app, ["types", "sync", str(root)], env=values)
    assert first.exit_code == 0 and f"registered {LIFT}" in first.stdout
    package = root / "co.acme" / "LiftPlan" / "1.0.0"
    (package / "README.md").write_text("edited\n")
    write_lock(package)
    result = runner.invoke(app, ["types", "sync", str(root)], env=values)
    assert result.exit_code == 0 and result.exception is None
    lines = result.stdout.splitlines()
    assert lines[0].startswith(f"conflict {LIFT} (kept ") and lines[0].endswith(")")
    assert len(lines[0]) == len(f"conflict {LIFT} (kept ") + 12 + 1
    assert lines[1].startswith("  conflict -: ")
    assert f"registered {LIFT}" not in result.stdout
    again = runner.invoke(app, ["types", "sync", str(root)], env=values)
    assert again.stdout.splitlines() == ["up to date (2 packages)"]


def test_deprecate_tells_the_schema_provider_after_the_commit(
    env: tuple[Path, dict[str, str]],
) -> None:
    from tl_core.extypes import registry

    root, values = env
    assert runner.invoke(app, ["types", "sync", str(root)], env=values).exit_code == 0
    before = registry.changes()
    result = runner.invoke(app, ["types", "deprecate", LIFT, "--reason", "old"], env=values)
    assert result.exit_code == 0 and result.stdout.splitlines() == [f"deprecated {LIFT}"]
    assert registry.changes() == before + 1
    refused = runner.invoke(app, ["types", "deprecate", LIFT, "--reason", "again"], env=values)
    assert refused.exit_code == 1
    assert registry.changes() == before + 1  # a refusal changes nothing
