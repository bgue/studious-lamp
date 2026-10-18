"""`tl rule ls|show|create|enable|disable|mode|dry-run` on a temporary ledger (P1-I7-T03b).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import (
    P,
    fields,
    lines,
    new_env,
    ok,
    post,
    refused,
    run,
    sql,
    write_json,
)
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult

RULE = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
}


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path) -> dict[str, str]:
    return new_env(new_db, tmp_path)


def create(env: dict[str, str], tmp_path: Path, rule: object = RULE, *extra: str) -> RunResult:
    path = write_json(tmp_path, "rule.json", rule)
    return run(env, "rule", "create", "--project", P, "--file", path, *extra)


def test_create_prints_the_key_and_id_and_the_rule_starts_off_in_propose_mode(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = ok(create(env, tmp_path))
    shown = fields(made)
    assert shown["rule"] == "hse-notify" and len(shown["id"]) == 26
    assert lines(run(env, "rule", "ls", "--project", P)) == [
        "hse-notify  off  propose  user  v1  Notify HSE"
    ]


def test_ls_with_no_scope_option_lists_every_scope_and_prints_nothing_when_empty(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert ok(run(env, "rule", "ls")).stdout == ""
    ok(create(env, tmp_path))
    assert len(lines(run(env, "rule", "ls"))) == 1
    assert ok(run(env, "rule", "ls", "--project", "OTHER")).stdout == ""
    refused(run(env, "rule", "ls", "--project", P, "--company"), "exactly one of")


def test_show_prints_the_rule_in_a_fixed_order(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    shown = lines(run(env, "rule", "show", "hse-notify", "--project", P))
    assert shown[0] == "rule hse-notify"
    assert [s.split(" ")[0] for s in shown[1:9]] == [
        "id", "scope", "version", "state", "mode", "access", "owner", "title"
    ]  # fmt: skip
    assert shown[2] == f"scope project:{P}" and shown[3] == "version 1" and shown[4] == "state off"
    assert shown[5] == "mode propose" and shown[6] == "access user" and shown[7] == "owner user:dev"
    assert shown[8] == "title Notify HSE"
    assert shown[9] == 'when {"event_types": ["Feed.Posted"], "hashtags": ["safety"]}'
    assert shown[10] == 'step 1 PostToFeed {"body": "HSE notified"}'
    assert len(shown) == 11  # no condition line when there is no condition


def test_show_prints_a_condition_when_the_rule_has_one(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path, {**RULE, "condition": "status:Draft"}))
    shown = lines(run(env, "rule", "show", "hse-notify", "--project", P))
    assert "condition status:Draft" in shown


def test_enable_and_disable_switch_the_rule_and_a_repeat_is_refused(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(create(env, tmp_path))
    assert (
        ok(run(env, "rule", "enable", "hse-notify", "--project", P)).stdout
        == "rule hse-notify on\n"
    )
    assert lines(run(env, "rule", "ls", "--project", P))[0].startswith("hse-notify  on  ")
    refused(run(env, "rule", "enable", "hse-notify", "--project", P), "already on")
    assert (
        ok(run(env, "rule", "disable", "hse-notify", "--project", P)).stdout
        == "rule hse-notify off\n"
    )
    refused(run(env, "rule", "disable", "hse-notify", "--project", P), "already off")


def test_mode_is_a_revision_with_a_reason(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    done = run(env, "rule", "mode", "hse-notify", "act", "--reason", "go live", "--project", P)
    assert ok(done).stdout == "rule hse-notify mode act\n"
    assert lines(run(env, "rule", "ls", "--project", P)) == [
        "hse-notify  off  act  user  v2  Notify HSE"
    ]
    revised = sql(env, "SELECT payload FROM events WHERE event_type = 'Rule.Revised'")
    assert len(revised) == 1 and "go live" in str(revised[0]["payload"])
    refused(
        run(env, "rule", "mode", "hse-notify", "yolo", "--reason", "x", "--project", P),
        "act or propose",
    )
    assert run(env, "rule", "mode", "hse-notify", "act", "--project", P).exit_code == 2  # no reason


def test_the_actor_is_recorded_and_defaults_to_the_dev_user(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(create(env, tmp_path))
    path = write_json(tmp_path, "r2.json", {**RULE, "key": "second"})
    ok(run(env, "rule", "create", "--project", P, "--file", path, "--actor", "user:boss"))
    actors = sql(env, "SELECT actor FROM events WHERE event_type = 'Rule.Created' ORDER BY seq")
    assert [a["actor"] for a in actors] == ["user:dev", "user:boss"]
    sources = sql(env, "SELECT DISTINCT source FROM events WHERE event_type = 'Rule.Created'")
    assert [s["source"] for s in sources] == ["cli"]


@pytest.mark.parametrize(
    ("body", "wanted"),
    [
        ({**RULE, "when": {}}, "when"),
        ({**RULE, "then": [{"command": "PostToFeed", "args": {"actor": "user:boss"}}]}, "server"),
        ({**RULE, "then": [{"command": "PostToFeed", "args": {"body": "${nope}"}}]}, "nope"),
        ({"key": "x"}, "title"),
        ([1, 2], "JSON object"),
    ],
)
def test_a_rule_that_cannot_be_stored_is_an_error_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path, body: object, wanted: str
) -> None:
    refused(create(env, tmp_path, body), wanted)
    assert sql(env, "SELECT 1 FROM cur_rule") == []


def test_a_file_that_is_not_json_or_is_missing_is_an_error(
    env: dict[str, str], tmp_path: Path
) -> None:
    bad = write_json(tmp_path, "bad.json", "{not json")
    refused(run(env, "rule", "create", "--project", P, "--file", bad), "cannot read JSON")
    refused(
        run(env, "rule", "create", "--project", P, "--file", str(tmp_path / "none.json")),
        "cannot read JSON",
    )


def test_a_duplicate_key_and_an_unknown_rule_are_errors(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(create(env, tmp_path))
    refused(create(env, tmp_path), "hse-notify")
    refused(run(env, "rule", "show", "nope", "--project", P), "no rule nope")
    refused(run(env, "rule", "enable", "nope", "--project", P), "no rule nope")
    refused(run(env, "rule", "show", "hse-notify", "--project", "OTHER"), "no rule hse-notify")


def test_dry_run_lists_what_the_rule_would_have_done_and_writes_nothing(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(create(env, tmp_path))
    post(env, "pump 7 tripped #safety")
    post(env, "lunch is ready")
    before = len(sql(env, "SELECT 1 FROM events"))
    result = ok(run(env, "rule", "dry-run", "hse-notify", "--project", P))
    shown = lines(result)
    assert shown[0].startswith("events ") and int(shown[0].split(" ")[1]) >= 2
    assert shown[1] == "firings 1" and shown[2] == "truncated no"
    seq, outcome, planned = shown[3].split("  ")
    assert seq.isdigit() and outcome == "proposed" and planned == "PostToFeed"
    assert len(shown) == 4
    assert (
        len(sql(env, "SELECT 1 FROM events")) == before
        and sql(env, "SELECT 1 FROM rule_firing") == []
    )


def test_dry_run_can_be_limited_to_a_range_of_events(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    post(env, "one #safety")
    last = sql(env, "SELECT MAX(seq) AS s FROM events")[0]["s"]
    post(env, "two #safety")
    assert "firings 2" in lines(run(env, "rule", "dry-run", "hse-notify", "--project", P))
    narrowed = run(
        env, "rule", "dry-run", "hse-notify", "--project", P, "--from-seq", str(last + 1)
    )
    assert "firings 1" in lines(narrowed)
    assert "firings 1" in lines(
        run(env, "rule", "dry-run", "hse-notify", "--project", P, "--to-seq", str(last))
    )
