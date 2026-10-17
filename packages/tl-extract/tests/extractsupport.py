# ruff: noqa: E501 (XML namespace URIs and PDF trailers are long single tokens)
"""Builders of the files the extractor tests read (P1-I3B-S2). Test code only.

Everything is made in memory from bytes, so no test needs a fixture file and a hostile file can be
written down in a few lines: a PDF, a PNG, a JPEG, a TIFF, an XLSX with the parts of one's choice.
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Mapping, Sequence

import openpyxl
from tl_core.derivation import Cell, ExtractionResult, Extractor, SourceFile
from tl_extract.reading import RawGrid

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def source_for(filename: str, content_type: str, data: bytes) -> SourceFile:
    import hashlib

    return SourceFile(
        file_id="f-test",
        filename=filename,
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_ref="src.doc.TEST-001@A",
    )


def run(
    extractor: Extractor,
    filename: str,
    content_type: str,
    data: bytes,
    options: Mapping[str, object] | None = None,
) -> ExtractionResult:
    """Run ``extractor`` over ``data`` as the file ``filename``."""
    return extractor.extract(
        source_for(filename, content_type, data), io.BytesIO(data), dict(options or {})
    )


def run_source(
    extractor: Extractor,
    source: SourceFile,
    data: bytes,
    options: Mapping[str, object] | None = None,
) -> ExtractionResult:
    """Run ``extractor`` with a ``SourceFile`` that may not match ``data`` (a claimed size)."""
    return extractor.extract(source, io.BytesIO(data), dict(options or {}))


def csv_bytes(text: str, encoding: str = "utf-8") -> bytes:
    return text.encode(encoding)


def grid_of(*records: Sequence[Cell]) -> RawGrid:
    """A ``RawGrid`` of the given records (the first is the header unless the options say so)."""
    return RawGrid(rows=[list(r) for r in records])


def xlsx_bytes(
    sheets: Mapping[str, Sequence[Sequence[object]]],
    *,
    title: str | None = None,
    creator: str | None = None,
    hidden: Sequence[str] = (),
) -> bytes:
    """An XLSX file with the given sheets (name to rows of values), written by openpyxl."""
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(list(row))
        if name in hidden:
            sheet.sheet_state = "hidden"
    if title is not None:
        workbook.properties.title = title
    if creator is not None:
        workbook.properties.creator = creator
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def zip_bytes(parts: Mapping[str, bytes], compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    """A ZIP archive with the given parts."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compress) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    b'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    b"</Types>"
)
ROOT_RELS = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    b"</Relationships>"
)
WORKBOOK = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    b'<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
WORKBOOK_RELS = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    b"</Relationships>"
)


def sheet_xml(rows_xml: str, dimension: str | None = None) -> bytes:
    """A worksheet part: ``rows_xml`` is the inside of ``<sheetData>`` (hand-written rows)."""
    dim = f'<dimension ref="{dimension}"/>' if dimension else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{dim}<sheetData>{rows_xml}</sheetData></worksheet>"
    ).encode()


def hand_xlsx(sheet: bytes, extra: Mapping[str, bytes] | None = None) -> bytes:
    """The smallest workbook that openpyxl opens, around one hand-written worksheet part."""
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "xl/workbook.xml": WORKBOOK,
        "xl/_rels/workbook.xml.rels": WORKBOOK_RELS,
        "xl/worksheets/sheet1.xml": sheet,
    }
    parts.update(extra or {})
    return zip_bytes(parts)


def inline_row(number: int, values: Sequence[str]) -> str:
    """A worksheet row of inline strings, for ``sheet_xml``."""
    cells = "".join(
        f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{v}</t></is></c>'
        for i, v in enumerate(values)
    )
    return f'<row r="{number}">{cells}</row>'


