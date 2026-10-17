"""Bounded readers of the XML parts of an XLSX workbook (P1-I3B-S14).

openpyxl is not used: it builds a whole row (or the whole shared-strings table) before any cap can
look at it, and a file of 99 KB made it spend 99 s and 7.7 GB. These readers stream the parts with
``xml.etree.ElementTree.iterparse`` and count as they go: elements, nesting depth, shared strings,
cells and characters. They refuse the moment a count passes its cap, and they drop each row and each
string element as soon as it is read, so the memory is the table that is kept, not the XML.

Entity tricks are shut out before a part reaches the parser (``xlsxgrid.scan_xml_parts`` refuses any
part with a document type or entity declaration). A formula is never evaluated: a cell is the value
the file stored (``<v>``), or empty. External links are never opened: only the parts named here are
read, by fixed or by relationship-resolved path inside the archive.
"""

from __future__ import annotations

import datetime as dt
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field

from tl_core.derivation import MAX_COLUMNS, MAX_ROWS, Cell

from tl_extract.reading import (
    MAX_BLANK_RUN,
    MAX_TOTAL_CHARS,
    CellBudget,
    GridMeta,
    Refusal,
    clean_metadata_text,
)

MAX_XML_DEPTH = 64
MAX_ELEMENTS = 5_000_000
MAX_SHEETS = 256
MAX_SHEET_NAME = 255
MAX_SHARED_STRINGS = 1_000_000
#: A shared string is cut here: a cell this long is refused by the table builder anyway.
MAX_STRING_CHARS = 40_000
MAX_STYLES = 65_536
WORKBOOK = "xl/workbook.xml"
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"

_W3CDTF = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$"
)
_DATE_LETTERS = re.compile(r"[dmyhs]", re.IGNORECASE)
_STRIP_FORMAT = re.compile(r'"[^"]*"|\\.|_.|\*.|\[(?![hms]+\])[^\]]*\]', re.IGNORECASE)
BUILTIN_DATE_IDS = frozenset([*range(14, 23), *range(27, 37), *range(45, 48), *range(50, 59)])


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


def local(tag: str) -> str:
    """The tag without its namespace: ``{...main}c`` is ``c``."""
    return tag.rsplit("}", 1)[-1]


def attribute(element: ET.Element, name: str) -> str | None:
    """An attribute by its local name (``id`` matches ``r:id``)."""
    for key, value in element.attrib.items():
        if local(key) == name:
            return value
    return None


def events(archive: zipfile.ZipFile, name: str) -> Iterator[tuple[str, ET.Element, list[str]]]:
    """``(event, element, path)`` for each start and end of an element of the part, ``path`` being
    the local names of the open elements, innermost last. Raises ``Refusal`` for a part that is not
    well formed, nests deeper than ``MAX_XML_DEPTH`` or has more than ``MAX_ELEMENTS`` elements."""
    path: list[str] = []
    count = 0
    try:
        with archive.open(name) as part:
            for event, element in ET.iterparse(part, events=("start", "end")):
                if event == "start":
                    path.append(local(element.tag))
                    count += 1
                    if len(path) > MAX_XML_DEPTH or count > MAX_ELEMENTS:
                        raise Refusal("unsafe_xlsx", "the workbook has an XML part that is too big")
                    yield event, element, path
                else:
                    yield event, element, path
                    path.pop()
    except ET.ParseError as exc:
        raise Refusal("not_xlsx", "the workbook has an XML part that is not well formed") from exc


def part_name(target: str, base: str = "xl/") -> str:
    """The archive path a relationship target names. Raises ``Refusal`` unless it stays inside the
    archive and ends in ``.xml`` (every part read here was scanned as XML)."""
    path = posixpath.normpath(target[1:] if target.startswith("/") else base + target)
    if path.startswith("..") or not path.endswith(".xml"):
        raise Refusal("unsafe_xlsx", "the workbook names a part it should not")
    return path


@dataclass
class SheetRef:
    name: str
    state: str
    kind: str  # "worksheet", "chartsheet" or "other"
    part: str | None


