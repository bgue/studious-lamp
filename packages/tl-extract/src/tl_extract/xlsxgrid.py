"""Read an XLSX workbook into a ``RawGrid`` (P1-I3B-T09b; rewritten in P1-I3B-S14).

An XLSX file is a ZIP archive of XML parts, which makes it the most dangerous input of this
package. The guards, in the order they run:

1. a legacy Office or encrypted Office file (a compound document, ``D0 CF 11 E0``) is
   ``encrypted_xlsx``; anything else must start like a ZIP archive (``not_xlsx``);
2. the end-of-central-directory record is read first (``check_central_directory``): the entry count
   and the size of the directory are checked before ``zipfile`` is asked to load the directory;
3. the archive is checked by what it declares (``check_archive``): at most ``MAX_MEMBERS`` parts, no
   encrypted part, plain relative names, the declared size of each part and of all parts together
   under their limits (``zip_bomb``); the size a ZIP archive declares bounds what ``zipfile``
   returns, so the declared sizes are the real bounds;
4. every XML part is scanned for a document type or entity declaration, and for an encoding that
   hides one (UTF-16), and refused if it has one (``unsafe_xlsx``);
5. the parts are streamed by ``tl_extract.xlsxxml`` with counts of elements, depth, strings, cells
   and characters. openpyxl is not used: it materialises a whole row or the whole shared-strings
   table before a cap can look at it. A formula is never evaluated (the stored value is read),
   external links are never opened, macros are never run.

Cell values are turned into text here, deterministically (see ``xlsxxml.cell_text``).
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Iterator

from tl_extract.options import TableOptions
from tl_extract.reading import MAX_BLANK_RUN as MAX_BLANK_RUN
from tl_extract.reading import GridMeta, RawGrid, Refusal, clean_metadata_text, shown
from tl_extract.xlsxxml import (
    SheetRef,
    read_book,
)
from tl_extract.xlsxxml import (
    cell_text as cell_text,
)

MAX_MEMBERS = 2000
MAX_CENTRAL_DIRECTORY = 2 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 128 * 1024 * 1024
MAX_SHARED_STRINGS_BYTES = 24 * 1024 * 1024
MAX_SHEET_BYTES = 48 * 1024 * 1024
MAX_OTHER_BYTES = 4 * 1024 * 1024
XML_SUFFIXES = (".xml", ".rels", ".vml")
SCAN_CHUNK = 64 * 1024
FORBIDDEN = (b"<!DOCTYPE", b"<!ENTITY")
COMPOUND_DOCUMENT = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

NOT_XLSX = "the file is not an XLSX workbook (a ZIP archive)"
ENCRYPTED_XLSX = (
    "the file is an encrypted or legacy Office document; save it as an unprotected XLSX"
)
LINKS_NOTE = "the workbook links to other workbooks; the links are not followed"
MACROS_NOTE = "the workbook holds macros; they are never run"
SHEET_NOT_FOUND = "there is no sheet {name}; the sheets are: {available}"


def _member_limit(name: str) -> int:
    if name == "xl/sharedStrings.xml":
        return MAX_SHARED_STRINGS_BYTES
    if name.startswith("xl/worksheets/") and name.endswith(".xml"):
        return MAX_SHEET_BYTES
    return MAX_OTHER_BYTES


def check_central_directory(raw: bytes) -> None:
    """Read the end-of-central-directory record and refuse an archive with too many entries or a
    directory that is too big, before ``zipfile`` loads the directory. Raises ``Refusal``
    (``not_xlsx``, ``zip_bomb``)."""
    tail = raw[-(65_535 + 22) :]
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) - at < 22:
        raise Refusal("not_xlsx", NOT_XLSX)
    _, _, _, _, entries, size, offset, _ = struct.unpack_from("<4s4H2IH", tail, at)
    if entries > MAX_MEMBERS or entries == 0xFFFF or size == 0xFFFFFFFF:
        raise Refusal("zip_bomb", f"the workbook has more than {MAX_MEMBERS} parts")
    if size > MAX_CENTRAL_DIRECTORY:
        raise Refusal("zip_bomb", "the workbook's list of parts is too big")
    if offset + size > len(raw):
        raise Refusal("not_xlsx", NOT_XLSX)


def check_archive(archive: zipfile.ZipFile) -> None:
    """Refuse an archive by what it declares, before any part is read. Raises ``Refusal``
    (``not_xlsx``, ``zip_bomb`` or ``encrypted_file``)."""
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise Refusal("zip_bomb", f"the workbook has more than {MAX_MEMBERS} parts")
    total = 0
    for info in members:
        name = info.filename
        if name.startswith("/") or ".." in name.replace("\\", "/").split("/") or "\x00" in name:
            raise Refusal("not_xlsx", "the workbook has a part with an unsafe name")
        if info.flag_bits & 0x1:
            raise Refusal("encrypted_file", "the workbook is encrypted; it cannot be read")
        if info.file_size > _member_limit(name):
            raise Refusal(
                "zip_bomb", f"a part of the workbook expands to {info.file_size} bytes; too big"
            )
        total += info.file_size
    if total > MAX_TOTAL_UNCOMPRESSED:
        raise Refusal(
            "zip_bomb",
            f"the workbook expands to {total} bytes; the limit is "
            f"{MAX_TOTAL_UNCOMPRESSED // (1024 * 1024)} MiB",
        )
    names = {info.filename for info in members}
    if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
        raise Refusal("not_xlsx", "the file is a ZIP archive but not an XLSX workbook")


def _chunks(archive: zipfile.ZipFile, name: str) -> Iterator[bytes]:
    with archive.open(name) as part:
        while chunk := part.read(SCAN_CHUNK):
            yield chunk


def scan_xml_parts(archive: zipfile.ZipFile) -> None:
    """Refuse a workbook whose XML declares a document type or an entity, or is in an encoding
    that would hide one. Raises ``Refusal("unsafe_xlsx", ...)``."""
    for info in archive.infolist():
        if not info.filename.lower().endswith(XML_SUFFIXES) or info.file_size == 0:
            continue
        tail = b""
        first = True
        for chunk in _chunks(archive, info.filename):
            if first:
                head = chunk[:4]
                if head.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in head:
                    raise Refusal(
                        "unsafe_xlsx", "the workbook has an XML part in an unsupported encoding"
                    )
                first = False
            window = tail + chunk
            if any(marker in window for marker in FORBIDDEN):
                raise Refusal(
                    "unsafe_xlsx",
                    "the workbook declares a document type or an entity, "
                    "which a spreadsheet program never writes",
                )
            tail = window[-(len(FORBIDDEN[0]) - 1) :]


def _sheet_list(sheets: list[SheetRef], chosen: str | None) -> SheetRef:
    worksheets = [s for s in sheets if s.kind == "worksheet"]
    if not worksheets:
        raise Refusal("no_sheet", "the workbook has no worksheet")
    if chosen is not None:
        for sheet in worksheets:
            if sheet.name == chosen:
                return sheet
        available = ", ".join(shown(s.name, 40) for s in worksheets[:10])
        raise Refusal(
            "sheet_not_found",
            SHEET_NOT_FOUND.format(name=shown(chosen, 40), available=available),
        )
    return next((s for s in worksheets if s.state == "visible"), worksheets[0])


def read_xlsx(raw: bytes, options: TableOptions) -> RawGrid:
    """The rows of one sheet of ``raw`` as a ``RawGrid`` (see its docstring for what they hold).

    The sheet is ``options.sheet`` or the first visible worksheet.

    Raises ``Refusal`` with the code ``not_xlsx``, ``encrypted_xlsx``, ``zip_bomb``,
    ``encrypted_file``, ``unsafe_xlsx``, ``sheet_not_found``, ``no_sheet``, ``too_many_sheets``,
    ``bad_sheet_name``, ``too_many_rows``, ``too_many_cells``, ``too_much_text`` or
    ``too_many_blank_rows``.
    """
    if raw.startswith(COMPOUND_DOCUMENT):
        raise Refusal("encrypted_xlsx", ENCRYPTED_XLSX)
    if not raw.startswith(b"PK\x03\x04"):
        raise Refusal("not_xlsx", NOT_XLSX)
    check_central_directory(raw)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise Refusal("not_xlsx", NOT_XLSX) from exc
    with archive:
        try:
            check_archive(archive)
            scan_xml_parts(archive)
        except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
            raise Refusal("not_xlsx", "the workbook archive is damaged") from exc
        names = set(archive.namelist())
        notes: list[str] = []
        if any(name.startswith("xl/externalLinks/") for name in names):
            notes.append(LINKS_NOTE)
        if "xl/vbaProject.bin" in names:
            notes.append(MACROS_NOTE)
        try:
            book = read_book(archive, names)
            chosen = _sheet_list(book.sheets, options.sheet)
            assert chosen.part is not None
            meta = GridMeta()
            if "docProps/core.xml" in names:
                meta = book.read_core(archive, "docProps/core.xml")
            reading = book.read_sheet(archive, chosen, header_row=options.header_row)
        except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
            raise Refusal("not_xlsx", "the workbook archive is damaged") from exc
    return RawGrid(
        rows=reading.rows,
        sheet=clean_metadata_text(chosen.name) or "",
        sheet_names=[s.name for s in book.sheets],
        skipped_blank_rows=reading.skipped_blank_rows,
        notes=notes,
        meta=meta,
    )
