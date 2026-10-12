"""`tl config ls|get|history|set|reset|lock|revert` on a temporary ledger (P0-I8-T01).

Provided; do not edit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pg_support import account_events
from tl_adapters.db import DbTarget
from tl_cli.config import detail_lines, history_line, view_line
from tl_cli.main import app
from tl_core.settings.registry import get_definition
from tl_core.settings.types import EffectiveSetting, ScheduledChange, SettingChange
from tl_core.settings.views import SettingView
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
DOT = "●"


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.delenv("TL_SETTINGS_PLATFORM_FILE", raising=False)
    values = {"TL_DB": str(new_db())}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, ["config", *args], env=env)


def ok(env: dict[str, str], *args: str) -> str:
    result = run(env, *args)
    assert result.exit_code == 0, (args, result.output)
    assert result.exception is None
    return result.stdout


def refused(env: dict[str, str], *args: str) -> str:
    result = run(env, *args)
    assert result.exit_code == 1, (args, result.output)
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    return result.stderr


def effective(key: str, **kw: object) -> EffectiveSetting:
    base: dict[str, object] = {
        "key": key,
        "value": True,
        "origin": "default",
        "modified_here": False,
        "locked": False,
        "bounds": None,
        "scheduled": [],
        "pending_effect": None,
    }
    return EffectiveSetting.model_validate({**base, **kw})


def view(key: str = "feed.reactions.enabled", **kw: object) -> SettingView:
    return SettingView(definition=get_definition(key), effective=effective(key, **kw))


# --- the pure formatters ------------------------------------------------------------------------


def test_view_line_has_five_columns() -> None:
    assert view_line(view()) == "feed.reactions.enabled  true  bool  default  -"
    got = view(value=False, origin="project", modified_here=True, locked=True)
    assert view_line(got) == f"feed.reactions.enabled  false  bool  project {DOT}  locked"


def test_view_line_shortens_a_long_list() -> None:
    got = view("feed.signal_tags", value=["a", "b", "c", "d", "e"], origin="company")
    assert view_line(got) == "feed.signal_tags  [a, b, c, +2]  list  company  -"


def test_detail_lines_for_a_plain_key() -> None:
    assert detail_lines(view()) == [
        "key feed.reactions.enabled",
        "description Whether people can react to posts in the activity feed.",
        "value true",
        "type bool",
        "origin default",
        "default true",
    ]


def test_detail_lines_show_only_what_applies() -> None:
    got = view(
        "webhooks.retry.max_hours",
        value=48,
        origin="company",
        modified_here=True,
        locked=True,
        bounds={"maximum": 72},
        pending_effect="restart",
        scheduled=[ScheduledChange(applies_at="2030-01-01T00:00:00.000000Z", new_value=12, seq=7)],
    )
    assert detail_lines(got) == [
        "key webhooks.retry.max_hours",
        "description How many hours a webhook delivery is retried before it goes to the "
        "dead-letter queue.",
        "value 48",
        "type decimal",
        "origin company " + DOT,
        "default 24",
        "risk advanced",
        "locked yes",
        'bounds {"maximum": 72}',
        "scheduled 2030-01-01T00:00:00.000000Z 12 (seq 7)",
        "pending restart",
    ]


def change(**kw: object) -> SettingChange:
    base: dict[str, object] = {
        "seq": 3,
        "key": "t.k",
        "layer": "project:P1",
        "old_value": 30,
        "new_value": 40,
        "reset": False,
        "actor": "user:dev",
        "reason": "field pilot",
        "recorded_at": "2026-10-10T09:00:00.000000Z",
        "applies_at": None,
    }
    return SettingChange.model_validate({**base, **kw})


def test_history_line() -> None:
    expected = "3  2026-10-10T09:00:00.000000Z  project:P1  30 -> 40  user:dev  field pilot"
    assert history_line(change()) == expected
    assert history_line(change(reason=None, old_value=None, new_value=True)).endswith(
        "null -> true  user:dev  -"
    )
    assert "30 -> (reset)" in history_line(change(reset=True, new_value=None))
    assert history_line(change(applies_at="2030-01-01T00:00:00.000000Z")).endswith(
        "  applies 2030-01-01T00:00:00.000000Z"
    )


# --- ls and get ---------------------------------------------------------------------------------


def test_ls_lists_every_key_sorted_with_its_origin(env: dict[str, str]) -> None:
    lines = ok(env, "ls").splitlines()
    keys = [line.split("  ")[0] for line in lines]
    assert keys == sorted(keys) and "feed.reactions.enabled" in keys and len(keys) == 10
    assert "feed.reactions.enabled  true  bool  default  -" in lines
    assert "lake.sync.interval  5m  duration  default  -" in lines


def test_ls_prefix_and_the_marker(env: dict[str, str]) -> None:
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    lines = ok(env, "ls", "--project", "P1", "--prefix", "feed.").splitlines()
    assert lines == [
        f"feed.reactions.enabled  false  bool  project {DOT}  -",
        "feed.signal_tags  [safety, hold, decision, +2]  list  default  -",
    ]
    assert ok(env, "ls", "--project", "P1", "--modified").splitlines() == [lines[0]]
    assert ok(env, "ls", "--project", "P2", "--modified") == ""
    plain = ok(env, "ls", "--prefix", "feed.reactions").splitlines()
    assert plain == ["feed.reactions.enabled  true  bool  default  -"]


def test_get_prints_the_effective_value(env: dict[str, str]) -> None:
    assert ok(env, "get", "feed.reactions.enabled") == "true\n"
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    assert ok(env, "get", "feed.reactions.enabled", "--project", "P1") == "false\n"
    assert ok(env, "get", "feed.reactions.enabled", "--project", "P2") == "true\n"
    assert ok(env, "get", "feed.signal_tags") == "[safety, hold, decision, urgent, fyi]\n"
    assert json.loads(ok(env, "get", "feed.signal_tags", "--json")) == [
        "safety",
        "hold",
        "decision",
        "urgent",
        "fyi",
    ]


def test_get_long_prints_the_detail_lines(env: dict[str, str]) -> None:
    ok(env, "set", "feed.reactions.enabled", "false", "--company")
    lines = ok(env, "get", "feed.reactions.enabled", "--long").splitlines()
    assert lines[0] == "key feed.reactions.enabled"
    assert f"origin company {DOT}" in lines and "value false" in lines and "default true" in lines


def test_get_an_unknown_key_is_an_error(env: dict[str, str]) -> None:
    assert "no.such" in refused(env, "get", "no.such")


# --- set and reset ------------------------------------------------------------------------------


def test_set_at_each_layer(env: dict[str, str]) -> None:
    assert ok(env, "set", "feed.reactions.enabled", "false", "--company") == (
        "set feed.reactions.enabled company false\n"
    )
    assert ok(env, "set", "feed.reactions.enabled", "yes", "--project", "P1") == (
        "set feed.reactions.enabled project:P1 true\n"
    )
    assert ok(env, "set", "ui.tui.keymap", "vim", "--user", "alice") == (
        'set ui.tui.keymap user:alice "vim"\n'
    )
    assert ok(env, "get", "ui.tui.keymap", "--user", "alice") == "vim\n"
    assert ok(env, "get", "feed.reactions.enabled", "--project", "P1") == "true\n"
    assert ok(env, "get", "feed.reactions.enabled") == "false\n"


def test_set_the_same_value_again_is_unchanged(env: dict[str, str]) -> None:
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    out = ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    assert out == "unchanged feed.reactions.enabled project:P1\n"


def test_set_reads_a_list_from_commas_or_json(env: dict[str, str]) -> None:
    out = ok(env, "set", "feed.signal_tags", "safety, hold", "--project", "P1")
    assert out == 'set feed.signal_tags project:P1 ["safety", "hold"]\n'
    ok(env, "set", "feed.signal_tags", '["urgent"]', "--company")
    assert ok(env, "get", "feed.signal_tags", "--json") == '["urgent"]\n'


def test_set_needs_exactly_one_layer(env: dict[str, str]) -> None:
    assert "exactly one of --company, --project and --user" in refused(
        env, "set", "feed.reactions.enabled", "false"
    )
    assert "exactly one of" in refused(
        env, "set", "feed.reactions.enabled", "false", "--company", "--project", "P1"
    )


def test_set_refuses_what_the_service_refuses(env: dict[str, str]) -> None:
    assert "is not true or false" in refused(
        env, "set", "feed.reactions.enabled", "maybe", "--company"
    )
    err = refused(env, "set", "lake.sync.interval", "5 minutes", "--company")
    assert "not a duration" in err
    err = refused(env, "set", "webhooks.retry.max_hours", "9999", "--company", "--reason", "x")
    assert "above the maximum" in err
    err = refused(env, "set", "webhooks.retry.max_hours", "48", "--project", "P1", "--reason", "x")
    assert "cannot be set at the project layer" in err
    err = refused(env, "set", "ui.tui.keymap", "vim", "--company")
    assert "cannot be set at the company layer" in err
    assert "there is no setting" in refused(env, "set", "no.such", "1", "--company")
    assert ok(env, "get", "feed.reactions.enabled") == "true\n"


def test_an_advanced_key_needs_a_reason_and_a_dangerous_one_the_risk(env: dict[str, str]) -> None:
    assert "say why" in refused(env, "set", "webhooks.retry.max_hours", "48", "--company")
    out = ok(
        env, "set", "webhooks.retry.max_hours", "48", "--company", "--reason", "partner outage"
    )
    assert out == "set webhooks.retry.max_hours company 48\n"
    err = refused(
        env, "set", "webhooks.egress.allowlist", "hub.example.com", "--company", "--reason", "hub"
    )
    assert "accept the risk" in err
    out = ok(
        env,
        "set",
        "webhooks.egress.allowlist",
        "hub.example.com",
        "--company",
        "--reason",
        "hub",
        "--accept-risk",
    )
    assert out == 'set webhooks.egress.allowlist company ["hub.example.com"]\n'


def test_set_at_a_future_time_is_scheduled(env: dict[str, str]) -> None:
    out = ok(
        env, "set", "feed.reactions.enabled", "false", "--company", "--at", "2099-01-01T00:00:00Z"
    )
    assert out == "scheduled feed.reactions.enabled company false at 2099-01-01T00:00:00.000000Z\n"
    assert ok(env, "get", "feed.reactions.enabled") == "true\n"
    long = ok(env, "get", "feed.reactions.enabled", "--long").splitlines()
    seq = 1 + account_events(env)  # the signed-in test account of a Postgres ledger comes first
    assert f"scheduled 2099-01-01T00:00:00.000000Z false (seq {seq})" in long


def test_set_at_needs_a_time_with_a_zone(env: dict[str, str]) -> None:
    for bad in ("tomorrow", "2099-01-01T00:00:00", "2099-01-01"):
        assert "--at must be an ISO 8601 time" in refused(
            env, "set", "feed.reactions.enabled", "false", "--company", "--at", bad
        )
    assert "not in the future" in refused(
        env, "set", "feed.reactions.enabled", "false", "--company", "--at", "2001-01-01T00:00:00Z"
    )


def test_reset_gives_the_layer_back(env: dict[str, str]) -> None:
    ok(env, "set", "feed.reactions.enabled", "false", "--company")
    ok(env, "set", "feed.reactions.enabled", "true", "--project", "P1")
    assert ok(env, "reset", "feed.reactions.enabled", "--project", "P1") == (
        "reset feed.reactions.enabled project:P1\n"
    )
    assert ok(env, "get", "feed.reactions.enabled", "--project", "P1") == "false\n"
    assert ok(env, "reset", "feed.reactions.enabled", "--project", "P1") == (
        "unchanged feed.reactions.enabled project:P1\n"
    )
    out = ok(env, "reset", "feed.reactions.enabled", "--company", "--at", "2099-01-01T00:00:00Z")
    assert out == "scheduled reset feed.reactions.enabled company at 2099-01-01T00:00:00.000000Z\n"
    assert "exactly one" in refused(env, "reset", "feed.reactions.enabled")


# --- lock ---------------------------------------------------------------------------------------


def test_lock_stops_projects_and_unlock_frees_them(env: dict[str, str]) -> None:
    assert ok(env, "lock", "feed.reactions.enabled", "--reason", "policy") == (
        "locked feed.reactions.enabled\n"
    )
    err = refused(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    assert "locked by the company" in err
    assert "locked yes" in ok(env, "get", "feed.reactions.enabled", "--long").splitlines()
    assert ok(env, "lock", "feed.reactions.enabled", "--reason", "thaw", "--unlock") == (
        "unlocked feed.reactions.enabled\n"
    )
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")


def test_lock_needs_a_reason_and_a_lockable_key(env: dict[str, str]) -> None:
    result = run(env, "lock", "feed.reactions.enabled")
    assert result.exit_code != 0 and "--reason" in result.output
    assert "cannot be locked" in refused(env, "lock", "ai.agents.daily_proposals", "--reason", "x")
    assert "there is no setting" in refused(env, "lock", "no.such", "--reason", "x")


def test_lock_bounds_limit_what_projects_may_set(env: dict[str, str]) -> None:
    out = ok(
        env, "lock", "project.mode", "--unlock", "--choices", "live, sandbox", "--reason", "policy"
    )
    assert out == 'unlocked project.mode bounds {"choices": ["live", "sandbox"]}\n'
    err = refused(env, "set", "project.mode", "simulated", "--project", "P1", "--reason", "r")
    assert "not one of the company's choices" in err
    ok(env, "set", "project.mode", "sandbox", "--project", "P1", "--reason", "r")
    assert "bounds" in ok(env, "get", "project.mode", "--project", "P1", "--long")


def test_lock_min_and_max_are_parsed_for_the_keys_type(env: dict[str, str]) -> None:
    out = ok(env, "lock", "webhooks.retry.max_hours", "--min", "1", "--max", "100", "--reason", "r")
    assert out == 'locked webhooks.retry.max_hours bounds {"maximum": 100, "minimum": 1}\n'
    err = refused(env, "lock", "webhooks.retry.max_hours", "--min", "x1", "--reason", "r")
    assert "is not a number" in err


# --- history and revert -------------------------------------------------------------------------


def test_history_lists_changes_oldest_first(env: dict[str, str]) -> None:
    assert ok(env, "history", "feed.reactions.enabled") == ""
    ok(env, "set", "feed.reactions.enabled", "false", "--company")
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1")
    ok(env, "reset", "feed.reactions.enabled", "--project", "P1")
    lines = ok(env, "history", "feed.reactions.enabled").splitlines()
    assert len(lines) == 3
    pattern = r"^(\d+)  \d{4}-\d\d-\d\dT[\d:.]+Z  (\S+)  (.+) -> (.+)  user:dev  -$"
    parsed = [re.match(pattern, line) for line in lines]
    assert all(parsed), lines
    assert [m.group(2) for m in parsed if m] == ["company", "project:P1", "project:P1"]
    assert [m.group(4) for m in parsed if m] == ["false", "false", "(reset)"]
    only = ok(env, "history", "feed.reactions.enabled", "--layer", "company").splitlines()
    assert only == [lines[0]]
    assert "not a layer" in refused(env, "history", "feed.reactions.enabled", "--layer", "nope")


def test_revert_undoes_a_change(env: dict[str, str]) -> None:
    ok(env, "set", "feed.signal_tags", "a", "--project", "P1")
    ok(env, "set", "feed.signal_tags", "b", "--project", "P1")
    seq = ok(env, "history", "feed.signal_tags").splitlines()[1].split("  ")[0]
    out = ok(env, "revert", "feed.signal_tags", "--layer", "project:P1", "--seq", seq)
    assert out == "reverted feed.signal_tags project:P1 to [a]\n"
    assert ok(env, "get", "feed.signal_tags", "--project", "P1") == "[a]\n"
    assert "no change at seq 999" in refused(
        env, "revert", "feed.signal_tags", "--layer", "project:P1", "--seq", "999"
    )
    assert run(env, "revert", "feed.signal_tags", "--layer", "company").exit_code != 0


def test_the_actor_and_source_are_recorded(env: dict[str, str]) -> None:
    ok(env, "set", "feed.reactions.enabled", "false", "--project", "P1", "--actor", "user:mlee")
    line = ok(env, "history", "feed.reactions.enabled").strip()
    assert "  user:mlee  " in line
    events = runner.invoke(app, ["events", "tail", "--project", "P1", "-n", "1"], env=env)
    assert events.exit_code == 0 and "Setting.Changed" in events.stdout
