"""`tl integration app add|ls|enable|disable` (P1-I7). Supervisor-built."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import P, fields, lines, new_env, ok, refused, run, sql
from tl_adapters.db import DbTarget


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path) -> dict[str, str]:
    return new_env(new_db, tmp_path)


def test_an_app_is_added_listed_switched_and_switched_back(env: dict[str, str]) -> None:
    made = fields(
        ok(run(env, "integration", "app", "add", "acme-nde", "--label", "Acme NDE", "--project", P))
    )
    assert made["app"] == "acme-nde" and len(made["id"]) == 26
    [listed] = lines(run(env, "integration", "app", "ls", "--project", P))
    assert listed.startswith("acme-nde  ") and listed.endswith("Acme NDE")
    assert " on " in f" {listed} "
    assert (
        ok(run(env, "integration", "app", "disable", "acme-nde", "--project", P)).stdout.strip()
        == "app acme-nde off"
    )
    assert sql(env, "SELECT enabled FROM cur_integration_app")[0]["enabled"] in (0, False)
    assert " off " in f" {lines(run(env, 'integration', 'app', 'ls'))[0]} "
    ok(run(env, "integration", "app", "enable", "acme-nde", "--project", P))
    assert sql(env, "SELECT enabled FROM cur_integration_app")[0]["enabled"] in (1, True)


def test_a_bad_name_an_unknown_app_and_a_double_switch_are_clean_errors(
    env: dict[str, str],
) -> None:
    refused(
        run(env, "integration", "app", "add", "Not A Slug", "--label", "x", "--project", P),
        "slug",
    )
    refused(run(env, "integration", "app", "disable", "nope", "--project", P), "no app nope")
    ok(run(env, "integration", "app", "add", "erp", "--label", "ERP", "--project", P))
    refused(run(env, "integration", "app", "enable", "erp", "--project", P), "error")
