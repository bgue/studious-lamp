"""`tl webhook add|ls|test|replay` on a temporary ledger and a local receiver (P0-I5-T25)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_cli.main import app
from tl_core.webhooks.dispatch import Dispatcher
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


def refused(result: RunResult, text: str) -> None:
    assert result.exit_code == 1, result.output
    assert not isinstance(result.exception, (NotImplementedError, AttributeError, TypeError))
    assert "error:" in result.stderr and text in result.stderr


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


def add(env: dict[str, str], *extra: str, url: str = "https://hook.example.net/in") -> RunResult:
    return run(env, "webhook", "add", "--project", "P123", "--name", "NDE", "--url", url, *extra)


def sql(env: dict[str, str], query: str) -> list[tuple[object, ...]]:
    with sqlite3.connect(env["TL_DB"]) as conn:
        return conn.execute(query).fetchall()


def test_add_prints_the_id_and_the_secret_and_stores_the_filter(env: dict[str, str]) -> None:
    result = ok(
        add(
            env,
            "--mode",
            "delta",
            "--event-type",
            "Workflow.Transitioned",
            "--event-type",
            "Record.*",
            "--transition",
            "* -> Issued",
            "--selector",
            "status:open",
            "--hashtag",
            "safety",
            "--changed-field",
            "status",
            "--link-relation",
            "raised_against",
            "--file-slot",
            "mtr",
            "--record-id",
            "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
            "--scope-selector",
            "project:*",
        )
    )
    printed = fields(result)
    assert len(printed["subscription"]) == 26
    assert len(printed["secret_id"]) == 26
    assert printed["secret"].startswith("whsec_")
    assert "not shown again" in result.stderr
    ((mode, status, filter_json),) = sql(
        env, "SELECT payload_mode, status, filter_json FROM cur_webhook_subscription"
    )
    assert (mode, status) == ("delta", "active")
    assert json.loads(str(filter_json)) == {
        "changed_fields": ["status"],
        "event_types": ["Workflow.Transitioned", "Record.*"],
        "file_slots": ["mtr"],
        "hashtags": ["safety"],
        "link_relations": ["raised_against"],
        "record_ids": ["01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"],
        "record_selector": "status:open",
        "scope_selector": "project:*",
        "transitions": ["* -> Issued"],
    }
    assert sql(env, "SELECT secret FROM wh_secret") == [(printed["secret"],)]


def test_the_secret_is_not_in_the_ledger_and_is_never_listed_again(env: dict[str, str]) -> None:
    secret = fields(ok(add(env)))["secret"]
    assert secret not in json.dumps(sql(env, "SELECT payload FROM events"))
    listing = ok(run(env, "webhook", "ls")).stdout
    assert secret not in listing and "whsec_" not in listing


def test_add_refuses_bad_input_without_writing_anything(env: dict[str, str]) -> None:
    refused(add(env, "--mode", "huge"), "payload_mode")
    refused(add(env, url="ftp://x.example.net/"), "target_url")
    refused(add(env, "--selector", "status:"), "record_selector")
    refused(add(env, "--transition", "InReview"), "transition")
    refused(add(env, "--expires", "tomorrow"), "")
    refused(
        run(env, "webhook", "add", "--name", "n", "--url", "https://h.example.net/"), "exactly one"
    )
    refused(
        run(
            env, "webhook", "add", "--project", "P1", "--company", "--name", "n",
            "--url", "https://h.example.net/",
        ),
        "exactly one",
    )  # fmt: skip
    assert sql(env, "SELECT * FROM events") == []


def test_ls_lists_one_line_per_subscription_and_filters_by_scope(env: dict[str, str]) -> None:
    first = fields(ok(add(env, "--mode", "full")))["subscription"]
    company = fields(
        ok(
            run(
                env, "webhook", "add", "--company", "--name", "ALL",
                "--url", "https://all.example.net/in",
            )
        )
    )["subscription"]  # fmt: skip
    lines = [line.split("\t") for line in ok(run(env, "webhook", "ls")).stdout.splitlines()]
    assert lines == [
        [first, "active", "full", "NDE", "https://hook.example.net/in", "0", "0", "0"],
        [company, "active", "thin", "ALL", "https://all.example.net/in", "0", "0", "0"],
    ]
    only = ok(run(env, "webhook", "ls", "--project", "P123")).stdout.splitlines()
    assert [line.split("\t")[0] for line in only] == [first]
    assert ok(run(env, "webhook", "ls", "--company")).stdout.startswith(company)
    assert ok(run(env, "webhook", "ls", "--project", "P999")).stdout == ""


@pytest.fixture
def receiver() -> Iterator[DevReceiver]:
    with DevReceiver() as running:
        yield running


def subscribe_to(env: dict[str, str], receiver: DevReceiver) -> tuple[str, str]:
    printed = fields(ok(add(env, url=receiver.url)))
    receiver.set_secrets([printed["secret"]])
    return printed["subscription"], printed["secret"]


def test_test_sends_a_signed_catalog_sample_to_an_allow_listed_receiver(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    sid, _ = subscribe_to(env, receiver)
    result = ok(run(env, "webhook", "test", sid, "--allow-host", "127.0.0.1"))
    printed = fields(result)
    assert printed["status"] == "200"
    assert receiver.wait_for(1, timeout_s=5)
    (message,) = receiver.messages()
    assert message.verified and message.webhook_id == printed["event_id"]
    assert message.event()["type"] == "tl.core.Record.Created.v1"
    ok(
        run(
            env,
            "webhook",
            "test",
            sid,
            "--allow-host",
            "127.0.0.1",
            "--event-type",
            "File.Uploaded",
        )
    )
    assert receiver.messages()[-1].event()["type"] == "tl.core.File.Uploaded.v1"
    assert sql(env, "SELECT * FROM wh_delivery") == []  # a test queues nothing


def test_the_allow_list_can_come_from_the_environment(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    sid, _ = subscribe_to(env, receiver)
    ok(run({**env, "TL_WEBHOOK_ALLOWLIST": "127.0.0.1"}, "webhook", "test", sid))
    assert len(receiver.messages()) == 1


def test_test_is_refused_for_a_target_that_is_not_allow_listed(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    sid, _ = subscribe_to(env, receiver)
    refused(run(env, "webhook", "test", sid), "egress policy")
    assert receiver.messages() == [] and receiver.rejected() == []


def test_test_reports_what_the_receiver_answered(
    env: dict[str, str], receiver: DevReceiver
) -> None:
    sid, _ = subscribe_to(env, receiver)
    receiver.fail_next([503])
    result = run(env, "webhook", "test", sid, "--allow-host", "127.0.0.1")
    refused(result, "503")
    assert fields(result)["status"] == "503"
    refused(
        run(env, "webhook", "test", "01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ", "--allow-host", "x"), "no webhook"
    )
    refused(run(env, "webhook", "test", sid, "--event-type", "Nope.Nothing"), "Nope.Nothing")


def seed_events(env: dict[str, str]) -> None:
    for key in ("R-1", "R-2", "R-3"):
        ok(run(env, "record", "create", "--project", "P123", "--key", key, "--title", key))


def test_replay_resends_a_seq_range_and_a_time_range(env: dict[str, str]) -> None:
    sid = fields(ok(add(env, "--event-type", "Record.*")))["subscription"]
    seed_events(env)
    factory = SqliteUowFactory(Path(env["TL_DB"]))
    try:
        Dispatcher(factory).run_until_idle()
    finally:
        factory.dispose()
    seqs = [row[0] for row in sql(env, "SELECT seq FROM wh_delivery ORDER BY seq")]
    assert len(seqs) == 3
    result = ok(
        run(env, "webhook", "replay", sid, "--from-seq", str(seqs[1]), "--to-seq", str(seqs[2]))
    )
    assert result.stdout.splitlines() == ["replayed 2"]
    assert sql(env, "SELECT COUNT(*) FROM wh_delivery WHERE origin = 'replay'") == [(2,)]
    now = datetime.now(UTC)
    window = (
        "--since",
        (now - timedelta(hours=1)).isoformat(),
        "--until",
        (now + timedelta(hours=1)).isoformat(),
    )
    assert ok(run(env, "webhook", "replay", sid, *window)).stdout.splitlines() == ["replayed 3"]
    naive = (now + timedelta(days=1)).replace(tzinfo=None).isoformat()
    assert ok(
        run(env, "webhook", "replay", sid, "--since", naive, "--until", naive)
    ).stdout.splitlines() == ["replayed 0"]  # a time without an offset is UTC


def test_replay_refuses_a_missing_or_mixed_range_and_an_unknown_subscription(
    env: dict[str, str],
) -> None:
    sid = fields(ok(add(env)))["subscription"]
    for args in (
        (),
        ("--from-seq", "1"),
        ("--since", "2026-01-01T00:00:00"),
        ("--from-seq", "1", "--to-seq", "2", "--since", "2026-01-01", "--until", "2026-01-02"),
        ("--from-seq", "1", "--until", "2026-01-02"),
    ):
        refused(run(env, "webhook", "replay", sid, *args), "give --from-seq")
    refused(run(env, "webhook", "replay", sid, "--from-seq", "5", "--to-seq", "1"), "from_seq")
    refused(
        run(
            env,
            "webhook",
            "replay",
            "01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ",
            "--from-seq",
            "1",
            "--to-seq",
            "2",
        ),
        "no webhook",
    )
    refused(run(env, "webhook", "replay", sid, "--since", "soon", "--until", "later"), "")
