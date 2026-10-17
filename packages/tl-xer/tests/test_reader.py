"""The tokeniser: structure, encodings, control characters and every bound (P1-I4-T03)."""

from __future__ import annotations

import time

import pytest
from tl_xer import limits
from tl_xer.reader import detect_encoding, read_xer
from tl_xer.refusals import MESSAGES, XerRefusal
from xersupport import encode, first_text, replace_once

HEADER = "ERMHDR\t20.12\t2026-10-05\tProject\tu\tU\tDB\tPM\tUSD"


def tiny(*tables: str) -> bytes:
    """A small file from table sections written as ``name|col col|row;row``."""
    out = [HEADER]
    for spec in tables:
        name, columns, rows = spec.split("|")
        out.append(f"%T\t{name}")
        out.append("\t".join(["%F", *columns.split()]))
        for row in filter(None, rows.split(";")):
            out.append("\t".join(["%R", *row.split(",")]))
    out.append("%E")
    return ("\r\n".join(out) + "\r\n").encode()


def refusal_of(data: bytes) -> XerRefusal:
    with pytest.raises(XerRefusal) as caught:
        read_xer(data)
    return caught.value


def test_a_file_is_read_into_its_tables_in_file_order() -> None:
    raw = read_xer(encode(first_text()))
    assert [t.name for t in raw.tables][:5] == [
        "PROJECT",
        "CALENDAR",
        "PROJWBS",
        "TASK",
        "TASKPRED",
    ]
    task = raw.table("TASK")
    assert task is not None and len(task.rows) == 21
    assert raw.header[0] == "20.12" and raw.encoding == "cp1252"
    names = {row[task.index()["task_code"]] for row in task.rows}
    assert "A1230" in names


def test_windows_1252_text_is_decoded_as_windows_1252() -> None:
    raw = read_xer(encode(first_text()))
    task = raw.table("TASK")
    assert task is not None
    column = task.index()["task_name"]
    assert "Hydrotest – pipe rack lines" in {row[column] for row in task.rows}


