"""`tl schema export-git` (P1-I8-T05a4b). Provided; do not edit."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, sign_in_as
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_mod_schemareg.handlers.packages import DraftSchemaPackage
from tl_mod_schemareg.testing import RegistryWorld, next_version, publish_version
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def export(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "export-git", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def two_published(env: dict[str, str]) -> dict[str, str]:
    """Publish 3.3.0 and 3.4.0 and draft 3.5.0; the text of each, by version."""
    world = RegistryWorld(as_target(env["TL_DB"]))
    texts: dict[str, str] = {}
    with world.installed():
        for version in ("3.3.0", "3.4.0"):
            made = publish_version(world, version)
            texts[version] = world.package(made.stream_id).content
        world.do(DraftSchemaPackage, content=next_version(NAME, "3.5.0"))
    return texts


def test_every_published_version_is_one_file_with_the_text_it_was_drafted_with(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    texts = two_published(env)
    out = tmp_path / "git" / "schema"
    lines = export(env, str(out)).stdout.splitlines()
    assert lines == [
        f"wrote {NAME}@3.3.0.yaml",
        f"wrote {NAME}@3.4.0.yaml",
        f"exported 2 written, 0 unchanged to {out}",
    ]
    assert sorted(p.name for p in out.iterdir()) == [f"{NAME}@3.3.0.yaml", f"{NAME}@3.4.0.yaml"]
    for version, text in texts.items():  # a draft (3.5.0) is not exported
        written = (out / f"{NAME}@{version}.yaml").read_bytes()
        assert written == text.encode("utf-8")
        assert hashlib.sha256(written).hexdigest()  # the bytes are the drafted text, no more


def test_a_second_export_changes_nothing(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    two_published(env)
    out = tmp_path / "out"
    export(env, str(out))
    again = export(env, str(out)).stdout.splitlines()
    assert again == [
        f"unchanged {NAME}@3.3.0.yaml",
        f"unchanged {NAME}@3.4.0.yaml",
        f"exported 0 written, 2 unchanged to {out}",
    ]
    assert not [p for p in out.iterdir() if p.name.startswith(".")]  # no temporary file is left


def test_one_package_can_be_asked_for_and_nothing_to_export_makes_no_directory(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    two_published(env)
    other = tmp_path / "other"
    assert export(env, str(other), "--package", "co.acme.nothing").stdout.strip() == (
        "nothing to export"
    )
    assert not other.exists()
    only = tmp_path / "only"
    export(env, str(only), "--package", NAME)
    assert len(list(only.iterdir())) == 2


def test_a_file_with_other_text_or_a_link_stops_the_export_before_anything_is_written(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    two_published(env)
    out = tmp_path / "out"
    out.mkdir()
    (out / f"{NAME}@3.4.0.yaml").write_text("changed by hand\n", encoding="utf-8")
    refused = export(env, str(out), ok=False)
    assert refused.output.startswith("error:") and f"{NAME}@3.4.0.yaml" in refused.output
    assert [p.name for p in out.iterdir()] == [f"{NAME}@3.4.0.yaml"]  # 3.3.0 was not written
    assert (out / f"{NAME}@3.4.0.yaml").read_text(encoding="utf-8") == "changed by hand\n"
    linked = tmp_path / "linked"
    linked.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("keep\n", encoding="utf-8")
    (linked / f"{NAME}@3.3.0.yaml").symlink_to(secret)
    assert "link" in export(env, str(linked), ok=False).output
    assert secret.read_text(encoding="utf-8") == "keep\n"


def test_a_file_in_place_of_the_directory_is_refused(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    two_published(env)
    plain = tmp_path / "plain"
    plain.write_text("x", encoding="utf-8")
    export(env, str(plain), ok=False)
    assert plain.read_text(encoding="utf-8") == "x"


def test_only_the_administrator_writes_files(env: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    two_published(env)
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    out = tmp_path / "out"
    assert "forbidden" in export(plain, str(out), ok=False).output
    assert not out.exists()
