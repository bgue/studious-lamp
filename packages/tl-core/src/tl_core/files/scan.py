"""The malware scan seam (brief 20.2). Phase 0 ships a stub that passes everything.

A real scanner (ClamAV) implements ``Scanner`` later and is passed to ``FileService``; nothing else
changes. The service reads the stored object and hands the stream to the scanner.
"""

from __future__ import annotations

from typing import Any, BinaryIO, Protocol

from pydantic import BaseModel


class ScanResult(BaseModel):
    clean: bool
    reason: str | None = None  # why it was refused, when ``clean`` is false
    report: dict[str, Any] = {}  # stored on the event as ``report``


class Scanner(Protocol):
    def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
        """Inspect the bytes. Must not raise for a bad file; return ``clean=False`` instead."""
        ...


class PassScanner:
    """The Phase 0 stub: every file is clean. It does not read the stream."""

    name = "pass"

    def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
        return ScanResult(clean=True, report={"scanner": self.name, "verdict": "not scanned"})
