"""`tl schema waiver request|approve|revoke|ls` (P1-I8-T05a3). Provided; do not edit."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_core.util import utcnow
from tl_mod_schemareg import views
from tl_mod_schemareg.handlers.waivers import RequestWaiver
from tl_mod_schemareg.testing import AUTHOR, RegistryWorld
from tl_mod_schemareg.views import WaiverView
from typer.testing import Result as RunResult

PATH = "psets.valve_data.size_in"
KEY = f"P999/{PATH}@1"
ID = r"[0-9A-Z]{26}"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def waiver(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "waiver", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def day(days: int) -> str:
    return (utcnow().date() + timedelta(days=days)).isoformat()


def asked_by_someone_else(env: dict[str, str], path: str = PATH) -> str:
    """A waiver for P999 asked for by another account; its record id."""
    world = RegistryWorld(as_target(env["TL_DB"]))
    with world.installed():
        made = world.do(
            RequestWaiver,
            AUTHOR,
            project="P999",
            path=path,
            reason="Legacy.",
            expires=day(20),
        )
    return made.stream_id


def test_a_request_is_listed_until_it_is_approved(env: dict[str, str]) -> None:
    as_admin(env)
    out = waiver(env, "request", "P999", PATH, "--reason", "Legacy valves.", "--expires", day(30))
    assert re.fullmatch(rf"requested {re.escape(KEY)} {ID}", out.stdout.strip())
    line = waiver(env, "ls").stdout.strip()
    assert re.fullmatch(
        rf"{re.escape(KEY)}  Requested  until {day(30)}  by user:\w+  approver -", line
    )


def test_a_request_that_cannot_be_honoured_is_one_error_line(env: dict[str, str]) -> None:
    as_admin(env)
    unknown = waiver(
        env,
        "request",
        "P999",
        "psets.valve_data.nope",
        "--reason",
        "x",
        "--expires",
        day(5),
        ok=False,
    )
    assert unknown.output.startswith("error:") and "names no property" in unknown.output
    past = waiver(env, "request", "P999", PATH, "--reason", "x", "--expires", day(-1), ok=False)
    assert past.output.startswith("error:") and "past" in past.output
    far = waiver(env, "request", "P999", PATH, "--reason", "x", "--expires", day(400), ok=False)
    assert far.output.startswith("error:") and "366" in far.output
    assert waiver(env, "ls").stdout.strip() == "no waivers"


def test_the_administrator_approves_by_key_and_then_by_id_it_is_already_approved(
    env: dict[str, str],
) -> None:
    as_admin(env)
    waiver_id = asked_by_someone_else(env)
    assert waiver(env, "approve", KEY, "--comment", "ok").stdout.strip() == f"approved {KEY}"
    line = waiver(env, "ls", "--state", "Approved").stdout.strip()
    assert re.fullmatch(
        rf"{re.escape(KEY)}  Approved  until {day(20)}  by user:author  approver user:\w+", line
    )
    again = waiver(env, "approve", waiver_id, ok=False)
    assert again.output.startswith("error:") and "Approved" in again.output


def test_the_person_who_asked_cannot_approve(env: dict[str, str]) -> None:
    as_admin(env)
    waiver(env, "request", "P999", PATH, "--reason", "Legacy.", "--expires", day(10))
    refused = waiver(env, "approve", KEY, ok=False)
    assert refused.output.startswith("error:") and "cannot approve" in refused.output
    assert " Requested " in waiver(env, "ls").stdout


def test_an_approved_waiver_can_be_revoked_once(env: dict[str, str]) -> None:
    as_admin(env)
    asked_by_someone_else(env)
    waiver(env, "approve", KEY)
    revoked = waiver(env, "revoke", KEY, "--reason", "Fixed at the source.")
    assert revoked.stdout.strip() == f"revoked {KEY}"
    assert " Revoked " in waiver(env, "ls", "--project", "P999", "--state", "Revoked").stdout
    again = waiver(env, "revoke", KEY, "--reason", "Again.", ok=False)
    assert again.output.startswith("error:") and "nothing to revoke" in again.output


def test_a_requested_waiver_can_be_refused_with_revoke(env: dict[str, str]) -> None:
    as_admin(env)
    asked_by_someone_else(env)
    assert waiver(env, "revoke", KEY, "--reason", "Not needed.").stdout.strip() == f"revoked {KEY}"


def test_ls_filters_by_project_and_says_when_there_is_none(env: dict[str, str]) -> None:
    as_admin(env)
    asked_by_someone_else(env)
    assert waiver(env, "ls", "--project", "P998").stdout.strip() == "no waivers"
    assert waiver(env, "ls", "--project", "P999").stdout.startswith(KEY)
    assert waiver(env, "ls", "--state", "Revoked").stdout.strip() == "no waivers"


def test_an_unknown_waiver_is_one_error_line(env: dict[str, str]) -> None:
    as_admin(env)
    for args in (("approve", "nope"), ("revoke", "nope", "--reason", "x")):
        refused = waiver(env, *args, ok=False)
        assert "error: no waiver 'nope'" in refused.output


def test_an_expired_waiver_is_marked(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    as_admin(env)
    old = WaiverView(
        id="W1",
        key="P1/psets.a.b@2",
        project="P1",
        path="psets.a.b",
        number=2,
        reason="r",
        expires="2026-01-01",
        expired=True,
        state="Approved",
        requested_by="user:a",
        approver="user:b",
    )
    monkeypatch.setattr(views, "waiver_views", lambda conn, project=None, state=None: [old])
    assert (
        waiver(env, "ls").stdout.strip()
        == "P1/psets.a.b@2  Approved (expired)  until 2026-01-01  by user:a  approver user:b"
    )


def test_anyone_may_ask_and_only_the_administrator_decides(
    env: dict[str, str], tmp_path: Path
) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    asked_by_someone_else(env)
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    own = waiver(plain, "request", "P998", PATH, "--reason", "Mine.", "--expires", day(9))
    assert own.stdout.startswith(f"requested P998/{PATH}@1 ")
    for args in (("approve", KEY), ("revoke", KEY, "--reason", "x")):
        assert "forbidden" in waiver(plain, *args, ok=False).output
    assert waiver(plain, "ls", "--project", "P999").stdout.startswith(KEY)
