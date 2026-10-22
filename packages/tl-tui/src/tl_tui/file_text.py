"""file_text writes one file the way a person reads it: name, kind, size, pages (P1-UX2-T02)."""

from __future__ import annotations

_SIZE_UNITS = ("KB", "MB", "GB")
_BINARY_STEP = 1024

_KIND_BY_EXTENSION = {
    ".pdf": "PDF document",
    ".doc": "Word document",
    ".docx": "Word document",
    ".xls": "Excel spreadsheet",
    ".xlsx": "Excel spreadsheet",
    ".csv": "CSV file",
    ".png": "Image",
    ".jpg": "Image",
    ".jpeg": "Image",
    ".gif": "Image",
    ".tif": "Image",
    ".tiff": "Image",
    ".dwg": "Drawing",
    ".dxf": "Drawing",
    ".eml": "Email",
    ".msg": "Email",
}


def human_size(n: int) -> str:
    """``0 B`` for zero or less, ``512 B`` below 1 KB, then KB, MB or GB to one decimal."""
    if n <= 0:
        return "0 B"
    if n < _BINARY_STEP:
        return f"{n} B"
    value = float(n)
    unit = _SIZE_UNITS[0]
    for unit in _SIZE_UNITS:
        value /= _BINARY_STEP
        if value < _BINARY_STEP or unit == _SIZE_UNITS[-1]:
            break
    return f"{value:.1f} {unit}"


def _kind_from_content_type(ctype: str) -> str:
    """The kind for a specific content type; anything unrecognised is ``File``."""
    if ctype == "application/pdf":
        return "PDF document"
    if "msword" in ctype or "wordprocessingml" in ctype:
        return "Word document"
    if "spreadsheetml" in ctype or "ms-excel" in ctype:
        return "Excel spreadsheet"
    if ctype == "text/csv":
        return "CSV file"
    if ctype.startswith("image/"):
        return "Image"
    if ctype == "message/rfc822":
        return "Email"
    return "File"


def _kind_from_extension(filename: str) -> str:
    dot = filename.lower().rfind(".")
    ext = filename.lower()[dot:] if dot >= 0 else ""
    return _KIND_BY_EXTENSION.get(ext, "File")


def file_kind(content_type: str | None, filename: str) -> str:
    """The kind a person sees: content type first, then the lower-cased extension of ``filename``.

    Only an empty content type or ``application/octet-stream`` falls through to the extension;
    any other unrecognised content type is ``File``.
    """
    ctype = (content_type or "").strip().lower()
    if ctype and ctype != "application/octet-stream":
        return _kind_from_content_type(ctype)
    return _kind_from_extension(filename)


def file_line(name: str, content_type: str | None, size: int, pages: int | None = None) -> str:
    """``name  kind  size  N pages``, parts joined by two spaces; pages only when ``pages >= 1``."""
    parts = [name, file_kind(content_type, name), human_size(size)]
    if pages is not None and pages >= 1:
        parts.append("1 page" if pages == 1 else f"{pages} pages")
    return "  ".join(parts)
