"""Read an XLSX workbook into a ``RawGrid`` (P1-I3B-T09b).

An XLSX file is a ZIP archive of XML parts, which makes it the most dangerous input of this
package. The guards, in the order they run:

1. the bytes must be a ZIP archive with a workbook part (``not_xlsx``);
2. the archive is checked before anything is parsed: at most ``MAX_MEMBERS`` parts, no encrypted
   part, a name that is a plain relative path, the declared size of each part and of all parts
   together under their limits (``zip_bomb``); the size the archive declares bounds what the
   reader will return, so the declared sizes are the real bounds;
3. every XML part is scanned for a document type declaration or an entity declaration, and for an
   encoding that hides one (UTF-16), and refused if it has one (``unsafe_xlsx``): a workbook
   written by a spreadsheet program has none, and without them entity expansion cannot happen;
4. openpyxl opens the workbook ``read_only`` (rows are streamed, not built), ``data_only`` (the
   values the file stored; a formula is never evaluated) and ``keep_links=False`` (external
   workbooks are never opened). Macros are never run.

Cell values are turned into text here, deterministically (see ``cell_text``).
"""

from __future__ import annotations

import datetime as dt
import io
import warnings
import zipfile
import zlib
from collections.abc import Iterator

import openpyxl
from tl_core.derivation import MAX_COLUMNS, MAX_ROWS, Cell

from tl_extract.options import TableOptions
from tl_extract.reading import (
    MAX_BLANK_RUN,
    CellBudget,
    GridMeta,
    RawGrid,
    Refusal,
    clean_metadata_text,
    shown,
)

MAX_MEMBERS = 2000
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024
MAX_SHARED_STRINGS_BYTES = 32 * 1024 * 1024
MAX_SHEET_BYTES = 150 * 1024 * 1024
MAX_OTHER_BYTES = 16 * 1024 * 1024
XML_SUFFIXES = (".xml", ".rels", ".vml")
SCAN_CHUNK = 64 * 1024
FORBIDDEN = (b"<!DOCTYPE", b"<!ENTITY")


def _member_limit(name: str) -> int:
    if name == "xl/sharedStrings.xml":
        return MAX_SHARED_STRINGS_BYTES
    if name.startswith("xl/worksheets/") and name.endswith(".xml"):
        return MAX_SHEET_BYTES
    return MAX_OTHER_BYTES


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
                first = False
                head = chunk[:4]
                if head.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in head:
                    raise Refusal(
                        "unsafe_xlsx", "the workbook has an XML part in an unsupported encoding"
                    )
            window = tail + chunk
            if any(marker in window for marker in FORBIDDEN):
                raise Refusal(
                    "unsafe_xlsx",
                    "the workbook declares a document type or an entity, which a spreadsheet "
                    "program never writes",
                )
            tail = window[-(len(FORBIDDEN[0]) - 1) :]


