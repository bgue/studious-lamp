"""`tl new record-type` scaffolds the offline class `none` and asks for a reason (OC-T3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from scaffold_support import copy_core_schema, tl_new

TODO = (
    "      # TODO: why this class? full = edited offline and merged; "
    "draft_only = drafted offline, issued online; none = online only.\n"
)
OFFLINE = "      tl:offline: none\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy_core_schema(tmp_path)
    assert tl_new(tmp_path, "module", "demo").exit_code == 0
    return tmp_path


def scaffold(root: Path, name: str = "demo.Weld") -> str:
    result = tl_new(root, "record-type", name)
    assert result.exit_code == 0, result.output
    module, cls = name.split(".")
    stem = "".join("_" + c.lower() if c.isupper() and i else c.lower() for i, c in enumerate(cls))
    return (root / "schema" / "modules" / module / f"{stem}.yaml").read_text(encoding="utf-8")


def test_the_schema_stub_declares_offline_none_with_a_todo_comment_line_before_it(
    root: Path,
) -> None:
    text = scaffold(root)
    assert TODO + OFFLINE in text  # the comment is the line directly above the key
    assert text.count("tl:offline:") == 1


def test_the_comment_names_the_three_classes_and_asks_for_a_reason() -> None:
    assert "why this class?" in TODO
    for word in ("full", "draft_only", "none"):
        assert word in TODO


def test_the_stub_still_parses_and_the_class_annotation_is_none(root: Path) -> None:
    text = scaffold(root)
    document = yaml.safe_load(text)
    annotations = document["classes"]["Weld"]["annotations"]
    assert str(annotations["tl:offline"]) == "none"
    assert annotations["tl:current_state"] is True  # the line it sits beside is untouched
    assert "tl:offline" not in document.get("annotations", {})  # class level, not schema level


def test_the_offline_key_sits_in_the_class_annotations_block(root: Path) -> None:
    lines = scaffold(root).splitlines(keepends=True)
    index = lines.index(OFFLINE)
    assert lines[index - 1] == TODO
    assert lines[index - 2] == "    annotations:\n"


def test_a_second_record_type_is_scaffolded_the_same_way(root: Path) -> None:
    scaffold(root, "demo.Weld")
    second = scaffold(root, "demo.PipeSpool")
    assert TODO + OFFLINE in second
    assert second.count("tl:offline:") == 1
