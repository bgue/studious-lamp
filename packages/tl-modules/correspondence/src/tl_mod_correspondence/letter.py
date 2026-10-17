"""A letter from a template to a PDF, with no library and no clock (brief 9 M10: issue).

``fill_template`` puts the fields of a letter into the text of a domain template, ``compose_letter``
lays the letter out as plain lines, and ``render_pdf`` writes those lines as a PDF 1.4 file with the
built-in Helvetica font. The output is a function of the input alone: no date, no random id, no
metadata other than the title, so the same letter always gives the same bytes (and the same
SHA-256). It is a stub of the letterhead and layout work a real renderer would do: one font, one
column, plain text. Characters that Windows-1252 cannot show become ``?``.

Bounds (a letter is bounded before it is laid out, and an over-long one is refused, not cut):
``MAX_CHARS`` characters, ``MAX_PAGES`` pages.
"""

from __future__ import annotations

import re
import textwrap
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

MAX_CHARS: Final = 60_000
MAX_PAGES: Final = 30
LINE_WIDTH: Final = 90  # characters per line (Helvetica 10 pt on an A4 page)
LINES_PER_PAGE: Final = 52
FIELD_NAMES: Final = ("number", "date", "subject", "to", "body")

_FIELD = re.compile(r"\{([a-z_]{1,32})\}")


class LetterError(ValueError):
    """The letter cannot be made: an unknown field, text too long, or a bad template."""


@dataclass(frozen=True)
class LetterFields:
    """The values that go into a letter. Every value is plain text."""

    number: str
    date: str
    subject: str
    to: str
    body: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "number": self.number,
            "date": self.date,
            "subject": self.subject,
            "to": self.to,
            "body": self.body,
        }


def fill_template(text: str, fields: Mapping[str, str]) -> str:
    """``text`` with each ``{name}`` replaced by ``fields[name]``.

    Only the names in ``FIELD_NAMES`` may appear; any other ``{name}`` raises ``LetterError``
    naming it. Braces that do not form ``{lower_case_name}`` stay as they are. A value is inserted
    as it is (it is never searched for further placeholders), and nothing is evaluated: this is
    not ``str.format``.
    """
    unknown = sorted({m for m in _FIELD.findall(text) if m not in FIELD_NAMES})
    if unknown:
        raise LetterError(f"the template uses {{{unknown[0]}}}, which is not a letter field")
    return _FIELD.sub(lambda match: fields.get(match.group(1), ""), text)


def compose_letter(header: str | None, footer: str | None, fields: LetterFields) -> list[str]:
    """The lines of the letter: header, number and date, recipient, subject, body, footer.

    Layout: the filled header (if any), a blank line, ``Our ref: <number>`` and ``Date: <date>``,
    a blank line, ``To: <to>``, a blank line, ``Subject: <subject>``, a blank line, the body, a
    blank line, the filled footer (if any). Every line is wrapped at ``LINE_WIDTH`` and the
    text is cleaned (tabs become four spaces, other control characters a space). Raises
    ``LetterError`` when the whole letter holds more than ``MAX_CHARS`` characters.
    """
    mapping = fields.as_mapping()
    parts: list[str] = []
    if header:
        parts += [fill_template(header, mapping), ""]
    parts += [
        f"Our ref: {fields.number}",
        f"Date: {fields.date}",
        "",
        f"To: {fields.to}",
        "",
        f"Subject: {fields.subject}",
        "",
        fields.body,
    ]
    if footer:
        parts += ["", fill_template(footer, mapping)]
    raw = "\n".join(parts)
    if len(raw) > MAX_CHARS:
        raise LetterError(f"the letter has {len(raw)} characters; the limit is {MAX_CHARS}")
    lines: list[str] = []
    for paragraph in _clean(raw).split("\n"):
        wrapped = textwrap.wrap(
            paragraph, width=LINE_WIDTH, replace_whitespace=False, drop_whitespace=True
        )
        lines.extend(wrapped or [""])
    return lines


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    return "".join(
        " " if c != "\n" and unicodedata.category(c).startswith("C") else c for c in text
    )


def _pdf_text(line: str) -> bytes:
    data = line.encode("cp1252", errors="replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def render_pdf(lines: Sequence[str], title: str) -> bytes:
    """A PDF 1.4 file with ``lines`` in Helvetica 10 pt, ``LINES_PER_PAGE`` to a page.

    The file has a catalog, a page tree, one page and one content stream per page, a Type1
    Helvetica font, an info dictionary with only ``/Title``, a cross-reference table with exact
    offsets and a trailer; it holds no date and no random id. An empty ``lines`` gives one empty
    page. Raises ``LetterError`` for more than ``MAX_PAGES`` pages.
    """
    pages = [list(lines[i : i + LINES_PER_PAGE]) for i in range(0, len(lines), LINES_PER_PAGE)]
    pages = pages or [[]]
    if len(pages) > MAX_PAGES:
        raise LetterError(f"the letter needs {len(pages)} pages; the limit is {MAX_PAGES}")
    first_page = 5
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{first_page + 2 * i} 0 R".encode() for i in range(len(pages)))
        + f"] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Title (" + _pdf_text(title[:200]) + b") >>",
    ]
    for index, page in enumerate(pages):
        content_id = first_page + 2 * index + 1
        stream = b"BT /F1 10 Tf 12 TL 50 790 Td\n"
        stream += b"".join(b"(" + _pdf_text(line) + b") Tj T*\n" for line in page)
        stream += b"ET"
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> " + f"/Contents {content_id} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 4 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)
