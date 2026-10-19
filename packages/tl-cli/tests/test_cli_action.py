"""`tl action ls|show|define|retire|rotate-secret|invoke|invocations` on a temporary ledger
(P1-I7-T02b). Provided; do not edit.
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
    make_record,
    new_env,
    ok,
    refused,
    run,
    sql,
    write_json,
)
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult

ECHO = {
    "name": "echo_it",
    "label": "Echo it",
    "executor": "job",
    "executor_config": {"job": "echo"},
    "side_effect_class": "read",
    "parameters": [{"name": "note", "label": "Note", "kind": "string", "required": True}],
}
HOOK = {
    "name": "send_to_nde",
    "label": "Send to NDE",
    "executor": "webhook",
    "executor_config": {"url": "https://nde.example.net/hooks/request"},
    "side_effect_class": "external",
    "access": "controller",
}


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path) -> dict[str, str]:
    values = new_env(new_db, tmp_path)
    values["TL_WEBHOOK_ALLOWLIST"] = "nde.example.net"  # defining checks the URL; nothing is sent
    return values


def define(env: dict[str, str], tmp_path: Path, body: object = ECHO, *extra: str) -> RunResult:
    path = write_json(tmp_path, "action.json", body)
    return run(env, "action", "define", "--project", P, "--file", path, *extra)


def test_define_a_job_action_prints_its_name_and_id_and_no_secret(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = ok(define(env, tmp_path))
    shown = fields(made)
    assert shown["action"] == "echo_it" and len(shown["id"]) == 26
    assert "secret" not in shown and "keep the secret" not in made.stderr
    assert lines(run(env, "action", "ls")) == ["echo_it  job  user  v1  Echo it"]


def test_define_a_webhook_action_prints_the_secret_once(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = ok(define(env, tmp_path, HOOK))
    shown = fields(made)
    assert shown["secret"].startswith("whsec_") and len(shown["secret_id"]) == 26
    assert "keep the secret" in made.stderr
    everything = json.dumps(sql(env, "SELECT * FROM events"), default=str)
    everything += json.dumps(sql(env, "SELECT * FROM cur_action_definition"), default=str)
    assert shown["secret"] not in everything
    for args in (("ls",), ("show", "send_to_nde")):
        assert shown["secret"] not in ok(run(env, "action", *args)).output


def test_show_prints_the_action_without_its_executor_configuration(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(define(env, tmp_path, HOOK))
    shown = ok(run(env, "action", "show", "send_to_nde"))
    out = lines(shown)
    assert [s.split(" ")[0] for s in out] == [
        "action", "id", "scope", "version", "label", "executor", "access", "side_effect",
        "approval", "owner", "state", "applies_to",
    ]  # fmt: skip
    assert (
        out[0] == "action send_to_nde"
        and out[5] == "executor webhook"
        and out[6] == "access controller"
    )
    assert out[7] == "side_effect external" and out[8] == "approval no" and out[10] == "state on"
    assert "nde.example.net" not in shown.output
    ok(define(env, tmp_path, ECHO))
    echo = lines(run(env, "action", "show", "echo_it"))
    assert echo[-1] == "parameter note string required"


def test_retire_removes_the_action_from_the_list_and_from_use(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(define(env, tmp_path))
    make_record(env, "W-1")
    done = run(env, "action", "retire", "echo_it", "--reason", "replaced")
    assert ok(done).stdout == "action echo_it retired\n"
    assert ok(run(env, "action", "ls")).stdout == ""
    assert "state retired" in lines(run(env, "action", "show", "echo_it"))
    refused(
        run(
            env,
            "action",
            "invoke",
            "echo_it",
            "--project",
            P,
            "--target",
            "W-1",
            "--param",
            "note=x",
        ),
        "no action",
    )
    assert run(env, "action", "retire", "echo_it").exit_code == 2  # no reason
    refused(run(env, "action", "retire", "nope", "--reason", "x"), "no action nope")


def test_rotate_secret_prints_a_new_secret_once_and_a_job_action_has_none(
    env: dict[str, str], tmp_path: Path
) -> None:
    first = fields(ok(define(env, tmp_path, HOOK)))
    rotated = ok(run(env, "action", "rotate-secret", "send_to_nde", "--overlap-hours", "2"))
    assert fields(rotated)["secret"] != first["secret"] and "keep the secret" in rotated.stderr
    ok(define(env, tmp_path, ECHO))
    refused(run(env, "action", "rotate-secret", "echo_it"), "no signing secret")
    assert (
        run(env, "action", "rotate-secret", "send_to_nde", "--overlap-hours", "99").exit_code == 2
    )


def test_invoke_queues_an_invocation_and_it_is_listed(env: dict[str, str], tmp_path: Path) -> None:
    ok(define(env, tmp_path))
    make_record(env, "W-1")
    result = ok(
        run(
            env,
            "action",
            "invoke",
            "echo_it",
            "--project",
            P,
            "--target",
            "W-1",
            "--param",
            "note=hi",
        )
    )
    invocation_id = fields(result)["invoked"]
    assert len(invocation_id) == 26
    row = sql(env, "SELECT status, invoked_by, parameters_json FROM cur_action_invocation")[0]
    assert (row["status"], row["invoked_by"]) == ("requested", "user:dev")
    assert json.loads(row["parameters_json"]) == {"note": "hi"}
    listed = lines(run(env, "action", "invocations"))
    assert len(listed) == 1 and listed[0].startswith(
        f"{invocation_id}  requested  echo_it  user:dev  "
    )
    assert lines(run(env, "action", "invocations", "--status", "failed")) == []
    assert len(lines(run(env, "action", "invocations", "--action", "echo_it", "-n", "1"))) == 1
    refused(run(env, "action", "invocations", "--status", "bogus"), "--status must be one of")


def test_invoke_judges_the_access_of_the_action_and_the_parameters(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(define(env, tmp_path, HOOK))
    ok(define(env, tmp_path, ECHO))
    make_record(env, "W-1")
    # a controller action: nobody is signed in, so only the `user` level is held
    refused(
        run(env, "action", "invoke", "send_to_nde", "--project", P, "--target", "W-1"), "controller"
    )
    assert sql(env, "SELECT 1 FROM cur_action_invocation") == []
    refused(run(env, "action", "invoke", "echo_it", "--project", P, "--target", "W-1"), "note")
    refused(
        run(
            env,
            "action",
            "invoke",
            "echo_it",
            "--project",
            P,
            "--target",
            "NOPE-1",
            "--param",
            "note=x",
        ),
        "no record NOPE-1",
    )
    refused(
        run(env, "action", "invoke", "echo_it", "--project", P, "--param", "note"), "name=value"
    )
    refused(run(env, "action", "invoke", "ghost", "--project", P), "no action")


@pytest.mark.parametrize(
    ("body", "wanted"),
    [
        ({**ECHO, "executor": "mcp_tool"}, "executor"),
        ({**ECHO, "executor_config": {"job": "no_such_job"}}, "No job is installed"),
        ({**HOOK, "executor_config": {"url": "https://10.0.0.1/h"}}, "not allowed"),
        ({**ECHO, "name": "Bad Name"}, "name"),
        ({"name": "x"}, "label"),
        ([1], "JSON object"),
    ],
)
def test_an_action_that_cannot_be_stored_is_an_error(
    env: dict[str, str], tmp_path: Path, body: object, wanted: str
) -> None:
    refused(define(env, tmp_path, body), wanted)
    assert sql(env, "SELECT 1 FROM cur_action_definition") == []


def test_a_duplicate_name_and_an_unknown_action_are_errors(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(define(env, tmp_path))
    refused(define(env, tmp_path), "echo_it")
    refused(run(env, "action", "show", "nope"), "no action nope")
