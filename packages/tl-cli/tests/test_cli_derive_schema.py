"""`tl derive schema register|ls|show|retire` (P1-I3-T14a). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from auth_support import run as tl
from derivecli_support import as_admin, derive_env, schema_file
from tl_adapters.db import DbTarget
from typer.testing import Result as RunResult


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    return derive_env(new_db, monkeypatch, tmp_path)


def derive(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "derive", "schema", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def test_register_then_list_and_show(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    out = derive(env, "register", str(schema_file(tmp_path)), "--company").stdout
    assert out.strip() == "registered instrument-index@1.0.0 company"
    listed = derive(env, "ls").stdout.splitlines()
    assert len(listed) == 1
    assert listed[0].startswith(
        "instrument-index@1.0.0  company  tags  tag  active  Instrument index"
    )
    shown = derive(env, "show", "instrument-index").stdout.splitlines()
    assert shown[0] == "schema instrument-index@1.0.0"
    assert "scope company" in shown and "target tags" in shown and "key column tag" in shown
    assert "status active" in shown
    assert "column tag string required" in shown and "column size_in number optional" in shown
    as_json = derive(env, "show", "instrument-index@1.0.0", "--json").stdout
    assert '"key": "instrument-index@1.0.0"' in as_json


def test_a_project_sees_its_own_schema_and_the_companys(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    derive(env, "register", str(schema_file(tmp_path)), "--company")
    own = schema_file(tmp_path, code="p123-list", mapping=None, target_kind=None, key_column=None)
    out = derive(env, "register", str(own), "--project", "P123").stdout
    assert out.strip() == "registered p123-list@1.0.0 project:P123"
    assert len(derive(env, "ls").stdout.splitlines()) == 1  # the company's only
    both = derive(env, "ls", "--project", "P123").stdout
    assert "p123-list@1.0.0" in both and "instrument-index@1.0.0" in both


def test_retire_hides_the_version_unless_all_is_given(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    derive(env, "register", str(schema_file(tmp_path)), "--company")
    out = derive(
        env, "retire", "instrument-index@1.0.0", "--company", "--reason", "superseded"
    ).stdout
    assert out.strip() == "retired instrument-index@1.0.0 company"
    assert derive(env, "ls").stdout.strip() == ""
    assert "retired" in derive(env, "ls", "--all").stdout
    assert "status retired: superseded" in derive(env, "show", "instrument-index@1.0.0").stdout
    derive(env, "retire", "instrument-index", "--company", "--reason", "x", ok=False)  # no version


def test_a_refused_schema_lists_its_problems_and_writes_nothing(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    bad = schema_file(
        tmp_path,
        mapping={
            "target": "tags",
            "key_column": "tag",
            "columns": [{"column": "nope", "to": "number"}],
        },
    )
    result = derive(env, "register", str(bad), "--company", ok=False)
    assert "error:" in result.output and "nope" in result.output
    assert derive(env, "ls").stdout.strip() == ""


def test_the_scope_must_be_one_of_project_or_company(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    path = str(schema_file(tmp_path))
    assert "give --project ID or --company" in derive(env, "register", path, ok=False).output
    both = derive(env, "register", path, "--company", "--project", "P123", ok=False)
    assert "give --project ID or --company" in both.output


def test_a_file_that_is_not_a_mapping_is_refused(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    path = tmp_path / "list.yaml"
    path.write_text(yaml.safe_dump(["a", "b"]), encoding="utf-8")
    result = derive(env, "register", str(path), "--company", ok=False)
    assert "must hold one mapping" in result.output


def test_registering_needs_the_admin_role(env: dict[str, str], tmp_path: Path) -> None:
    from auth_support import bootstrap, sign_in
    from tl_adapters.db import as_target, is_postgres

    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("on Postgres the conftest signs an admin in for every command")
    assert bootstrap(env).exit_code == 0
    # nobody signed in: the command refuses before reading the file
    result = derive(env, "register", str(schema_file(tmp_path)), "--company", ok=False)
    assert "not signed in" in result.output
    sign_in(env)
    derive(env, "register", str(schema_file(tmp_path)), "--company")
