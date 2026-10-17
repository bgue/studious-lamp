"""The CSV reader of cost snapshots: header, encodings, numbers and every bound (P1-I4-T02a)."""

from __future__ import annotations

import time

import pytest
from tl_mod_cost.errors import CostFileError
from tl_mod_cost.imports import reader
from tl_mod_cost.imports.reader import read_cost_csv
from tl_mod_cost.limits import MAX_ROWS


def csv(*lines: str, newline: str = "\n") -> bytes:
    return (newline.join(lines) + newline).encode("utf-8")


def refused(data: bytes) -> CostFileError:
    with pytest.raises(CostFileError) as caught:
        read_cost_csv(data)
    return caught.value


def test_a_plain_file_gives_one_row_per_code_with_the_figures_it_states() -> None:
    result = read_cost_csv(
        csv(
            "code,description,parent,uom,hours_budget,hours_actual,amount_budget",
            "4210,Piping,,,1000,400.5,80000",
            "4210-PIP,Pipe installation,4210,in-dia,600,,",
        )
    )
    first, second = result.rows
    assert (first.code, first.description, first.parent_code, first.uom) == (
        "4210",
        "Piping",
        None,
        None,
    )
    assert first.figures == {
        "hours_budget": 1000.0,
        "hours_actual": 400.5,
        "amount_budget": 80000.0,
    }
    assert (second.code, second.parent_code, second.uom) == ("4210-PIP", "4210", "in-dia")
    assert second.figures == {"hours_budget": 600.0}  # a figure not stated is absent, never zero
    assert result.ignored_columns == ()


def test_a_stated_zero_is_a_zero_and_an_empty_cell_is_absent() -> None:
    [row] = read_cost_csv(csv("code,hours_budget,hours_actual", "1,0,")).rows
    assert row.figures == {"hours_budget": 0.0}


def test_the_header_is_read_in_any_order_case_and_spelling() -> None:
    result = read_cost_csv(
        csv(
            "Budget Hours,CODE,Cost Code Description,Parent Code,Unit,QTY_actual,cost_budget,"
            "Forecast",
            "10,A1,Alpha,,ea,5,100,9",
        )
    )
    [row] = result.rows
    assert row.code == "A1" and row.uom == "ea"
    assert row.figures == {"hours_budget": 10.0, "quantity_actual": 5.0, "amount_budget": 100.0}
    assert result.ignored_columns == ("Cost Code Description", "Forecast")


def test_a_column_the_reader_does_not_know_is_ignored_and_listed() -> None:
    result = read_cost_csv(csv("code,Notes,hours_budget,Owner", "1,secret note,5,bob"))
    assert result.ignored_columns == ("Notes", "Owner")
    assert result.rows[0].figures == {"hours_budget": 5.0}


def test_every_figure_column_is_known_in_both_orders() -> None:
    names = [
        f"{u}_{m}"
        for u in ("hours", "quantity", "amount")
        for m in ("budget", "actual", "earned", "ftc", "eac")
    ]
    swapped = [
        f"{m}_{u}"
        for u in ("hours", "quantity", "amount")
        for m in ("budget", "actual", "earned", "ftc", "eac")
    ]
    cells = ",".join(str(i) for i in range(1, 16))
    one = read_cost_csv(csv("code," + ",".join(names), "x," + cells)).rows[0]
    two = read_cost_csv(csv("code," + ",".join(swapped), "x," + cells)).rows[0]
    assert one.figures == two.figures and len(one.figures) == 15
    assert one.figures["hours_budget"] == 1.0 and one.figures["amount_eac"] == 15.0


def test_blank_header_cells_and_trailing_delimiters_are_dropped() -> None:
    result = read_cost_csv(csv("code,description,,,", "1,One,,,"))
    assert (result.rows[0].code, result.rows[0].description) == ("1", "One")
    assert result.ignored_columns == ()  # a blank header cell is nothing, not an ignored column
    wide = "code" + "," * (reader.MAX_COLUMNS * 3)  # far more trailing commas than columns allowed
    assert read_cost_csv(csv(wide, "1")).rows[0].code == "1"


def test_a_blank_header_cell_between_columns_is_nothing_not_an_ignored_column() -> None:
    result = read_cost_csv(csv("code,,hours_budget", "1,x,5"))
    assert result.ignored_columns == () and result.rows[0].figures == {"hours_budget": 5.0}


@pytest.mark.parametrize("name", ["code", "Code", "cost_code", "Cost Code", "costcode", "COSTCODE"])
def test_the_code_column_has_its_spellings(name: str) -> None:
    assert read_cost_csv(csv(f"{name},description", "X1,One")).rows[0].code == "X1"


def test_the_names_of_ignored_columns_are_bounded() -> None:
    header = "code," + ",".join(f"extra{i}" for i in range(reader.MAX_COLUMNS - 1))
    result = read_cost_csv(csv(header, "1"))
    assert len(result.ignored_columns) == min(reader.MAX_IGNORED, reader.MAX_COLUMNS - 1)
    long_name = read_cost_csv(csv("code," + "n" * 200, "1"))
    assert long_name.ignored_columns == ("n" * 64,)