@dataclass
class Book:
    sheets: list[SheetRef]
    date1904: bool = False
    shared_strings: str | None = None
    styles: str | None = None

    def read_core(self, archive: zipfile.ZipFile, name: str) -> GridMeta:
        return read_core(archive, name)

    def read_sheet(
        self, archive: zipfile.ZipFile, sheet: SheetRef, *, header_row: int
    ) -> SheetReading:
        """Load the shared strings and the date styles (only this sheet needs them) and stream the
        sheet's records."""
        strings = read_shared_strings(archive, self.shared_strings) if self.shared_strings else []
        styles = read_date_styles(archive, self.styles) if self.styles else frozenset[int]()
        assert sheet.part is not None
        return read_sheet(
            archive,
            sheet.part,
            header_row=header_row,
            strings=strings,
            date_styles=styles,
            date1904=self.date1904,
        )


def read_rels(archive: zipfile.ZipFile) -> dict[str, tuple[str, str]]:
    """``{id: (type, target)}`` of the workbook's relationships (internal targets only)."""
    found: dict[str, tuple[str, str]] = {}
    for event, element, _ in events(archive, WORKBOOK_RELS):
        if event == "end" and local(element.tag) == "Relationship":
            if element.get("TargetMode", "Internal").lower() == "external":
                continue
            ident, kind, target = element.get("Id"), element.get("Type"), element.get("Target")
            if ident and kind and target and len(found) < 4 * MAX_SHEETS:
                found[ident] = (kind.rsplit("/", 1)[-1], target)
        if event == "end":
            element.clear()
    return found


def read_book(archive: zipfile.ZipFile, names: set[str]) -> Book:
    """The sheets (in workbook order), the date system and the parts the cells need.

    Raises ``Refusal`` (``too_many_sheets``, ``bad_sheet_name``, ``unsafe_xlsx``, ``not_xlsx``).
    """
    rels = read_rels(archive) if WORKBOOK_RELS in names else {}
    book = Book(sheets=[])
    for event, element, _ in events(archive, WORKBOOK):
        if event != "end":
            continue
        tag = local(element.tag)
        if tag == "workbookPr":
            book.date1904 = (element.get("date1904") or "").lower() in ("1", "true")
        elif tag == "sheet":
            if len(book.sheets) >= MAX_SHEETS:
                raise Refusal("too_many_sheets", f"the workbook has more than {MAX_SHEETS} sheets")
            name = element.get("name") or ""
            if len(name) > MAX_SHEET_NAME:
                raise Refusal("bad_sheet_name", "the workbook has a sheet with a very long name")
            kind, target = rels.get(attribute(element, "id") or "", ("", ""))
            part = part_name(target) if target and kind in ("worksheet", "chartsheet") else None
            if part is not None and part not in names:
                part = None
            book.sheets.append(
                SheetRef(
                    name=clean_metadata_text(name, MAX_SHEET_NAME) or "",
                    state=element.get("state") or "visible",
                    kind=kind if kind in ("worksheet", "chartsheet") and part else "other",
                    part=part,
                )
            )
        element.clear()
    for kind, target in rels.values():
        if kind == "sharedStrings" and book.shared_strings is None:
            candidate = part_name(target)
            book.shared_strings = candidate if candidate in names else None
        elif kind == "styles" and book.styles is None:
            candidate = part_name(target)
            book.styles = candidate if candidate in names else None
    return book


def read_shared_strings(archive: zipfile.ZipFile, name: str) -> list[str]:
    """The shared strings, in order. A string is the text of its ``<t>`` elements (phonetic runs
    left out), cut at ``MAX_STRING_CHARS``. Raises ``Refusal("too_many_cells")`` past
    ``MAX_SHARED_STRINGS`` strings and ``Refusal("too_much_text")`` past ``MAX_TOTAL_CHARS``."""
    strings: list[str] = []
    stack: list[ET.Element] = []
    pieces: list[str] = []
    chars = 0
    for event, element, path in events(archive, name):
        if event == "start":
            stack.append(element)
            continue
        stack.pop()
        tag = path[-1]
        if tag == "t" and "rPh" not in path and (len(path) < 2 or path[-2] in ("si", "r")):
            piece = element.text or ""
            chars += len(piece)
            if chars > MAX_TOTAL_CHARS:
                raise Refusal("too_much_text", "the shared strings hold too much text")
            pieces.append(piece)
        elif tag == "si":
            if len(strings) >= MAX_SHARED_STRINGS:
                raise Refusal("too_many_cells", "the workbook has too many shared strings")
            strings.append("".join(pieces)[:MAX_STRING_CHARS])
            pieces = []
            if stack:
                stack[-1].remove(element)
        if tag != "t":
            element.clear()
    return strings