def make_pdf(
    info: Mapping[str, str | bytes] | None = None,
    pages: int = 1,
    header: bytes = b"%PDF-1.4\n",
    encrypted: bool = False,
    count: int | None = None,
) -> bytes:
    """A small valid PDF with ``pages`` blank pages and the given information dictionary.

    An ``info`` value that is ``str`` is written as a literal string ``(...)``; ``bytes`` are
    written as they are (a hex string ``<FEFF...>``, a name). ``encrypted`` adds an ``/Encrypt``
    dictionary to the trailer (the file stays unreadable content, as an encrypted one is).
    ``count`` overrides the ``/Count`` of the page tree.
    """
    objects: list[bytes] = []
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    shown_count = pages if count is None else count
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {shown_count} >>".encode())
    for _ in range(pages):
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>")
    info_ref = ""
    if info:
        body = b"".join(
            f"/{key} ".encode()
            + (value if isinstance(value, bytes) else f"({value})".encode("latin-1"))
            + b" "
            for key, value in info.items()
        )
        objects.append(b"<< " + body + b">>")
        info_ref = f" /Info {len(objects)} 0 R"
    if encrypted:
        objects.append(
            b"<< /Filter /Standard /V 1 /R 2 /P -4 /O ("
            + b"o" * 32
            + b") /U ("
            + b"u" * 32
            + b") >>"
        )
        info_ref += f" /Encrypt {len(objects)} 0 R /ID [<00112233445566778899aabbccddeeff> <00112233445566778899aabbccddeeff>]"
    out = io.BytesIO()
    out.write(header)
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R{info_ref} >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def make_png(
    width: int = 8,
    height: int = 6,
    text: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
    time: tuple[int, int, int, int, int, int] | None = None,
) -> bytes:
    """A PNG whose header says ``width`` x ``height`` (the pixel data is one empty block).

    ``text`` is the tEXt chunks (keyword and text), in the order given."""
    pairs = list(text.items()) if isinstance(text, Mapping) else list(text or [])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    parts = [b"\x89PNG\r\n\x1a\n", png_chunk(b"IHDR", ihdr)]
    for key, value in pairs:
        parts.append(png_chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1")))
    if time is not None:
        parts.append(png_chunk(b"tIME", struct.pack(">HBBBBB", *time)))
    parts.append(png_chunk(b"IDAT", zlib.compress(b"")))
    parts.append(png_chunk(b"IEND", b""))
    return b"".join(parts)


def make_jpeg(width: int = 8, height: int = 6) -> bytes:
    """A JPEG that is a start of image, a comment, a frame header and an end of image."""
    sof = struct.pack(">BHHB", 8, height, width, 1) + b"\x01\x11\x00"
    return (
        b"\xff\xd8"
        + b"\xff\xfe"
        + struct.pack(">H", 2 + 4)
        + b"hi!!"
        + b"\xff\xc0"
        + struct.pack(">H", 2 + len(sof))
        + sof
        + b"\xff\xd9"
    )


def make_tiff(
    width: int = 8,
    height: int = 6,
    text: Mapping[int, str] | None = None,
    byte_order: str = "<",
) -> bytes:
    """A TIFF with one directory: ImageWidth, ImageLength and the text tags given (tag to text)."""
    tags: list[tuple[int, int, int, bytes]] = [
        (256, 4, 1, struct.pack(byte_order + "I", width)),
        (257, 3, 1, struct.pack(byte_order + "H", height) + b"\x00\x00"),
    ]
    extra = b""
    count = 2 + len(text or {})
    base = 8 + 2 + 12 * count + 4
    for tag, value in sorted((text or {}).items()):
        data = value.encode("latin-1") + b"\x00"
        if len(data) <= 4:
            tags.append((tag, 2, len(data), data.ljust(4, b"\x00")))
        else:
            tags.append((tag, 2, len(data), struct.pack(byte_order + "I", base + len(extra))))
            extra += data
    tags.sort()
    head = (b"II*\x00" if byte_order == "<" else b"MM\x00*") + struct.pack(byte_order + "I", 8)
    directory = struct.pack(byte_order + "H", len(tags))
    for tag, kind, n, slot in tags:
        directory += struct.pack(byte_order + "HHI", tag, kind, n) + slot
    directory += struct.pack(byte_order + "I", 0)
    return head + directory + extra


def pdf_from_objects(objects: Sequence[bytes]) -> bytes:
    """A PDF made of exactly these objects (object 1 is the catalog), with a correct xref table."""
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()
