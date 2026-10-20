"""`tl schema package diff|classify|impact|test` (P1-I8-T05a1). Provided; do not edit."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from auth_support import run as tl
from derivecli_support import as_admin
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_mod_schemareg import analysis, views
from tl_mod_schemareg.testing import (
    RegistryWorld,
    add_optional_property,
    add_required_property,
    fixture_text,
    make_record,
    next_version,
    publish_version,
    retype_property,
)
from tl_mod_schemareg.views import SampleExample, SampleTestView
from typer.testing import Result as RunResult

NAME = "co.acme.engineering"
SHA = re.compile(r"[0-9a-f]{64}")


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def pkg(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "package", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def draft(env: dict[str, str], tmp_path: Path, version: str, edit: object = None) -> str:
    """Draft ``NAME@version`` from the fixture package with ``edit`` applied; its key."""
    path = tmp_path / f"{NAME}-{version}.yaml"
    path.write_text(next_version(NAME, version, edit or add_optional_property), encoding="utf-8")  # type: ignore[arg-type]
    pkg(env, "draft", str(path))
    return f"{NAME}@{version}"


def test_diff_prints_the_text_diff_against_the_version_below(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0")
    assert (
        pkg(env, "diff", ref).stdout.strip() == f"not analysed: run tl schema package analyse {ref}"
    )
    pkg(env, "analyse", ref)
    lines = pkg(env, "diff", ref).stdout.splitlines()
    assert any(line.startswith("+") and "seat_leak_class" in line for line in lines)
    assert not any(line.startswith("-") and "seat_leak_class" in line for line in lines)
    assert lines[-1] != "(diff cut)"


def long_edit(data: dict[str, Any]) -> None:
    properties = data["psets"]["valve_data"]["properties"]
    for n in range(150):
        properties[f"extra_{n:03d}"] = {"description": f"Extra property {n}.", "range": "string"}


def test_a_version_with_the_content_of_its_base_has_no_differences(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0", lambda data: None)
    pkg(env, "analyse", ref)
    assert pkg(env, "diff", ref).stdout.strip() == f"no differences from {NAME}@3.2.0"


def test_a_long_diff_is_cut_and_says_so(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0", long_edit)
    pkg(env, "analyse", ref)
    lines = pkg(env, "diff", ref).stdout.splitlines()
    assert lines[-1] == "(diff cut)" and len(lines) == views.MAX_DIFF_LINES + 1


def test_diff_of_a_first_version_says_there_is_no_base(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    path = tmp_path / "prj.P555@1.0.0.yaml"
    path.write_text(fixture_text("prj.P123").replace("P123", "P555"), encoding="utf-8")
    pkg(env, "draft", str(path))
    pkg(env, "analyse", "prj.P555@1.0.0")
    out = pkg(env, "diff", "prj.P555@1.0.0").stdout
    assert out.strip() == "no base to compare with (first version)"


def test_classify_says_not_analysed_until_analyse_has_run(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0")
    out = pkg(env, "classify", ref).stdout.strip()
    assert out == f"not analysed: run tl schema package analyse {ref}"
    pkg(env, "analyse", ref)
    lines = pkg(env, "classify", ref).stdout.splitlines()
    assert lines[:6] == [
        f"classification {ref}",
        f"base {NAME}@3.2.0",
        "worst additive",
        "auto-adoptable yes",
        "blocks submit no",
        "counts additive 1",
    ]
    assert len(lines) == 7 and lines[6].startswith("additive  psets.valve_data.seat_leak_class  ")


def test_classify_of_a_breaking_change_blocks_submit(env: dict[str, str], tmp_path: Path) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "4.0.0", retype_property)
    pkg(env, "analyse", ref)
    lines = pkg(env, "classify", ref).stdout.splitlines()
    assert "worst breaking" in lines and "blocks submit yes" in lines
    assert "auto-adoptable no" in lines
    assert any(line.startswith("breaking  psets.valve_data.size_in  ") for line in lines)
    counts = next(line for line in lines if line.startswith("counts "))
    assert counts.startswith("counts ") and "breaking 1" in counts
    as_json = json.loads(pkg(env, "classify", ref, "--json").stdout)
    assert as_json["worst"] == "breaking" and as_json["blocks_submit"] is True


def test_impact_prints_the_stored_report_and_its_digest(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0")
    assert (
        pkg(env, "impact", ref).stdout.strip()
        == f"not analysed: run tl schema package analyse {ref}"
    )
    pkg(env, "analyse", ref)
    lines = pkg(env, "impact", ref).stdout.splitlines()
    assert lines[0] == "impact company"
    assert lines[1].startswith("digest ") and SHA.fullmatch(lines[1].removeprefix("digest "))
    assert lines[2].startswith("counts ")
    entries = lines[3:]
    assert entries and all(len(line.split("  ")) == 5 for line in entries)
    assert all(line.split("  ")[3] == "-" or line.split("  ")[3].isdigit() for line in entries)
    assert any(line.startswith("views  ") for line in entries)
    report = json.loads(pkg(env, "impact", ref, "--json").stdout)
    assert report["scope"] == "company" and report["entries"]
    stored = json.loads(pkg(env, "show", ref, "--json").stdout)["impact_sha256"]
    assert lines[1] == f"digest {stored}"


def test_a_package_that_changes_nothing_has_empty_reports(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    ref = draft(env, tmp_path, "3.3.0", lambda data: None)
    pkg(env, "analyse", ref)
    classified = pkg(env, "classify", ref).stdout.splitlines()
    assert "worst additive" in classified and "counts -" in classified
    assert len(classified) == 6
    impact = pkg(env, "impact", ref).stdout.splitlines()
    assert impact[0] == "impact company" and impact[2] == "counts -" and len(impact) == 3


def test_impact_for_a_project_is_made_now_and_has_the_digest_adopt_wants(
    env: dict[str, str],
) -> None:
    as_admin(env)
    world = RegistryWorld(as_target(env["TL_DB"]))
    with world.installed():
        publish_version(world, "3.3.0")
    ref = f"{NAME}@3.3.0"
    lines = pkg(env, "impact", ref, "--project", "P999").stdout.splitlines()
    assert lines[0] == "impact project:P999"
    digest = lines[1].removeprefix("digest ")
    assert SHA.fullmatch(digest)
    with world.installed(), open_uow(world.db, readonly=True) as uow:
        wanted = analysis.project_impact(uow.conn(), "P999", NAME, "3.3.0")[0].digest
    assert digest == wanted  # the value `tl schema adopt --impact-sha256` is checked against
    again = pkg(env, "impact", ref, "--project", "P999", "--json").stdout
    assert json.loads(again)["scope"] == "project:P999"


def required_everywhere(data: dict[str, Any]) -> None:
    """A constraining change that every record without the property breaks."""
    add_required_property(data)
    data["psets"]["valve_data"]["properties"]["seat_leak_class"]["required_in_states"] = ["*"]


def test_test_counts_a_sample_of_the_records_you_may_read(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    world = RegistryWorld(as_target(env["TL_DB"]))
    with world.installed():
        make_record(world, "R-1", {"valve_data": {"manufacturer": "Acme"}})
        make_record(world, "R-2", {"valve_data": {"manufacturer": "Borealis"}})
    ref = draft(env, tmp_path, "3.3.0", required_everywhere)
    lines = pkg(env, "test", ref, "--sample", "50").stdout.splitlines()
    # the two records and the draft package, which is a readable record too
    assert lines[0] == f"tested {ref}  scope company  sample 50  checked 3"
    assert lines[1:4] == ["newly nonconformant 2", "newly warning 0", "fixed 0"]
    assert len(lines) == 6
    assert lines[4].startswith("R-1  psets.valve_data.seat_leak_class  required_in_state  ")
    assert lines[5].startswith("R-2  psets.valve_data.seat_leak_class  required_in_state  ")
    as_json = json.loads(pkg(env, "test", ref, "--json").stdout)
    assert as_json["sample"] == 1000 and as_json["checked"] == 3


def test_the_lines_of_a_sample_test_follow_the_documented_order(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    as_admin(env)
    made = SampleTestView(
        package="p@1.0.0",
        scope="project:P1",
        sample=7,
        checked=6,
        newly_nonconformant=3,
        newly_warning=5,
        fixed=4,
        examples=[SampleExample(key="K-1", path="psets.a.b", rule="r", message="m")],
    )
    monkeypatch.setattr(views, "sample_test", lambda conn, ref, sample=0: made)
    lines = pkg(env, "test", "anything").stdout.splitlines()
    assert lines == [
        "tested p@1.0.0  scope project:P1  sample 7  checked 6",
        "newly nonconformant 3",
        "newly warning 5",
        "fixed 4",
        "K-1  psets.a.b  r  m",
    ]


def test_an_unknown_package_is_one_error_line(env: dict[str, str]) -> None:
    as_admin(env)
    for command in ("diff", "classify", "impact", "test"):
        refused = pkg(env, command, "nope@1.0.0", ok=False)
        assert "error: no schema package 'nope@1.0.0'" in refused.output
