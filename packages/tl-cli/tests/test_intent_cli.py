"""The intent options of `tl record create|void` and `tl link add|retract` (P2-INT-T02; ADR-0025).

The events carry the intent with ids, not keys."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_cli.main import app
from tl_core import confidentiality
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
P = ("--project", "P123")


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(new_db())}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def create(env: dict[str, str], title: str, *extra: str) -> tuple[str, str]:
    """Create a record; returns (stream id, key)."""
    result = run(env, "record", "create", *P, "--title", title, *extra)
    assert result.exit_code == 0, result.output
    stream = result.stdout.splitlines()[0].split()[1]
    key = next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))
    return stream, key


def events_with_intent(env: dict[str, str]) -> list[tuple[str, str | None]]:
    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        rows = uow.conn().execute(
            text("SELECT stream_id, intent FROM events WHERE intent IS NOT NULL")
        )
        return [(row.stream_id, row.intent) for row in rows]


def event_count(env: dict[str, str]) -> int:
    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


def intent_of(env: dict[str, str], stream: str) -> str | None:
    """The intent column of the latest event on the stream."""
    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text(
                    "SELECT intent FROM events WHERE stream_id = :s "
                    "ORDER BY stream_version DESC LIMIT 1"
                ),
                {"s": stream},
            )
            .first()
        )
    assert row is not None
    return row.intent


def test_record_create_with_why_and_toward_stores_ids_not_keys(env: dict[str, str]) -> None:
    target_stream, target_key = create(env, "Gate")
    stream, _ = create(env, "Pump", "--why", "x", "--toward", f"{target_key}:~released")
    stored = intent_of(env, stream)
    assert stored is not None
    assert json.loads(stored) == {
        "why": "x",
        "toward": {"target": target_stream, "condition": "released"},
    }
    assert target_key not in stored


def test_without_options_the_intent_column_is_null(env: dict[str, str]) -> None:
    stream, _ = create(env, "Plain")
    assert intent_of(env, stream) is None
    assert events_with_intent(env) == []


def test_an_unknown_key_and_an_unreadable_key_print_the_same_error(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, hidden_key = create(env, "Restricted")
    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        hidden_id = str(
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": hidden_key})
            .scalar_one()
        )
    original = confidentiality.is_hidden
    monkeypatch.setattr(
        confidentiality,
        "is_hidden",
        lambda conn, record_id, viewer=None: (
            record_id == hidden_id or original(conn, record_id, viewer)
        ),
    )
    before = event_count(env)
    unknown = run(env, "record", "create", *P, "--title", "A", "--toward", "NOPE-9:~x")
    unreadable = run(env, "record", "create", *P, "--title", "B", "--toward", f"{hidden_key}:~x")
    assert unknown.exit_code == 1 and unreadable.exit_code == 1
    assert unknown.stderr == unreadable.stderr == "error: intent reference not found\n"
    assert event_count(env) == before


def test_link_add_why_is_carried_on_the_link_event(env: dict[str, str]) -> None:
    _, a = create(env, "NCR")
    _, b = create(env, "Support")
    result = run(env, "link", "add", *P, a, b, "--why", "found on site")
    assert result.exit_code == 0, result.output
    link_id = result.stdout.splitlines()[0].split()[1]
    assert json.loads(intent_of(env, link_id) or "null") == {"why": "found on site"}


def test_a_too_long_why_is_refused_before_any_event(env: dict[str, str]) -> None:
    before = event_count(env)
    result = run(env, "record", "create", *P, "--title", "Long", "--why", "x" * 501)
    assert result.exit_code == 1
    assert result.stderr == "error: intent why is longer than 500 characters\n"
    assert event_count(env) == before


def test_retract_takes_the_options(env: dict[str, str]) -> None:
    _, a = create(env, "NCR")
    _, b = create(env, "Support")
    link_id = run(env, "link", "add", *P, a, b).stdout.splitlines()[0].split()[1]
    result = run(env, "link", "retract", *P, link_id, "--reason", "wrong pair", "--why", "clean up")
    assert result.exit_code == 0, result.output
    assert json.loads(intent_of(env, link_id) or "null") == {"why": "clean up"}


def test_a_malformed_next_is_an_error_with_nothing_appended(env: dict[str, str]) -> None:
    before = event_count(env)
    result = run(env, "record", "create", *P, "--title", "N", "--next", "nocolon")
    assert result.exit_code == 1
    assert result.stderr == ("error: --next 'nocolon': expected command:target or text:<words>\n")
    assert event_count(env) == before


def test_next_and_goal_ref_are_stored(env: dict[str, str]) -> None:
    stream, _ = create(env, "Steps", "--next", "text:call the foreman", "--goal-ref", "g-1")
    assert json.loads(intent_of(env, stream) or "null") == {
        "next": [{"text": "call the foreman"}],
        "goal_ref": "g-1",
    }


@pytest.mark.parametrize("name", ["record", "link"])
def test_help_names_the_intent_options(env: dict[str, str], name: str) -> None:
    args = ["record", "create", "--help"] if name == "record" else ["link", "add", "--help"]
    result = run(env, *args)
    for flag in ("--why", "--next", "--toward", "--goal-ref"):
        assert flag in result.output
    assert "read by nobody to decide anything" in result.output


@pytest.mark.parametrize("bad", ["WP-1", "WP-1:~"])
def test_a_malformed_toward_is_a_usage_error(env: dict[str, str], bad: str) -> None:
    result = run(env, "record", "create", *P, "--title", "T", "--toward", bad)
    assert result.exit_code == 1
    assert "expected target:state or target:~condition" in result.stderr
