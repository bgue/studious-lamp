"""The scaffold engine: names, rendering, and writing a plan without overwriting."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_cli.scaffold.engine import (
    Plan,
    ScaffoldError,
    find_root,
    render,
    require_module,
    use_root,
    write_plan,
)
from tl_cli.scaffold.names import (
    NameError_,
    camel,
    check_event_type,
    parse_module,
    parse_projector,
    parse_record_type,
    snake,
)


def test_a_module_name_gives_its_package_and_directory() -> None:
    module = parse_module("weld_quality")
    assert (module.package, module.distribution, module.directory) == (
        "tl_mod_weld_quality",
        "tl-mod-weld-quality",
        "packages/tl-mod-weld-quality",
    )


@pytest.mark.parametrize(
    "name",
    ["", "a", "Inspection", "core", "tests", "1abc", "a__b", "a-b", "a b", "x" * 31, "../x", "a/b"],
)
def test_a_module_name_outside_the_rule_is_refused(name: str) -> None:
    with pytest.raises(NameError_):
        parse_module(name)


def test_a_record_type_gives_its_spellings() -> None:
    record_type = parse_record_type("inspection.WeldInspection")
    assert record_type.cls == "WeldInspection" and record_type.snake == "weld_inspection"
    assert record_type.qualified == "inspection.WeldInspection"
    assert record_type.table == "cur_inspection_weld_inspection"
    assert parse_record_type("inspection.NCR").snake == "ncr"


@pytest.mark.parametrize(
    "text", ["Weld", "inspection.weld", "inspection.", ".Weld", "inspection.Weld_X", "a.B.C"]
)
def test_a_record_type_outside_the_rule_is_refused(text: str) -> None:
    with pytest.raises(NameError_):
        parse_record_type(text)


def test_a_projector_gives_its_class_and_table() -> None:
    projector = parse_projector("inspection.weld_counts")
    assert projector.cls == "WeldCountsProjector"
    assert projector.table == "proj_inspection_weld_counts"


@pytest.mark.parametrize("text", ["counts", "inspection.Counts", "inspection.c", "inspection.a-b"])
def test_a_projector_outside_the_rule_is_refused(text: str) -> None:
    with pytest.raises(NameError_):
        parse_projector(text)


def test_event_types_have_the_class_dot_verb_shape() -> None:
    assert check_event_type("Weld.Created") == "Weld.Created"
    for bad in ("weld.created", "Weld", "Weld.Created.Twice", "Weld Created"):
        with pytest.raises(NameError_):
            check_event_type(bad)


def test_snake_and_camel_round_trip() -> None:
    assert snake("WeldInspection") == "weld_inspection"
    assert camel("weld_inspection") == "WeldInspection"


def test_render_fills_every_value_and_refuses_a_missing_one() -> None:
    text = render("module/package_init.py.tmpl", name="inspection")
    assert 'MODULE = "inspection"' in text
    with pytest.raises(KeyError):
        render("module/package_init.py.tmpl")


def test_a_plan_writes_its_files_and_ends_each_with_a_newline(tmp_path: Path) -> None:
    plan = Plan()
    plan.add("a/b.txt", "one")
    plan.add("c.txt", "two\n")
    assert write_plan(tmp_path, plan) == ["a/b.txt", "c.txt"]
    assert (tmp_path / "a/b.txt").read_text() == "one\n"
    assert (tmp_path / "c.txt").read_text() == "two\n"


def test_a_plan_never_overwrites_and_writes_nothing_when_one_file_exists(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("mine")
    plan = Plan()
    plan.add("a.txt", "new")
    plan.add("b.txt", "new")
    with pytest.raises(ScaffoldError, match="refusing to overwrite: b.txt"):
        write_plan(tmp_path, plan)
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text() == "mine"


@pytest.mark.parametrize("path", ["../x.txt", "/etc/x.txt", "a/../../x.txt", ""])
def test_a_path_that_leaves_the_root_is_refused(tmp_path: Path, path: str) -> None:
    plan = Plan()
    plan.add(path, "x")
    with pytest.raises(ScaffoldError):
        write_plan(tmp_path, plan)


def test_a_symlinked_directory_cannot_carry_a_write_out_of_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    plan = Plan()
    plan.add("link/x.txt", "x")
    with pytest.raises(ScaffoldError, match="leaves the repository"):
        write_plan(root, plan)
    assert list(outside.iterdir()) == []


def test_a_plan_lists_a_path_once() -> None:
    plan = Plan()
    plan.add("a", "x")
    with pytest.raises(ScaffoldError, match="twice"):
        plan.add("a", "y")


def test_the_root_is_found_from_inside_the_repository_and_checked_when_given(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("x")
    (tmp_path / "justfile").write_text("x")
    (tmp_path / "packages").mkdir()
    deep = tmp_path / "packages" / "x"
    deep.mkdir()
    assert find_root(deep) == tmp_path.resolve()
    assert use_root(tmp_path) == tmp_path.resolve()
    with pytest.raises(ScaffoldError, match="not a directory"):
        use_root(tmp_path / "missing")
    with pytest.raises(ScaffoldError, match="not inside the repository"):
        find_root(Path("/"))


def test_a_record_type_needs_its_module(tmp_path: Path) -> None:
    with pytest.raises(ScaffoldError, match="tl new module inspection"):
        require_module(tmp_path, "packages/tl-mod-inspection", "inspection")
    (tmp_path / "packages/tl-mod-inspection").mkdir(parents=True)
    (tmp_path / "packages/tl-mod-inspection/pyproject.toml").write_text("x")
    require_module(tmp_path, "packages/tl-mod-inspection", "inspection")
