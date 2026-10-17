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
from xersupport import big_text, drop_table, encode, first_text

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
    assert result.raw_gz is not None and result.typed_json is not None


def test_more_cells_than_the_limit_is_a_refusal_not_a_slow_read() -> None:
    columns = 16
    rows = limits.MAX_CELLS // columns + 1000
    data = big_text(10, wide_rows=rows, wide_columns=columns, short_cells=True)
    assert len(data) < limits.MAX_BYTES
    started = time.monotonic()
    result = read_xer_file(data)
    assert result.status == "refused"
    assert [p["code"] for p in result.report["problems"]] == ["too_many_cells"]
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
