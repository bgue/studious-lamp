"""Shared helpers: kinds, options, limits, the guard around ``extract`` (P1-I3B-S1)."""

from __future__ import annotations

import io

import pytest
from extractsupport import source_for
from tl_core.derivation import MAX_SOURCE_BYTES
from tl_extract.kinds import extension_of, file_kind
from tl_extract.options import TableOptions, parse_options
from tl_extract.reading import (
    MAX_MESSAGE_CHARS,
    CellBudget,
    Refusal,
    clean_metadata_text,
    has_unstorable_character,
    metadata_for,
    problem,
    read_exact,
    run_guarded,
    shown,
)


@pytest.mark.parametrize(
    ("filename", "content_type", "kind"),
    [
        ("index.csv", "text/csv", "csv"),
        ("index.CSV", "application/octet-stream", "csv"),
        ("index.tsv", "text/plain", "csv"),
        ("book.xlsx", "application/octet-stream", "xlsx"),
        ("scan.PDF", "application/pdf", "pdf"),
        ("scan.png", "image/png", "image"),
        ("scan.jpeg", "image/jpeg", "image"),
        ("scan.tif", "image/tiff", "image"),
        # the extension decides when it is ours, even against the content type
        ("report.pdf", "text/csv", "pdf"),
        # a revision code is not a file type: the content type decides
        ("ISD-001.A", "application/pdf", "pdf"),
        ("noext", "text/csv; charset=utf-8", "csv"),
        ("C:\\files\\a.csv", "x/y", "csv"),
        ("dir.csv/readme", "text/plain", None),
        ("data.xls", "application/vnd.ms-excel", None),
        ("a.bin", "application/octet-stream", None),
    ],
)
def test_file_kind(filename: str, content_type: str, kind: str | None) -> None:
    assert file_kind(source_for(filename, content_type, b"x")) == kind


def test_extension_of() -> None:
    assert extension_of("a/b\\c.TXT") == "txt"
    assert extension_of("archive.tar.gz") == "gz"
    assert extension_of("noext") == ""
    assert extension_of("dir.d/file") == ""


def test_options_default_and_valid() -> None:
    assert parse_options({}) == TableOptions()
    opts = parse_options(
        {"sheet": "Index", "header_row": 3, "delimiter": ";", "header_map": {"A": "b"}}
    )
    assert (opts.sheet, opts.header_row, opts.delimiter, opts.header_map) == (
        "Index",
        3,
        ";",
        {"A": "b"},
    )


@pytest.mark.parametrize(
    "options",
    [
        {"shet": "Index"},
        {"header_row": 0},
        {"header_row": 1001},
        {"header_row": "2"},
        {"delimiter": "x"},
        {"duplicate_headers": "merge"},
        {"header_map": {"a": ""}},
        {"header_map": {"a": 1}},
        {"sheet": ""},
        {"normalise_headers": "yes please"},
    ],
)
def test_a_bad_option_is_refused_and_the_value_is_not_echoed(options: dict[str, object]) -> None:
    with pytest.raises(Refusal) as caught:
        parse_options(options)
    assert caught.value.code == "bad_option"
    assert caught.value.message.startswith("option ")
    assert "please" not in caught.value.message and "merge" not in caught.value.message


def test_unstorable_characters() -> None:
    assert has_unstorable_character("a\x00b")
    assert has_unstorable_character("a\x1fb")
    assert has_unstorable_character("a\x7fb")
    assert has_unstorable_character("a\ud800b")
    assert not has_unstorable_character("tab\tCR\rLF\n é ü 日本")


def test_shown_cleans_and_cuts() -> None:
    assert shown("a\x00b\n  c") == "a?b c"
    assert shown("x" * 100, 10) == "x" * 9 + "…"
    assert shown("short") == "short"


def test_clean_metadata_text() -> None:
    assert clean_metadata_text(None) is None
    assert clean_metadata_text("  \x00  ") is None
    assert clean_metadata_text("A\x00 B \n C") == "A B C"
    assert clean_metadata_text("x" * 5000) == "x" * 1000
    assert clean_metadata_text("x" * 50, limit=10) == "x" * 10


def test_problem_messages_are_cut() -> None:
    assert len(problem("c", "m" * 1000).message) == MAX_MESSAGE_CHARS


def test_read_exact_reads_the_stated_size_and_refuses_anything_else() -> None:
    data = b"0123456789"
    assert read_exact(source_for("a.csv", "text/csv", data), io.BytesIO(data)) == data
    source = source_for("a.csv", "text/csv", data)
    for stream in (io.BytesIO(data + b"x"), io.BytesIO(data[:-1])):
        with pytest.raises(Refusal) as caught:
            read_exact(source, stream)
        assert caught.value.code == "size_mismatch"


def test_read_exact_refuses_a_source_over_the_limit_before_reading() -> None:
    source = source_for("a.csv", "text/csv", b"x").model_copy(update={"size": MAX_SOURCE_BYTES + 1})

    class Unreadable(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise AssertionError("must not read")

    with pytest.raises(Refusal) as caught:
        read_exact(source, Unreadable())
    assert caught.value.code == "source_too_large"
    exactly = source.model_copy(update={"size": MAX_SOURCE_BYTES})
    with pytest.raises(Refusal) as caught2:  # at the limit it reads, and the stream is short
        read_exact(exactly, io.BytesIO(b"abc"))
    assert caught2.value.code == "size_mismatch"


def test_metadata_for_carries_the_sources_facts() -> None:
    source = source_for("a.pdf", "application/pdf", b"abc")
    meta = metadata_for(source, page_count=3, title="T")
    assert (meta.content_type, meta.size, meta.sha256) == (
        "application/pdf",
        3,
        source.sha256,
    )
    assert (meta.page_count, meta.title, meta.author) == (3, "T", None)


def test_run_guarded_turns_a_refusal_into_a_failed_result() -> None:
    source = source_for("a.csv", "text/csv", b"abc")

    def refuse() -> None:
        raise Refusal("too_many_rows", "the file has more than 20000 data rows", row=7)

    result = run_guarded("x", "9", source, refuse)  # type: ignore[arg-type]
    assert (result.extractor, result.extractor_version, result.status) == ("x", "9", "failed")
    assert [(p.code, p.row) for p in result.problems] == [("too_many_rows", 7)]
    assert result.metadata is not None and result.metadata.sha256 == source.sha256


@pytest.mark.parametrize("error", [ValueError("/home/secret/x"), RecursionError(), MemoryError()])
def test_run_guarded_hides_any_other_error(error: Exception) -> None:
    source = source_for("a.csv", "text/csv", b"abc")

    def boom() -> None:
        raise error

    result = run_guarded("x", "1", source, boom)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert [p.code for p in result.problems] == ["unreadable"]
    assert "secret" not in result.problems[0].message


def test_the_cell_budget_refuses_past_its_limits() -> None:
    budget = CellBudget()
    budget.take(["a", None, "bc"])
    assert (budget.cells, budget.chars) == (3, 3)
    with pytest.raises(Refusal) as caught:
        CellBudget(cells=999_999).take(["a", "b"])
    assert caught.value.code == "too_many_cells"
    with pytest.raises(Refusal) as caught2:
        CellBudget(chars=64 * 1024 * 1024).take(["a"])
    assert caught2.value.code == "too_much_text"
