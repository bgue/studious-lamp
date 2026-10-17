"""``read_csv``: a CSV file into a ``RawGrid`` (P1-I3B-T09a)."""

from __future__ import annotations

import pytest
from tl_core.derivation import MAX_CELL_CHARS, MAX_COLUMNS, MAX_ROWS
from tl_extract import reading
from tl_extract.csvgrid import MAX_LINE_CHARS, decode_text, detect_delimiter, read_csv
from tl_extract.options import TableOptions
from tl_extract.reading import Refusal

OPTIONS = TableOptions()


def read(text: str | bytes, **options: object) -> list[list[str | None]]:
    raw = text if isinstance(text, bytes) else text.encode("utf-8")
    return read_csv(raw, TableOptions.model_validate(options)).rows


def refusal(raw: bytes, **options: object) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_csv(raw, TableOptions.model_validate(options))
    return caught.value


def test_a_csv_becomes_records_of_raw_cell_text() -> None:
    grid = read_csv(b"TAG NO,SERVICE\n47-FV-1001,Feed gas\n47-FV-1002,\n", OPTIONS)
    assert grid.rows == [["TAG NO", "SERVICE"], ["47-FV-1001", "Feed gas"], ["47-FV-1002"]]
    assert (grid.sheet, grid.sheet_names, grid.skipped_blank_rows, grid.notes) == (
        None,
        None,
        0,
        [],
    )
    assert grid.meta.title is None and grid.meta.created is None


def test_cells_are_not_stripped_but_empty_cells_are_none() -> None:
    assert read("A,B,C\n x , ,z\n") == [["A", "B", "C"], [" x ", " ", "z"]]
    assert read("A,B,C\n,b,\n") == [["A", "B", "C"], [None, "b"]]


def test_trailing_empty_cells_are_dropped_and_inner_ones_kept() -> None:
    assert read("A,B,C,D,\n1,,3,,\n") == [["A", "B", "C", "D"], ["1", None, "3"]]


def test_a_utf8_byte_order_mark_is_ignored() -> None:
    assert read(b"\xef\xbb\xbfA,B\n1,2\n") == [["A", "B"], ["1", "2"]]


def test_utf16_with_a_byte_order_mark_is_read() -> None:
    text = "A\tB\n1\täö\n"
    assert read(text.encode("utf-16")) == [["A", "B"], ["1", "äö"]]
    assert read(b"\xfe\xff" + text.encode("utf-16-be")) == [["A", "B"], ["1", "äö"]]


def test_text_that_is_not_utf8_is_refused() -> None:
    error = refusal("A,B\n1,caf\xe9\n".encode("latin-1"))
    assert error.code == "not_utf8"
    assert "UTF-8" in error.message
    assert refusal(b"\x00\xff" * 64).code == "not_utf8"
    assert refusal(b"\xff\xfe\x00").code == "not_utf8"  # a UTF-16 mark, then half a character


def test_decode_text() -> None:
    assert decode_text(b"\xef\xbb\xbfhi") == "hi"
    assert decode_text(b"") == ""


@pytest.mark.parametrize(("delimiter", "name"), [(";", "semicolon"), ("\t", "tab"), ("|", "bar")])
def test_the_delimiter_is_found_in_the_header_and_noted(delimiter: str, name: str) -> None:
    text = delimiter.join(["A", "B", "C"]) + "\n" + delimiter.join(["1", "2", "3"]) + "\n"
    grid = read_csv(text.encode(), OPTIONS)
    assert grid.rows == [["A", "B", "C"], ["1", "2", "3"]]
    assert grid.notes == [f"delimiter detected: {name}"]


def test_a_comma_is_the_default_and_is_not_noted() -> None:
    assert read_csv(b"A,B\n1,2\n", OPTIONS).notes == []
    assert read_csv(b"A\n1\n", OPTIONS).notes == []  # one column: nothing splits the header


def test_a_delimiter_inside_quotes_does_not_count() -> None:
    grid = read_csv(b'"A;1","B;2",C\n1,2,3\n', OPTIONS)
    assert grid.rows[0] == ["A;1", "B;2", "C"] and grid.notes == []


def test_ties_go_to_the_earlier_candidate() -> None:
    assert detect_delimiter("a,b;c\n", 1) == ","
    assert detect_delimiter("a;b|c\n", 1) == ";"
    assert detect_delimiter("", 1) == ","


def test_detection_reads_the_header_row_not_the_first() -> None:
    text = "Title, with, commas, everywhere\nA;B\n1;2\n"
    grid = read_csv(text.encode(), TableOptions(header_row=2))
    assert grid.rows[1] == ["A", "B"] and grid.notes == ["delimiter detected: semicolon"]


def test_an_explicit_delimiter_wins_and_is_not_noted() -> None:
    grid = read_csv(b"A,B;C\n1,2;3\n", TableOptions(delimiter=";"))
    assert grid.rows == [["A,B", "C"], ["1,2", "3"]] and grid.notes == []


def test_quoted_cells_may_hold_delimiters_quotes_and_line_breaks() -> None:
    grid = read_csv(b'A,B\n"x, y","say ""hi""\nsecond line"\n', OPTIONS)
    assert grid.rows[1] == ["x, y", 'say "hi"\nsecond line']


