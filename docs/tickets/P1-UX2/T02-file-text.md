# P1-UX2-T02 — file_text: human_size, file_kind, file_line

Status: ready
Tier: haiku
Labels: tui
Depends on: —
Branch: `p1/ux2-t02-file-text`
Review: full

## Goal
Pure text helpers that write one file as a person reads it: `Piling-layout.pdf  PDF document  1.2 MB  3 pages`. Used by
the Files tab and the document panel.

## Brief references (pasted)
> SCOPE §3: Files: each with name, type, size and pages (PDFs).
Rules:
- `human_size(n)`: `n <= 0` -> `0 B`; below 1024 -> `<n> B`; then KB, MB, GB with one decimal and binary steps (1024): `1024` -> `1.0 KB`, `1536` -> `1.5 KB`, `1048576` -> `1.0 MB`, `5 * 1024**3` -> `5.0 GB`; larger than GB stays in GB.
- `file_kind(content_type, filename)`: content type first, then the lower-cased extension of `filename`. `application/pdf` or `.pdf` -> `PDF document`; Word (`.doc`, `.docx`, `msword`, `wordprocessingml`) -> `Word document`; Excel (`.xls`, `.xlsx`, `spreadsheetml`, `ms-excel`) -> `Excel spreadsheet`; `.csv` or `text/csv` -> `CSV file`; `image/*` or `.png .jpg .jpeg .gif .tif .tiff` -> `Image`; `.dwg .dxf` -> `Drawing`; `message/rfc822` or `.eml .msg` -> `Email`; anything else -> `File`. A content type of `application/octet-stream` or empty falls through to the extension.
- `file_line(name, content_type, size, pages=None)`: parts joined by two spaces: name, kind, size, then `1 page` / `<n> pages` only when `pages` is not None and `pages >= 1`. No trailing spaces. The name is never altered or shortened.

## Interfaces
```python
# packages/tl-tui/src/tl_tui/file_text.py
def human_size(n: int) -> str: ...
def file_kind(content_type: str | None, filename: str) -> str: ...
def file_line(name: str, content_type: str | None, size: int, pages: int | None = None) -> str: ...
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/text.py` (module style)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/file_text.py` (create)
- `packages/tl-tui/tests/test_file_text.py` (create: copy `docs/tickets/P1-UX2/provided/test_file_text.py` byte for byte)
- `docs/reports/P1-UX2/T02.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_file_text.py
```
Expected: gate PASS; `just check` clean.

## Tests to add
The provided file only.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- A provided test expectation disagrees with the rules above: stop, write *Blocked*.