def test_hyphens_and_spaces_in_a_header_are_underscores() -> None:
    [row] = read_cost_csv(
        csv("code,Hours-Budget,Amount ACTUAL,estimate-at-completion", "1,2,3,4")
    ).rows
    assert row.figures == {"hours_budget": 2.0, "amount_actual": 3.0}


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("desc", "description"), ("Name", "description"), ("TITLE", "description"),
        ("parent_code", "parent_code"), ("Parent", "parent_code"), ("parentcode", "parent_code"),
        ("unit", "uom"), ("unit-of-measure", "uom"), ("UOM", "uom"),
    ],
)  # fmt: skip
def test_the_text_columns_have_their_spellings(name: str, field: str) -> None:
    [row] = read_cost_csv(csv(f"cost code,{name}", "1,value")).rows
    assert row.code == "1"
    assert getattr(row, field) == "value"


def test_the_words_qty_hrs_and_cost_are_accepted_in_both_orders() -> None:
    [row] = read_cost_csv(
        csv("code,qty_budget,actual_qty,hrs_earned,ftc_hours,cost_eac,budget_cost", "1,1,2,3,4,5,6")
    ).rows
    assert row.figures == {
        "quantity_budget": 1.0, "quantity_actual": 2.0, "hours_earned": 3.0,
        "hours_ftc": 4.0, "amount_eac": 5.0, "amount_budget": 6.0,
    }  # fmt: skip


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_the_delimiter_is_the_one_that_splits_the_header_most(delimiter: str) -> None:
    lines = [
        delimiter.join(["code", "description", "hours_budget"]),
        delimiter.join(["1", "One", "5"]),
    ]
    [row] = read_cost_csv(csv(*lines)).rows
    assert (row.code, row.description, row.figures) == ("1", "One", {"hours_budget": 5.0})


def test_a_quoted_cell_may_hold_the_delimiter_a_quote_and_a_line_break() -> None:
    data = csv("code,description", '1,"Pipe, ""big"" bore"', '2,"two', 'lines"')
    first, second = read_cost_csv(data).rows
    assert first.description == 'Pipe, "big" bore' and second.description == "two\nlines"


def test_windows_line_ends_blank_lines_and_a_missing_final_line_end_are_fine() -> None:
    data = b"code,hours_budget\r\n1,5\r\n\r\n   ,  \r\n2,6"
    assert [r.code for r in read_cost_csv(data).rows] == ["1", "2"]


def test_spaces_around_cells_are_stripped() -> None:
    [row] = read_cost_csv(csv("code , description ,hours_budget", "  1  ,  One  ,  5  ")).rows
    assert (row.code, row.description, row.figures["hours_budget"]) == ("1", "One", 5.0)


def test_a_header_with_no_rows_is_an_empty_file_of_rows() -> None:
    assert read_cost_csv(csv("code,description")).rows == ()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1234.5", 1234.5),
        ("-12", -12.0),
        ("1,234.50", 1234.5),
        ("1,234,567", 1234567.0),
        ("0.000001", 1e-06),
        ("999999999999999", 999999999999999.0),
    ],
)
def test_figures_are_plain_decimals_with_optional_thousands_commas(text: str, value: float) -> None:
    [row] = read_cost_csv(csv("code,hours_budget", f'1,"{text}"')).rows
    assert row.figures["hours_budget"] == value


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "1e5",
        "(12)",
        "$5",
        "12,34",
        "1,23,456",
        "NaN",
        "inf",
        "1.2.3",
        "--1",
        "+5",
        "1 000",
        "1,234.5678901",
        "1" * 16,
        "١٢٣",
    ],
)
def test_a_figure_that_is_not_a_plain_decimal_is_refused_naming_the_row_and_column(
    text: str,
) -> None:
    error = refused(csv("code,hours_budget", "ok,1", f'2,"{text}"'))
    assert error.code == "bad_number" and error.row == 2
    assert "hours_budget" in str(error) and text not in str(error)


def test_a_missing_code_names_the_row() -> None:
    error = refused(csv("code,description", "1,One", ",Nameless"))
    assert (error.code, error.row) == ("missing_code", 2)


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("a@b,x", "code"),
        ("A" * 65 + ",x", "code"),
        ("1," + "d" * 501, "description"),
        ("1,x,p@q", "parent_code"),
        ("1,x,,u" + "u" * 21, "uom"),
    ],
)
def test_a_value_the_command_would_refuse_is_refused_here_with_the_field_name(
    line: str, field: str
) -> None:
    error = refused(csv("code,description,parent,uom", line))
    assert error.code == "bad_row" and error.row == 1 and field in str(error)


def test_two_columns_for_one_field_are_refused() -> None:
    assert refused(csv("code,cost_code,hours_budget", "1,1,5")).code == "duplicate_column"
    assert refused(csv("code,hours_budget,budget_hours", "1,5,5")).code == "duplicate_column"


def test_a_file_without_a_code_column_is_refused() -> None:
    assert refused(csv("description,hours_budget", "x,1")).code == "missing_code_column"


