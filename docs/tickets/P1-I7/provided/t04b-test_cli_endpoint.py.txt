"""`tl endpoint ls|show|create|enable|disable|mode|rotate-secret` on a temporary ledger
(P1-I7-T04b). Provided; do not edit.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import (
    P,
    fields,
    lines,
    new_env,
    ok,
    refused,
    register_app,
    run,
    sql,
    write_json,
)
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult

MAPPING = '{"command": "PostToFeed", "args": {"body": $.text}}'


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path) -> dict[str, str]:
    values = new_env(new_db, tmp_path)
    register_app(values)
    return values


def create(env: dict[str, str], tmp_path: Path, path: str = "erp/orders", *extra: str) -> RunResult:
    mapping = write_json(tmp_path, "mapping.jsonata", MAPPING)
    args = ["--project", P, "--mapping-file", mapping, "--allow", "PostToFeed", *extra]
    return run(env, "endpoint", "create", path, *args)


def test_create_prints_the_path_the_id_and_the_secret_once(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = ok(create(env, tmp_path))
    shown = fields(made)
    assert shown["endpoint"] == "erp/orders" and len(shown["id"]) == 26
    assert shown["secret"].startswith("whsec_") and len(shown["secret_id"]) == 26
    assert "keep the secret" in made.stderr
    assert shown["secret"] not in made.stderr


def test_the_secret_is_in_no_event_and_no_listing(env: dict[str, str], tmp_path: Path) -> None:
    secret = fields(ok(create(env, tmp_path)))["secret"]
    everything = json.dumps(sql(env, "SELECT * FROM events"), default=str)
    everything += json.dumps(sql(env, "SELECT * FROM cur_inbound_endpoint"), default=str)
    assert secret not in everything
    for args in (("ls",), ("show", "erp/orders", "--project", P)):
        assert secret not in ok(run(env, "endpoint", *args)).output


def test_an_endpoint_starts_off_and_in_dry_run(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    assert lines(run(env, "endpoint", "ls", "--project", P)) == [
        "erp/orders  off  hmac_sha256  user  dry-run  v1"
    ]
    assert ok(run(env, "endpoint", "ls", "--project", "OTHER")).stdout == ""


def test_show_prints_the_endpoint_in_a_fixed_order(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    shown = lines(run(env, "endpoint", "show", "erp/orders", "--project", P))
    names = [s.split(" ")[0] for s in shown]
    assert names == [
        "endpoint", "id", "scope", "version", "state", "mode", "auth", "access", "max_body_bytes",
        "rate_per_minute", "actor", "owner", "allowed", "mapping",
    ]  # fmt: skip
    assert (
        shown[0] == "endpoint erp/orders" and shown[4] == "state off" and shown[5] == "mode dry-run"
    )
    assert shown[6] == "auth hmac_sha256" and shown[7] == "access user"
    assert shown[10] == "actor svc:inbound-erp.orders" and shown[12] == "allowed PostToFeed"
    assert shown[13] == "mapping " + json.dumps(MAPPING)


def test_enable_disable_and_mode(env: dict[str, str], tmp_path: Path) -> None:
    ok(create(env, tmp_path))
    assert ok(run(env, "endpoint", "enable", "erp/orders", "--project", P)).stdout == (
        "endpoint erp/orders on\n"
    )
    refused(run(env, "endpoint", "enable", "erp/orders", "--project", P), "already on")
    done = run(env, "endpoint", "mode", "erp/orders", "live", "--reason", "go", "--project", P)
    assert ok(done).stdout == "endpoint erp/orders mode live\n"
    assert lines(run(env, "endpoint", "ls", "--project", P)) == [
        "erp/orders  on  hmac_sha256  user  live  v2"
    ]
    assert ok(run(env, "endpoint", "disable", "erp/orders", "--project", P)).stdout == (
        "endpoint erp/orders off\n"
    )
    refused(
        run(env, "endpoint", "mode", "erp/orders", "yolo", "--reason", "x", "--project", P),
        "live or dry-run",
    )
    assert run(env, "endpoint", "mode", "erp/orders", "live", "--project", P).exit_code == 2


def test_rotate_secret_prints_a_new_secret_once_and_keeps_the_old_for_the_overlap(
    env: dict[str, str], tmp_path: Path
) -> None:
    first = fields(ok(create(env, tmp_path)))
    rotated = ok(
        run(env, "endpoint", "rotate-secret", "erp/orders", "--project", P, "--overlap-hours", "2")
    )
    second = fields(rotated)
    assert second["endpoint"] == "erp/orders" and second["secret"] != first["secret"]
    assert second["secret"].startswith("whsec_") and "keep the secret" in rotated.stderr
    assert len(sql(env, "SELECT 1 FROM int_secret WHERE owner_kind = 'inbound'")) == 2
    too_long = run(
        env, "endpoint", "rotate-secret", "erp/orders", "--project", P, "--overlap-hours", "99"
    )
    assert too_long.exit_code == 2  # at most 24 hours


def test_create_options_and_the_actor(env: dict[str, str], tmp_path: Path) -> None:
    ok(
        create(
            env,
            tmp_path,
            "erp/tokens",
            "--auth",
            "jwt_hs256",
            "--access",
            "controller",
            "--actor",
            "user:boss",
        )
    )
    row = sql(env, "SELECT auth, access, owner FROM cur_inbound_endpoint")[0]
    assert (row["auth"], row["access"], row["owner"]) == ("jwt_hs256", "controller", "user:boss")
    actor = sql(env, "SELECT actor FROM events WHERE event_type = 'InboundEndpoint.Created'")[0]
    assert actor["actor"] == "user:boss"


@pytest.mark.parametrize(
    ("path", "extra", "wanted"),
    [
        ("orders", (), "<app>/<name>"),
        ("erp/", (), "<app>/<name>"),
        ("erp/a/b", (), "<app>/<name>"),
        ("nope/orders", (), "no integration app"),
        ("erp/Bad Name", (), "pattern"),
        ("erp/x", ("--auth", "basic"), "auth"),
        ("erp/x", ("--access", "admin"), "access"),
    ],
)
def test_an_endpoint_that_cannot_be_stored_is_an_error_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path, path: str, extra: tuple[str, ...], wanted: str
) -> None:
    refused(create(env, tmp_path, path, *extra), wanted)
    assert sql(env, "SELECT 1 FROM cur_inbound_endpoint") == []


def test_a_mapping_outside_the_profile_is_an_error(env: dict[str, str], tmp_path: Path) -> None:
    bad = write_json(tmp_path, "bad.jsonata", "$eval('1')")
    result = run(
        env,
        "endpoint",
        "create",
        "erp/orders",
        "--project",
        P,
        "--mapping-file",
        bad,
        "--allow",
        "PostToFeed",
    )
    refused(result, "not allowed")
    missing = run(
        env,
        "endpoint",
        "create",
        "erp/orders",
        "--project",
        P,
        "--mapping-file",
        str(tmp_path / "x"),
        "--allow",
        "PostToFeed",
    )
    assert missing.exit_code == 1 and "error:" in missing.stderr
    noallow = run(env, "endpoint", "create", "erp/orders", "--project", P, "--mapping-file", bad)
    assert noallow.exit_code == 2  # --allow is required


def test_the_mapping_can_come_from_standard_input(env: dict[str, str]) -> None:
    result = run(
        env, "endpoint", "create", "erp/orders", "--project", P, "--mapping-file", "-",
        "--allow", "PostToFeed", input=MAPPING,
    )  # fmt: skip
    assert ok(result) and fields(result)["endpoint"] == "erp/orders"


def test_a_duplicate_and_an_unknown_endpoint_are_errors(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(create(env, tmp_path))
    refused(create(env, tmp_path), "erp/orders")
    refused(run(env, "endpoint", "show", "erp/nope", "--project", P), "no endpoint erp/nope")
    refused(run(env, "endpoint", "enable", "erp/nope", "--project", P), "no endpoint erp/nope")
    refused(
        run(env, "endpoint", "rotate-secret", "erp/nope", "--project", P), "no endpoint erp/nope"
    )
    refused(run(env, "endpoint", "show", "erp/orders", "--project", "OTHER"), "no endpoint")
