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
from tl_mod_materials import __file__ as materials_file
from tl_mod_materials.loaders.materials import items_loader
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
        "materials_item_master  materials  company",
        "materials_location  materials  project",
        "materials_po_line  materials  project",
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


def test_a_company_run_goes_from_open_to_show_with_the_company_option(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    items = tmp_path / "items.csv"
    items.write_bytes((Path(materials_file).parent / "samples" / "items.csv").read_bytes())
    with use_loaders({"mat-items": items_loader()}):
        opened = load(env, "open", str(items), "--company", "--loader", "mat-items")
        assert opened.stdout.startswith("opened mat/items#1 ")
        run = "mat/items#1"
        assert load(env, "extract", run, "--company").stdout.strip() == (
            "extracted mat/items#1 rows 50 columns 8"
        )
        assert load(env, "profile", run, "--company").stdout.strip() == "profiled mat/items#1"
        assert "new 50 existing 0 invalid 0" in load(env, "plan", run, "--company").stdout
        loaded = load(env, "load", run, "--company", "--expect-new", "50").stdout
        assert loaded.startswith("loaded mat/items#1 created 50 existing 0 invalid 0 ")
        reconciled = load(env, "reconcile", run, "--company").stdout.strip()
        assert reconciled == (
            "reconciled mat/items#1 matched 50 mismatches 0 left-alone-that-differ 0"
        )
        assert "state Reconciled" in load(env, "show", run, "--company").stdout


def test_extract_needs_exactly_one_of_project_and_company(env: dict[str, str]) -> None:
    as_admin(env)
    message = "give --project ID or --company, and not both"
    neither = load(env, "extract", "plantx/tags#1", ok=False)
    assert message in neither.output
    both = load(env, "extract", "plantx/tags#1", "--project", "P123", "--company", ok=False)
    assert message in both.output


def test_ls_with_a_project_still_lists_the_project_runs(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    load(env, "open", str(csv_file(tmp_path)), "--project", "P123", "--loader", "test-tags")
    listed = load(env, "ls", "--project", "P123").stdout.splitlines()
    assert listed == ["plantx/tags#1  Opened  test-tags  index.csv"]