def cell_text(value: object) -> Cell:
    """A cell value as text, the same for the same value every time.

    None and an empty string are None. A bool is ``TRUE`` or ``FALSE``. An int is its digits. A
    float is written with up to 15 significant digits and no trailing zeros (``2024.0`` is
    ``2024``). A date is ``YYYY-MM-DD``; a date with a time is ISO 8601 and drops the time when it
    is midnight; a time of day is ``HH:MM:SS``. Everything else is ``str(value)``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0):
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat()
    text = str(value)
    return text if text else None


def _iso(value: object) -> str | None:
    if isinstance(value, dt.datetime):
        text = value.isoformat(timespec="seconds")
        return text if value.tzinfo is not None else text + "Z"
    return None


def read_xlsx(raw: bytes, options: TableOptions) -> RawGrid:
    """The rows of one sheet of ``raw`` as a ``RawGrid`` (see its docstring for what they hold).

    The sheet is ``options.sheet`` or the first visible worksheet. Rows are read until the end of
    the sheet or until ``MAX_BLANK_RUN`` blank rows in a row (a note says so).

    Raises ``Refusal`` with the code ``not_xlsx``, ``zip_bomb``, ``encrypted_file``,
    ``unsafe_xlsx``, ``sheet_not_found``, ``no_sheet``, ``too_many_rows``, ``too_many_cells`` or
    ``too_much_text``.
    """
    if not raw.startswith(b"PK\x03\x04"):
        raise Refusal("not_xlsx", "the file is not an XLSX workbook (a ZIP archive)")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise Refusal("not_xlsx", "the file is not an XLSX workbook (a ZIP archive)") from exc
    with archive:
        try:
            check_archive(archive)
            scan_xml_parts(archive)
        except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
            raise Refusal("not_xlsx", "the workbook archive is damaged") from exc
        names = set(archive.namelist())
    notes: list[str] = []
    if any(name.startswith("xl/externalLinks/") for name in names):
        notes.append("the workbook links to other workbooks; the links are not followed")
    if "xl/vbaProject.bin" in names:
        notes.append("the workbook holds macros; they are never run")

    with warnings.catch_warnings():
        # openpyxl warns about workbooks other programs wrote (no default style, unknown parts)
        warnings.simplefilter("ignore")
        return _read_workbook(raw, options, notes, "docProps/core.xml" in names)


def _read_workbook(
    raw: bytes, options: TableOptions, notes: list[str], has_core_properties: bool
) -> RawGrid:
    workbook = openpyxl.load_workbook(
        io.BytesIO(raw), read_only=True, data_only=True, keep_links=False
    )
    try:
        sheets = list(workbook.worksheets)
        if not sheets:
            raise Refusal("no_sheet", "the workbook has no worksheet")
        sheet_names = [clean_metadata_text(s) or "" for s in workbook.sheetnames]
        if options.sheet is not None:
            chosen = next((s for s in sheets if s.title == options.sheet), None)
            if chosen is None:
                available = ", ".join(shown(s.title, 40) for s in sheets[:10])
                raise Refusal(
                    "sheet_not_found",
                    f"there is no sheet {shown(options.sheet, 40)}; the sheets are: {available}",
                )
        else:
            chosen = next((s for s in sheets if s.sheet_state == "visible"), sheets[0])
        meta = GridMeta()
        if has_core_properties:
            # without a core part openpyxl invents creator "openpyxl" and the time of the call
            props = workbook.properties
            meta = GridMeta(
                title=clean_metadata_text(props.title),
                author=clean_metadata_text(props.creator),
                created=_iso(props.created),
                modified=_iso(props.modified),
            )
        rows, skipped = _read_rows(
            chosen.iter_rows(max_col=MAX_COLUMNS + 1, values_only=True), options, notes
        )
        title = clean_metadata_text(chosen.title) or ""
    finally:
        workbook.close()
    return RawGrid(
        rows=rows,
        sheet=title,
        sheet_names=sheet_names,
        skipped_blank_rows=skipped,
        notes=notes,
        meta=meta,
    )


def _read_rows(
    source: Iterator[tuple[object, ...]], options: TableOptions, notes: list[str]
) -> tuple[list[list[Cell]], int]:
    budget = CellBudget()
    rows: list[list[Cell]] = []
    skipped = 0
    kept = 0
    blank_run = 0
    for index, values in enumerate(source, start=1):
        cells = [cell_text(v) for v in values]
        while cells and not (cells[-1] or "").strip():
            cells.pop()  # iter_rows(max_col=...) already cut the record at MAX_COLUMNS + 1
        budget.take(cells)
        if index <= options.header_row:
            rows.append(cells)
            continue
        if not cells:
            skipped += 1
            blank_run += 1
            if blank_run >= MAX_BLANK_RUN:
                notes.append(f"reading stopped after {MAX_BLANK_RUN} blank rows in a row")
                break
            continue
        blank_run = 0
        kept += 1
        if kept > MAX_ROWS:
            raise Refusal(
                "too_many_rows", f"the sheet has more than {MAX_ROWS} data rows; split the file"
            )
        rows.append(cells)
    return rows, skipped
