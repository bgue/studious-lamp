"""The label renderer (P2-QR T02): one printable HTML page per code.

Pure: no database, no network, no clock. The QR holds exactly
``<api.public_base_url>/web/q/<code>``. The code is printed under the QR in four
groups so it can be typed. A label never prints state, the URL or the
run-together code. The page is script-free and loads nothing from outside. The QR
library ``segno`` is the optional ``labels`` extra of ``tl-mod-qr``.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.confidentiality import LOWEST, Viewer

LABEL_SIZES: dict[str, tuple[int, int]] = {"tag": (50, 80)}  # millimetres, width x height

NO_QR_NOTE = "The QR library is not installed: install the labels extra. No label was drawn."

_CODE_RE = re.compile(r"[A-Z0-9]{16}")
# The base address pattern of the setting api.public_base_url, minus its empty alternative.
_BASE_RE = re.compile(
    r"https://[A-Za-z0-9.-]+(:[0-9]{1,5})?|http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?"
)
_TEXT_MAX = 40
_UNAVAILABLE = ("card", "sheet")


class LabelError(ValueError):
    """A label cannot be built: a bad base address, code, text or size."""


def format_code(code: str) -> str:
    """Group a 16-character code in fours: ``7KQ2M9XA4TTCP0HV`` -> ``7KQ2-M9XA-4TTC-P0HV``."""
    if not _CODE_RE.fullmatch(code):
        raise LabelError("a scan code is 16 characters of A-Z and 0-9")
    return "-".join(code[i : i + 4] for i in range(0, 16, 4))


def label_url(base_url: str, code: str) -> str:
    """The address the QR holds: ``<base>/web/q/<code>``."""
    if not _BASE_RE.fullmatch(base_url):
        raise LabelError("the public base address is not an https address or a local http address")
    if not _CODE_RE.fullmatch(code):
        raise LabelError("a scan code is 16 characters of A-Z and 0-9")
    return f"{base_url}/web/q/{code}"


def make_svg(url: str) -> str | None:
    """The QR for ``url`` as inline SVG, or ``None`` when the optional ``segno`` is missing."""
    try:
        import segno  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None
    return segno.make(url, error="q").svg_inline(scale=4, border=2)


def render_label(*, code: str, text: str | None, size: str = "tag", svg: str | None) -> str:
    """One printable HTML page for ``code``; ``svg`` is the QR, or ``None`` for the note."""
    if size in _UNAVAILABLE:
        raise LabelError(f"label size {size} is not available yet")
    if size not in LABEL_SIZES:
        raise LabelError(f"unknown label size: {size}")
    width, height = LABEL_SIZES[size]
    grouped = format_code(code)
    if text is not None and len(text) > _TEXT_MAX:
        raise LabelError(f"label text is at most {_TEXT_MAX} characters")
    picture = svg if svg is not None else f'<p class="note">{NO_QR_NOTE}</p>'
    text_line = f'<div class="text">{html.escape(text)}</div>' if text is not None else ""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Scan label</title>\n"
        "<style>\n"
        f"@page {{ size: {width}mm {height}mm; margin: 0 }}\n"
        "html, body { margin: 0; padding: 0; }\n"
        f"body {{ width: {width}mm; height: {height}mm; display: flex; flex-direction: column; "
        "align-items: center; justify-content: center; font-family: sans-serif; }\n"
        f"svg {{ width: {width - 10}mm; height: auto; }}\n"
        ".note { font-size: 7pt; text-align: center; margin: 0 2mm; }\n"
        ".code { font-family: monospace; font-size: 10pt; letter-spacing: 0.1em; margin-top: 2mm;"
        " }\n"
        ".text { font-size: 8pt; text-align: center; margin: 2mm 2mm 0 2mm; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{picture}\n"
        f'<div class="code">{grouped}</div>\n'
        f"{text_line}\n"
        "</body>\n"
        "</html>\n"
    )


@dataclass(frozen=True)
class LabelFields:
    """What a label may print about its record: the key and the typed text, or ``None`` for each."""

    key: str | None
    text: str | None


_NOTHING = LabelFields(None, None)
_RECORD = text("SELECT key, title, voided FROM cur_core_record WHERE id = :id")


def label_fields(conn: Connection, target_id: str, viewer: Viewer = LOWEST) -> LabelFields:
    """The record's key and title for a record at the lowest class (``internal``) that ``viewer``
    can read; both ``None`` above it, when the viewer cannot read it, or when it does not exist.
    One rule: every label surface calls it. The text is cut to ``_TEXT_MAX`` characters."""
    if confidentiality.is_hidden(conn, target_id, LOWEST):
        return _NOTHING
    if confidentiality.is_hidden(conn, target_id, viewer):
        return _NOTHING
    row = conn.execute(_RECORD, {"id": target_id}).first()
    if row is None or bool(row.voided):
        return _NOTHING
    title = None if row.title is None else str(row.title)[:_TEXT_MAX] or None
    return LabelFields(key=None if row.key is None else str(row.key), text=title)
