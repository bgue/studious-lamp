"""`tl standards` (load, ls, show, values, add-value, close, close-value; P1-I1-T09a)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from engcli_support import ACME, admin_env, count, ordinary_env
from tl_adapters.db import DbTarget, is_postgres
from tl_mod_engineering.document import load_standards_file

DOC = load_standards_file(ACME)


@pytest.fixture
def env(new_db: Callable[[], DbTarget]) -> dict[str, str]:
    return admin_env(new_db)


@pytest.fixture
def loaded(env: dict[str, str]) -> dict[str, str]:
    assert tl(env, "standards", "load", str(ACME)).exit_code == 0
    return env


def ok(env: dict[str, str], *args: str) -> list[str]:
    result = tl(env, *args)
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def refused(env: dict[str, str], *args: str) -> str:
    result = tl(env, *args)
    assert result.exit_code == 1, result.output
    assert result.stdout == "" and "Traceback" not in result.output
    return result.stderr.strip()


def summary() -> list[str]:
    values = sum(len(c.values) for c in DOC.code_lists.values())
    return [
        f"code_list  create={len(DOC.code_lists)}  skip=0",
        f"code_value  create={values}  skip=0",
        f"mnemonic  create={len(DOC.mnemonics)}  skip=0",
        f"numbering_pattern  create={len(DOC.numbering_patterns)}  skip=0",
        f"tag_class  create={len(DOC.tag_classes)}  skip=0",
    ]


def test_load_reports_what_it_made_and_a_second_load_skips_everything(env: dict[str, str]) -> None:
    assert ok(env, "standards", "load", str(ACME)) == ["loaded co.acme.standards@1.0.0", *summary()]
    again = ok(env, "standards", "load", str(ACME))
    assert again[0] == "loaded co.acme.standards@1.0.0"
    assert all("create=0" in line for line in again[1:])
    assert [line.split("skip=")[1] for line in again[1:]] == [
        str(len(DOC.code_lists)),
        str(sum(len(c.values) for c in DOC.code_lists.values())),
        str(len(DOC.mnemonics)),
        str(len(DOC.numbering_patterns)),
        str(len(DOC.tag_classes)),
    ]


def test_a_dry_run_prints_the_plan_and_writes_nothing(env: dict[str, str]) -> None:
    if is_postgres(env["TL_DB"]):
        pytest.skip("counts rows of a SQLite file")
    before = count(env)
    assert ok(env, "standards", "load", str(ACME), "--dry-run") == [
        "plan co.acme.standards@1.0.0",
        *summary(),
    ]
    assert count(env) == before


def test_load_names_a_file_it_cannot_use(env: dict[str, str], tmp_path: Path) -> None:
    assert "cannot read file" in refused(env, "standards", "load", str(tmp_path / "missing.yaml"))
    broken = tmp_path / "broken.yaml"
    broken.write_text("standards: Not Valid\nversion: 1\n")
    message = refused(env, "standards", "load", str(broken))
    assert message.startswith("error: broken.yaml: ")


def test_ls_lists_entries_by_kind(loaded: dict[str, str]) -> None:
    lines = ok(loaded, "standards", "ls", "--kind", "code-list")
    assert len(lines) == len(DOC.code_lists)
    assert "code-list  Area  co.acme.standards@1.0.0  active  Area" in lines
    assert all(line.startswith("code-list  ") for line in lines)
    every = ok(loaded, "standards", "ls")
    assert len(every) == len(DOC.code_lists) + len(DOC.mnemonics) + len(DOC.numbering_patterns)
    assert "pattern  tag  co.acme.standards@1.0.0  active  Tag number" in every
    assert "unknown kind 'tree'" in refused(loaded, "standards", "ls", "--kind", "tree")


def test_show_prints_the_fields_of_one_entry(loaded: dict[str, str]) -> None:
    area = ok(loaded, "standards", "show", "code-list", "Area")
    assert area[:5] == [
        "kind: code-list",
        "code: Area",
        "label: Area",
        "edition: co.acme.standards@1.0.0",
        "lifecycle: active",
    ]
    assert "key: CL:Area@1.0.0" in area
    assert area[-2:] == ["value_list_policy: extensible", "values: 6"]
    pattern = ok(loaded, "standards", "show", "pattern", "tag")
    assert pattern[-2:] == ["record_type: engineering.Tag", "template: {area}-{mnemonic}-{seq:4}"]
    assert "mnemonic FV" not in ok(loaded, "standards", "show", "mnemonic", "FV")
    assert refused(loaded, "standards", "show", "code-list", "Nope") == (
        "error: no code-list 'Nope' in the registry"
    )


def test_values_lists_company_values_in_file_order_then_the_projects_own(
    loaded: dict[str, str],
) -> None:
    lines = ok(loaded, "standards", "values", "Area")
    codes = [line.split("  ")[0] for line in lines]
    assert codes == [v.code for v in DOC.code_lists["Area"].values]
    assert lines[0].split("  ")[2:] == ["company", "10", "active"]
    ok(
        loaded,
        "standards",
        "add-value",
        "Area",
        "T1",
        "--label",
        "Temp",
        "--crosswalk",
        "10",
        "--project",
        "P123",
    )
    mine = ok(loaded, "standards", "values", "Area", "--project", "P123")
    assert mine[-1] == "T1  Temp  project  10  active"
    assert ok(loaded, "standards", "values", "Area") == lines  # another scope does not see it
    assert "no active code list 'Nope'" in refused(loaded, "standards", "values", "Nope")


def test_add_value_follows_the_policy_of_the_list(loaded: dict[str, str]) -> None:
    assert ok(loaded, "standards", "add-value", "Area", "60", "--label", "Unit 60") == [
        "added Area.60 origin=company crosswalk=-"
    ]
    assert "already has a value '60'" in refused(
        loaded, "standards", "add-value", "Area", "60", "--label", "Again"
    )
    assert "must name the company value" in refused(
        loaded, "standards", "add-value", "Area", "X1", "--label", "Local", "--project", "P123"
    )
    assert "is closed" in refused(
        loaded, "standards", "add-value", "WeldType", "ZZ", "--label", "Z", "--project", "P123"
    )
    assert ok(
        loaded, "standards", "add-value", "Craft", "FIT", "--label", "Fitter", "--project", "P123"
    ) == ["added Craft.FIT origin=project crosswalk=-"]


def test_close_value_hides_the_value_unless_all_is_asked(loaded: dict[str, str]) -> None:
    assert ok(loaded, "standards", "close-value", "Area", "50", "--reason", "unit sold") == [
        "closed value Area.50 as retired"
    ]
    shown = [line.split("  ")[0] for line in ok(loaded, "standards", "values", "Area")]
    assert "50" not in shown
    everything = ok(loaded, "standards", "values", "Area", "--all")
    assert "50  Unit 50, Sulfur recovery  company  50  retired" in everything
    assert "is retired" in refused(
        loaded, "standards", "close-value", "Area", "50", "--reason", "x"
    )
    assert "no value Area.ZZ in company" in refused(
        loaded, "standards", "close-value", "Area", "ZZ", "--reason", "x"
    )
    assert ok(
        loaded,
        "standards",
        "close-value",
        "Area",
        "40",
        "--reason",
        "merged",
        "--superseded-by",
        "10",
    ) == ["closed value Area.40 as superseded"]


def test_close_retires_an_entry_and_ls_all_still_lists_it(loaded: dict[str, str]) -> None:
    assert ok(loaded, "standards", "close", "mnemonic", "FV", "--reason", "retired prefix") == [
        "closed mnemonic FV co.acme.standards@1.0.0 as retired"
    ]
    assert not any(" FV " in line for line in ok(loaded, "standards", "ls", "--kind", "mnemonic"))
    kept = ok(loaded, "standards", "ls", "--kind", "mnemonic", "--all")
    assert "mnemonic  FV  co.acme.standards@1.0.0  retired  Flow control valve" in kept
    assert refused(loaded, "standards", "close", "mnemonic", "FV", "--reason", "again") == (
        "error: no active mnemonic 'FV'"
    )


def test_close_can_name_the_replacing_entry_by_key(loaded: dict[str, str]) -> None:
    assert "no mnemonic with key 'MN:XX@1.0.0'" in refused(
        loaded,
        "standards",
        "close",
        "mnemonic",
        "FV",
        "--reason",
        "r",
        "--superseded-by",
        "MN:XX@1.0.0",
    )
    assert ok(
        loaded,
        "standards",
        "close",
        "mnemonic",
        "FV",
        "--reason",
        "folded into PV",
        "--superseded-by",
        "MN:PV@1.0.0",
    ) == ["closed mnemonic FV co.acme.standards@1.0.0 as superseded"]


def test_only_an_admin_changes_the_company_registry(loaded: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(loaded["TL_DB"]):
        pytest.skip("the Postgres test account is an admin")
    amy = ordinary_env(loaded, tmp_path)
    forbidden = "error: forbidden: this command needs the admin role"
    assert refused(amy, "standards", "load", str(ACME)) == forbidden
    assert refused(amy, "standards", "add-value", "Area", "61", "--label", "x") == forbidden
    assert refused(amy, "standards", "close", "mnemonic", "FV", "--reason", "r") == forbidden
    assert refused(amy, "standards", "close-value", "Area", "10", "--reason", "r") == forbidden
    # reading is open, and a project may add its own value when the list's policy allows it
    assert ok(amy, "standards", "ls", "--kind", "code-list")
    assert ok(
        amy,
        "standards",
        "add-value",
        "Area",
        "T2",
        "--label",
        "Temp",
        "--crosswalk",
        "10",
        "--project",
        "P123",
    ) == ["added Area.T2 origin=project crosswalk=10"]
    assert ok(
        amy, "standards", "close-value", "Area", "T2", "--reason", "gone", "--project", "P123"
    ) == ["closed value Area.T2 as retired"]


def test_nothing_changes_without_a_session(loaded: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(loaded["TL_DB"]):
        pytest.skip("the Postgres test account is signed in by the conftest")
    nobody = loaded | {"TL_SESSION_FILE": str(tmp_path / "nobody.json")}
    assert refused(nobody, "standards", "load", str(ACME)).startswith("error: not signed in")
