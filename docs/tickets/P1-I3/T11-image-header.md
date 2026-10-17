# P1-I3-T11 — Image format and size from the header

Status: ready
Tier: haiku
Labels: core, security
Depends on: P1-I3B-S1, S2b, S4 on `p1/i3b` (the package, the shared helpers and the stubs are in the tree); no other ticket
Branch: `p1/i3b-t11-image-header`

## Goal
`read_image_header(raw)` returns the format, width, height and the text properties of the header of a PNG, JPEG or TIFF, parsed by hand with `struct`. `packages/tl-extract/src/tl_extract/imagehdr.py` has the constants, `ImageInfo` and the messages written; `sniff`, `_png`, `_jpeg`, `_tiff` and `read_image_header` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass. There is no image library and no decoder: nothing is allocated by a size the file declares, every offset and length is checked against the bytes at hand, and every walk has a fixed bound.

## Brief references (pasted)
> **FANOUT D1 (orchestrator decision).** ADR-0008 decision 8 is applied as follows. PDF and OCR extractors read real metadata and return `status="metadata_only"` with empty rows and a note naming the decision. A CSV or XLSX that a person attaches as the derived content is read deterministically and fills `rows`: that is data entry, not content extraction. No LLM, no OCR engine, no network, no spend.
>
> **FANOUT D4 (bounds).** 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused with a problem, never truncated. Extractors are pure: no ledger, no unit of work, no network, no filesystem path from user input.
>
> **Contract (`tl_core.derivation.types`).** `extract` never raises for bad input: a bad file is `status="failed"` with problems; messages hold fixed text and the caller's values, never a stack trace or a path.
>
> **How the package is built.** The readers of this package are small functions that return a value or raise `Refusal(code, message)`. `reading.run_guarded` (in the extractor, already written) turns a `Refusal`, and any other exception, into a `failed` result. A reader therefore never builds an `ExtractionResult`.

### Specification
- No new dependency: no Pillow, no `imghdr`, no OCR engine. Only `struct`, `zlib` (for the PNG header checksum) and the standard library.
- Every number read from the file is untrusted. A length or offset is compared with `len(raw)` before it is used to slice, and a loop runs at most the bound the STEPS name (`MAX_PNG_CHUNKS`, `MAX_JPEG_SEGMENTS`, `MAX_TIFF_ENTRIES`, `MAX_TIFF_TEXT`).
- Text from the header goes through `clean_metadata_text` (it removes control characters and cuts at 1000 characters). `latin-1` decoding never fails; keep it.
- A damaged header is `Refusal("broken_image", ...)`, never an exception: the final `except` in `read_image_header` is a safety net for `struct.error` and `IndexError`, the explicit checks in each parser come first.
- A message never contains `str(exc)`, a path or bytes of the file.

### Learnings that apply
> **L-P0-I8A-9.** Hostile numbers raise errors other than the ones a parser documents; here every slice is bounds-checked first and the last `except` converts what is left.

> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I8A-9.** Hostile input raises errors other than the ones a parser documents (`RecursionError`, `ValueError` for integers over 4300 digits, `OverflowError`). Here `run_guarded` catches them, so do not add `except Exception` to a reader unless the STEPS say so.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-extract/src/tl_extract/imagehdr.py` (the stub you complete; the whole file):
```python
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
```

`packages/tl-extract/src/tl_extract/reading.py` (excerpt; read-only for you):
```python
#: Cells of one table (rows times named columns). The contract allows 20 000 x 200 = 4 million,
#: which would hold gigabytes of text; one million is more than any index or list needs.
MAX_CELLS = 1_000_000

#: Characters of cell text read from one file, over all cells.
MAX_TOTAL_CHARS = 64 * 1024 * 1024

#: A sheet that was formatted down to row one million has blank rows with cells; after this many
#: blank rows in a row the reader stops and says so in a note.
MAX_BLANK_RUN = 1000

