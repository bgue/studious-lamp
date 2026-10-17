"""Which kind of file a source is, so that exactly one extractor accepts it.

The extension of the display name decides first; the content type decides only when the
extension is not one of ours (a revision code such as ``ISD-001.A`` is not a file type). A
client can type either, so neither is trusted to be right: each extractor also checks the bytes
it reads (magic numbers) and refuses what is not its format.
"""

from __future__ import annotations

from typing import Literal

from tl_core.derivation import SourceFile

FileKind = Literal["csv", "xlsx", "pdf", "image"]

EXTENSION_KINDS: dict[str, FileKind] = {
    "csv": "csv",
    "tsv": "csv",
    "xlsx": "xlsx",
    "pdf": "pdf",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "tif": "image",
    "tiff": "image",
}

CONTENT_TYPE_KINDS: dict[str, FileKind] = {
    "text/csv": "csv",
    "application/csv": "csv",
    "text/tab-separated-values": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
    "image/tiff": "image",
}


def extension_of(filename: str) -> str:
    """The lower-case extension of the last path component of a display name, or ``""``."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].strip().lower()


def file_kind(source: SourceFile) -> FileKind | None:
    """The kind of file ``source`` claims to be, or None when no extractor here reads it."""
    by_extension = EXTENSION_KINDS.get(extension_of(source.filename))
    if by_extension is not None:
        return by_extension
    content_type = source.content_type.split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_KINDS.get(content_type)
