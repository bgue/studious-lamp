"""`tl schema package ls|show|draft|revise|analyse|submit|changes|approve` (P1-I8, plumbing)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_mod_schemareg.testing import add_optional_property, next_version
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def pkg(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "package", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def package_file(tmp_path: Path, version: str = "3.3.0") -> Path:
    path = tmp_path / f"{NAME}-{version}.yaml"
    path.write_text(next_version(NAME, version, add_optional_property), encoding="utf-8")
    return path


def test_a_draft_goes_through_analysis_and_review(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    out = pkg(env, "draft", str(package_file(tmp_path)), "--changelog", "seat leak").stdout
    assert out.startswith(f"drafted {NAME}@3.3.0 ")
    listed = pkg(env, "ls", "--state", "Draft").stdout.splitlines()
    assert len(listed) == 1 and listed[0].startswith(f"{NAME}@3.3.0  company  Draft")
    assert "not-analysed" in listed[0]
    assert pkg(env, "analyse", f"{NAME}@3.3.0").stdout.strip() == f"analysed {NAME}@3.3.0 additive"
    shown = pkg(env, "show", f"{NAME}@3.3.0", "--diff").stdout
    assert f"package {NAME}@3.3.0" in shown and "class additive  (current)" in shown
    assert "seat_leak_class" in shown
    assert pkg(env, "submit", f"{NAME}@3.3.0").stdout.startswith(f"submitted {NAME}@3.3.0 ")
    assert "InReview" in pkg(env, "ls", "--package", NAME).stdout.splitlines()[0]


def test_the_author_cannot_approve_their_own_package(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    pkg(env, "draft", str(package_file(tmp_path)))
    pkg(env, "analyse", f"{NAME}@3.3.0")
    pkg(env, "submit", f"{NAME}@3.3.0")
    refused = pkg(env, "approve", f"{NAME}@3.3.0", ok=False)
    assert refused.output.startswith("error:")
    if is_postgres(as_target(env["TL_DB"])):
        return  # one signed-in admin only
    other = sign_in_as(env, tmp_path, "second", ["admin"])
    sent = pkg(other, "changes", f"{NAME}@3.3.0", "--reason", "needs a note").stdout
    assert sent.startswith(f"sent-back {NAME}@3.3.0 ")
    assert "Draft" in pkg(env, "ls", "--package", NAME).stdout.splitlines()[0]
    pkg(env, "submit", f"{NAME}@3.3.0")
    assert pkg(other, "approve", f"{NAME}@3.3.0").stdout.startswith(f"approved {NAME}@3.3.0 ")


def test_an_unknown_package_and_an_unsigned_caller_are_refused(
    env: dict[str, str], tmp_path: Path
) -> None:
    if not as_admin(env):
        pytest.skip("the conftest signs every Postgres command in")
    missing = pkg(env, "show", "nope@1.0.0", ok=False)
    assert "error: no schema package" in missing.output
    tl(env, "logout")
    unsigned = pkg(env, "ls", ok=False)
    assert "not signed in" in unsigned.output
    assert "not signed in" in pkg(env, "draft", str(package_file(tmp_path)), ok=False).output
