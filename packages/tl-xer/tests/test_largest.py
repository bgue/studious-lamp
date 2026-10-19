"""The largest legal file and the hostile ones through the envelope (P1-I4-T03).

L-P1-I3B-7: a bound is proved by a crafted file that finishes quickly or a limit patched down,
never by a test that spends many seconds. The one exception is the largest legal file, which has to
be read to show that the envelope's own limits (60 s, 1 GiB) are not the ones that decide.
"""

from __future__ import annotations

import time

import pytest
from tl_xer import limits
from tl_xer.run import read_xer_file
from xersupport import big_text, drop_table, encode, first_text, max_counts_text

pytestmark = pytest.mark.slow


def test_a_file_near_the_byte_and_cell_limits_is_read_inside_the_envelope() -> None:
    data = big_text(60_000, wide_rows=15_000)
    assert 40 * 1024 * 1024 < len(data) <= limits.MAX_BYTES
    started = time.monotonic()
    result = read_xer_file(data)
    assert result.status == "valid", result.report["problems"][:2]
    assert result.report["counts"]["activities"] == 60_000
    assert result.report["counts"]["cells"] > 4_500_000
    assert time.monotonic() - started < 60
    assert result.raw_gz is not None and result.typed_sha256 is not None


def wide_rows_over_the_memory_limit(cell: str) -> int:
    """Rows of 200 cells of ``cell`` that cost a little more than the limit allows."""
    from tl_xer.reader import row_memory

    values = [cell] * 200
    line = "\t".join(["%R", *values])
    return limits.MAX_ROW_MEMORY // row_memory(line, values, 200) + 1000


def test_more_memory_than_the_limit_is_a_refusal_not_a_slow_read() -> None:
    rows = wide_rows_over_the_memory_limit("12")  # about 35 000 rows of 200 two-character cells
    data = big_text(10, wide_rows=rows, wide_columns=200, cell="12")
    assert len(data) < limits.MAX_BYTES
    started = time.monotonic()
    result = read_xer_file(data)
    assert result.status == "refused"
    assert [p["code"] for p in result.report["problems"]] == ["too_many_cells"]
    assert time.monotonic() - started < 30


def test_cells_of_wide_characters_are_refused_by_the_reader_not_killed_by_the_envelope() -> None:
    """The review's file: 0x80 (the euro sign) in every cell cost 76 bytes a cell and reached the
    envelope's 1 GiB before the cell count refused it. Now the estimate refuses it first."""
    rows = wide_rows_over_the_memory_limit("\u20ac")
    data = big_text(10, wide_rows=rows, wide_columns=200, cell="\u20ac")
    assert len(data) < limits.MAX_BYTES
    result = read_xer_file(data)  # raises XerLimitError if the envelope ends the child
    assert result.status == "refused"
    assert [p["code"] for p in result.report["problems"]] == ["too_many_cells"]


def test_many_narrow_tables_are_a_refusal_by_their_rows_not_a_slow_read() -> None:
    """The reviewer's file: junk tables of one column, each under the per-table limit."""
    tables = limits.MAX_ROWS_TOTAL // 300_000 + 1
    junk = "".join(f"%T\tJ{n}\r\n%F\ta\r\n" + "%R\tx\r\n" * 300_000 for n in range(tables))
    text = "ERMHDR\t20.12\t2026-10-05\tProject\tu\tU\tDB\tPM\tUSD\r\n" + junk + "%E\r\n"
    started = time.monotonic()
    result = read_xer_file(text.encode())
    assert result.status == "refused"
    assert [p["code"] for p in result.report["problems"]] == ["too_many_rows"]
    assert time.monotonic() - started < 30


def test_more_rows_in_a_table_than_the_limit_is_a_refusal() -> None:
    lines = "\r\n".join("%R\tx" for _ in range(limits.MAX_ROWS_PER_TABLE + 1))
    text = (
        "ERMHDR\t20.12\t2026-10-05\tProject\tu\tU\tDB\tPM\tUSD\r\n"
        f"%T\tJUNK\r\n%F\ta\r\n{lines}\r\n%E\r\n"
    )
    result = read_xer_file(text.encode())
    assert [p["code"] for p in result.report["problems"]] == ["too_many_rows"]


def test_a_wbs_tree_deeper_than_the_limit_is_an_error_not_a_hang() -> None:
    depth = limits.MAX_WBS_DEPTH + 50
    nodes = "\r\n".join(
        f"%R\t{2000 + i}\t1\t{i}\tN\tD{i}\tDeep {i}\t{'100' if i == 0 else 2000 + i - 1}"
        for i in range(depth)
    )
    text = first_text()
    assert "%T\tPROJWBS\r\n" in text
    text = text.replace("\r\n%T\tTASK\r\n", f"\r\n{nodes}\r\n%T\tTASK\r\n", 1)
    started = time.monotonic()
    result = read_xer_file(encode(text))
    assert result.status == "invalid"
    assert "wbs_too_deep" in [p["code"] for p in result.report["problems"]]
    assert time.monotonic() - started < 10


def test_a_missing_required_table_costs_almost_nothing() -> None:
    started = time.monotonic()
    assert read_xer_file(encode(drop_table(first_text(), "TASK"))).status == "invalid"
    assert time.monotonic() - started < 5


# --- the typed JSON is made in pieces: a wide character does not widen the whole (round 3) -------

#: The envelope allows 1 GiB; the file at the typed maximum must fit in three quarters of it.
MARGIN_MB = 768


def test_a_file_at_the_typed_maximum_is_read_in_three_quarters_of_the_envelope() -> None:
    data = max_counts_text()
    assert 45 * 1024 * 1024 < len(data) <= limits.MAX_BYTES
    result = read_xer_file(data, memory_limit_mb=MARGIN_MB)
    assert result.status == "valid", result.report["problems"][:2]
    assert result.report["counts"]["codes"] == 300_000


def test_the_same_file_with_a_character_outside_latin_1_in_it_fits_the_same_margin() -> None:
    """An emoji in a code name used to make the whole typed text four bytes a character (and the
    envelope kill the child at 1 GiB); the text is now made in pieces of bytes."""
    data = max_counts_text(name_char="\U0001f600", code_name_len=1)
    result = read_xer_file(data, memory_limit_mb=MARGIN_MB)
    assert result.status == "valid", result.report["problems"][:2]
    assert result.snapshot is not None
    names = {row[3] for row in result.snapshot.tables["codes"]}
    assert "\U0001f600" in names


def test_quote_heavy_names_are_refused_by_the_budget_before_they_are_written() -> None:
    """A quote costs two bytes in the JSON; the budget counts them, so the file is refused as too
    large (a report) and not killed."""
    data = max_counts_text(name_char='"', code_name_len=120)
    result = read_xer_file(data, memory_limit_mb=MARGIN_MB)
    assert result.status == "invalid"
    assert "typed_too_large" in {p["code"] for p in result.report["problems"]}
