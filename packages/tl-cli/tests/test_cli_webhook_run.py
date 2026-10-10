"""`tl webhook run --once` and the empty cell of `tl webhook dlq ls` (P0-I5)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_cli.main import app
from tl_core.webhooks.receiver import DevReceiver
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def ok(result: RunResult) -> RunResult:
    assert result.exit_code == 0, result.output
    assert result.exception is None
    return result


def fields(result: RunResult) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, value = line.partition(" ")
        found[name] = value
    return found


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    env = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "dev", "TL_WEBHOOK_ALLOWLIST": ""}
    ok(run(env, "init"))
    return env


@pytest.fixture
def receiver() -> Iterator[DevReceiver]:
    with DevReceiver() as running:
        yield running


def test_run_once_dispatches_delivers_and_prints_a_summary(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    added = fields(
        ok(
            run(
                env, "webhook", "add", "--project", "P1", "--name", "n", "--url", receiver.url,
                "--event-type", "Record.*",
            )
        )
    )  # fmt: skip
    receiver.set_secrets([added["secret"]])
    for key in ("R-1", "R-2"):
        ok(run(env, "record", "create", "--project", "P1", "--key", key, "--title", key))
    summary = fields(ok(run(env, "webhook", "run", "--once", "--allow-host", "127.0.0.1")))
    assert summary == {
        "dispatched": "2", "claimed": "2", "delivered": "2",
        "retried": "0", "dead": "0", "disabled": "0",
    }  # fmt: skip
    assert len(receiver.unique()) == 2
    again = fields(ok(run(env, "webhook", "run", "--once", "--allow-host", "127.0.0.1")))
    assert again["claimed"] == "0" and len(receiver.messages()) == 2


def test_run_once_without_an_allow_list_dead_letters_a_loopback_target(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    ok(run(env, "webhook", "add", "--project", "P1", "--name", "n", "--url", receiver.url))
    ok(run(env, "record", "create", "--project", "P1", "--key", "R-1", "--title", "r"))
    summary = fields(ok(run(env, "webhook", "run", "--once")))
    assert (summary["delivered"], summary["dead"]) == ("0", "1")
    assert receiver.messages() == [] and receiver.rejected() == []
    row = ok(run(env, "webhook", "dlq", "ls")).stdout.rstrip("\n").split("\t")
    assert row[5] == "" and row[6] == "egress_denied"  # no HTTP status: an empty cell, not "None"
    with sqlite3.connect(env["TL_DB"]) as conn:
        assert conn.execute("SELECT status FROM wh_delivery").fetchall() == [("dead",)]
