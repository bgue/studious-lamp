"""The properties of a PDF file, read with pypdf (P1-I3B-T10; ADR-0008 decision 8).

Only the document information is read: the page count and the title, author, producer and dates
of the information dictionary. No page is parsed, no content stream is decoded, no text is
extracted; that is the stubbed part of the decision. An encrypted PDF is refused without trying a
password, and any error inside pypdf is a refusal of this file, never an exception.

pypdf itself is not a bounded reader: asked for ``len(reader.pages)`` it decodes object streams, and
a crafted file of a megabyte costs minutes and gigabytes. What bounds the cost here, in order:

1. the bytes are scanned before pypdf sees them (``check_pdf_bytes``): a fixed number of object
   streams, cross-reference sections (``startxref``, ``/Prev``, ``/XRef``, names spelt with ``#xx``
   escapes included), ``/Length`` values, no ``/Length`` past the end of the file, no ``/Size``
   past ``MAX_SIZE``;
2. pypdf reads through a stream that counts its operations (``_BudgetStream``): every byte of a
   string, an array or an xref line that pypdf looks at costs an operation, and past
   ``MAX_STREAM_OPS`` the read is ``pdf_too_complex``. This bounds the work whatever the file
   puts in the objects pypdf parses (a 47 MB title, a million-entry ``/Kids``, a long ``/Prev``
   chain) without parsing the file a second time to find out;
3. the reader is opened with ``strict=True`` (no repair paths, which are the slow ones) and with
   pypdf's own decompression limits lowered to ``PYPDF_LIMIT`` (``apply_configuration``, per call,
   per thread);
4. the page count is the integer ``/Root/Pages/Count`` and nothing else: no page tree is walked;
5. pypdf's log records are dropped while it runs (they can quote the file).

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
XREF_DAMAGED = "the PDF's cross-reference table is damaged"
BAD_PAGE_COUNT = "the PDF states a page count that is out of range"

#: Limits of the byte scan.
MAX_OBJSTM = 500
#: Cross-reference sections: ``startxref`` records, ``/Prev`` links and ``/XRef`` streams.
MAX_XREF_SECTIONS = 32
MAX_LENGTH_VALUES = 100_000
#: The most objects a file may declare (``/Size``). A PDF of the 50 MiB the contract allows has
#: fewer than a million.
MAX_SIZE = 2_000_000
MAX_PAGES = 1_000_000
#: pypdf's decompression limits are 75 MB each; the streams we decode are object streams and
#: cross-reference streams (about 5 bytes per object): 2 MiB is 400 000 objects.
PYPDF_LIMIT = 2 * 1024 * 1024
#: Operations (reads, line reads, seeks) pypdf may make on the file in one call. It reads a
#: string one byte at a time, so this is also the longest string, array or run of garbage it will
#: look at; a classic cross-reference table costs about one operation per object.
MAX_STREAM_OPS = 600_000
#: The bytes pypdf may be handed in all: this many times the file, plus a fixed allowance.
STREAM_BYTE_FACTOR = 4
STREAM_BYTE_ALLOWANCE = 4 * 1024 * 1024

_LENGTH = re.compile(rb"/Length\s+(\d+)(?!\s+\d+\s+R)")
_SIZE = re.compile(rb"/Size\s+(\d+)")


def _name(text: bytes) -> re.Pattern[bytes]:
    """A pattern for the PDF name ``/text`` in any spelling: each letter may be written ``#xx``."""
    letters = b"".join(b"(?:%s|#%02X|#%02x)" % (bytes([c]), c, c) for c in text)
    return re.compile(b"/" + letters)


_OBJSTM = _name(b"ObjStm")
_XREF_NAMES = (_name(b"Prev"), _name(b"XRef"), re.compile(b"startxref"))


class _OutOfBudget(BaseException):
    """Raised by ``_BudgetStream``; not an ``Exception``, so that pypdf's own handlers, which catch
    ``Exception`` and carry on, cannot swallow it."""


class _NeedsRepair(_OutOfBudget):
    """pypdf asked for the whole file at once, which it does only to repair an unparsable
    cross-reference entry."""


