"""The largest legal table passes through the envelope (security re-review of ce5ac64).

20 000 rows of 50 columns of 50-character cells is 1 000 000 cells (`MAX_CELLS`) in a CSV just
under the 50 MiB source limit. Sent with every column name in every row its JSON would be several
times the CSV; rows travel as lists in column order, so the answer is about the size of the text.
"""

from __future__ import annotations

import pytest
from extractsupport import source_for
from tl_core.derivation import MAX_CELLS, MAX_COLUMNS, MAX_ROWS, MAX_SOURCE_BYTES
from tl_core.derivation.envelope import MAX_ANSWER_BYTES
from tl_core.derivation.isolated import _wire, run_isolated  # pyright: ignore[reportPrivateUsage]

COLUMNS = 50
CELL = 50


def largest_csv() -> bytes:
    header = ",".join(f"column_{n:02d}" for n in range(COLUMNS))
    row = ",".join("x" * CELL for _ in range(COLUMNS))
    return ("\n".join([header, *[row] * MAX_ROWS]) + "\n").encode()


@pytest.mark.slow
def test_a_table_of_the_largest_legal_size_extracts_end_to_end() -> None:
    data = largest_csv()
    assert COLUMNS <= MAX_COLUMNS and COLUMNS * MAX_ROWS == MAX_CELLS
    assert 0.9 * MAX_SOURCE_BYTES < len(data) <= MAX_SOURCE_BYTES
    result = run_isolated(source_for("big.csv", "text/csv", data), data, timeout_s=120)
    assert result.status == "ok" and result.problems == []
    assert len(result.rows) == MAX_ROWS and list(result.rows[0]) == result.columns
    assert result.rows[-1]["column_49"] == "x" * CELL
    # the point of the wire format: the answer is about the size of the text, far below the cap
    assert len(_wire(result)) < 1.1 * len(data) < MAX_ANSWER_BYTES
