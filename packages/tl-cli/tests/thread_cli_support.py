"""Helpers of the `tl thread` tests: a ledger with threads on, records, and a command runner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_cli.main import app
from tl_core import settings
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
P = "P123"


def thread_env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    """A fresh ledger (``tl init``) with threads on for ``core.Record``."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(new_db())}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    with open_uow(values["TL_DB"]) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def create(env: dict[str, str], title: str) -> str:
    """A ``core.Record`` numbered by the fixture schema; returns its key."""
    result = run(env, "record", "create", "--project", P, "--title", title)
    assert result.exit_code == 0, result.output
    return next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))
