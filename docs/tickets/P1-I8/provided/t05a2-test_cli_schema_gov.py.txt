"""`tl schema package publish|deprecate|retire` and `tl schema adopt|adoptions|drift`.

P1-I8-T05a2. Provided; do not edit.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_mod_schemareg import views
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.testing import (
    ADMIN,
    RegistryWorld,
    add_optional_property,
    add_required_property,
    next_version,
    publish_version,
)
from tl_mod_schemareg.views import AdoptionView
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"
ID = r"[0-9A-Z]{26}"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def world(env: dict[str, str]) -> RegistryWorld:
    return RegistryWorld(as_target(env["TL_DB"]))


def schema(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def approved(world: RegistryWorld, version: str, edit: Any = add_optional_property) -> str:
    """Draft, analyse, submit and approve ``NAME@version``; the ref (not yet published)."""
    with world.installed():
        made = world.do(DraftSchemaPackage, content=next_version(NAME, version, edit))
        for command in (AnalyseSchemaPackage, SubmitSchemaPackage):
            world.do(command, package_id=made.stream_id)
        world.do(ApproveSchemaPackage, ADMIN, package_id=made.stream_id)
    return f"{NAME}@{version}"


def test_publish_makes_an_approved_version_adoptable(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    ref = approved(world, "3.3.0")
    out = schema(env, "package", "publish", ref).stdout.strip()
    assert re.fullmatch(rf"published {re.escape(ref)} {ID}", out)
    assert schema(env, "package", "ls", "--state", "Published").stdout.startswith(ref)
    again = schema(env, "package", "publish", ref, ok=False)
    assert again.output.startswith("error:")


def test_publish_refuses_a_version_that_is_not_approved(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        made = world.do(DraftSchemaPackage, content=next_version(NAME, "3.3.0", None))
        world.do(AnalyseSchemaPackage, package_id=made.stream_id)
        world.do(SubmitSchemaPackage, package_id=made.stream_id)
    refused = schema(env, "package", "publish", f"{NAME}@3.3.0", ok=False)
    assert refused.output.startswith("error:") and "Approved" in refused.output
    assert "InReview" in schema(env, "package", "ls", "--package", NAME).stdout


def test_auto_adopt_moves_the_projects_that_pin_the_version_below(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0")
    adopted = schema(env, "adopt", "P999", NAME, "3.3.0").stdout.strip()
    assert adopted == f"adopted P999 {NAME}@3.3.0"
    schema(env, "adopt", "P998", NAME, "3.3.0")
    ref = approved(world, "3.4.0", lambda data: add_optional_property_again(data))
    out = schema(env, "package", "publish", ref, "--auto-adopt").stdout.splitlines()
    assert out[0].startswith(f"published {ref} ") and out[1] == "auto-adopted 2"
    assert len(schema(env, "adoptions").stdout.splitlines()) == 2
    lines = schema(env, "adoptions", "--project", "P999").stdout.splitlines()
    assert len(lines) == 1
    assert re.fullmatch(
        rf"P999  {re.escape(NAME)}@3.4.0  from 3.3.0  additive  by user:\w+", lines[0]
    )


def test_adoptions_show_a_dash_for_what_is_not_known(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    as_admin(env)
    unknown = AdoptionView(
        id="A1",
        project="P1",
        package="p",
        version="1.0.0",
        previous_version=None,
        worst_class=None,
        impact_sha256=None,
        adopted_by="user:x",
        adopted_at="2026-10-20T00:00:00Z",
    )
    monkeypatch.setattr(views, "adoption_views", lambda conn, project=None: [unknown])
    assert schema(env, "adoptions").stdout.strip() == "P1  p@1.0.0  from -  -  by user:x"


def add_optional_property_again(data: dict[str, Any]) -> None:
    add_optional_property(data)
    data["psets"]["valve_data"]["properties"]["actuator_make"] = {
        "description": "Make of the actuator.",
        "range": "string",
    }


def test_a_constraining_adoption_needs_the_digest_of_the_report_that_was_read(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0", add_required_property)
    ref = f"{NAME}@3.3.0"
    refused = schema(env, "adopt", "P999", NAME, "3.3.0", ok=False)
    assert refused.output.startswith("error:") and "digest" in refused.output
    wrong = schema(env, "adopt", "P999", NAME, "3.3.0", "--impact-sha256", "0" * 64, ok=False)
    assert wrong.output.startswith("error:")
    digest = schema(env, "package", "impact", ref, "--project", "P999").stdout.splitlines()[1]
    pinned = schema(
        env, "adopt", "P999", NAME, "3.3.0", "--impact-sha256", digest.removeprefix("digest ")
    )
    assert pinned.stdout.strip() == f"adopted P999 {NAME}@3.3.0"
    line = schema(env, "adoptions").stdout.splitlines()[0]
    assert line.startswith(f"P999  {NAME}@3.3.0  from 3.2.0  constraining  by ")


def test_adoptions_and_drift_are_lines_a_person_can_read(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    assert schema(env, "adoptions").stdout.strip() == "no adoptions"
    with world.installed():
        publish_version(world, "3.3.0")
    drift = schema(env, "drift", "P999").stdout.splitlines()
    assert f"{NAME}  project 3.2.0  company 3.3.0  behind  following" in drift
    schema(env, "adopt", "P999", NAME, "3.3.0")
    drift = schema(env, "drift", "P999").stdout.splitlines()
    assert f"{NAME}  project 3.3.0  company 3.3.0  current  pinned" in drift
    assert schema(env, "adoptions", "--project", "P998").stdout.strip() == "no adoptions"


def test_a_version_can_be_deprecated_and_then_retired_when_nobody_pins_it(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0")
    ref = f"{NAME}@3.3.0"
    gone = schema(
        env, "package", "deprecate", ref, "--reason", "Superseded.", "--replacement", "3.4.0"
    )
    assert gone.stdout.strip() == f"deprecated {ref}"
    payload = world.rows("SELECT payload FROM events WHERE event_type = 'SchemaPackage.Deprecated'")
    assert '"replacement":"3.4.0"' in str(payload[0]["payload"]).replace(" ", "")
    assert "Superseded." in str(payload[0]["payload"])
    assert schema(env, "package", "ls", "--state", "Deprecated").stdout.startswith(ref)
    retired = schema(env, "package", "retire", ref, "--reason", "Nobody uses it.")
    assert retired.stdout.strip() == f"retired {ref}"
    payload = world.rows("SELECT payload FROM events WHERE event_type = 'SchemaPackage.Retired'")
    assert "Nobody uses it." in str(payload[0]["payload"])
    assert schema(env, "package", "ls", "--state", "Retired").stdout.startswith(ref)


def test_a_version_a_project_pins_cannot_be_retired(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0")
    schema(env, "adopt", "P999", NAME, "3.3.0")
    ref = f"{NAME}@3.3.0"
    schema(env, "package", "deprecate", ref, "--reason", "Superseded.")
    refused = schema(env, "package", "retire", ref, "--reason", "Try.", ok=False)
    assert refused.output.startswith("error:") and "P999" in refused.output
    assert "Deprecated" in schema(env, "package", "ls", "--package", NAME).stdout


def test_publish_adopt_deprecate_and_retire_are_the_administrators(
    env: dict[str, str], world: RegistryWorld, tmp_path: Any
) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    ref = approved(world, "3.3.0")
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    for args in (
        ("package", "publish", ref),
        ("package", "deprecate", ref, "--reason", "x"),
        ("package", "retire", ref, "--reason", "x"),
        ("adopt", "P999", NAME, "3.2.0"),
    ):
        denied = schema(plain, *args, ok=False)
        assert "forbidden" in denied.output, args
    assert schema(plain, "adoptions").stdout.strip() == "no adoptions"
