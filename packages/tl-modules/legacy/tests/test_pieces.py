"""The small parts: names, the source layer, the profile, bronze, the loader registry."""

from __future__ import annotations

import json

import pytest
from tl_lake import LakeConfig
from tl_lake.duck import open_lake
from tl_mod_legacy.bronze import column_names, table_name
from tl_mod_legacy.errors import NotConfiguredError, SourceFileError
from tl_mod_legacy.extract import kind_of, read_grid
from tl_mod_legacy.model import Grid, LoaderLoadError, load_loaders, use_loaders
from tl_mod_legacy.profile import profile_grid
from tl_mod_legacy.service import LoadService
from tl_mod_legacy.source_layer import clean_values, property_name
from tl_mod_legacy.testing import ADMIN, PROJECT, LegacyWorld, tag_csv, tag_loader


def test_property_names_are_folded_and_bounded() -> None:
    assert property_name("P&ID") == "p_id"
    assert property_name("  Size (IN) ") == "size_in"
    assert property_name("1st pass") == "c_1st_pass"
    assert property_name("***") is None
    assert property_name("x" * 200) == "x" * 62


def test_values_are_cleaned_before_they_reach_the_source_layer() -> None:
    kept = clean_values(
        {
            "Tag No": "47-FV-1",
            "Empty": "  ",
            "Bell": "a\x07b",
            "Tag-No": "second wins nothing",
            "Long": "y" * 900,
            "$$$": "no name",
        }
    )
    assert list(kept) == ["tag_no", "long"]
    assert kept["tag_no"] == "47-FV-1" and len(kept["long"]) == 500


def test_a_record_takes_at_most_sixty_columns() -> None:
    kept = clean_values({f"col{n}": "v" for n in range(100)})
    assert len(kept) == 60 and list(kept)[0] == "col0"


def test_bronze_names() -> None:
    assert table_name("dms", "register") == "legacy_dms_register"
    for bad in ("DMS", "d ms", "1x", "", "a" * 40, "a;drop"):
        with pytest.raises(ValueError):
            table_name(bad, "t")
    assert column_names(["TAG NO", "Tag No", "tag-no", "", "9x"]) == [
        "tag_no",
        "tag_no_2",
        "tag_no_3",
        "c",
        "c_9x",
    ]
    with pytest.raises(ValueError):
        column_names([f"c{n}" for n in range(201)])


def test_the_profile_counts_what_is_in_the_columns() -> None:
    grid = Grid(
        columns=["id", "kind", "note"],
        rows=[["A-1", "CV", None], ["A-2", "CV", ""], ["A-3", "HV", None], ["A-3", "HV", None]],
    )
    result = profile_grid(grid)
    assert result.rows == 4 and result.duplicate_rows == 1
    columns = {c.name: c for c in result.columns}
    assert columns["id"].distinct == 3 and columns["id"].repeats == 1
    assert columns["id"].key_candidate is False and columns["id"].shape == "code"
    assert columns["note"].non_empty == 0 and columns["note"].empty == 4
    assert [(v.value, v.count) for v in columns["kind"].top_values] == [("CV", 2), ("HV", 2)]
    assert json.loads(result.model_dump_json())["rows"] == 4


def test_a_value_in_a_profile_is_cut() -> None:
    result = profile_grid(Grid(columns=["a"], rows=[["z" * 300]]))
    assert len(result.columns[0].top_values[0].value) <= 60


def test_a_header_cannot_be_sql() -> None:
    result = profile_grid(Grid(columns=['a"; DROP TABLE t; --', "b"], rows=[["1", "2"]]))
    assert [c.name for c in result.columns] == ['a"; DROP TABLE t; --', "b"]


def test_the_file_kind_is_taken_from_the_name() -> None:
    assert kind_of("A.CSV") == "csv" and kind_of("a.xlsx") == "xlsx"
    assert kind_of("a.xls") is None and kind_of("csv") is None


def test_a_loader_does_not_read_a_kind_it_did_not_declare() -> None:
    only_csv = tag_loader()
    only_csv = type(only_csv)(**{**only_csv.__dict__, "file_types": ("csv",)})
    with pytest.raises(SourceFileError, match="reads csv"):
        read_grid(b"x", "a.xlsx", only_csv)


def test_a_file_that_is_not_tabular_is_refused_without_its_text() -> None:
    with pytest.raises(SourceFileError) as raised:
        read_grid(b"PK\x03\x04 not a workbook", "a.xlsx", tag_loader())
    assert "not a workbook" not in str(raised.value)


def test_loaders_come_from_the_override_and_a_broken_one_is_named() -> None:
    with use_loaders({"x": tag_loader("x")}):
        assert list(load_loaders()) == ["x"]
    assert LoaderLoadError.__mro__[1] is RuntimeError


def test_bronze_copies_the_cells_as_they_are_and_replaces_a_run(
    world: LegacyWorld, lake: LakeConfig
) -> None:
    run = world.through_plan("test-tags", "a.csv", tag_csv(5))
    assert world.service.bronze(PROJECT, run.key, actor=ADMIN) == 5
    assert world.service.bronze(PROJECT, run.key, actor=ADMIN) == 5  # again: same rows, not ten
    with open_lake(lake, write=False) as con:
        rows = con.execute(
            "SELECT _row_no, tag_no, mfr FROM legacy_plantx_tags ORDER BY _row_no"
        ).fetchall()
    assert rows[0] == (1, "47-FV-1001", "Acme Valves") and len(rows) == 5
    assert world.run(run.key).bronze_rows == 5
    assert world.events_of(run.id).count("LoadRun.Bronzed") == 2


def test_bronze_needs_a_lake_and_an_extract(world: LegacyWorld, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    run = world.open("test-tags", "a.csv", tag_csv(2))
    with pytest.raises(Exception, match="extract it before bronze"):
        world.service.bronze(PROJECT, run.key, actor=ADMIN)
    bare = LoadService(db, world.files)
    with pytest.raises(NotConfiguredError):
        bare.bronze(PROJECT, run.key, actor=ADMIN)