def is_date_format(number_format_id: int, code: str | None) -> bool:
    """Whether a number format shows a date or a time: a built-in date id, or a custom code with a
    d, m, y, h or s once quoted text, escaped characters, padding and colours are taken out."""
    if code is None:
        return number_format_id in BUILTIN_DATE_IDS
    stripped = _STRIP_FORMAT.sub("", code)
    return _DATE_LETTERS.search(stripped) is not None and "general" not in stripped.lower()


def read_date_styles(archive: zipfile.ZipFile, name: str) -> frozenset[int]:
    """The indexes of the cell formats (``cellXfs``) that show a date or a time."""
    codes: dict[int, str] = {}
    date_styles: set[int] = set()
    index = 0
    for event, element, path in events(archive, name):
        if event != "end":
            continue
        tag = path[-1]
        if tag == "numFmt" and "numFmts" in path:
            ident, code = element.get("numFmtId"), element.get("formatCode")
            if ident and ident.isdigit() and code is not None and len(codes) < MAX_STYLES:
                codes[int(ident)] = code[:256]
        elif tag == "xf" and "cellXfs" in path:
            ident = element.get("numFmtId") or "0"
            number = int(ident) if ident.isdigit() else 0
            if index < MAX_STYLES and is_date_format(number, codes.get(number)):
                date_styles.add(index)
            index += 1
        element.clear()
    return frozenset(date_styles)


def read_core(archive: zipfile.ZipFile, name: str) -> GridMeta:
    """Title, author and the two dates of ``docProps/core.xml``, as stored. A date that is not
    W3CDTF is dropped; a field the file does not have stays None."""
    meta = GridMeta()
    for event, element, _ in events(archive, name):
        if event != "end":
            continue
        tag = local(element.tag)
        text = element.text or ""
        if tag == "title":
            meta.title = clean_metadata_text(text)
        elif tag == "creator":
            meta.author = clean_metadata_text(text)
        elif tag in ("created", "modified"):
            value = text.strip()[:40]
            if _W3CDTF.match(value):
                setattr(meta, tag, value)
        element.clear()
    return meta


def from_serial(value: float, date1904: bool) -> dt.datetime | dt.time | None:
    """An Excel serial number as a date and time (to the second), or a time of day for a fraction
    of a day. None when the number is not a date (negative, or past the year 9999)."""
    if not 0 <= value < 2_958_466:
        return None
    seconds = round(value * 86_400)
    if date1904:
        base = dt.datetime(1904, 1, 1)
    else:
        # serial 1 is 1900-01-01; Excel counts a 29 February 1900 that never was, so from serial
        # 61 the epoch is 1899-12-30
        base = dt.datetime(1899, 12, 30) if value >= 61 else dt.datetime(1899, 12, 31)
    moment = base + dt.timedelta(seconds=seconds)
    if value < 1:
        return moment.time()
    return moment


def number_value(text: str) -> int | float | str:
    """The number a ``<v>`` holds: an int when it has no point or exponent, else a float; the text
    itself when it is not a number (a number of thousands of digits included)."""
    text = text.strip()
    try:
        if "." in text or "e" in text or "E" in text:
            return float(text)
        return int(text) if len(text) < 400 else text[:40]
    except ValueError:
        return text[:40]


@dataclass
class SheetReading:
    rows: list[list[Cell]] = field(default_factory=list[list[Cell]])
    skipped_blank_rows: int = 0


def column_index(reference: str) -> int:
    """The 1-based column of a cell reference such as ``AB12`` (0 when it has none)."""
    index = 0
    for char in reference:
        if "A" <= char <= "Z":
            index = index * 26 + ord(char) - 64
        elif "a" <= char <= "z":
            index = index * 26 + ord(char) - 96
        else:
            break
        if index > 1_000_000:
            return 0
    return index


