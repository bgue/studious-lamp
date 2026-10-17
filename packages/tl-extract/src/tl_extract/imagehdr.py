# ruff: noqa: F401, F841
"""The size and format of an image file, read from its header by hand (P1-I3B-T11).

PNG, JPEG and TIFF only. No pixel is decoded and no image library is used, so a large or hostile
image costs nothing beyond reading a few hundred bytes; nothing here allocates by a size the file
declares. Every offset and length read from the file is checked against the bytes at hand.

STUB (P1-I3B-T11): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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

NOT_AN_IMAGE = "the file is not a PNG, JPEG or TIFF image"
BIGTIFF = "BigTIFF files are not read"
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
    # STEPS
    # 1. Return "png" if raw starts with PNG_SIGNATURE; "jpeg" if it starts with
    #    b"\xff\xd8\xff"; "tiff" if raw[:4] is one of b"II*\x00", b"MM\x00*", b"II+\x00",
    #    b"MM\x00+"; otherwise None.
    raise NotImplementedError


def _png(raw: bytes) -> ImageInfo:
    # chunks: length (4, big endian), type (4), data, crc (4); IHDR comes first
    # STEPS
    # 1. The header chunk: len(raw) >= 33, raw[12:16] == b"IHDR" and struct.unpack(">I",
    #    raw[8:12])[0] == 13. Otherwise raise Refusal("broken_image", "the PNG has no valid
    #    header chunk").
    # 2. If zlib.crc32(raw[12:29]) != struct.unpack(">I", raw[29:33])[0] raise
    #    Refusal("broken_image", "the PNG header chunk is damaged").
    # 3. width, height = struct.unpack(">II", raw[16:24]). Unless 1 <= width <= 0x7FFFFFFF and 1
    #    <= height <= 0x7FFFFFFF raise Refusal("broken_image", "the PNG declares a size of zero
    #    or too large").
    # 4. info = ImageInfo("png", width, height); pos = 33. Repeat at most MAX_PNG_CHUNKS times
    #    (`for _ in range(MAX_PNG_CHUNKS)`):
    # 5. (a) If pos + 8 > len(raw): stop. length, kind = struct.unpack(">I4s", raw[pos : pos +
    #    8]); data = raw[pos + 8 : pos + 8 + length].
    # 6. (b) Stop if len(data) < length (the chunk is cut short) or kind is b"IDAT" or b"IEND".
    # 7. (c) kind == b"tEXt" and b"\x00" in data: keyword, _, text = data.partition(b"\x00");
    #    value = clean_metadata_text(text.decode("latin-1")); name = keyword.decode("latin-1").
    #    "Title" sets info.title, "Author" info.author, "Software" info.producer, "Creation
    #    Time" info.created; each only while that field is still None (the first chunk of a
    #    keyword wins).
    # 8. (d) kind == b"tIME" and length == 7 and info.modified is None: year, month, day, hour,
    #    minute, second = struct.unpack(">HBBBBB", data). When 1 <= month <= 12, 1 <= day <= 31,
    #    hour < 24, minute < 60 and second < 61 set info.modified =
    #    f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z".
    # 9. (e) pos += 12 + length. Chunks of any other kind, zTXt and iTXt included, are skipped
    #    unread.
    # 10. Return info.
    raise NotImplementedError


def _jpeg(raw: bytes) -> ImageInfo:
    # segments: 0xFF, a marker byte, then (except for standalone markers) a two-byte length that
    # counts itself; the frame header (SOFn) gives height then width
    # STEPS
    # 1. pos = 2. Repeat at most MAX_JPEG_SEGMENTS times (`for _ in range(MAX_JPEG_SEGMENTS)`);
    #    "stop" below means break out of that loop:
    # 2. (a) Stop if pos >= len(raw) or raw[pos] != 0xFF.
    # 3. (b) Skip fill bytes: while pos < len(raw) and raw[pos] == 0xFF: pos += 1. Stop if pos
    #    >= len(raw).
    # 4. (c) marker = raw[pos]; pos += 1. Stop if marker == 0x00.
    # 5. (d) If marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7 the marker has no length:
    #    continue.
    # 6. (e) If marker in (0xD9, 0xDA) stop: end of image, or start of scan with no frame header
    #    before it. Scan data is never searched.
    # 7. (f) Stop if pos + 2 > len(raw). length = struct.unpack(">H", raw[pos : pos + 2])[0].
    #    Stop if length < 2.
    # 8. (g) If marker in _SOF_MARKERS: frame = raw[pos + 2 : pos + length]; stop if len(frame)
    #    < 5; height, width = struct.unpack(">HH", frame[1:5]) (height comes first); stop if
    #    width == 0 or height == 0; return ImageInfo("jpeg", width, height).
    # 9. (h) pos += length.
    # 10. After the loop raise Refusal("broken_image", "the JPEG has no valid frame header").
    raise NotImplementedError


def _tiff(raw: bytes) -> ImageInfo:
    # STEPS
    # 1. BigTIFF has "+" at index 2 or 3 of the header (II+\0 and MM\0+). If raw[2:3] == b"+" or
    #    raw[3:4] == b"+" raise Refusal("unsupported_image", BIGTIFF).
    # 2. order = "<" if raw[:2] == b"II" else ">". If len(raw) < 8 raise Refusal("broken_image",
    #    "the TIFF is too short"). offset = struct.unpack(order + "I", raw[4:8])[0].
    # 3. If offset < 8 or offset + 2 > len(raw) raise Refusal("broken_image", "the TIFF has no
    #    valid first directory"). count = struct.unpack(order + "H", raw[offset : offset +
    #    2])[0]. If count == 0 or count > MAX_TIFF_ENTRIES or offset + 2 + 12 * count > len(raw)
    #    raise the same Refusal.
    # 4. width = height = None; texts = {} (tag number to text). For index in range(count): base
    #    = offset + 2 + 12 * index; tag, kind, n = struct.unpack(order + "HHI", raw[base : base
    #    + 8]); slot = raw[base + 8 : base + 12].
    # 5. (a) tag 256 or 257 with n == 1 and kind in (3, 4): value = struct.unpack(order + "H",
    #    slot[:2])[0] when kind == 3 (SHORT, in the first two bytes of the slot), else
    #    struct.unpack(order + "I", slot)[0] (LONG). 256 is the width, 257 the height.
    # 6. (b) tag in (270, 305, 306, 315) with kind == 2 (ASCII) and 0 < n <= MAX_TIFF_TEXT: when
    #    n <= 4 the text is slot[:n]; otherwise where = struct.unpack(order + "I", slot)[0] and
    #    the text is raw[where : where + n] if where + n <= len(raw), else b"". Then text =
    #    clean_metadata_text(data.split(b"\x00", 1)[0].decode("latin-1")); keep it in texts[tag]
    #    when it is not None.
    # 7. If not width or not height raise Refusal("broken_image", "the TIFF has no width and
    #    height").
    # 8. modified: stamp = texts.get(306). Only when stamp is 19 characters long, has ":" at
    #    index 4 and 7 and " " at index 10, modified = stamp[:4] + "-" + stamp[5:7] + "-" +
    #    stamp[8:10] + "T" + stamp[11:]; otherwise None.
    # 9. Return ImageInfo("tiff", width, height, title=texts.get(270), author=texts.get(315),
    #    producer=texts.get(305), modified=modified).
    raise NotImplementedError


def read_image_header(raw: bytes) -> ImageInfo:
    """The format, width and height of the image in ``raw``, with the text properties its header
    carries (PNG ``tEXt`` Title/Author/Software/Creation Time and ``tIME``; TIFF
    ImageDescription/Artist/Software/DateTime).

    Raises ``Refusal`` with the code ``not_an_image`` (not PNG, JPEG or TIFF),
    ``unsupported_image`` (BigTIFF) or ``broken_image`` (the header is damaged or cut short).
    """
    # STEPS
    # 1. kind = sniff(raw). None raises Refusal("not_an_image", NOT_AN_IMAGE).
    # 2. In a try block return _png(raw), _jpeg(raw) or _tiff(raw) by kind. `except
    #    (struct.error, IndexError, UnicodeError) as exc` raises Refusal("broken_image", "the
    #    image header is damaged") from exc. A Refusal raised inside passes through unchanged.
    raise NotImplementedError