def test_utf8_with_and_without_a_byte_order_mark_and_plain_ascii() -> None:
    text = first_text()
    as_utf8 = read_xer(text.encode("utf-8"))
    with_bom = read_xer(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert as_utf8.encoding == with_bom.encoding == "utf-8"
    assert as_utf8.tables == with_bom.tables == read_xer(encode(text)).tables
    plain = read_xer(tiny("T|a b|1,2"))
    assert plain.encoding == "ascii"


def test_the_encoding_is_decided_once_for_the_file() -> None:
    assert detect_encoding(b"abc")[0] == "ascii"
    assert detect_encoding("café".encode())[0] == "utf-8"
    assert detect_encoding("café".encode("cp1252"))[0] == "cp1252"
    # a valid UTF-8 multi-byte sequence at the very end of a chunk boundary is still UTF-8
    padded = b"a" * ((1 << 20) - 1) + "é".encode() + b"tail"
    assert detect_encoding(padded)[0] == "utf-8"


@pytest.mark.parametrize("bom", [b"\xff\xfe", b"\xfe\xff"])
def test_utf16_is_refused_with_its_own_code(bom: bytes) -> None:
    assert refusal_of(bom + "ERMHDR".encode("utf-16-le")).code == "unsupported_encoding"


def test_a_byte_that_windows_1252_leaves_undefined_is_refused() -> None:
    data = tiny("T|a|x").replace(b"x", b"\x81\xe9")  # 0x81 is undefined; \xe9 alone is not UTF-8
    assert refusal_of(data).code == "bad_encoding"


@pytest.mark.parametrize(
    "char",
    [
        "\x00",
        "\x01",
        "\x08",
        "\x0b",
        "\x1b",
        "\x7f",
        "\u0085",
        chr(0x202E),
        chr(0x2066),
        chr(0x200F),
        chr(0x2028),
        chr(0xFEFF),
    ],
)
def test_control_characters_and_direction_marks_refuse_the_file(char: str) -> None:
    text = f"{HEADER}\r\n%T\tT\r\n%F\ta\r\n%R\tx{char}y\r\n%E\r\n"
    assert refusal_of(text.encode("utf-8")).code == "control_character"


def test_a_nul_byte_is_refused_in_any_encoding() -> None:
    assert refusal_of(tiny("T|a|x").replace(b"x", b"x\x00y")).code == "control_character"


def test_a_lone_carriage_return_inside_a_line_is_refused() -> None:
    assert refusal_of(tiny("T|a|x").replace(b"x", b"x\ry")).code == "control_character"


def test_tabs_and_line_ends_inside_the_syntax_are_fine() -> None:
    raw = read_xer(tiny("T|a b c|1,,3"))
    assert raw.tables[0].rows == (("1", "", "3"),)


def test_lines_may_end_with_a_bare_line_feed_and_blank_lines_are_skipped() -> None:
    data = tiny("T|a|1").replace(b"\r\n", b"\n\n")
    assert read_xer(data).tables[0].rows == (("1",),)


def test_a_short_row_is_padded_and_a_long_row_is_refused() -> None:
    assert read_xer(tiny("T|a b c|1")).tables[0].rows == (("1", "", ""),)
    error = refusal_of(tiny("T|a|1,2"))
    assert (error.code, error.table, error.row) == ("ragged_row", "T", 1)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "not_xer"),
        (b"hello\r\n%E\r\n", "not_xer"),
        (b"%T\tT\r\n", "not_xer"),
        (HEADER.encode() + b"\r\n", "missing_end"),
        (b"ERMHDR" + b"\t1" * 25 + b"\r\n%E\r\n", "bad_header"),
        (b"ERMHDRX\t1\r\n%E\r\n", "bad_header"),
        (HEADER.encode() + b"\r\n%E\r\nmore\r\n", "data_after_end"),
        (HEADER.encode() + b"\r\n%Q\tx\r\n%E\r\n", "unknown_marker"),
        (HEADER.encode() + b"\r\nplain text\r\n%E\r\n", "unexpected_line"),
        (HEADER.encode() + b"\r\n%R\tx\r\n%E\r\n", "row_before_fields"),
        (HEADER.encode() + b"\r\n%F\ta\r\n%E\r\n", "fields_before_table"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%F\ta\r\n%F\tb\r\n%E\r\n", "fields_before_table"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%R\tx\r\n%E\r\n", "row_before_fields"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%E\r\n", "no_columns"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%F\r\n%E\r\n", "no_columns"),
        (HEADER.encode() + b"\r\n%T\tT\tU\r\n%E\r\n", "bad_table_marker"),
        (HEADER.encode() + b"\r\n%T\r\n%E\r\n", "bad_table_marker"),
        (HEADER.encode() + b"\r\n%T\t1bad\r\n%E\r\n", "bad_table_name"),
        (HEADER.encode() + b"\r\n%T\tA B\r\n%E\r\n", "bad_table_name"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%F\ta b\tc\r\n%E\r\n", "bad_field_name"),
        (HEADER.encode() + b"\r\n%T\tT\r\n%F\ta\ta\r\n%E\r\n", "duplicate_field"),
        (tiny("T|a|1").replace(b"%E", b"%T\tT\r\n%F\ta\r\n%E"), "duplicate_table"),
    ],
)
def test_malformed_files_are_refused_with_a_code_and_a_fixed_message(
    data: bytes, code: str
) -> None:
    error = refusal_of(data)
    assert error.code == code
    assert error.message == MESSAGES[code]


def test_a_refusal_never_carries_the_text_of_the_file() -> None:
    error = refusal_of(tiny("T|a|1,2").replace(b"1,2", b"SECRET-VALUE\tmore"))
    assert "SECRET" not in error.message and "SECRET" not in repr(error.__dict__)


def test_every_message_is_fixed_text() -> None:
    for code, message in MESSAGES.items():
        assert code and message and "{" not in message


# --- the bounds ---------------------------------------------------------------------------------


def test_a_file_over_the_byte_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    data = tiny("T|a|1")
    monkeypatch.setattr(limits, "MAX_BYTES", len(data) - 1)
    assert refusal_of(data).code == "too_large"
    monkeypatch.setattr(limits, "MAX_BYTES", len(data))
    assert read_xer(data).tables


def test_too_many_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_TABLES", 2)
    assert len(read_xer(tiny("A|a|", "B|a|")).tables) == 2
    assert refusal_of(tiny("A|a|", "B|a|", "C|a|")).code == "too_many_tables"


def test_too_many_columns_is_decided_before_the_line_is_split() -> None:
    wide = " ".join(f"c{i}" for i in range(limits.MAX_COLUMNS))
    assert len(read_xer(tiny(f"T|{wide}|")).tables[0].columns) == limits.MAX_COLUMNS
    assert refusal_of(tiny(f"T|{wide} extra|")).code == "too_many_columns"
    started = time.monotonic()
    hostile = HEADER.encode() + b"\r\n%T\tT\r\n%F\ta\r\n%R" + b"\t" * 5_000_000 + b"\r\n%E\r\n"
    assert refusal_of(hostile).code == "too_many_columns"
    assert time.monotonic() - started < 2