class _BudgetStream(io.BytesIO):
    """The bytes of the file, charging everything pypdf does with them.

    Each read, line read and seek costs one operation (``MAX_STREAM_OPS``), and each byte handed
    out costs one byte of a total of ``STREAM_BYTE_FACTOR`` times the file plus
    ``STREAM_BYTE_ALLOWANCE``. The ways to get the whole file at once, which pypdf's repair paths
    use once per unparsable cross-reference entry (``getbuffer``, ``getvalue``, ``readlines``), are
    not allowed at all: a file that reaches them is ``damaged_pdf`` (its table is damaged).
    """

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self._size = len(data)
        self.operations = 0
        self.bytes_left = STREAM_BYTE_FACTOR * len(data) + STREAM_BYTE_ALLOWANCE

    def _charge(self, nbytes: int) -> None:
        self.operations += 1
        self.bytes_left -= nbytes
        if self.operations > MAX_STREAM_OPS or self.bytes_left < 0:
            raise _OutOfBudget

    def _ahead(self, size: int | None) -> int:
        """What a read of ``size`` will hand out, at most; cheap for the one-byte reads that
        dominate."""
        if size is not None and size >= 0:
            return size
        return max(self._size - self.tell(), 0)

    def read(self, size: int | None = -1) -> bytes:
        self._charge(self._ahead(size))
        return super().read(size)

    def read1(self, size: int | None = -1) -> bytes:
        self._charge(self._ahead(size))
        return super().read1(size)

    def readline(self, size: int | None = -1) -> bytes:
        line = super().readline(size)
        self._charge(len(line))
        return line

    def readinto(self, buffer: object) -> int:
        count = super().readinto(buffer)  # type: ignore[arg-type]
        self._charge(count)
        return count

    def seek(self, offset: int, whence: int = 0) -> int:
        self._charge(0)
        return super().seek(offset, whence)

    def __next__(self) -> bytes:
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def __iter__(self) -> _BudgetStream:
        return self

    def readlines(self, hint: int | None = -1) -> list[bytes]:
        raise _NeedsRepair

    def getbuffer(self) -> memoryview:
        raise _NeedsRepair

    def getvalue(self) -> bytes:
        raise _NeedsRepair


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


def _more_than(pattern: re.Pattern[bytes], raw: bytes, limit: int) -> bool:
    count = 0
    for _ in pattern.finditer(raw):
        count += 1
        if count > limit:
            return True
    return False


def check_pdf_bytes(raw: bytes) -> None:
    """Refuse a PDF that is built to make a reader work too hard, before pypdf is asked anything.

    Raises ``Refusal`` with the code ``pdf_too_complex`` (more than ``MAX_OBJSTM`` object streams,
    ``MAX_XREF_SECTIONS`` cross-reference sections, ``MAX_LENGTH_VALUES`` lengths, or a ``/Size``
    over ``MAX_SIZE``) or ``damaged_pdf`` (a ``/Length`` that is longer than the file). Names are
    matched in any ``#xx`` spelling. Every step is a linear pass over the bytes, in C.
    """
    if _more_than(_OBJSTM, raw, MAX_OBJSTM):
        raise Refusal("pdf_too_complex", TOO_COMPLEX)
    if any(_more_than(pattern, raw, MAX_XREF_SECTIONS) for pattern in _XREF_NAMES):
        raise Refusal("pdf_too_complex", TOO_COMPLEX)
    if raw.count(b"/Length") > MAX_LENGTH_VALUES:
        raise Refusal("pdf_too_complex", TOO_COMPLEX)
    for match in _LENGTH.finditer(raw):
        if int(match.group(1)) > len(raw):
            raise Refusal("damaged_pdf", DAMAGED_PDF)
    for match in _SIZE.finditer(raw):
        if int(match.group(1)) > MAX_SIZE:
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
            _read_into(info, raw)
        except _NeedsRepair as exc:
            raise Refusal("damaged_pdf", XREF_DAMAGED) from exc
        except _OutOfBudget as exc:
            raise Refusal("pdf_too_complex", TOO_COMPLEX) from exc
    return info


def _read_into(info: PdfInfo, raw: bytes) -> None:
    """Fill ``info`` from the PDF. May raise ``Refusal`` and ``_OutOfBudget``."""
    try:
        reader = PdfReader(_BudgetStream(raw), strict=True)
        if reader.is_encrypted:
            raise Refusal("encrypted_pdf", ENCRYPTED_PDF)
        metadata = reader.metadata
        root = reader.trailer["/Root"]
    except (Refusal, _OutOfBudget):
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
