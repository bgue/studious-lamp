"""File slot declarations: tl:file_slots parsing and loading (P0-I4-T22)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core.files.slots import (
    FileSlot,
    FileSlotError,
    FileSlotRegistry,
    default_file_slots,
    load_file_slots,
    parse_file_slots,
)

HEADER = """\
id: https://example.org/t
name: t
annotations:
  tl:module: core
"""

ONE_CLASS = (
    HEADER
    + """\
classes:
  Record:
    annotations:
      tl:file_slots:
        - name: report
          label: Report
          cardinality: one
          accepted_types: [application/pdf]
          max_size: 1000
          required_in_states: [Approved]
          capture_hint: scan
          metadata_pset: ndt
          processing: [thumbnail]
          retention_class: project
          confidentiality: restricted
        - name: photo
          accepted_types: ["image/*"]
"""
)


def write(directory: Path, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


# --- the model (implemented) --------------------------------------------------------------


def test_defaults_and_display() -> None:
    slot = FileSlot(name="mtr")
    assert slot.cardinality == "many" and slot.capture_hint == "file"
    assert slot.accepted_types == [] and slot.max_size is None
    assert slot.display == "mtr"
    assert FileSlot(name="mtr", label="Mill Test Report").display == "Mill Test Report"


@pytest.mark.parametrize("name", ["", "Mtr", "1mtr", "a-b", "a b"])
def test_a_slot_name_is_lower_snake_case(name: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FileSlot(name=name)


def test_accepts_matches_media_types_with_wildcards() -> None:
    slot = FileSlot(name="s", accepted_types=["application/pdf", "image/*"])
    assert slot.accepts("application/pdf")
    assert slot.accepts("Application/PDF; charset=binary")
    assert slot.accepts("image/png") and slot.accepts("image/jpeg")
    assert not slot.accepts("text/plain") and not slot.accepts("application/pdfx")
    assert FileSlot(name="any").accepts("anything/at-all")


def test_registry_keeps_declaration_order_and_refuses_duplicates() -> None:
    registry = FileSlotRegistry()
    registry.add("core.Record", FileSlot(name="b"))
    registry.add("core.Record", FileSlot(name="a"))
    assert [s.name for s in registry.for_type("core.Record")] == ["b", "a"]
    assert registry.get("core.Record", "a") == FileSlot(name="a")
    assert registry.get("core.Record", "zz") is None and registry.get("x.Y", "a") is None
    assert registry.for_type("x.Y") == [] and registry.record_types() == ["core.Record"]
    with pytest.raises(FileSlotError, match="declared twice"):
        registry.add("core.Record", FileSlot(name="a"))
    registry.for_type("core.Record").clear()  # a copy: the registry is unchanged
    assert len(registry.for_type("core.Record")) == 2


# --- parse_file_slots ---------------------------------------------------------------------


def test_parse_reads_every_key_of_every_slot() -> None:
    registry = parse_file_slots(ONE_CLASS)
    assert registry.record_types() == ["core.Record"]
    report, photo = registry.for_type("core.Record")
    assert report == FileSlot(
        name="report",
        label="Report",
        cardinality="one",
        accepted_types=["application/pdf"],
        max_size=1000,
        required_in_states=["Approved"],
        capture_hint="scan",
        metadata_pset="ndt",
        processing=["thumbnail"],
        retention_class="project",
        confidentiality="restricted",
    )
    assert photo == FileSlot(name="photo", accepted_types=["image/*"])


def test_a_single_mapping_is_accepted() -> None:
    text = HEADER + (
        "classes:\n  Record:\n    annotations:\n      tl:file_slots:\n        name: report\n"
    )
    assert [s.name for s in parse_file_slots(text).for_type("core.Record")] == ["report"]


def test_the_record_type_is_module_dot_class() -> None:
    text = (
        "name: t\nannotations:\n  tl:module: piping\nclasses:\n  Weld:\n    annotations:\n"
        "      tl:file_slots:\n        - name: nde_report\n"
    )
    assert parse_file_slots(text).record_types() == ["piping.Weld"]


@pytest.mark.parametrize("text", ["", "# only a comment\n", "~\n"])
def test_an_empty_file_declares_nothing(text: str) -> None:
    assert parse_file_slots(text).record_types() == []


def test_classes_without_the_annotation_contribute_nothing() -> None:
    text = HEADER + (
        "classes:\n  Record:\n    description: x\n  Other:\n"
        "  Third:\n    annotations:\n      tl:other: 1\n"
    )
    assert parse_file_slots(text).record_types() == []
    assert parse_file_slots(HEADER).record_types() == []
    assert parse_file_slots(HEADER + "classes: []\n").record_types() == []


def test_invalid_yaml_is_reported_with_the_source() -> None:
    with pytest.raises(FileSlotError, match=r"^core-record\.yaml: invalid YAML: "):
        parse_file_slots("a: [unclosed", source="core-record.yaml")


def test_a_document_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(FileSlotError) as caught:
        parse_file_slots("- a\n- b\n", source="x.yaml")
    assert str(caught.value) == "x.yaml: a schema file must be a YAML mapping"


def test_slots_without_a_module_are_refused() -> None:
    text = (
        "name: t\nclasses:\n  Record:\n    annotations:\n      tl:file_slots:\n        - name: a\n"
    )
    with pytest.raises(FileSlotError) as caught:
        parse_file_slots(text, source="x.yaml")
    assert str(caught.value) == (
        "x.yaml: class Record has tl:file_slots but the schema has no tl:module"
    )


def test_an_invalid_entry_names_the_class_index_and_problem() -> None:
    text = HEADER + (
        "classes:\n  Record:\n    annotations:\n      tl:file_slots:\n"
        "        - name: ok\n        - name: Bad Name\n          cardinality: lots\n"
    )
    with pytest.raises(FileSlotError) as caught:
        parse_file_slots(text, source="x.yaml")
    message = str(caught.value)
    assert message.startswith("x.yaml: Record.tl:file_slots[1]: ")
    assert "name: " in message and "cardinality: " in message and "; " in message


def test_an_unknown_key_in_an_entry_is_refused() -> None:
    text = HEADER + (
        "classes:\n  Record:\n    annotations:\n      tl:file_slots:\n"
        "        - name: a\n          colour: red\n"
    )
    with pytest.raises(FileSlotError, match="colour"):
        parse_file_slots(text)


def test_a_value_that_is_not_a_mapping_or_list_is_refused() -> None:
    text = HEADER + "classes:\n  Record:\n    annotations:\n      tl:file_slots: nope\n"
    with pytest.raises(FileSlotError, match="must be a mapping or a list of mappings"):
        parse_file_slots(text, source="x.yaml")


def test_a_slot_declared_twice_on_a_class_is_refused_with_the_source() -> None:
    text = HEADER + (
        "classes:\n  Record:\n    annotations:\n      tl:file_slots:\n"
        "        - name: a\n        - name: a\n"
    )
    with pytest.raises(FileSlotError, match=r"^x\.yaml: .*declared twice"):
        parse_file_slots(text, source="x.yaml")


# --- load_file_slots ----------------------------------------------------------------------


def test_load_merges_a_directory_in_name_order(tmp_path: Path) -> None:
    other = HEADER + (
        "classes:\n  Record:\n    annotations:\n      tl:file_slots:\n        - name: drawing\n"
    )
    write(tmp_path, "b.yaml", other)
    write(tmp_path, "a.yaml", ONE_CLASS)
    write(tmp_path, "ignored.txt", "not yaml: [")
    write(tmp_path, "c.yml", "not read")
    names = [s.name for s in load_file_slots(tmp_path).for_type("core.Record")]
    assert names == ["report", "photo", "drawing"]


def test_load_reads_one_file(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", ONE_CLASS)
    assert load_file_slots(tmp_path / "a.yaml").record_types() == ["core.Record"]


def test_load_of_a_missing_path_is_empty(tmp_path: Path) -> None:
    assert load_file_slots(tmp_path / "nowhere").record_types() == []


def test_load_names_the_file_in_parse_errors(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", ONE_CLASS)
    write(tmp_path, "b.yaml", "a: [unclosed")
    with pytest.raises(FileSlotError, match=r"^b\.yaml: invalid YAML"):
        load_file_slots(tmp_path)


def test_load_names_the_file_when_two_files_clash(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", ONE_CLASS)
    write(tmp_path, "b.yaml", ONE_CLASS)
    with pytest.raises(FileSlotError, match=r"^b\.yaml: .*declared twice"):
        load_file_slots(tmp_path)


def test_load_reports_an_unreadable_file(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    with pytest.raises(FileSlotError, match=r"^bad\.yaml: cannot read file: "):
        load_file_slots(tmp_path)


# --- default_file_slots -------------------------------------------------------------------


def test_default_reads_the_files_folder_of_the_schema_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path / "files", "core-record.yaml", ONE_CLASS)
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    assert [s.name for s in default_file_slots().for_type("core.Record")] == ["report", "photo"]


def test_default_without_the_env_reads_the_repository_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    registry = default_file_slots()
    report = registry.get("core.Record", "report")
    photo = registry.get("core.Record", "photo")
    assert report is not None and photo is not None
    assert report.cardinality == "one" and report.accepted_types == ["application/pdf"]
    assert report.required_in_states == ["Approved"] and report.max_size == 52428800
    assert photo.cardinality == "many" and photo.accepts("image/jpeg")