def read_sheet(
    archive: zipfile.ZipFile,
    name: str,
    *,
    header_row: int,
    strings: list[str],
    date_styles: frozenset[int],
    date1904: bool,
) -> SheetReading:
    """The records of one worksheet, streamed.

    Records up to and including ``header_row`` are kept as they are (a row the file does not have
    is an empty record); after it a blank record is skipped and counted, and ``MAX_ROWS`` data
    rows are allowed. A record is cut after the last non-empty cell and at ``MAX_COLUMNS + 1``
    cells. Raises ``Refusal`` (``too_many_rows``, ``too_many_cells``, ``too_much_text``,
    ``too_many_blank_rows`` when data follows ``MAX_BLANK_RUN`` blank rows, and the XML refusals
    of ``events``).
    """
    out = SheetReading()
    budget = CellBudget()
    width = MAX_COLUMNS + 1
    stack: list[ET.Element] = []
    expected = 1  # the number of the next row to be written
    blank_run = 0
    kept = 0
    # the cell being read
    values: list[Cell] = []
    cell_col = 0
    cell_type = ""
    cell_style = -1
    cell_value: str | None = None
    cell_inline: list[str] = []

    def blank_rows(count: int) -> None:
        nonlocal blank_run
        while count > 0 and len(out.rows) < header_row:
            out.rows.append([])
            count -= 1
        out.skipped_blank_rows += count
        blank_run += count

    for event, element, path in events(archive, name):
        tag = path[-1]
        if event == "start":
            stack.append(element)
            if tag == "row":
                values = []
                number = element.get("r") or ""
                row_number = (
                    int(number) if number.isdigit() and int(number) >= expected else expected
                )
                blank_rows(row_number - expected)
                expected = row_number
            elif tag == "c":
                cell_col = column_index(element.get("r") or "") or len(values) + 1
                cell_type = element.get("t") or "n"
                style = element.get("s") or ""
                cell_style = int(style) if style.isdigit() else -1
                cell_value = None
                cell_inline = []
            continue
        stack.pop()
        if tag == "v" and "c" in path:
            cell_value = element.text or ""
        elif tag == "t" and "is" in path and "rPh" not in path:
            cell_inline.append(element.text or "")
        elif tag == "c":
            if cell_col <= width:
                text = _cell(
                    cell_type,
                    cell_value,
                    cell_inline,
                    cell_style,
                    strings,
                    date_styles,
                    date1904,
                )
                if text is not None:
                    while len(values) < cell_col:
                        values.append(None)
                    values[cell_col - 1] = text
        elif tag == "row":
            expected += 1
            cells = values
            values = []
            while cells and not (cells[-1] or "").strip():
                cells.pop()
            if len(out.rows) < header_row:
                budget.take(cells, count_cells=False)
                out.rows.append(cells)
            elif not cells:
                out.skipped_blank_rows += 1
                blank_run += 1
            else:
                if blank_run >= MAX_BLANK_RUN:
                    raise Refusal(
                        "too_many_blank_rows",
                        f"data follows {blank_run} blank rows; the sheet is not read past them",
                    )
                blank_run = 0
                kept += 1
                if kept > MAX_ROWS:
                    raise Refusal(
                        "too_many_rows",
                        f"the sheet has more than {MAX_ROWS} data rows; split the file",
                    )
                budget.take(cells)
                out.rows.append(cells)
            if stack:
                stack[-1].remove(element)
        if tag in ("c", "row", "v", "t", "is", "f", "si"):
            element.clear()
    return out


def _cell(
    kind: str,
    value: str | None,
    inline: list[str],
    style: int,
    strings: list[str],
    date_styles: frozenset[int],
    date1904: bool,
) -> Cell:
    if kind == "inlineStr":
        return cell_text("".join(inline))
    if value is None:
        return None
    if kind == "s":
        if value.strip().isdigit() and int(value) < len(strings):
            return cell_text(strings[int(value)])
        return None
    if kind in ("str", "e", "d"):
        return cell_text(value)
    if kind == "b":
        return cell_text(value.strip().lower() in ("1", "true"))
    number = number_value(value)
    if isinstance(number, str):
        return cell_text(number)
    if style in date_styles:
        moment = from_serial(float(number), date1904)
        if moment is not None:
            return cell_text(moment)
    return cell_text(number)
