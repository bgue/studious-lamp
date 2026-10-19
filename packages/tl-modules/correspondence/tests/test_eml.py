"""Reading an email file: what it takes, and a corpus of hostile messages it refuses (P1-I5-T11a).

Every refusal is ``EmlRefused`` with a fixed text; none repeats part of the message, none is a
crash, and none leaves a process running (the isolated form is tested too).
"""

from __future__ import annotations

import socket
from email.message import EmailMessage
from typing import Any

import pytest
from tl_mod_correspondence import eml
from tl_mod_correspondence.eml import EmlLimits, EmlRefused, parse_eml
from tl_mod_correspondence.eml_isolated import parse_eml_isolated


def simple(**headers: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Pat Jones <pat@meridian.example>"
    msg["To"] = "Project Manager <pm@acme.example>, site@acme.example"
    msg["Cc"] = "Copy Person <copy@acme.example>"
    msg["Subject"] = "Revised programme"
    msg["Date"] = "Fri, 16 Oct 2026 10:00:00 +0000"
    msg["Message-ID"] = "<abc123@mail.meridian.example>"
    msg["In-Reply-To"] = "<prev@mail.acme.example>"
    msg["References"] = "<first@mail.acme.example> <prev@mail.acme.example>"
    for name, value in headers.items():
        del msg[name.replace("_", "-")]
        msg[name.replace("_", "-")] = value
    msg.set_content("Please confirm the revised programme.\nRegards, Pat")
    return msg


def refused(data: bytes, limits: EmlLimits | None = None) -> str:
    with pytest.raises(EmlRefused) as caught:
        parse_eml(data, limits)
    return str(caught.value)


# --- what it takes ---------------------------------------------------------------------------


def test_a_plain_message_gives_its_headers_and_body() -> None:
    got = parse_eml(simple().as_bytes())
    assert got.subject == "Revised programme"
    assert (got.from_name, got.from_email) == ("Pat Jones", "pat@meridian.example")
    assert [(a.name, a.email) for a in got.to] == [
        ("Project Manager", "pm@acme.example"),
        (None, "site@acme.example"),
    ]
    assert [(a.name, a.email) for a in got.cc] == [("Copy Person", "copy@acme.example")]
    assert got.sent_on == "2026-10-16"
    assert got.message_id == "abc123@mail.meridian.example"
    assert got.in_reply_to == "prev@mail.acme.example"
    assert got.references == ("first@mail.acme.example", "prev@mail.acme.example")
    assert got.body == "Please confirm the revised programme.\nRegards, Pat"
    assert (got.html_only, got.attachments) == (False, ())


def test_an_encoded_subject_and_a_non_ascii_body_are_decoded() -> None:
    msg = simple()
    del msg["Subject"]
    msg["Subject"] = "Zeitplan für die Überprüfung"
    msg.set_content("Grüße aus Köln, ½ Stunde", charset="iso-8859-1")
    got = parse_eml(msg.as_bytes())
    assert got.subject == "Zeitplan für die Überprüfung"
    assert got.body == "Grüße aus Köln, ½ Stunde"


def test_white_space_of_any_kind_is_folded_to_one_space() -> None:
    """A line or paragraph separator is white space: it folds, and so cannot break a table."""
    raw = "From: a@b.example\nSubject: line\u2028one\u2029two\x0bthree\n\nbody\n".encode()
    assert parse_eml(raw).subject == "line one two three"


def test_a_folded_subject_is_one_line() -> None:
    raw = b"From: a@b.example\nSubject: first line\n  second   line\n\nbody\n"
    assert parse_eml(raw).subject == "first line second line"


def test_attachments_are_carried_with_their_names_and_types() -> None:
    msg = simple()
    msg.add_attachment(b"%PDF-1.7 data", maintype="application", subtype="pdf", filename="spec.pdf")
    msg.add_attachment(b"PNGDATA", maintype="image", subtype="png", filename="plan.png")
    got = parse_eml(msg.as_bytes())
    assert [(a.filename, a.content_type, a.data) for a in got.attachments] == [
        ("spec.pdf", "application/pdf", b"%PDF-1.7 data"),
        ("plan.png", "image/png", b"PNGDATA"),
    ]
    assert got.body is not None and got.body.startswith("Please confirm")


def test_a_message_with_only_html_has_no_body_and_says_so() -> None:
    msg = EmailMessage()
    msg["From"] = "a@b.example"
    msg["Subject"] = "Newsletter"
    msg.set_content(
        "<html><body><a href='http://evil.example/x'>click</a></body></html>", subtype="html"
    )
    got = parse_eml(msg.as_bytes())
    assert got.body is None and got.html_only is True and got.attachments == ()


def test_the_plain_part_wins_over_the_html_part() -> None:
    msg = simple()
    msg.add_alternative("<p>HTML version</p>", subtype="html")
    got = parse_eml(msg.as_bytes())
    assert got.body == "Please confirm the revised programme.\nRegards, Pat"
    assert got.html_only is False


def test_a_nested_message_is_one_attachment_and_is_not_opened() -> None:
    inner = simple()
    outer = EmailMessage()
    outer["From"] = "fwd@acme.example"
    outer["Subject"] = "Fwd: Revised programme"
    outer.set_content("see attached")
    outer.add_attachment(inner)
    got = parse_eml(outer.as_bytes())
    [attachment] = got.attachments
    assert attachment.content_type == "message/rfc822"
    assert b"Revised programme" in attachment.data
    assert got.subject == "Fwd: Revised programme" and got.body == "see attached"


def test_a_message_without_date_or_ids_has_none_of_them() -> None:
    got = parse_eml(b"From: a@b.example\nSubject: x\n\nbody\n")
    assert (got.sent_on, got.message_id, got.in_reply_to, got.references) == (None, None, None, ())
    assert parse_eml(b"From: a@b.example\nDate: not a date\n\nb\n").sent_on is None


def test_names_are_cut_to_a_name_and_an_empty_one_is_numbered() -> None:
    msg = simple()
    msg.add_attachment(
        b"1", maintype="application", subtype="octet-stream", filename="../../etc/passwd"
    )
    msg.add_attachment(
        b"2", maintype="application", subtype="octet-stream", filename="C:\\Temp\\x.exe"
    )
    msg.add_attachment(b"3", maintype="application", subtype="octet-stream", filename="..")
    got = parse_eml(msg.as_bytes())
    assert [a.filename for a in got.attachments] == ["passwd", "x.exe", "attachment-3"]


def test_an_attachment_with_a_bad_declared_type_is_octet_stream() -> None:
    raw = (
        b"From: a@b.example\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: text/plain\n\nhi\n--B\nContent-Type: application/x y;z\n"
        b'Content-Disposition: attachment; filename="f.bin"\n\nDATA\n--B--\n'
    )
    [attachment] = parse_eml(raw).attachments
    assert attachment.content_type == "application/octet-stream"


# --- the corpus of hostile messages ------------------------------------------------------------


def test_a_message_over_the_size_limit_is_refused_before_it_is_parsed() -> None:
    limits = EmlLimits(max_bytes=1000)
    assert refused(simple().as_bytes() + b"x" * 2000, limits) == eml.TOO_BIG
    assert refused(b"   \n  ") == "the message is empty"


def test_too_many_headers_or_a_huge_header_is_refused() -> None:
    many = b"".join(f"X-H{i}: v\n".encode() for i in range(300))
    assert "too many headers" in refused(b"From: a@b.example\n" + many + b"\nbody\n")
    huge = b"From: a@b.example\nX-Big: " + b"a" * 5000 + b"\n\nbody\n"
    assert "longer than the limit" in refused(huge)


def test_too_many_parts_or_too_deep_a_nesting_is_refused() -> None:
    parts = b"".join(b"--B\nContent-Type: text/plain\n\nx\n" for _ in range(80))
    wide = b"From: a@b.example\nContent-Type: multipart/mixed; boundary=B\n\n" + parts + b"--B--\n"
    assert "too many parts" in refused(wide)
    raw = b"From: a@b.example\n"
    for depth in range(40):
        raw += f"Content-Type: multipart/mixed; boundary=B{depth}\n\n--B{depth}\n".encode()
    deep = raw + b"Content-Type: text/plain\n\nx\n"
    assert refused(deep) in ("the message is nested too deeply", "the message has too many parts")


def test_a_message_nested_thousands_of_levels_deep_is_refused_not_a_crash() -> None:
    raw = b"From: a@b.example\n"
    for depth in range(3000):
        raw += f"Content-Type: multipart/mixed; boundary=B{depth}\n\n--B{depth}\n".encode()
    text = refused(raw + b"Content-Type: text/plain\n\nx\n", EmlLimits(max_bytes=10**7))
    assert "deeply" in text or "too many" in text or "could not be read" in text


def test_too_many_attachments_or_attachments_that_are_too_large_are_refused() -> None:
    msg = simple()
    for i in range(5):
        msg.add_attachment(b"x" * 10, maintype="application", subtype="pdf", filename=f"{i}.pdf")
    assert "too many attachments" in refused(msg.as_bytes(), EmlLimits(max_attachments=3))
    big = simple()
    big.add_attachment(b"x" * 5000, maintype="application", subtype="pdf", filename="big.pdf")
    assert "larger than the limit" in refused(big.as_bytes(), EmlLimits(max_attachment_bytes=1000))
    several = simple()
    for i in range(4):
        several.add_attachment(b"x" * 600, maintype="application", subtype="pdf", filename=f"{i}")
    limits = EmlLimits(max_attachment_bytes=1000, max_total_bytes=2000)
    assert "together" in refused(several.as_bytes(), limits)


def test_an_encoded_attachment_that_would_decode_past_the_limit_is_refused_before_decoding() -> (
    None
):
    raw = (
        b"From: a@b.example\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: application/octet-stream\nContent-Transfer-Encoding: base64\n"
        b'Content-Disposition: attachment; filename="z"\n\n' + b"AAAA" * 20000 + b"\n--B--\n"
    )
    assert "larger than the limit" in refused(raw, EmlLimits(max_attachment_bytes=1000))


def test_a_body_longer_than_the_record_allows_is_refused_not_cut() -> None:
    msg = simple()
    msg.set_content("word " * 6000)
    assert "longer than" in refused(msg.as_bytes())
    ok = simple()
    ok.set_content("word " * 100)
    assert parse_eml(ok.as_bytes()).body == ("word " * 100).strip()


@pytest.mark.parametrize(
    "header",
    [
        "Subject: bell\x07 here",
        "Subject: bidi \u202eevil",
        "Subject: zero\u200ewidth mark",
        "Subject: =?utf-8?b?QUJDXHUyMDJFREVG?=",  # decodes to text with U+202E
    ],
)
def test_text_that_becomes_record_text_refuses_control_and_direction_characters(
    header: str,
) -> None:
    raw = f"From: a@b.example\n{header}\n\nbody\n".encode()
    if "QUJD" in header:  # build the encoded word from real bytes
        import base64

        encoded = base64.b64encode("ABC\u202eDEF".encode()).decode()
        raw = f"From: a@b.example\nSubject: =?utf-8?b?{encoded}?=\n\nbody\n".encode()
    assert "character" in refused(raw)


def test_a_name_or_a_file_name_with_a_hostile_character_is_refused() -> None:
    from_bad = b"From: =?utf-8?q?Pat=E2=80=AEx?= <a@b.example>\n\nbody\n"
    assert "character" in refused(from_bad)
    msg = simple()
    msg.add_attachment(b"x", maintype="application", subtype="pdf", filename="evil\u202egnp.pdf")
    assert "character" in refused(msg.as_bytes())
    long_name = simple()
    long_name.add_attachment(
        b"x", maintype="application", subtype="pdf", filename="n" * 300 + ".pdf"
    )
    assert "file name is longer" in refused(long_name.as_bytes())


def test_a_control_character_in_the_body_is_refused_but_ordinary_line_breaks_are_kept() -> None:
    raw = b"From: a@b.example\nContent-Type: text/plain\n\nline one\x00nul\n"
    assert "character" in refused(raw)
    assert parse_eml(b"From: a@b.example\n\nline one\r\nline two\r\n").body == "line one\nline two"


def test_too_many_recipients_is_refused_and_odd_addresses_are_dropped_or_kept_as_names() -> None:
    many = ", ".join(f"u{i}@x.example" for i in range(120))
    assert "too many people" in refused(f"From: a@b.example\nTo: {many}\n\nb\n".encode())
    got = parse_eml(
        b"From: a@b.example\nTo: undisclosed-recipients:;, Real <real@x.example>\n\nb\n"
    )
    assert [(a.name, a.email) for a in got.to] == [("Real", "real@x.example")]
    odd = parse_eml(b"From: a@b.example\nTo: Nobody <nodomain>\n\nb\n")
    assert [(a.name, a.email) for a in odd.to] == [("Nobody", None)]


def test_an_implausible_date_is_refused_and_a_garbled_one_is_no_date() -> None:
    assert "plausible" in refused(
        b"From: a@b.example\nDate: Mon, 01 Jan 1901 00:00:00 +0000\n\nb\n"
    )
    assert "plausible" in refused(
        b"From: a@b.example\nDate: Mon, 01 Jan 2500 00:00:00 +0000\n\nb\n"
    )


def test_an_unknown_charset_is_decoded_as_utf_8_with_replacement() -> None:
    raw = (
        b"From: a@b.example\nContent-Type: text/plain; charset=made-up-9\n"
        b"Content-Transfer-Encoding: 8bit\n\ncaf\xc3\xa9 \xff\n"
    )
    body = parse_eml(raw).body
    assert body is not None and body.startswith("café")


def test_parsing_opens_no_connection_and_follows_no_link() -> None:
    real = socket.socket

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the parser must not open a socket")

    socket.socket = refuse  # type: ignore[misc,assignment]
    try:
        msg = simple()
        msg.add_alternative(
            '<html><img src="http://tracker.example/p.gif"><a href="http://x.example">x</a></html>',
            subtype="html",
        )
        got = parse_eml(msg.as_bytes())
    finally:
        socket.socket = real  # type: ignore[misc]
    assert got.body is not None and "tracker.example" not in got.body


def test_the_refusal_texts_repeat_nothing_of_the_message() -> None:
    secret = "SECRETVALUE"
    raw = f"From: a@b.example\nSubject: {secret}\x07\n\nbody\n".encode()
    assert secret not in refused(raw)
    msg = simple()
    msg.add_attachment(b"x", maintype="application", subtype="pdf", filename=f"{secret}\u202e.pdf")
    assert secret not in refused(msg.as_bytes())


def test_a_defective_message_does_not_escape_as_another_exception() -> None:
    for raw in (
        b"\xff\xfe\x00garbage with no headers at all",
        b"Content-Type: multipart/mixed\n\nno boundary here",
        b"From: =?utf-8?b?!!!notbase64?= <a@b.example>\n\nb\n",
        b"Content-Type: multipart/mixed; boundary=\n\n--\n",
        b"Subject: " + b"=?utf-8?q?" * 200 + b"\n\nb\n",
    ):
        try:
            parse_eml(raw)
        except EmlRefused:
            pass


# --- the process of its own --------------------------------------------------------------------


def test_the_isolated_form_gives_the_same_message() -> None:
    msg = simple()
    msg.add_attachment(b"%PDF-1.7 data", maintype="application", subtype="pdf", filename="spec.pdf")
    data = msg.as_bytes()
    assert parse_eml_isolated(data) == parse_eml(data)


def test_the_isolated_form_refuses_with_the_same_fixed_text() -> None:
    with pytest.raises(EmlRefused) as inner:
        parse_eml(b"From: a@b.example\n\nline\x00nul\n")
    with pytest.raises(EmlRefused) as outer:
        parse_eml_isolated(b"From: a@b.example\n\nline\x00nul\n")
    assert str(outer.value) == str(inner.value)
    big = EmlLimits(max_bytes=100)
    with pytest.raises(EmlRefused, match="larger than the limit"):
        parse_eml_isolated(b"x" * 500, big)


def test_a_message_that_breaks_the_envelope_is_refused_with_no_detail() -> None:
    data = simple().as_bytes()
    with pytest.raises(EmlRefused) as caught:
        parse_eml_isolated(data, memory_limit_mb=8)  # the interpreter itself does not fit
    assert (
        str(caught.value)
        == "the message could not be read safely (it took too long or too much memory)"
    )


# --- bounds the first corpus left open (found by the mutation run) ------------------------------


def test_the_headers_of_all_parts_together_are_bounded() -> None:
    headers = b"".join(f"X-H{i}: v\n".encode() for i in range(40))
    part = b"--B\n" + headers + b"Content-Type: text/plain\n\nx\n"
    raw = (
        b"From: a@b.example\nContent-Type: multipart/mixed; boundary=B\n\n" + part * 3 + b"--B--\n"
    )
    limits = EmlLimits(max_headers=60, max_headers_total=100)
    assert "too many headers" in refused(raw, limits)
    assert parse_eml(raw, EmlLimits(max_headers=60, max_headers_total=1000)).body == "x"


def test_an_encoded_attachment_is_refused_by_its_text_size_before_it_is_decoded() -> None:
    # base64 ignores white space, so this decodes to three bytes: only the size of the text
    # (read before decoding) can refuse it
    raw = (
        b"From: a@b.example\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: application/octet-stream\nContent-Transfer-Encoding: base64\n"
        b'Content-Disposition: attachment; filename="z"\n\n' + b"AAAA" + b" " * 20000 + b"\n--B--\n"
    )
    assert "larger than the limit" in refused(raw, EmlLimits(max_attachment_bytes=1000))
    assert (
        parse_eml(raw, EmlLimits(max_attachment_bytes=1_000_000)).attachments[0].data == b"\0\0\0"
    )


def test_an_attachment_that_is_not_encoded_is_bounded_by_its_size_too() -> None:
    msg = simple()
    msg.add_attachment("x" * 1500, filename="notes.txt")  # 7bit: the text is the content
    assert "larger than the limit" in refused(msg.as_bytes(), EmlLimits(max_attachment_bytes=1000))
    assert len(parse_eml(msg.as_bytes()).attachments[0].data) >= 1500


def test_the_first_plain_part_is_the_body() -> None:
    raw = (
        b"From: a@b.example\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: text/plain\n\nfirst\n--B\nContent-Type: text/plain\n\nsecond\n--B--\n"
    )
    assert parse_eml(raw).body == "first"


def test_a_subject_longer_than_the_record_allows_is_refused_not_cut() -> None:
    long_subject = simple(Subject="s" * 600)
    assert "the subject is longer than 500" in refused(long_subject.as_bytes())
    assert parse_eml(simple(Subject="s" * 500).as_bytes()).subject == "s" * 500
