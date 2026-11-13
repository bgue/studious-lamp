"""The count columns of the IWP log and the summary's filter arguments, as pure text (P2-I5
T06c1). No Textual, no pilot: the rows come from ``FakeClient`` with ``seed_iwp``."""

from __future__ import annotations

from fakes import FakeClient
from fakes_iwp import PROJECT, seed_iwp
from tl_mod_awp.iwp_counts import IwpCountRow
from tl_tui.iwp_text import (
    IWP_COLUMNS,
    IWP_COUNT_COLUMNS,
    IWP_COUNT_DROP,
    IWP_COUNT_RIGHT,
    IWP_DROP,
    IWP_RIGHT,
    iwp_cells,
    iwp_count_cells,
    iwp_summary,
)


def _rows() -> list:  # type: ignore[type-arg]
    client = FakeClient()
    seed_iwp(client)
    return client.list_iwps(PROJECT)


def _iwp(suffix: str):  # type: ignore[no-untyped-def]
    return next(row for row in _rows() if row.number.endswith(suffix))


def _count(number: str, **kw: object) -> IwpCountRow:
    fields: dict[str, object] = {
        "state_since": "2026-10-27",
        "ready_ok": 2,
        "ready_total": 3,
        "evaluated": True,
        "open_blocking": 1,
    }
    fields.update(kw)
    return IwpCountRow(number=number, **fields)  # type: ignore[arg-type]


def test_columns_extend_the_log_and_leave_the_web_columns_alone() -> None:
    assert IWP_COLUMNS == (
        "Number",
        "Subject",
        "State",
        "Discipline",
        "Foreman",
        "Planned start",
        "Scope",
        "Hours",
    )
    assert IWP_COUNT_COLUMNS == (*IWP_COLUMNS, "Ready", "Blocking", "Since")
    assert IWP_COUNT_DROP == (*IWP_DROP, "Since")
    assert IWP_COUNT_RIGHT == (*IWP_RIGHT, "Ready", "Blocking")


def test_count_cells_for_an_evaluated_iwp() -> None:
    row = _iwp("PIP-0002")  # Ready
    cells = iwp_count_cells(row, _count(row.number, ready_ok=2, ready_total=3, open_blocking=1))
    assert len(cells) == len(IWP_COUNT_COLUMNS)
    assert cells[: len(IWP_COLUMNS)] == iwp_cells(row)
    assert cells[len(IWP_COLUMNS) :] == ("2/3", "1", "2026-10-27")


def test_count_cells_for_a_never_evaluated_iwp() -> None:
    row = _iwp("PIP-0001")
    counts = _count(row.number, state_since=None, evaluated=False, ready_ok=0, ready_total=0)
    cells = iwp_count_cells(row, counts)
    assert cells[len(IWP_COLUMNS) :] == ("—", "1", "—")


def test_count_cells_when_there_is_no_count() -> None:
    row = _iwp("PIP-0001")
    assert iwp_count_cells(row, None)[len(IWP_COLUMNS) :] == ("—", "—", "—")


def test_summary_unchanged_for_the_old_calls() -> None:
    assert iwp_summary(7, 7) == "7 IWPs"
    assert iwp_summary(1, 1) == "1 IWP"
    assert iwp_summary(7, 3, state="Ready") == "3 of 7 IWPs, state Ready"
    assert iwp_summary(7, 2, foreman="user:sue") == "2 of 7 IWPs, foreman sue"


def test_summary_with_discipline_and_text() -> None:
    assert (
        iwp_summary(7, 3, state="Ready", discipline="Piping", text="rack")
        == "3 of 7 IWPs, state Ready, discipline Piping, filter 'rack'"
    )
    assert iwp_summary(7, 3, discipline="Piping") == "3 of 7 IWPs, discipline Piping"
    assert iwp_summary(7, 4, text="rack") == "4 of 7 IWPs, filter 'rack'"
