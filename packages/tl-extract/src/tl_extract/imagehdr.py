"""The size and format of an image file, read from its header by hand (P1-I3B-T11).

PNG, JPEG and TIFF only. No pixel is decoded and no image library is used, so a large or hostile
image costs nothing beyond reading a few hundred bytes; nothing here allocates by a size the file
declares. Every offset and length read from the file is checked against the bytes at hand.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Literal

from tl_extract.reading import Refusal, clean_metadata_text

ImageFormat = Literal["png", "jpeg", "tiff"]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_CHUNKS = 200
MAX_JPEG_SEGMENTS = 500
MAX_TIFF_ENTRIES = 512
MAX_TIFF_TEXT = 4096
_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


@dataclass
class ImageInfo:
    format: ImageFormat
    width: int
    height: int
    title: str | None = None
    author: str | None = None
    producer: str | None = None
    created: str | None = None
    modified: str | None = None


def sniff(raw: bytes) -> ImageFormat | None:
    """The format the first bytes say: PNG, JPEG or TIFF (classic or big-endian/little-endian
    BigTIFF), else None."""
    if raw.startswith(PNG_SIGNATURE):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return "tiff"
    return None


def _png(raw: bytes) -> ImageInfo:
    # chunks: length (4, big endian), type (4), data, crc (4); IHDR comes first
    if len(raw) < 33 or raw[12:16] != b"IHDR" or struct.unpack(">I", raw[8:12])[0] != 13:
        raise Refusal("broken_image", "the PNG has no valid header chunk")
    if zlib.crc32(raw[12:29]) != struct.unpack(">I", raw[29:33])[0]:
        raise Refusal("broken_image", "the PNG header chunk is damaged")
    width, height = struct.unpack(">II", raw[16:24])
    if not (1 <= width <= 0x7FFFFFFF and 1 <= height <= 0x7FFFFFFF):
        raise Refusal("broken_image", "the PNG declares a size of zero or too large")
    info = ImageInfo("png", width, height)
    pos = 33
    for _ in range(MAX_PNG_CHUNKS):
        if pos + 8 > len(raw):
            break
        length, kind = struct.unpack(">I4s", raw[pos : pos + 8])
        data = raw[pos + 8 : pos + 8 + length]
        if len(data) < length or kind in (b"IDAT", b"IEND"):
            break
        if kind == b"tEXt" and b"\x00" in data:
            keyword, _, text = data.partition(b"\x00")
            value = clean_metadata_text(text.decode("latin-1"))
            name = keyword.decode("latin-1")
            if name == "Title" and info.title is None:
                info.title = value
            elif name == "Author" and info.author is None:
                info.author = value
            elif name == "Software" and info.producer is None:
                info.producer = value
            elif name == "Creation Time" and info.created is None:
                info.created = value
        elif kind == b"tIME" and length == 7 and info.modified is None:
            year, month, day, hour, minute, second = struct.unpack(">HBBBBB", data)
            if 1 <= month <= 12 and 1 <= day <= 31 and hour < 24 and minute < 60 and second < 61:
                info.modified = (
                    f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
                )
        pos += 12 + length
    return info


def _jpeg(raw: bytes) -> ImageInfo:
    # segments: 0xFF, a marker byte, then (except for standalone markers) a two-byte length that
    # counts itself; the frame header (SOFn) gives height then width
    pos = 2
    for _ in range(MAX_JPEG_SEGMENTS):
        if pos >= len(raw) or raw[pos] != 0xFF:
            break
        while pos < len(raw) and raw[pos] == 0xFF:
            pos += 1  # fill bytes
        if pos >= len(raw):
            break
        marker = raw[pos]
        pos += 1
        if marker == 0x00:
            break
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            continue  # standalone: no length
        if marker in (0xD9, 0xDA):
            break  # end of image or start of scan, and no frame header came first
        if pos + 2 > len(raw):
            break
        length = struct.unpack(">H", raw[pos : pos + 2])[0]
        if length < 2:
            break
        if marker in _SOF_MARKERS:
            frame = raw[pos + 2 : pos + length]
            if len(frame) < 5:
                break
            height, width = struct.unpack(">HH", frame[1:5])
            if width == 0 or height == 0:
                break
            return ImageInfo("jpeg", width, height)
        pos += length
    raise Refusal("broken_image", "the JPEG has no valid frame header")


def _tiff(raw: bytes) -> ImageInfo:
    if raw[2:3] == b"+" or raw[3:4] == b"+":
        raise Refusal("unsupported_image", "BigTIFF files are not read")
    order = "<" if raw[:2] == b"II" else ">"
    if len(raw) < 8:
        raise Refusal("broken_image", "the TIFF is too short")
    offset = struct.unpack(order + "I", raw[4:8])[0]
    if offset < 8 or offset + 2 > len(raw):
        raise Refusal("broken_image", "the TIFF has no valid first directory")
    count = struct.unpack(order + "H", raw[offset : offset + 2])[0]
    if count == 0 or count > MAX_TIFF_ENTRIES or offset + 2 + 12 * count > len(raw):
        raise Refusal("broken_image", "the TIFF has no valid first directory")
    width = height = None
    texts: dict[int, str] = {}
    for index in range(count):
        base = offset + 2 + 12 * index
        tag, kind, n = struct.unpack(order + "HHI", raw[base : base + 8])
        slot = raw[base + 8 : base + 12]
        if tag in (256, 257) and n == 1 and kind in (3, 4):
            value = (
                struct.unpack(order + "H", slot[:2])[0]
                if kind == 3
                else struct.unpack(order + "I", slot)[0]
            )
            if tag == 256:
                width = value
            else:
                height = value
        elif tag in (270, 305, 306, 315) and kind == 2 and 0 < n <= MAX_TIFF_TEXT:
            if n <= 4:
                data = slot[:n]
            else:
                where = struct.unpack(order + "I", slot)[0]
                data = raw[where : where + n] if where + n <= len(raw) else b""
            text = clean_metadata_text(data.split(b"\x00", 1)[0].decode("latin-1"))
            if text is not None:
                texts[tag] = text
    if not width or not height:
        raise Refusal("broken_image", "the TIFF has no width and height")
    modified = None
    stamp = texts.get(306)
    if stamp and len(stamp) == 19 and stamp[4] == stamp[7] == ":" and stamp[10] == " ":
        modified = stamp[:4] + "-" + stamp[5:7] + "-" + stamp[8:10] + "T" + stamp[11:]
    return ImageInfo(
        "tiff",
        width,
        height,
        title=texts.get(270),
        author=texts.get(315),
        producer=texts.get(305),
        modified=modified,
    )


def read_image_header(raw: bytes) -> ImageInfo:
    """The format, width and height of the image in ``raw``, with the text properties its header
    carries (PNG ``tEXt`` Title/Author/Software/Creation Time and ``tIME``; TIFF
    ImageDescription/Artist/Software/DateTime).

    Raises ``Refusal`` with the code ``not_an_image`` (not PNG, JPEG or TIFF),
    ``unsupported_image`` (BigTIFF) or ``broken_image`` (the header is damaged or cut short).
    """
    kind = sniff(raw)
    if kind is None:
        raise Refusal("not_an_image", "the file is not a PNG, JPEG or TIFF image")
    try:
        if kind == "png":
            return _png(raw)
        if kind == "jpeg":
            return _jpeg(raw)
        return _tiff(raw)
    except (struct.error, IndexError, UnicodeError) as exc:
        raise Refusal("broken_image", "the image header is damaged") from exc
