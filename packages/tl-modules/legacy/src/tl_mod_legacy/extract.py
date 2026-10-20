"""Reading a legacy file into a grid, in the resource envelope of the derivation pipeline.

The file is untrusted, so it is never parsed in this process: ``run_isolated`` runs the tabular
extractor in a child with a scrubbed environment, address-space and CPU limits and a wall clock
(ADR-0014 D9), and the parent checks the answer against the contract's bounds (50 MiB, 20 000
rows, 200 columns, 10 000 characters a cell). A breach, a refusal or a file that is not tabular is
a ``SourceFileError`` with fixed text and the reader's own code; no cell and no path.
"""

from __future__ import annotations

import hashlib
import mimetypes

from tl_core.derivation.isolated import ExtractorSelectionError, run_isolated
from tl_core.derivation.types import SourceFile

from tl_mod_legacy.errors import SourceFileError
from tl_mod_legacy.model import Grid, LoaderDef

EXTRACTOR = "tabular"
_TYPES = {
    "csv": ("text/csv", "text/plain", "application/csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
}


def kind_of(filename: str) -> str | None:
    """``csv`` or ``xlsx`` from the file name's ending; ``None`` for anything else."""
    lowered = filename.lower()
    for kind in _TYPES:
        if lowered.endswith(f".{kind}"):
            return kind
    return None


def content_type_of(filename: str) -> str:
    kind = kind_of(filename)
    if kind is not None:
        return _TYPES[kind][0]
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def read_grid(data: bytes, filename: str, loader: LoaderDef) -> tuple[Grid, str]:
    """``(grid, extractor name)`` for the bytes of a file named ``filename``.

    Raises ``SourceFileError`` when the kind is not one the loader reads, or the envelope or the
    reader refuses the file.
    """
    kind = kind_of(filename)
    if kind is None or kind not in loader.file_types:
        raise SourceFileError(
            f"loader {loader.name} reads {', '.join(loader.file_types)} files, "
            f"not {filename[-40:]!r}"
        )
    source = SourceFile(
        file_id="legacy",
        filename=filename[:255],
        content_type=_TYPES[kind][0],
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_ref=f"src.legacy-{loader.system}",
    )
    options: dict[str, object] = {"header_row": loader.header_row}
    if loader.sheet is not None:
        options["sheet"] = loader.sheet
    try:
        result = run_isolated(source, data, name=EXTRACTOR, options=options)
    except ExtractorSelectionError as exc:
        raise SourceFileError("no reader for this kind of file is installed") from exc
    if result.status != "ok":
        problem = result.problems[0] if result.problems else None
        code = problem.code if problem is not None else result.status
        message = problem.message if problem is not None else "the file could not be read"
        raise SourceFileError(f"the file was refused ({code}): {message[:200]}")
    rows = [[row.get(column) for column in result.columns] for row in result.rows]
    return Grid(columns=list(result.columns), rows=rows), result.extractor
