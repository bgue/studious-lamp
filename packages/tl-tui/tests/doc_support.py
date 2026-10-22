"""Helpers for the tests of the document log and the file panel (P1-UX2-S4)."""

from __future__ import annotations

from typing import Any

from textual.pilot import Pilot


async def settle(pilot: Pilot[Any]) -> None:
    """Wait for the workers that read the rows, the actions and the files, then redraw."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()  # a worker started by the last answer
    await pilot.pause()


def pdf_bytes(pages: int = 1, width: float = 300, height: float = 400) -> bytes:
    """A real small PDF (pypdfium2 writes it)."""
    import tempfile
    from pathlib import Path

    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(width, height)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "made.pdf"
        document.save(str(target))
        return target.read_bytes()
