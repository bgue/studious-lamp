"""`tl schema import-git` (P1-I8-T05a4c). Provided; do not edit."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, is_postgres, open_uow
from tl_mod_schemareg import registry
from tl_mod_schemareg.limits import MAX_CONTENT_BYTES
from tl_mod_schemareg.testing import RegistryWorld, fixture_text, next_version, publish_version
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"
ID = r"[0-9A-Z]{26}"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def import_git(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "import-git", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def put(directory: Path, version: str, text: str | None = None) -> str:
    """A package file for NAME at `version` in `directory`; its text."""
    directory.mkdir(exist_ok=True)
    text = next_version(NAME, version) if text is None else text
    (directory / f"{NAME}@{version}.yaml").write_text(text, encoding="utf-8")
    return text


def held(env: dict[str, str], version: str) -> registry.PackageRow | None:
    with open_uow(as_target(env["TL_DB"]), readonly=True) as uow:
        return registry.find_package(uow.conn(), NAME, version)


def test_new_files_become_drafts_and_nothing_is_published(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    src = tmp_path / "git"
    texts = {v: put(src, v) for v in ("3.4.0", "3.3.0")}
    lines = import_git(env, str(src)).stdout.splitlines()
    assert len(lines) == 3
    assert re.fullmatch(rf"drafted {NAME}@3\.3\.0 {ID}", lines[0])
    assert re.fullmatch(rf"drafted {NAME}@3\.4\.0 {ID}", lines[1])
    assert lines[2] == "imported 2 drafted, 0 unchanged, 0 skipped, 0 problems"
    for version, text in texts.items():
        row = held(env, version)
        assert row is not None and row.state == "Draft" and row.content == text


def test_a_second_import_of_the_same_files_changes_nothing(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    src = tmp_path / "git"
    put(src, "3.3.0")
    import_git(env, str(src))
    again = import_git(env, str(src)).stdout.splitlines()
    assert again == [
        f"unchanged {NAME}@3.3.0",
        "imported 0 drafted, 1 unchanged, 0 skipped, 0 problems",
    ]


def test_a_published_version_and_a_version_of_the_schema_directory_are_not_drafted_again(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    world = RegistryWorld(as_target(env["TL_DB"]))
    with world.installed():
        made = publish_version(world, "3.3.0")
        published = world.package(made.stream_id).content
    src = tmp_path / "git"
    put(src, "3.3.0", published)
    put(src, "3.2.0", fixture_text(NAME))
    lines = import_git(env, str(src)).stdout.splitlines()
    assert lines == [
        f"skipped {NAME}@3.2.0 in force already",
        f"unchanged {NAME}@3.3.0",
        "imported 0 drafted, 1 unchanged, 1 skipped, 0 problems",
    ]


def test_a_dry_run_drafts_nothing(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    src = tmp_path / "git"
    put(src, "3.3.0")
    lines = import_git(env, str(src), "--dry-run").stdout.splitlines()
    assert lines == [
        f"would draft {NAME}@3.3.0",
        "dry run 1 to draft, 0 unchanged, 0 skipped, 0 problems",
    ]
    assert held(env, "3.3.0") is None


def test_one_bad_file_names_its_problem_stops_the_import_and_exits_one(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    src = tmp_path / "git"
    put(src, "3.3.0")
    put(src, "3.4.0", "package: [not a package\n")
    (src / "misnamed.yaml").write_text(next_version(NAME, "3.5.0"), encoding="utf-8")
    out = import_git(env, str(src), ok=False).stdout.splitlines()
    assert out[0].startswith(f"problem {NAME}@3.4.0.yaml ") and len(out[0]) > 40
    assert out[1] == "problem misnamed.yaml name does not match its package and version"
    assert out[2] == "imported 0 drafted, 0 unchanged, 0 skipped, 2 problems"
    assert len(out) == 3 and held(env, "3.3.0") is None


def test_a_version_held_with_other_text_is_a_problem(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    src = tmp_path / "git"
    put(src, "3.3.0")
    import_git(env, str(src))
    put(src, "3.3.0", next_version(NAME, "3.3.0") + "# edited in git\n")
    out = import_git(env, str(src), ok=False).stdout.splitlines()
    assert out[0] == f"problem {NAME}@3.3.0.yaml exists with other text"


def test_links_folders_big_files_and_other_files_are_not_followed(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    src = tmp_path / "git"
    put(src, "3.3.0")
    (src / "notes.txt").write_text("not a package\n", encoding="utf-8")
    (src / "sub.yaml").mkdir()
    secret = tmp_path / "secret.yaml"
    secret.write_text(next_version(NAME, "3.7.0"), encoding="utf-8")
    (src / f"{NAME}@3.7.0.yaml").symlink_to(secret)
    (src / "big.yaml").write_text("x" * (MAX_CONTENT_BYTES + 1), encoding="utf-8")
    (src / "binary.yaml").write_bytes(b"\xff\xfe\x00")
    out = import_git(env, str(src), ok=False).stdout.splitlines()
    assert out == [
        "problem big.yaml is larger than 262144 bytes",
        "problem binary.yaml is not UTF-8 text",
        f"problem {NAME}@3.7.0.yaml is not a regular file",
        "problem sub.yaml is not a regular file",
        "imported 0 drafted, 0 unchanged, 0 skipped, 4 problems",
    ]
    assert held(env, "3.7.0") is None and held(env, "3.3.0") is None


def test_more_than_two_hundred_files_are_refused(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    src = tmp_path / "many"
    src.mkdir()
    for n in range(201):
        (src / f"p{n}.yaml").write_text("x", encoding="utf-8")
    refused = import_git(env, str(src), ok=False)
    assert refused.output.startswith("error:") and "200" in refused.output


def test_a_missing_directory_is_refused(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    import_git(env, str(tmp_path / "nowhere"), ok=False)


def test_any_signed_in_person_may_draft_like_tl_schema_package_draft(
    env: dict[str, str], tmp_path: Path
) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    src = tmp_path / "git"
    put(src, "3.3.0")
    assert import_git(plain, str(src)).stdout.startswith(f"drafted {NAME}@3.3.0 ")
