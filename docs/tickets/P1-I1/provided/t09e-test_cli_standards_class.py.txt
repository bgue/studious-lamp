"""`tl standards class define|ls|show|revise|close` on a temporary ledger (P1-I1-T09e)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from engcli_support import admin_env, load_acme, ordinary_env
from tl_adapters.db import DbTarget, is_postgres

EDITION = "co.acme.standards@1.0.0"


@pytest.fixture
def env(new_db: Callable[[], DbTarget]) -> dict[str, str]:
    values = admin_env(new_db)
    load_acme(values)
    return values


def ok(env: dict[str, str], *args: str) -> list[str]:
    result = tl(env, "standards", "class", *args)
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def refused(env: dict[str, str], *args: str) -> str:
    result = tl(env, "standards", "class", *args)
    assert result.exit_code == 1, result.output
    assert result.stdout == "" and "Traceback" not in result.output
    return result.stderr.strip()


def define(env: dict[str, str], code: str = "GlobeValve", *more: str) -> list[str]:
    return ok(
        env,
        "define",
        code,
        "--label",
        "Globe valve",
        "--family",
        "valve",
        "--edition",
        EDITION,
        "--pset",
        "valve_data",
        "--mnemonic",
        "FV",
        "--itr",
        "ITR-VALVE-01",
        *more,
    )


def test_define_then_show_and_list(env: dict[str, str]) -> None:
    assert define(env) == ["defined class GlobeValve", "psets valve_data"]
    assert ok(env, "show", "GlobeValve") == [
        "code: GlobeValve",
        "label: Globe valve",
        "family: valve",
        "lifecycle: active",
        f"edition: {EDITION}",
        "key: TC:GlobeValve",
        "superseded_by: -",
        "psets: valve_data",
        "mnemonics: FV",
        "itr: ITR-VALVE-01",
        "version: 2",
    ]
    listed = ok(env, "ls")
    assert "GlobeValve  valve  active  valve_data  Globe valve" in listed
    assert "SafetyValve  valve  active  valve_data, safety_data  Pressure safety valve" in listed
    assert listed == sorted(listed)


def test_define_refuses_what_the_module_refuses(env: dict[str, str]) -> None:
    define(env)
    assert "already defined" in refused(
        env, "define", "GlobeValve", "--label", "x", "--family", "valve", "--edition", EDITION
    )
    assert "pset 'no_such_pset' is not in the company effective schema" in refused(
        env, "define", "Odd", "--label", "x", "--family", "valve", "--edition", EDITION,
        "--pset", "no_such_pset",
    )  # fmt: skip
    assert "family" in refused(
        env, "define", "Odd", "--label", "x", "--family", "tree", "--edition", EDITION
    )
    assert refused(env, "show", "Nope") == "error: no tag class 'Nope'"


def test_a_defined_class_binds_its_property_sets_to_tags(env: dict[str, str]) -> None:
    define(env)
    made = tl(env, "tag", "create", "47-FV-1001", "--class", "GlobeValve", "--project", "P123")
    assert made.exit_code == 0, made.output
    assert "conformance nonconformant" in made.stdout
    assert any(
        line.startswith("issue nonconformant") and "valve_data" in line
        for line in made.stdout.splitlines()
    )


def test_revise_changes_only_what_is_named(env: dict[str, str]) -> None:
    define(env)
    assert ok(
        env, "revise", "GlobeValve", "--reason", "rename", "--label", "Globe", "--mnemonic", "PV",
        "--mnemonic", "TV",
    ) == ["revised class GlobeValve: label, mnemonics"]  # fmt: skip
    shown = ok(env, "show", "GlobeValve")
    assert "label: Globe" in shown and "mnemonics: PV, TV" in shown
    assert "psets: valve_data" in shown and "version: 3" in shown
    assert "no field of tag class GlobeValve differs" in refused(
        env, "revise", "GlobeValve", "--reason", "same", "--label", "Globe"
    )
    assert refused(env, "revise", "GlobeValve", "--reason", "r").startswith(
        "error: nothing to revise"
    )
    assert "no_such_pset" in refused(
        env, "revise", "GlobeValve", "--reason", "r", "--pset", "no_such_pset"
    )


def test_close_retires_a_class_and_ls_all_still_lists_it(env: dict[str, str]) -> None:
    define(env)
    assert ok(env, "close", "GlobeValve", "--reason", "no longer used") == [
        "closed class GlobeValve as retired"
    ]
    assert not any(line.startswith("GlobeValve") for line in ok(env, "ls"))
    assert "GlobeValve  valve  retired  valve_data  Globe valve" in ok(env, "ls", "--all")
    assert "lifecycle: retired" in ok(env, "show", "GlobeValve")
    assert "is retired" in refused(env, "close", "GlobeValve", "--reason", "again")


def test_close_can_name_the_replacing_class(env: dict[str, str]) -> None:
    define(env)
    assert ok(
        env, "close", "GlobeValve", "--reason", "folded in", "--superseded-by", "ControlValve"
    ) == ["closed class GlobeValve as superseded"]
    assert "superseded_by: " in "\n".join(ok(env, "show", "GlobeValve"))
    assert "superseded_by: -" not in ok(env, "show", "GlobeValve")
    define(env, "OtherValve")
    assert "no tag class 'Ghost'" in refused(
        env, "close", "OtherValve", "--reason", "r", "--superseded-by", "Ghost"
    )


def test_only_an_admin_defines_revises_and_closes(env: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(env["TL_DB"]):
        pytest.skip("the Postgres test account is an admin")
    amy = ordinary_env(env, tmp_path)
    forbidden = "error: forbidden: this command needs the admin role"
    assert (
        refused(amy, "define", "Odd", "--label", "x", "--family", "valve", "--edition", EDITION)
        == forbidden
    )
    assert refused(amy, "revise", "ControlValve", "--reason", "r", "--label", "x") == forbidden
    assert refused(amy, "close", "ControlValve", "--reason", "r") == forbidden
    assert ok(amy, "ls") and ok(amy, "show", "ControlValve")
