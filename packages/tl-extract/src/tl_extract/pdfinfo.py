"""The properties of a PDF file, read with pypdf (P1-I3B-T10; ADR-0008 decision 8).

Only the document information is read: the page count and the title, author, producer and dates
of the information dictionary. No page is parsed, no content stream is decoded, no text is
extracted; that is the stubbed part of the decision. An encrypted PDF is refused without trying a
password, and any error inside pypdf is a refusal of this file, never an exception.
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
    match = _DATE.match(text.strip())
    if match is None:
        return None
    year, month, day, hour, minute, second, zulu, sign, zone_h, zone_m = match.groups()
    y = int(year)
    m = int(month) if month else None
    d = int(day) if day else None
    if m is not None and not 1 <= m <= 12:
        return None
    if d is not None and m is not None and not 1 <= d <= monthrange(y if y else 1, m)[1]:
        return None
    if hour is not None and int(hour) > 23:
        return None
    if minute is not None and int(minute) > 59:
        return None
    if second is not None and int(second) > 59:
        return None
    result = f"{year}"
    if month:
        result += f"-{month}"
    if day:
        result += f"-{day}"
    if hour:
        result += f"T{hour}:{minute or '00'}:{second or '00'}"
    if hour is None:
        return result  # a zone means nothing without a time
    if zulu:
        result += "Z"
    elif sign:
        offset_m = zone_m or "00"
        if int(zone_h) > 23 or int(offset_m) > 59:
            return None
        result += "Z" if (zone_h, offset_m) == ("00", "00") else f"{sign}{zone_h}:{offset_m}"
    return result


def _text(value: object) -> str | None:
    return clean_metadata_text(str(value)) if isinstance(value, str) else None


def read_pdf_info(raw: bytes) -> PdfInfo:
    """The page count and document information of the PDF in ``raw``.

    Raises ``Refusal`` with the code ``not_pdf`` (no ``%PDF-`` header in the first kilobyte),
    ``encrypted_pdf`` (the file is encrypted; no password is tried) or ``broken_pdf`` (pypdf
    could not open it or read its trailer).
    """
    if b"%PDF-" not in raw[:HEADER_WINDOW]:
        raise Refusal("not_pdf", "the file is not a PDF (no %PDF- header)")
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise Refusal("encrypted_pdf", "the PDF is encrypted; it cannot be read")
        metadata = reader.metadata
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal("broken_pdf", "the PDF is damaged and cannot be read") from exc
    info = PdfInfo()
    try:
        info.page_count = len(reader.pages)
    except Exception:
        info.page_count = None
    if metadata is not None:
        try:
            info.title = _text(metadata.title)
            info.author = _text(metadata.author)
            info.producer = _text(metadata.producer)
            created = metadata.get("/CreationDate")
            modified = metadata.get("/ModDate")
            info.created = pdf_date_to_iso(str(created)) if created is not None else None
            info.modified = pdf_date_to_iso(str(modified)) if modified is not None else None
        except Exception:
            pass
    return info
