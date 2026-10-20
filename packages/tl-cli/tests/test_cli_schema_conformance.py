"""`tl schema conformance --project P [--json]` (P1-I8-S9)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, is_postgres, open_uow
from tl_core import confidentiality as cf
from tl_core.modules import ConfidentialSource
from tl_core.util import utcnow
from tl_mod_schemareg.dashboard import ConformanceView
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver
from tl_mod_schemareg.testing import (
    ADMIN,
    AUTHOR,
    RegistryWorld,
    make_record,
    publish_version,
)
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"
PATH = "psets.valve_data.size_in"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def world(env: dict[str, str]) -> RegistryWorld:
    return RegistryWorld(as_target(env["TL_DB"]))


def conformance(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "conformance", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def place(
    world: RegistryWorld, key: str, kind: str, status: str, hash: str | None, project: str = "P999"
) -> str:
    record = make_record(world, key, {}, f"project:{project}")
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text(
                "UPDATE cur_core_record SET type = :t, conformance = :c, "
                "effective_schema_hash = :h WHERE id = :id"
            ),
            {"t": kind, "c": status, "h": hash, "id": record},
        )
    return record


def days(n: int) -> str:
    return (utcnow().date() + timedelta(days=n)).isoformat()


def test_a_project_with_no_records_prints_one_line(env: dict[str, str]) -> None:
    as_admin(env)
    lines = conformance(env, "--project", "P999").stdout.splitlines()
    assert len(lines) == 1
    head, schema, digest, records, count = lines[0].replace("  ", " ").split(" ")
    assert (head, schema, records, count) == ("P999", "schema", "records", "0")
    assert len(digest) == 12


def test_the_text_is_one_line_per_type_waiver_and_drifting_package(
    env: dict[str, str], world: RegistryWorld
) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0")
        made = world.do(
            RequestWaiver, AUTHOR, project="P999", path=PATH, reason="Legacy.", expires=days(10)
        )
        world.do(ApproveWaiver, ADMIN, waiver_id=made.stream_id)
        key = world.waiver(made.stream_id).key
        in_force = world.provider.effective("project:P999").hash
        place(world, "A", "core.Record", "ok", in_force)
        place(world, "B", "core.Record", "warning", "1" * 64)
        place(world, "C", "core.Record", "nonconformant", None)
        place(world, "D", "core.Other", "ok", in_force)
        place(world, "E", "core.Waived", "waived", in_force)
    out = conformance(env, "--project", "P999").stdout.splitlines()
    # 6: the five records and the waiver, which is a record of the project too
    assert out[0] == f"P999  schema {in_force[:12]}  records 6"
    record = "core.Record  total 3  ok 1  warning 1  nonconformant 1  waived 0  stale 2"
    other = "core.Other  total 1  ok 1  warning 0  nonconformant 0  waived 0  stale 0"
    waived = "core.Waived  total 1  ok 0  warning 0  nonconformant 0  waived 1  stale 0"
    assert record in out and other in out and waived in out
    assert out.index(other) < out.index(record)  # sorted by type
    assert f"waiver {key}  until {days(10)}  10 days left" in out
    assert not any(line.startswith("expired waivers") for line in out)
    assert out[-1] == f"behind {NAME}  3.2.0 < 3.3.0"


def test_an_expired_waiver_is_a_count_not_a_line(env: dict[str, str], world: RegistryWorld) -> None:
    as_admin(env)
    with world.installed():
        made = world.do(
            RequestWaiver, AUTHOR, project="P999", path=PATH, reason="Legacy.", expires=days(5)
        )
        world.do(ApproveWaiver, ADMIN, waiver_id=made.stream_id)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_waiver SET expires = :e WHERE id = :id"),
            {"e": days(-2), "id": made.stream_id},
        )
    out = conformance(env, "--project", "P999").stdout.splitlines()
    assert "expired waivers 1" in out and not any(line.startswith("waiver ") for line in out)


def test_json_is_the_view_and_nothing_else(env: dict[str, str], world: RegistryWorld) -> None:
    as_admin(env)
    with world.installed():
        publish_version(world, "3.3.0")
        place(world, "A", "core.Record", "warning", None)
    result = conformance(env, "--project", "P999", "--json")
    view = ConformanceView.model_validate_json(result.stdout)
    assert json.loads(result.stdout) == json.loads(view.model_dump_json())
    assert result.stdout == view.model_dump_json(indent=2) + "\n"
    assert view.project == "P999" and view.drift[0].package == NAME
    assert [(t.type, t.warning, t.waived, t.stale) for t in view.by_type] == [
        ("core.Record", 1, 0, 1)
    ]
    assert json.loads(result.stdout)["by_type"][0]["waived"] == 0


def test_a_person_who_is_not_signed_in_is_refused(env: dict[str, str]) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    refused = conformance(env, "--project", "P999", ok=False)
    assert refused.stderr.startswith("error: not signed in")


def test_the_project_is_required(env: dict[str, str]) -> None:
    as_admin(env)
    result = conformance(env, ok=False)
    assert result.exit_code == 2 and "--project" in result.output


def test_a_person_sees_the_counts_of_what_they_may_read(
    env: dict[str, str],
    world: RegistryWorld,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    with open_uow(world.db) as uow:
        uow.conn().execute(text("CREATE TABLE cur_zz_klass (id TEXT PRIMARY KEY, klass TEXT)"))
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}),
        table="cur_zz_klass",
        id_column="id",
        class_column="klass",
    )
    monkeypatch.setattr(cf, "confidential_sources", lambda: [source])
    for key, klass in (("OPEN", "internal"), ("SECRET", "restricted")):
        record = place(world, key, "core.Record", "nonconformant", None)
        with open_uow(world.db) as uow:
            uow.conn().execute(
                text("INSERT INTO cur_zz_klass (id, klass) VALUES (:id, :k)"),
                {"id": record, "k": klass},
            )
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    assert "records 1" in conformance(plain, "--project", "P999").stdout
    assert "records 2" in conformance(env, "--project", "P999").stdout
