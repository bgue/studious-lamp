"""The properties of a PDF file, read with pypdf (P1-I3B-T10; ADR-0008 decision 8).

Only the document information is read: the page count and the title, author, producer and dates
of the information dictionary. No page is parsed, no content stream is decoded, no text is
extracted; that is the stubbed part of the decision. An encrypted PDF is refused without trying a
password, and any error inside pypdf is a refusal of this file, never an exception.

pypdf itself is not a bounded reader: asked for ``len(reader.pages)`` it decodes object streams, and
a crafted file of a megabyte costs minutes and gigabytes. What bounds the cost here, in order:

1. the bytes are scanned before pypdf sees them (``check_pdf_bytes``): a fixed number of object
   streams, of ``startxref`` records and of ``/Length`` values, no ``/Length`` past the end of the
   file, no string longer than ``MAX_STRING_BYTES``;
2. the reader is opened with ``strict=True`` (no repair paths, which are the slow ones) and with
   pypdf's own decompression limits lowered (``apply_configuration``, per call, per thread);
3. the page count is the integer ``/Root/Pages/Count`` and nothing else: no page tree is walked;
4. pypdf's log records are dropped while it runs (they can quote the file).

The job runner's subprocess limits (FANOUT D9) are the backstop, not the plan.
"""

from __future__ import annotations

import io
import logging
import re
from calendar import monthrange
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from pypdf import PdfReader, apply_configuration

from tl_extract.reading import Refusal, clean_metadata_text

# pypdf reports repairs and damage through logging; a library adds a handler so that Python's
# last-resort handler does not print them to standard error.
logging.getLogger("pypdf").addHandler(logging.NullHandler())

#: A PDF whose header is not in the first kilobyte is not read as one.
HEADER_WINDOW = 1024

NOT_PDF = "the file is not a PDF (no %PDF- header)"
ENCRYPTED_PDF = "the PDF is encrypted; it cannot be read"
DAMAGED_PDF = "the PDF is damaged and cannot be read"
TOO_COMPLEX = "the PDF is too complex to read safely"
BAD_PAGE_COUNT = "the PDF states a page count that is out of range"

#: Limits of the byte scan.
MAX_OBJSTM = 500
MAX_STARTXREF = 100
MAX_LENGTH_VALUES = 100_000
MAX_STRING_BYTES = 1024 * 1024
MAX_PAGES = 1_000_000
#: pypdf's decompression limits are 75 MB each; the objects we read are small.
PYPDF_LIMIT = 8 * 1024 * 1024

_LENGTH = re.compile(rb"/Length\s+(\d+)(?!\s+\d+\s+R)")
# a string that goes on for a megabyte without a bare parenthesis (a backslash escape is one unit)
_LONG_LITERAL = re.compile(rb"\((?:[^()\\]|\\.){%d,}" % MAX_STRING_BYTES, re.DOTALL)
_LONG_HEX = re.compile(rb"<[0-9A-Fa-f\s]{%d,}" % MAX_STRING_BYTES)

_DATE = re.compile(
    r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?"
    r"(?:(Z)(?:00'?(?:00'?)?)?|([+-])(\d{2})(?:'?(\d{2})'?)?)?$"
)


@dataclass
class PdfInfo:
    page_count: int | None = None
    #: (code, message) of a problem that does not stop the read, e.g. a page count out of range.
    problems: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
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
    if month is not None and not 1 <= int(month) <= 12:
        return None
    if month is not None and day is not None:
        days_in_month = monthrange(int(year) or 1, int(month))[1]
        if not 1 <= int(day) <= days_in_month:
            return None
    if hour is not None and int(hour) > 23:
        return None
    if minute is not None and int(minute) > 59:
        return None
    if second is not None and int(second) > 59:
        return None
    result = year
    if month is not None:
        result += f"-{month}"
    if day is not None:
        result += f"-{day}"
    if hour is not None:
        result += f"T{hour}:{minute or '00'}:{second or '00'}"
    if hour is None:
        return result
    if zulu:
        result += "Z"
    elif sign:
        offset_m = zone_m or "00"
        if int(zone_h or "00") > 23 or int(offset_m) > 59:
            return None
        if (zone_h, offset_m) == ("00", "00"):
            result += "Z"
        else:
            result += f"{sign}{zone_h}:{offset_m}"
    return result