def test_too_many_rows_and_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_ROWS_PER_TABLE", 3)
    assert len(read_xer(tiny("T|a|1;2;3")).tables[0].rows) == 3
    error = refusal_of(tiny("T|a|1;2;3;4"))
    assert (error.code, error.table) == ("too_many_rows", "T")
    monkeypatch.setattr(limits, "MAX_ROWS_PER_TABLE", 100)
    monkeypatch.setattr(limits, "MIN_ROW_WEIGHT", 1)
    monkeypatch.setattr(limits, "MAX_CELLS", 6)
    assert read_xer(tiny("T|a b|1,2;3,4;5,6")).cells == 6
    assert refusal_of(tiny("T|a b|1,2;3,4;5,6;7,8")).code == "too_many_cells"


def test_the_rows_of_all_tables_together_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Many small tables, each under the per-table limit, still cost a tuple a row."""
    monkeypatch.setattr(limits, "MAX_ROWS_TOTAL", 5)
    two_tables = "\r\n".join(
        [HEADER, "%T\tA", "%F\ta", "%R\t1", "%R\t2", "%R\t3", "%T\tB", "%F\tb", "%R\t1", "%R\t2"]
    )
    assert read_xer((two_tables + "\r\n%E\r\n").encode()).cells == 5
    over = "\r\n".join([two_tables, "%R\t3", "%E", ""])
    error = refusal_of(over.encode())
    assert (error.code, error.table) == ("too_many_rows", None)


def test_a_narrow_row_weighs_as_many_cells_as_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """One column or sixteen, a row costs about the same: it counts as ``MIN_ROW_WEIGHT`` cells."""
    monkeypatch.setattr(limits, "MIN_ROW_WEIGHT", 4)
    monkeypatch.setattr(limits, "MAX_CELLS", 12)
    assert read_xer(tiny("T|a|1;2;3")).cells == 3  # 3 rows x 4 = 12: at the limit
    assert refusal_of(tiny("T|a|1;2;3;4")).code == "too_many_cells"  # 16 > 12 though 4 cells
    wide = tiny("T|a b c d e|1,2,3,4,5;1,2,3,4,5")  # 5 columns weigh 5 each: 10
    assert len(read_xer(wide).tables[0].rows) == 2
    assert refusal_of(tiny("T|a b c d e|1,2,3,4,5;1,2,3,4,5;1,2,3,4,5")).code == "too_many_cells"


def test_a_field_over_the_length_limit_is_refused_not_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_FIELD_CHARS", 5)
    assert read_xer(tiny("T|a|abcde")).tables[0].rows == (("abcde",),)
    error = refusal_of(tiny("T|a|abcdef"))
    assert (error.code, error.table, error.row) == ("field_too_long", "T", 1)


def test_a_header_field_over_its_limit_is_refused() -> None:
    long_field = "x" * (limits.MAX_HEADER_FIELD_CHARS + 1)
    assert refusal_of(f"ERMHDR\t{long_field}\r\n%E\r\n".encode()).code == "bad_header"


def test_names_over_the_name_limit_are_refused() -> None:
    long_name = "T" * (limits.MAX_NAME_CHARS + 1)
    assert refusal_of(f"{HEADER}\r\n%T\t{long_name}\r\n%E\r\n".encode()).code == "bad_table_name"
    assert (
        refusal_of(f"{HEADER}\r\n%T\tT\r\n%F\t{long_name}\r\n%E\r\n".encode()).code
        == "bad_field_name"
    )


def test_one_huge_line_without_tabs_is_refused_quickly() -> None:
    started = time.monotonic()
    data = HEADER.encode() + b"\r\n" + b"x" * (8 * 1024 * 1024) + b"\r\n%E\r\n"
    assert refusal_of(data).code == "unexpected_line"
    assert time.monotonic() - started < 2


def test_the_same_bytes_give_the_same_tables() -> None:
    data = encode(first_text())
    assert read_xer(data) == read_xer(data)


def test_a_table_may_be_empty() -> None:
    assert read_xer(tiny("T|a b|")).tables[0].rows == ()


def test_duplicate_detection_uses_the_exact_name() -> None:
    assert len(read_xer(tiny("T|a|", "t|a|")).tables) == 2


def test_replace_helper_is_exact() -> None:
    assert replace_once("abc", "b", "x") == "axc"
