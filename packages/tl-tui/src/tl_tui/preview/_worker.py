"""The child that draws page 1 of a PDF (P1-UX2-S4). Run as ``python -I -m tl_tui.preview._worker``.

``argv``: the PDF path, its SHA-256 and the cache directory. It reads that one file, writes one PNG
into that cache directory, prints one JSON line (``{"pages": n}`` or ``{"error": "<state>"}``)
and exits. It imports no network module, prints no traceback and opens no other file. The parent
sets the wall-clock limit; the child sets its own address-space and CPU limits where the system
supports them.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

MAX_SIDE = 1200  # px
MAX_PIXELS = 1_500_000
MAX_SCALE = 2.0  # a small page is drawn at most twice its size
MEMORY_LIMIT = 1 << 30  # 1 GiB of address space
CPU_SECONDS = 10
HEADER = b"%PDF-"


def _limit_resources() -> None:
    """Best effort: cap the address space and the CPU time (not every system has ``resource``)."""
    try:
        import resource
    except ImportError:
        return
    for name, value in (("RLIMIT_AS", MEMORY_LIMIT), ("RLIMIT_CPU", CPU_SECONDS)):
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass


def scale_for(width: float, height: float) -> float:
    """The scale that keeps the longer side within ``MAX_SIDE``, the area within ``MAX_PIXELS``."""
    if width <= 0 or height <= 0:
        return 0.0
    by_side = MAX_SIDE / max(width, height)
    by_area = math.sqrt(MAX_PIXELS / (width * height))
    return min(MAX_SCALE, by_side, by_area)


def has_pdf_header(path: Path) -> bool:
    """True when the file begins with ``%PDF-`` (a symlink is not followed)."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return False
    with os.fdopen(fd, "rb") as handle:
        return handle.read(len(HEADER)) == HEADER


def render(path: Path, sha256: str, root: Path) -> int:
    """Draw page 1 into the cache and return the page count; ``ValueError`` names a refusal."""
    from tl_tui.preview import cache

    if not cache.valid_hash(sha256):
        raise ValueError("error")
    if not has_pdf_header(path):
        raise ValueError("not_pdf")
    import pypdfium2 as pdfium
    from PIL.PngImagePlugin import PngInfo

    document = pdfium.PdfDocument(str(path))
    pages = len(document)
    if pages < 1:
        raise ValueError("error")
    page = document[0]
    width, height = page.get_size()
    scale = scale_for(width, height)
    if scale <= 0:
        raise ValueError("error")
    bitmap = page.render(scale=scale)  # pyright: ignore[reportArgumentType]  # a float works
    image = bitmap.to_pil().convert("RGB")
    if image.width > MAX_SIDE or image.height > MAX_SIDE:  # rounding up by a pixel
        image.thumbnail((MAX_SIDE, MAX_SIDE))
    meta = PngInfo()
    meta.add_text(cache.PAGES_KEY, str(pages))

    def fill(target: Path) -> None:
        image.save(target, format="PNG", pnginfo=meta)

    cache.write_entry(root, sha256, fill)
    cache.evict(root)
    return pages


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(json.dumps({"error": "error"}))
        return 2
    _limit_resources()
    try:
        pages = render(Path(argv[0]), argv[1], Path(argv[2]))
    except ValueError as refusal:
        state = str(refusal) if str(refusal) in ("not_pdf", "too_big") else "error"
        print(json.dumps({"error": state}))
        return 1
    except Exception:  # noqa: BLE001  # a broken PDF, no memory: one word, never a traceback
        print(json.dumps({"error": "error"}))
        return 1
    print(json.dumps({"pages": pages}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