def _text(value: object) -> str | None:
    return clean_metadata_text(str(value)) if isinstance(value, str) else None


def check_pdf_bytes(raw: bytes) -> None:
    """Refuse a PDF that is built to make a reader work too hard, before pypdf is asked anything.

    Raises ``Refusal`` with the code ``pdf_too_complex`` (more than ``MAX_OBJSTM`` object streams,
    ``MAX_STARTXREF`` cross-reference sections or ``MAX_LENGTH_VALUES`` lengths, or a string of
    ``MAX_STRING_BYTES`` or more) or ``damaged_pdf`` (a ``/Length`` that is longer than the file).
    Every step is a linear pass over the bytes, in C.
    """
    if raw.count(b"/ObjStm") > MAX_OBJSTM or raw.count(b"startxref") > MAX_STARTXREF:
        raise Refusal("pdf_too_complex", TOO_COMPLEX)
    if raw.count(b"/Length") > MAX_LENGTH_VALUES:
        raise Refusal("pdf_too_complex", TOO_COMPLEX)
    for match in _LENGTH.finditer(raw):
        if int(match.group(1)) > len(raw):
            raise Refusal("damaged_pdf", DAMAGED_PDF)
    if _LONG_LITERAL.search(raw) or _LONG_HEX.search(raw):
        raise Refusal("pdf_too_complex", TOO_COMPLEX)


@contextmanager
def _guarded_pypdf() -> Iterator[None]:
    """pypdf with lowered decompression limits and its log records dropped, for one call."""
    logger = logging.getLogger("pypdf")
    saved = (logger.level, logger.propagate)
    logger.setLevel(logging.CRITICAL + 1)
    logger.propagate = False
    try:
        with apply_configuration(
            maximum_declared_stream_length=PYPDF_LIMIT,
            array_based_stream_maximum_output_length=PYPDF_LIMIT,
            jbig2_maximum_output_length=PYPDF_LIMIT,
            lzw_maximum_output_length=PYPDF_LIMIT,
            run_length_maximum_output_length=PYPDF_LIMIT,
            zlib_maximum_output_length=PYPDF_LIMIT,
            xmp_maximum_input_length=PYPDF_LIMIT,
        ):
            yield
    finally:
        logger.setLevel(saved[0])
        logger.propagate = saved[1]


def read_pdf_info(raw: bytes) -> PdfInfo:
    """The page count and document information of the PDF in ``raw``.

    Raises ``Refusal`` with the code ``not_pdf`` (no ``%PDF-`` header in the first kilobyte),
    ``pdf_too_complex`` or ``damaged_pdf`` (see ``check_pdf_bytes``; also pypdf, in strict mode,
    could not open the file or read its trailer), or ``encrypted_pdf`` (no password is tried).
    The page count is ``/Root/Pages/Count``; when it is missing or unreadable the count is None,
    when it is an integer out of range the count is None and ``problems`` says so.
    """
    start = raw.find(b"%PDF-", 0, HEADER_WINDOW)
    if start < 0:
        raise Refusal("not_pdf", NOT_PDF)
    if start:
        raw = raw[start:]  # offsets in a PDF count from its header
    check_pdf_bytes(raw)
    info = PdfInfo()
    with _guarded_pypdf():
        try:
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise Refusal("encrypted_pdf", ENCRYPTED_PDF)
            metadata = reader.metadata
            root = reader.trailer["/Root"]
        except Refusal:
            raise
        except Exception as exc:
            raise Refusal("damaged_pdf", DAMAGED_PDF) from exc
        try:
            pages = root["/Pages"]  # type: ignore[index]
            count = pages["/Count"]
            if isinstance(count, int) and not isinstance(count, bool):
                if 0 <= count <= MAX_PAGES:
                    info.page_count = int(count)
                else:
                    info.problems.append(("bad_page_count", BAD_PAGE_COUNT))
        except Exception:
            pass
        if metadata is not None:
            try:
                info.title = _text(metadata.title)
                info.author = _text(metadata.author)
                info.producer = _text(metadata.producer)
                created = metadata.get("/CreationDate")
                modified = metadata.get("/ModDate")
                if created is not None:
                    info.created = pdf_date_to_iso(str(created)[:64])
                if modified is not None:
                    info.modified = pdf_date_to_iso(str(modified)[:64])
            except Exception:
                pass
    return info