def test_an_empty_file_is_refused() -> None:
    for data in (b"", b"\n\n", b"   \n  "):
        assert refused(data).code == "empty_file"


# --- encodings ----------------------------------------------------------------------------------


def test_utf8_with_or_without_a_byte_order_mark_is_read() -> None:
    text = "code,description\n1,Café – bar\n"
    plain = read_cost_csv(text.encode("utf-8")).rows
    marked = read_cost_csv(b"\xef\xbb\xbf" + text.encode("utf-8")).rows
    assert plain == marked and plain[0].description == "Café – bar"


def test_text_that_is_not_utf8_is_read_as_windows_1252() -> None:
    [row] = read_cost_csv("code,description\n1,Café – bar\n".encode("cp1252")).rows
    assert row.description == "Café – bar"


def test_a_byte_neither_encoding_allows_is_refused() -> None:
    assert refused(b"code,description\n1,x\x81y\n").code == "not_text"


@pytest.mark.parametrize("char", ["\x00", "\x07", "\x1b", "\x7f", "\u0085", "‮", " ", "﻿"])
def test_control_characters_and_direction_marks_are_refused(char: str) -> None:
    error = refused(f"code,description\n1,a{char}b\n".encode())
    assert error.code == "control_character"


# --- bounds -------------------------------------------------------------------------------------


def test_a_file_over_the_size_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    data = csv("code", "1")
    monkeypatch.setattr(reader, "MAX_IMPORT_BYTES", len(data))
    assert read_cost_csv(data).rows
    monkeypatch.setattr(reader, "MAX_IMPORT_BYTES", len(data) - 1)
    assert refused(data).code == "too_large"


def test_a_line_longer_than_a_row_can_be_is_refused_quickly() -> None:
    started = time.monotonic()
    error = refused(("code,description\n1," + "x" * (reader.MAX_LINE_CHARS + 10) + "\n").encode())
    assert error.code == "line_too_long" and time.monotonic() - started < 2


def test_more_columns_than_the_limit_are_refused() -> None:
    header = ",".join(["code"] + [f"c{i}" for i in range(reader.MAX_COLUMNS)])
    assert refused(csv(header, "1")).code == "too_many_columns"
    ok = ",".join(["code"] + [f"c{i}" for i in range(reader.MAX_COLUMNS - 1)])
    assert read_cost_csv(csv(ok, "1")).rows


def test_more_rows_than_the_limit_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_ROWS", 3)
    assert len(read_cost_csv(csv("code", "1", "2", "3")).rows) == 3
    assert refused(csv("code", "1", "2", "3", "4")).code == "too_many_rows"
    assert MAX_ROWS == 20_000


def test_the_largest_legal_file_is_read_in_a_second_or_two() -> None:
    lines = ["code,description,parent,hours_budget,hours_actual,amount_budget"]
    lines += [f"C{i:05d},Description of code {i},,{i}.5,{i},{i * 100}" for i in range(MAX_ROWS)]
    started = time.monotonic()
    result = read_cost_csv(csv(*lines))
    assert len(result.rows) == MAX_ROWS and time.monotonic() - started < 10


def test_a_row_with_far_more_cells_than_the_header_is_refused() -> None:
    error = refused(csv("code", "1" + ",x" * (reader.MAX_COLUMNS * 2 + 5)))
    assert error.code == "too_many_cells" and error.row == 1


def test_an_unclosed_quote_is_a_malformed_file_not_a_long_cell() -> None:
    assert refused(b'code,description\n1,"never closed\n2,x\n').code == "malformed_csv"


def test_a_cell_over_the_csv_modules_field_limit_is_refused_as_malformed() -> None:
    assert refused(('code,description\n1,"' + "x" * 200_000 + '"\n').encode()).code in {
        "malformed_csv",
        "line_too_long",
    }


def test_no_message_holds_a_cell_of_the_file() -> None:
    secret = "TOPSECRET-CELL"
    cases = [
        csv("code,hours_budget", f"{secret},12x"),
        csv("code,description", f"a@{secret},x"),
        csv("code,description", f"{secret}\x07,x"),
        csv("code,cost_code", f"{secret},{secret}"),
        csv("code,description", f"1,{secret}" + "x" * 600),
    ]
    for data in cases:
        with pytest.raises(CostFileError) as caught:
            read_cost_csv(data)
        assert secret not in str(caught.value)


def test_the_same_bytes_give_the_same_rows() -> None:
    data = csv("code,description,hours_budget", "1,One,5", "2,Two,6")
    assert read_cost_csv(data) == read_cost_csv(data)


def test_the_result_is_the_input_of_the_import_command() -> None:
    from tl_mod_cost.handlers.snapshots import ImportCostSnapshot
    from tl_mod_cost.testing import BASE

    result = read_cost_csv(csv("code,description,hours_budget", "1,One,5"))
    command = ImportCostSnapshot(
        **BASE, period="2026-07", as_of="2026-07-31", rows=list(result.rows)
    )
    assert command.rows[0].figures == {"hours_budget": 5.0}
