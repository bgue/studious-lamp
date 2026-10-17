"""The golden dataset: three sources, their exact expected results (P1-I3B-T12).

The sources are built by ``golden/make_golden.py`` and committed; the expected JSON files were read
by a person. A change to an extractor that changes any of these results fails here and is a
decision: bump the extractor's ``version`` and rewrite the expected file with
``make_golden.py --write-expected``, then read the diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_extractor_contract import check_extractor_contract

GOLDEN = Path(__file__).resolve().parent / "golden"
sys.path.insert(0, str(GOLDEN))

import make_golden  # noqa: E402

CASES = {case.name: case for case in make_golden.CASES}


def committed(name: str) -> bytes:
    return make_golden.source_path(CASES[name]).read_bytes()


def expected(name: str) -> dict[str, object]:
    return json.loads(make_golden.expected_path(CASES[name]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(CASES))
def test_the_script_builds_the_committed_source_byte_for_byte(name: str) -> None:
    assert make_golden.BUILDERS[name]() == committed(name)


@pytest.mark.parametrize("name", list(CASES))
def test_the_result_is_exactly_the_expected_file(name: str) -> None:
    result = make_golden.run_case(CASES[name], committed(name))
    assert result == expected(name)
    assert make_golden.dumps(result) == make_golden.expected_path(CASES[name]).read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("name", list(CASES))
def test_the_extractors_pass_the_contract_on_the_golden_sources(name: str) -> None:
    case = CASES[name]
    extractor = make_golden.extractors()[case.extractor]
    check_extractor_contract(extractor, [(case.filename, case.content_type, committed(name))])


def test_the_script_checks_clean() -> None:
    assert make_golden.main(["--check"]) == 0


# --- what the three files are expected to say, written down by hand --------------------------


def test_the_pdf_says_what_its_information_dictionary_says_and_nothing_more() -> None:
    result = make_golden.run_case(CASES["pdf"], committed("pdf"))
    assert result["status"] == "metadata_only" and result["rows"] == []
    meta = result["metadata"]
    assert isinstance(meta, dict)
    assert (meta["page_count"], meta["title"], meta["author"], meta["producer"]) == (
        3,
        "Instrument index – ISD-001",
        "Acme Instrumentation",
        "Throughline golden script",
    )
    assert (meta["created"], meta["modified"]) == (
        "2024-03-01T10:15:30+02:00",
        "2024-03-05T17:00:00Z",
    )


def test_the_csv_gives_ten_rows_two_skipped_lines_and_two_row_problems() -> None:
    result = make_golden.run_case(CASES["csv"], committed("csv"))
    rows = result["rows"]
    assert isinstance(rows, list) and len(rows) == 10
    assert rows[2]["service"] == "Flare header; north leg, pressure control"
    assert rows[3]["service"] == "Feed gas isolation"  # the padding is stripped
    assert rows[6]["service"] == "Separator level\ncontroller"
    assert rows[7]["remarks"] is None  # the control character left the cell empty
    problems = result["problems"]
    assert isinstance(problems, list)
    assert [(p["code"], p["row"]) for p in problems] == [
        ("control_character", 8),
        ("extra_cells", 10),
    ]
    notes = result["notes"]
    assert isinstance(notes, list)
    assert notes[0] == "delimiter detected: semicolon" and notes[-1] == "skipped 2 blank row(s)"


def test_the_xlsx_gives_four_rows_from_the_index_sheet() -> None:
    result = make_golden.run_case(CASES["xlsx"], committed("xlsx"))
    assert result["sheet"] == "Index"
    meta = result["metadata"]
    assert isinstance(meta, dict)
    assert meta["sheet_names"] == ["Cover", "Index", "Archive"]
    assert (meta["created"], meta["modified"]) == ("2024-03-01T10:15:30Z", "2024-03-05T17:00:00Z")
    rows = result["rows"]
    assert isinstance(rows, list) and len(rows) == 4
    assert (rows[0]["size_in"], rows[0]["Issued"], rows[0]["Witnessed"]) == (
        "4",
        "2024-03-01",
        "TRUE",
    )
    assert (rows[1]["size_in"], rows[1]["Issued"]) == ("6.5", "2024-03-01T13:05:00")
    assert rows[2]["size_in"] is None  # a formula with no stored value reads as empty
    assert result["problems"] == []
