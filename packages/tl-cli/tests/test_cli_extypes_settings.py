"""`tl config` knows the settings keys of a registered extension type (P0-I8 B, brief 31.1)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from typer.testing import CliRunner

runner = CliRunner()
TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
KEY = "co.acme.lift_plan.max_load_tonnes"


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, dict[str, str]]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.delenv("TL_SETTINGS_PLATFORM_FILE", raising=False)
    root = tmp_path / "types"
    shutil.copytree(TYPES, root)
    values = {"TL_DB": str(new_db())}
    with use_provider(DirectorySchemaProvider()):
        assert runner.invoke(app, ["init"], env=values).exit_code == 0
        yield root, values


def test_the_keys_of_a_registered_type_can_be_read_and_changed(
    env: tuple[Path, dict[str, str]],
) -> None:
    root, values = env
    before = runner.invoke(app, ["config", "get", KEY], env=values)
    assert before.exit_code == 1  # nothing registered yet
    assert runner.invoke(app, ["types", "sync", str(root)], env=values).exit_code == 0

    got = runner.invoke(app, ["config", "get", KEY], env=values)
    assert got.exit_code == 0, got.output
    assert got.stdout.strip() == "250"
    listed = runner.invoke(app, ["config", "ls"], env=values)
    assert KEY in listed.stdout

    changed = runner.invoke(
        app,
        ["config", "set", KEY, "300", "--company", "--reason", "heavier cranes"],
        env=values,
    )
    assert changed.exit_code == 0, changed.output
    again = runner.invoke(app, ["config", "get", KEY], env=values)
    assert again.stdout.strip() == "300"