def test_line_endings_may_be_lf_crlf_or_cr() -> None:
    expected = [["A", "B"], ["1", "2"], ["3", "4"]]
    assert read("A,B\n1,2\n3,4\n") == expected
    assert read("A,B\r\n1,2\r\n3,4\r\n") == expected
    assert read("A,B\r1,2\r3,4\r") == expected
    assert read("A,B\n1,2\n3,4") == expected


def test_blank_data_records_are_skipped_and_counted() -> None:
    grid = read_csv(b"A,B\n\n1,2\n,,\n  , \n3,4\n\n", OPTIONS)
    assert grid.rows == [["A", "B"], ["1", "2"], ["3", "4"]]
    assert grid.skipped_blank_rows == 4


def test_records_up_to_the_header_are_kept_as_they_are() -> None:
    grid = read_csv(b"Instrument index\n\nA,B\n1,2\n\n3,4\n", TableOptions(header_row=3))
    assert grid.rows == [["Instrument index"], [], ["A", "B"], ["1", "2"], ["3", "4"]]
    assert grid.skipped_blank_rows == 1


def test_an_empty_file_has_no_records() -> None:
    assert read(b"") == []
    assert read(b"\xef\xbb\xbf") == []


def test_a_record_is_cut_after_the_column_limit_plus_one() -> None:
    wide = ",".join(f"c{i}" for i in range(MAX_COLUMNS + 50))
    rows = read(wide + "\n" + wide + "\n")
    assert len(rows[0]) == MAX_COLUMNS + 1 and rows[0][-1] == f"c{MAX_COLUMNS}"
    assert len(rows[1]) == MAX_COLUMNS + 1


def test_a_quote_that_is_never_closed_is_refused() -> None:
    error = refusal(b'A,B\n1,"never closed\n2,3\n')
    assert error.code == "malformed_csv"
    assert "line" in error.message


def test_a_quote_in_the_middle_of_a_cell_is_refused() -> None:
    assert refusal(b'A,B\n1,"x"y\n').code == "malformed_csv"


def test_a_cell_over_the_csv_field_limit_is_refused() -> None:
    error = refusal(b"A\n" + b"x" * 200_000 + b"\n")
    assert error.code == "cell_too_long"
    assert "x" * 20 not in error.message


def test_a_cell_over_the_cell_limit_but_under_the_field_limit_is_returned_whole() -> None:
    # the limit of a cell is enforced where headers and cells are read as a table
    long = "x" * (MAX_CELL_CHARS + 1)
    assert read(f"A\n{long}\n")[1] == [long]


def test_a_line_far_longer_than_any_row_can_be_is_refused_before_it_is_split() -> None:
    error = refusal(b"A\n" + b"," * (MAX_LINE_CHARS + 1) + b"\n")
    assert error.code == "record_too_long"


def test_exactly_the_row_limit_is_read_and_one_more_is_refused() -> None:
    body = "A\n" + "x\n" * MAX_ROWS
    assert len(read(body)) == MAX_ROWS + 1
    error = refusal((body + "x\n").encode())
    assert error.code == "too_many_rows"
    assert str(MAX_ROWS) in error.message


def test_blank_records_do_not_count_toward_the_row_limit() -> None:
    assert len(read("A\n" + "\n" * 30_000 + "x\n")) == 2


def test_too_many_cells_is_refused_while_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reading, "MAX_CELLS", 20)
    # MAX_CELLS counts data cells, as the contract's does: the header is free
    assert len(read("A,B\n" + "1,2\n" * 10)) == 11  # 20 data cells
    assert refusal(("A,B\n" + "1,2\n" * 11).encode()).code == "too_many_cells"


def test_too_much_text_is_refused_while_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reading, "MAX_TOTAL_CHARS", 30)
    assert len(read("A\n" + "y" * 10 + "\n")) == 2  # 11 characters
    assert refusal(("A\n" + ("y" * 10 + "\n") * 4).encode()).code == "too_much_text"


def test_a_nul_and_other_control_characters_pass_through_for_the_table_to_judge() -> None:
    assert read("A,B\nx\x00y,z\x07\n")[1] == ["x\x00y", "z\x07"]


def test_reading_is_deterministic_and_leaks_nothing() -> None:
    raw = "A;B\nä;ö\n".encode()
    assert read_csv(raw, OPTIONS) == read_csv(raw, OPTIONS)
    error = refusal(b'A\n"open\n')
    assert "Traceback" not in error.message and "/home" not in error.message


def test_the_source_is_not_changed_by_reading() -> None:
    raw = bytearray(b"A,B\n1,2\n")
    before = bytes(raw)
    read_csv(bytes(raw), OPTIONS)
    assert bytes(raw) == before


def test_a_title_block_above_the_header_does_not_use_up_the_cell_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reading, "MAX_CELLS", 4)
    title_block = "t1,t2,t3,t4,t5,t6\n" * 3
    assert len(read(title_block + "A,B\n1,2\n3,4\n", header_row=4)) == 6


def test_a_unicode_error_in_the_middle_of_a_long_file_is_refused() -> None:
    raw = b"A\n" + b"ok\n" * 10_000 + b"caf\xe9\n"
    assert refusal(raw).code == "not_utf8"
