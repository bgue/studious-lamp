# ruff: noqa: F401, F841
"""The properties of a PDF file, read with pypdf (P1-I3B-T10; ADR-0008 decision 8).

Only the document information is read: the page count and the title, author, producer and dates
of the information dictionary. No page is parsed, no content stream is decoded, no text is
extracted; that is the stubbed part of the decision. An encrypted PDF is refused without trying a
password, and any error inside pypdf is a refusal of this file, never an exception.

STUB (P1-I3B-T10): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import io
import logging
import re
from calendar import monthrange
from dataclasses import dataclass

from pypdf import PdfReader

from tl_extract.reading import Refusal, clean_metadata_text

# pypdf reports repairs and damage through logging; a library adds a handler so that Python's
# last-resort handler does not print them to standard error.
logging.getLogger("pypdf").addHandler(logging.NullHandler())

#: A PDF whose header is not in the first kilobyte is not read as one.
HEADER_WINDOW = 1024

NOT_PDF = "the file is not a PDF (no %PDF- header)"
ENCRYPTED_PDF = "the PDF is encrypted; it cannot be read"
BROKEN_PDF = "the PDF is damaged and cannot be read"

_DATE = re.compile(
    r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?"
    r"(?:(Z)(?:00'?(?:00'?)?)?|([+-])(\d{2})(?:'?(\d{2})'?)?)?$"
)


@dataclass
class PdfInfo:
    page_count: int | None = None
    title: str | None = None
    author: str | None = None
    producer: str | None = None
    #: ISO 8601, written from the PDF date string (``D:20240301101530+02'00'``).
    created: str | None = None
    modified: str | None = None


def pdf_date_to_iso(text: str) -> str | None:
    """A PDF date string as ISO 8601, or None when it is not a valid date.

    The string is ``D:YYYYMMDDHHmmSSOHH'mm'`` with every part after the year optional. The result
    keeps the parts that are there: ``2024``, ``2024-03``, ``2024-03-01``, and from an hour on
    ``2024-03-01T10:15:30`` (minutes and seconds default to ``00``). A zone is ``Z`` or
    ``+02:00``; ``Z``, ``Z00'00'`` and ``+00'00'`` are written ``Z``. A month, day, hour, minute
    or second out of range, or any other shape, is None.
    """
    # STEPS
    # 1. match = _DATE.match(text.strip()). No match gives None.
    # 2. year, month, day, hour, minute, second, zulu, sign, zone_h, zone_m = match.groups().
    #    Each of them is a string or None. The pattern only lets a part appear when the parts
    #    before it do.
    # 3. Return None when a part is out of range: month not in 1..12; day not in
    #    1..calendar.monthrange(year, month)[1] (use year 1 when the year is 0); hour > 23;
    #    minute > 59; second > 59. Check only the parts that are present.
    # 4. result = year. If month: result += f"-{month}". If day: result += f"-{day}". If hour:
    #    result += f"T{hour}:{minute or '00'}:{second or '00'}".
    # 5. If hour is None return result: a zone means nothing without a time.
    # 6. If zulu: result += "Z". Elif sign: offset_m = zone_m or "00"; return None when
    #    int(zone_h) > 23 or int(offset_m) > 59; otherwise result += "Z" when (zone_h, offset_m)
    #    == ("00", "00"), else f"{sign}{zone_h}:{offset_m}".
    # 7. Return result.
    raise NotImplementedError


def _text(value: object) -> str | None:
    return clean_metadata_text(str(value)) if isinstance(value, str) else None


def read_pdf_info(raw: bytes) -> PdfInfo:
    """The page count and document information of the PDF in ``raw``.

    Raises ``Refusal`` with the code ``not_pdf`` (no ``%PDF-`` header in the first kilobyte),
    ``encrypted_pdf`` (the file is encrypted; no password is tried) or ``broken_pdf`` (pypdf
    could not open it or read its trailer).
    """
    # STEPS
    # 1. If b"%PDF-" is not in raw[:HEADER_WINDOW] raise Refusal("not_pdf", NOT_PDF).
    # 2. In one try block: reader = PdfReader(io.BytesIO(raw), strict=False). If
    #    reader.is_encrypted raise Refusal("encrypted_pdf", ENCRYPTED_PDF); do not touch pages
    #    or metadata and do not try a password. Then metadata = reader.metadata. Let a Refusal
    #    pass through (`except Refusal: raise`) and turn any other Exception into
    #    Refusal("broken_pdf", BROKEN_PDF) from the error.
    # 3. info = PdfInfo(). In its own try/except Exception: info.page_count = len(reader.pages).
    #    When it fails the page count stays None.
    # 4. If metadata is not None, in another try/except Exception (a failure leaves the fields
    #    not yet set as None): info.title, info.author and info.producer are
    #    _text(metadata.title), _text(metadata.author) and _text(metadata.producer). created =
    #    metadata.get("/CreationDate") and modified = metadata.get("/ModDate"); each field is
    #    pdf_date_to_iso(str(value)) when the value is not None.
    # 5. Return info.
    raise NotImplementedError
