"""Classification of repository LinkML schemas between two trees (brief 27.5, 04-gates; T02)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tl_schema.classify import ClassificationReport
from tl_schema.classify_linkml import classify_trees

SCHEMA = Path(__file__).resolve().parents[3] / "schema"
COST = "modules/cost/cost_snapshot.yaml"
EVENTS = "modules/cost/events.yaml"


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("base") / "schema"
    for top in ("core", "modules"):
        shutil.copytree(SCHEMA / top, root / top)
    return root


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "schema"
    shutil.copytree(base, root)
    return root


def _edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} must occur once in {name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _codes(report: ClassificationReport) -> dict[str, str]:
    return {f"{c.path}|{c.code}": c.cls for c in report.changes}


def test_identical_trees_have_no_changes(base: Path, work: Path) -> None:
    report = classify_trees(base, work)
    assert report.changes == () and report.worst == "additive" and not report.blocks_submit


def test_the_real_tree_against_itself_is_clean() -> None:
    assert classify_trees(SCHEMA, SCHEMA).changes == ()


def test_an_optional_slot_is_additive(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "      row_count:\n",
        "      remark:\n        description: A remark on the snapshot.\n      row_count:\n",
    )
    report = classify_trees(base, work)
    assert _codes(report) == {f"{COST}:classes.CostSnapshot.remark|slot_added": "additive"}
    assert report.auto_adoptable


def test_a_required_slot_on_a_current_state_class_is_constraining(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "      row_count:\n",
        "      remark:\n        required: true\n        description: A remark.\n      row_count:\n",
    )
    report = classify_trees(base, work)
    assert report.worst == "constraining" and not report.blocks_submit


def test_a_required_slot_on_an_event_payload_is_breaking(base: Path, work: Path) -> None:
    _edit(
        work,
        EVENTS,
        '      uom:\n        description: "Unit of measure of the quantity figures."\n',
        '      uom:\n        description: "Unit of measure of the quantity figures."\n'
        '      remark:\n        required: true\n        description: "A remark."\n',
    )
    report = classify_trees(base, work)
    assert report.worst == "breaking" and report.blocks_submit
    assert any(c.code == "slot_added_required" and "payload" in c.detail for c in report.changes)


def test_a_removed_slot_a_changed_range_and_a_made_required_slot(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "      currency:\n        description:",
        "      currency:\n        range: integer\n        description:",
    )
    _edit(
        work,
        COST,
        "      source_name:\n        description: Display name of the file that was imported.\n",
        "",
    )
    _edit(
        work,
        COST,
        '      as_of:\n        required: true\n        description: "The date the figures',
        '      as_of:\n        required: false\n        description: "The date the figures',
    )
    codes = _codes(classify_trees(base, work))
    assert codes[f"{COST}:classes.CostSnapshot.currency|range_changed"] == "breaking"
    assert codes[f"{COST}:classes.CostSnapshot.source_name|slot_removed"] == "breaking"
    assert codes[f"{COST}:classes.CostSnapshot.as_of|required_dropped"] == "additive"


def test_a_removed_class_and_a_new_file(base: Path, work: Path) -> None:
    (work / "modules" / "cost" / "extra.yaml").write_text(
        (work / COST)
        .read_text(encoding="utf-8")
        .replace("tl_mod_cost_cost_snapshot", "tl_mod_cost_x"),
        encoding="utf-8",
    )
    report = classify_trees(base, work)
    assert _codes(report) == {"modules/cost/extra.yaml|file_added": "additive"}

    (work / "modules" / "cost" / "extra.yaml").unlink()
    (work / COST).unlink()
    codes = _codes(classify_trees(base, work))
    assert codes[f"{COST}|file_removed"] == "breaking"


def test_a_file_that_does_not_load_is_reported_as_breaking(base: Path, work: Path) -> None:
    (work / COST).write_text("classes: [this is not a schema", encoding="utf-8")
    report = classify_trees(base, work)
    assert report.worst == "breaking"
    assert [c.code for c in report.changes] == ["schema_unreadable"]


def test_a_unique_key_added_is_constraining(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "    unique_keys:\n      scope_period_revision:",
        "    unique_keys:\n      scope_period_as_of:\n"
        "        unique_key_slots:\n          - scope\n"
        "          - as_of\n      scope_period_revision:",
    )
    codes = _codes(classify_trees(base, work))
    assert codes[
        f"{COST}:classes.CostSnapshot.unique_keys.scope_period_as_of|unique_key_added"
    ] == ("constraining")


def test_a_description_change_asks_for_a_review(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "      period:\n        required: true\n"
        '        description: "The period the figures cover, `YYYY-MM`."',
        '      period:\n        required: true\n        description: "Another idea."',
    )
    (change,) = classify_trees(base, work).changes
    assert change.code == "description_changed" and change.review


def test_pattern_and_bounds_on_a_slot(base: Path, work: Path) -> None:
    _edit(
        work,
        COST,
        "      row_count:\n        range: integer\n",
        "      row_count:\n        range: integer\n        minimum_value: 0\n"
        "        pattern: '^[0-9]+$'\n",
    )
    codes = _codes(classify_trees(base, work))
    assert (
        codes[f"{COST}:classes.CostSnapshot.row_count.minimum|minimum_tightened"] == "constraining"
    )
    assert codes[f"{COST}:classes.CostSnapshot.row_count.pattern|pattern_changed"] == "constraining"