class Refusal(Exception):
    """A reader cannot go on. ``code`` is the problem code; ``message`` is fixed text.

    Never reaches a caller: ``run_guarded`` turns it into a ``failed`` result.
    """

    def __init__(self, code: str, message: str, row: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.row = row

class CellBudget:
    """Counts the cells and the characters a reader has taken, and refuses past the limits."""

    cells: int = 0
    chars: int = 0

    def take(self, record: Sequence[Cell]) -> None:
        """Count one record (a row of cells). Raises ``Refusal`` at ``MAX_CELLS`` or
        ``MAX_TOTAL_CHARS``."""
        self.cells += len(record)
        self.chars += sum(len(cell) for cell in record if cell is not None)
        if self.cells > MAX_CELLS:
            raise Refusal(
                "too_many_cells",
                f"the file holds more than {MAX_CELLS} cells; split it",
            )
        if self.chars > MAX_TOTAL_CHARS:
            raise Refusal(
                "too_much_text",
                f"the file holds more than {MAX_TOTAL_CHARS // (1024 * 1024)} MiB of cell text; "
                "split it",
            )

class GridMeta:
    """What a spreadsheet file says about itself (XLSX core properties). All text is cleaned."""

    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None

class RawGrid:
    """What a grid reader (CSV or XLSX) hands to ``table.build_table``.

    ``rows`` are records of raw cell text, not stripped: ``None`` is an empty cell. They hold the
    records up to and including the header record (``options.header_row``), as they are, and then
    the data records that are not entirely blank. A record is cut after the last non-empty cell
    or after ``MAX_COLUMNS + 1`` cells, whichever comes first, so a cell at position
    ``MAX_COLUMNS + 1`` is how a too-wide header is seen without keeping a million cells.
    """

    rows: list[list[Cell]]
    #: The sheet read (XLSX), else None.
    sheet: str | None = None
    #: Every sheet's name (XLSX), else None.
    sheet_names: list[str] | None = None
    #: Data records skipped because every cell was blank.
    skipped_blank_rows: int = 0
    #: Notes the reader adds (for instance that it stopped at a long run of blank rows).
    notes: list[str] = field(default_factory=list[str])
    meta: GridMeta = field(default_factory=GridMeta)

def has_unstorable_character(text: str) -> bool:
    """A control character other than tab, CR and LF (as the P1-I2 import reads them), or a
    character that cannot be encoded as UTF-8 (a lone surrogate)."""
    for ch in text:
        code = ord(ch)
        if (code < 32 and ch not in "\t\r\n") or code == 127 or 0xD800 <= code <= 0xDFFF:
            return True
    return False

def shown(text: str, limit: int = 60) -> str:
    """Text that came from a file, made safe to put in a message: control characters become ``?``
    and a long text is cut with an ellipsis."""
    cleaned = "".join("?" if has_unstorable_character(ch) else ch for ch in text)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"

def clean_metadata_text(text: str | None, limit: int = 1000) -> str | None:
    """A metadata string of a file (title, author, producer) made storable: unstorable characters
    become spaces, runs of whitespace one space, and the text is cut at ``limit``.

    None and an empty result are None.
    """
    if text is None:
        return None
    cleaned = "".join(" " if has_unstorable_character(ch) else ch for ch in text)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    return cleaned[:limit]
```


## Context (read these, nothing else)
- `packages/tl-extract/src/tl_extract/imagehdr.py`
- `packages/tl-extract/src/tl_extract/reading.py`
- `docs/tickets/P1-I3/provided/t11-test_imagehdr.py.txt`
- `packages/tl-extract/tests/extractsupport.py` (the test helpers the provided test imports)
may explore: (none)

## Allowed paths
- `packages/tl-extract/src/tl_extract/imagehdr.py` (edit)
- `packages/tl-extract/tests/test_imagehdr.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T11.md` (create; commit it)

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I3/provided/t11-test_imagehdr.py.txt` to `packages/tl-extract/tests/test_imagehdr.py`. Do not edit it.
3. Implement the functions marked STEPS in `imagehdr.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the `# ruff: noqa: F401, F841` line; remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-extract/tests/test_imagehdr.py -q
uv run pytest packages/tl-extract -q
```
Expected: `just check` clean; 40 tests pass in `test_imagehdr.py` (32 test functions; the rest are parametrized cases); the whole package passes (109 tests that are already there, plus these). These tests do not touch a database, so there is no `--adapters` run.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a new dependency, a change to `reading.py`, `options.py` or `table.py`, or a change to the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
