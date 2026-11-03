"""`tl load targets` and the scope options of `tl load open` (W0-B2)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, derive_env
from tl_adapters.db import DbTarget, as_target
from tl_mod_legacy.model import LoaderDef, use_loaders
from tl_mod_legacy.targets import documents_target, mapping_target, tags_target, use_targets
from tl_mod_legacy.testing import LegacyWorld, document_loader, tag_csv, tag_loader
from typer.testing import Result as RunResult


@pytest.fixture(autouse=True)
def loaders() -> Iterator[None]:
    with use_loaders({"test-tags": tag_loader(), "test-docs": document_loader()}):
        yield


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    values["TL_LAKE_DIR"] = str(tmp_path / "lake")
    LegacyWorld(as_target(values["TL_DB"]), tmp_path / "unused").load_standards()
    return values


def load(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "load", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def csv_file(tmp_path: Path, name: str = "index.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(tag_csv(3))
    return path


def test_targets_lists_the_built_ins_with_module_and_scope(env: dict[str, str]) -> None:
    result = load(env, "targets")
    assert result.stdout.splitlines() == [
        "awp_cwa  awp  project",
        "awp_wbs  awp  project",
        "documents  legacy  project",
        "tags  legacy  project",
    ]


def test_targets_lists_a_registered_company_target_in_name_order(env: dict[str, str]) -> None:
    extra = mapping_target(
        "costcodes", module="cost", record_type="cost.CostCode", key_column="Code", columns={}
    )
    company = mapping_target(
        "registry",
        module="cost",
        record_type="cost.CostCode",
        key_column="Code",
        columns={},
        scope="company",
    )
    targets = {
        "documents": documents_target(),
        "tags": tags_target(),
        "costcodes": extra,
        "registry": company,
    }
    with use_targets(targets):
        lines = load(env, "targets").stdout.splitlines()
    assert lines == [
        "costcodes  cost  project",
        "documents  legacy  project",
        "registry  cost  company",
        "tags  legacy  project",
    ]


def test_open_for_a_project_target_with_the_company_option_is_refused(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    refused = load(
        env, "open", str(csv_file(tmp_path)), "--company", "--loader", "test-tags", ok=False
    )
    assert "error:" in refused.output and "--project" in refused.output
    assert "loads into a project" in refused.output
    assert load(env, "ls", "--project", "P123").stdout.strip() == ""


def test_open_for_a_project_target_with_a_project_still_works(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    opened = load(
        env, "open", str(csv_file(tmp_path)), "--project", "P123", "--loader", "test-tags"
    )
    assert opened.stdout.startswith("opened plantx/tags#1 ")


def test_open_needs_exactly_one_of_project_and_company(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    path = str(csv_file(tmp_path))
    both = load(
        env, "open", path, "--project", "P123", "--company", "--loader", "test-tags", ok=False
    )
    assert "give --project ID or --company, and not both" in both.output
    neither = load(env, "open", path, "--loader", "test-tags", ok=False)
    assert "give --project ID or --company, and not both" in neither.output
    assert load(env, "ls", "--project", "P123").stdout.strip() == ""


def test_open_for_a_company_target_with_a_project_is_refused(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    loader = LoaderDef(
        name="test-cc",
        system="cost",
        table="codes",
        target="registry",
        description="Company cost codes.",
        mapping_text="",
        file_types=("csv",),
    )
    company = mapping_target(
        "registry",
        module="cost",
        record_type="cost.CostCode",
        key_column="Code",
        columns={},
        scope="company",
    )
    path = tmp_path / "codes.csv"
    path.write_text("Code,Name\nC1,One\n", encoding="utf-8")
    with use_targets({"registry": company}), use_loaders({"test-cc": loader}):
        refused = load(env, "open", str(path), "--project", "P123", "--loader", "test-cc", ok=False)
    assert "error:" in refused.output and "--company" in refused.output
    assert "loads into the company" in refused.output
