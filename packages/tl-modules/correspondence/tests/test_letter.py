"""A letter from a template to a deterministic PDF (P1-I5-T07d)."""

from __future__ import annotations

import hashlib
import re

import pytest
from tl_mod_correspondence import letter as lt

FIELDS = lt.LetterFields(
    number="P123-COR-0002",
    date="2026-10-17",
    subject="Revised programme",
    to="Meridian Energy",
    body="We confirm the revised programme.",
)


def test_a_template_takes_the_fields_by_name() -> None:
    text = lt.fill_template(
        "Ref {number} of {date}: {subject} for {to}. {body}", FIELDS.as_mapping()
    )
    assert text == (
        "Ref P123-COR-0002 of 2026-10-17: Revised programme for Meridian Energy. "
        "We confirm the revised programme."
    )


def test_a_field_the_letter_does_not_have_is_refused_by_name() -> None:
    with pytest.raises(lt.LetterError, match=r"\{secret\}"):
        lt.fill_template("Hello {secret}", FIELDS.as_mapping())


def test_braces_that_are_not_a_field_name_stay_and_nothing_is_evaluated() -> None:
    text = "{0} {} {a.b} {number.__class__} {Number} {{number}}"
    assert lt.fill_template(text, FIELDS.as_mapping()) == (
        "{0} {} {a.b} {number.__class__} {Number} {P123-COR-0002}"
    )


def test_a_value_that_looks_like_a_placeholder_is_not_filled_again() -> None:
    mapping = {**FIELDS.as_mapping(), "subject": "{body}"}
    assert lt.fill_template("{subject}", mapping) == "{body}"


def test_the_letter_has_its_parts_in_order() -> None:
    lines = lt.compose_letter("ACME CONSTRUCTION", "Kind regards, {number}", FIELDS)
    assert lines == [
        "ACME CONSTRUCTION",
        "",
        "Our ref: P123-COR-0002",
        "Date: 2026-10-17",
        "",
        "To: Meridian Energy",
        "",
        "Subject: Revised programme",
        "",
        "We confirm the revised programme.",
        "",
        "Kind regards, P123-COR-0002",
    ]


def test_a_letter_without_header_or_footer_has_neither() -> None:
    lines = lt.compose_letter(None, None, FIELDS)
    assert lines[0] == "Our ref: P123-COR-0002" and lines[-1] == "We confirm the revised programme."


def test_long_lines_wrap_and_paragraphs_stay_apart() -> None:
    body = "word " * 60 + "\n\nSecond paragraph"
    lines = lt.compose_letter(None, None, lt.LetterFields("N", "D", "S", "T", body))
    assert all(len(line) <= lt.LINE_WIDTH for line in lines)
    assert "" in lines[9:] and lines[-1] == "Second paragraph"


def test_tabs_and_control_characters_are_cleaned() -> None:
    lines = lt.compose_letter(None, None, lt.LetterFields("N", "D", "S", "T", "a\tb\x00c\x1bd‮e"))
    assert lines[-1] == "a    b c d e"


def test_a_letter_over_the_character_bound_is_refused() -> None:
    with pytest.raises(lt.LetterError, match="characters"):
        lt.compose_letter(None, None, lt.LetterFields("N", "D", "S", "T", "x" * lt.MAX_CHARS))


def test_the_pdf_is_a_structurally_sound_file() -> None:
    pdf = lt.render_pdf(lt.compose_letter(None, None, FIELDS), "Letter P123-COR-0002")
    assert pdf.startswith(b"%PDF-1.4\n") and pdf.endswith(b"%%EOF\n")
    start = re.search(rb"startxref\n(\d+)\n%%EOF\n$", pdf)
    assert start is not None
    xref_at = int(start.group(1))
    assert pdf[xref_at : xref_at + 5] == b"xref\n"
    header = re.match(rb"xref\n0 (\d+)\n", pdf[xref_at:])
    assert header is not None
    size = int(header.group(1))
    entries = pdf[xref_at + header.end() : xref_at + header.end() + 20 * size]
    rows = [entries[i : i + 20] for i in range(0, len(entries), 20)]
    assert rows[0] == b"0000000000 65535 f \n"
    for number, row in enumerate(rows[1:], start=1):
        offset = int(row[:10])
        assert pdf[offset : offset + len(f"{number} 0 obj\n")] == f"{number} 0 obj\n".encode()
    trailer = pdf[xref_at + header.end() + 20 * size :]
    assert trailer.startswith(b"trailer\n<< /Size " + str(size).encode() + b" /Root 1 0 R")


def test_the_text_is_in_the_content_stream_with_brackets_escaped() -> None:
    fields = lt.LetterFields("N", "D", r"Re (urgent) \ done", "T", "b")
    pdf = lt.render_pdf(lt.compose_letter(None, None, fields), "t")
    assert rb"(Subject: Re \(urgent\) \\ done) Tj" in pdf


def test_a_character_windows_1252_cannot_show_becomes_a_question_mark() -> None:
    pdf = lt.render_pdf(["café 中"], "t")
    assert b"(caf\xe9 ?) Tj" in pdf


def test_the_same_letter_gives_the_same_bytes_and_a_different_one_does_not() -> None:
    lines = lt.compose_letter("H", "F", FIELDS)
    first = lt.render_pdf(lines, "title")
    assert lt.render_pdf(lines, "title") == first
    assert (
        hashlib.sha256(first).hexdigest()
        == hashlib.sha256(lt.render_pdf(lines, "title")).hexdigest()
    )
    assert lt.render_pdf(lines, "other title") != first
    assert lt.render_pdf([*lines, "more"], "title") != first


def test_the_file_holds_no_date_and_no_random_id() -> None:
    pdf = lt.render_pdf(["x"], "t")
    for banned in (b"CreationDate", b"ModDate", b"/ID", b"Producer"):
        assert banned not in pdf


def test_a_long_letter_is_laid_on_several_pages() -> None:
    lines = [f"line {i}" for i in range(lt.LINES_PER_PAGE * 2 + 1)]
    pdf = lt.render_pdf(lines, "t")
    assert b"/Count 3 " in pdf and pdf.count(b"/Type /Page ") == 3


def test_an_empty_letter_is_one_empty_page() -> None:
    assert b"/Count 1 " in lt.render_pdf([], "t")


def test_more_pages_than_the_bound_is_refused() -> None:
    too_many = ["x"] * (lt.LINES_PER_PAGE * lt.MAX_PAGES + 1)
    with pytest.raises(lt.LetterError, match="pages"):
        lt.render_pdf(too_many, "t")
    assert lt.render_pdf(too_many[:-1], "t")  # exactly the bound is fine
