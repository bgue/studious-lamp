"""Dev resources: the ADRs, the runbooks and the stored test reports (brief 25.2, 25.3; FANOUT D12).

Each kind has an index (``tl://dev/adrs``, ``tl://dev/runbooks``, ``tl://dev/test-reports``) and one
document by its name (``tl://dev/adr/{name}``, ``tl://dev/runbook/{name}``,
``tl://dev/test-report/{name}``). Directories are listed with :func:`list_documents` and opened with
:func:`safe_child`; a name never becomes a path here.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError

from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import list_documents, safe_child
from tl_mcp.dev.runtime import DevContext, guarded

MAX_NAME_CHARS = 128
"""A ``{name}`` longer than this is not a document."""

MAX_DOC_BYTES = 1024 * 1024
"""A document is served up to this many bytes; the rest is cut."""

CUT_MARK = "\n... (cut)\n"
MAX_REPORTS = 100
MD = ".md"
TXT = ".txt"
RUNBOOK_EXCLUDED = frozenset({"README.md"})
"""Files in ``docs/runbooks`` that are not runbooks: left out of the index and never served."""

NOT_FOUND = "no such document"


def _check_name(name: str) -> None:
    if len(name) > MAX_NAME_CHARS:
        raise ResourceError(NOT_FOUND)


def _find(directory: Path, file_name: str, suffixes: Collection[str]) -> Path:
    """The document ``file_name`` in ``directory``; a refusal has no path in its text."""
    try:
        return safe_child(directory, file_name, list(suffixes))
    except DevGuardError:
        raise ResourceError(NOT_FOUND) from None


def _read(path: Path) -> str:
    """The text of ``path`` as UTF-8 (undecodable bytes replaced), cut to ``MAX_DOC_BYTES``."""
    with path.open("rb") as handle:
        data = handle.read(MAX_DOC_BYTES + 1)
    if len(data) > MAX_DOC_BYTES:
        return data[:MAX_DOC_BYTES].decode("utf-8", errors="replace") + CUT_MARK
    return data.decode("utf-8", errors="replace")


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def _status(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("Status:"):
            return line[len("Status:") :].strip() or None
    return None


def _document_index(
    directory: Path, suffix: str, excluded: Collection[str]
) -> list[dict[str, Any]]:
    """Index entries for ``name`` + ``suffix`` files: name, title and status, sorted by name."""
    entries: list[dict[str, Any]] = []
    for file_name in list_documents(directory, [suffix]):
        if file_name in excluded:
            continue
        name = file_name[: -len(suffix)]
        text = _read(_find(directory, file_name, [suffix]))
        entries.append({"name": name, "title": _title(text, name), "status": _status(text)})
    return sorted(entries, key=lambda entry: entry["name"])


def _report_index(directory: Path) -> list[dict[str, Any]]:
    """Stored reports, newest first (file names are time-ordered), at most ``MAX_REPORTS``."""
    names = sorted(list_documents(directory, [TXT]), reverse=True)[:MAX_REPORTS]
    return [{"name": n, "bytes": _find(directory, n, [TXT]).stat().st_size} for n in names]


def _json(entries: list[dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2)


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.resource(
        "tl://dev/adrs",
        name="adrs",
        title="ADR index",
        description="The architecture decision records in docs/adr: name, title and status.",
        mime_type="application/json",
    )
    def adrs() -> str:
        with guarded(ctx, "resource.adrs", error=ResourceError):
            directory = ctx.repo_root / "docs" / "adr"
            return _json(_document_index(directory, MD, ()))

    @server.resource(
        "tl://dev/adr/{name}",
        name="adr",
        title="ADR",
        description="One architecture decision record; name is the file name without .md.",
        mime_type="text/markdown",
    )
    def adr(name: str) -> str:
        with guarded(ctx, "resource.adr", {"name": name}, error=ResourceError):
            _check_name(name)
            directory = ctx.repo_root / "docs" / "adr"
            return _read(_find(directory, name + MD, [MD]))

    @server.resource(
        "tl://dev/runbooks",
        name="runbooks",
        title="Runbook index",
        description="The runbooks in docs/runbooks (README excluded): name, title and status.",
        mime_type="application/json",
    )
    def runbooks() -> str:
        with guarded(ctx, "resource.runbooks", error=ResourceError):
            directory = ctx.repo_root / "docs" / "runbooks"
            return _json(_document_index(directory, MD, RUNBOOK_EXCLUDED))

    @server.resource(
        "tl://dev/runbook/{name}",
        name="runbook",
        title="Runbook",
        description="One runbook; name is the file name without .md.",
        mime_type="text/markdown",
    )
    def runbook(name: str) -> str:
        with guarded(ctx, "resource.runbook", {"name": name}, error=ResourceError):
            _check_name(name)
            if name + MD in RUNBOOK_EXCLUDED:
                raise ResourceError(NOT_FOUND)
            directory = ctx.repo_root / "docs" / "runbooks"
            return _read(_find(directory, name + MD, [MD]))

    @server.resource(
        "tl://dev/test-reports",
        name="test-reports",
        title="Test report index",
        description="The stored test reports, newest first: file name and size in bytes.",
        mime_type="application/json",
    )
    def test_reports() -> str:
        with guarded(ctx, "resource.test-reports", error=ResourceError):
            return _json(_report_index(ctx.reports_dir))

    @server.resource(
        "tl://dev/test-report/{name}",
        name="test-report",
        title="Test report",
        description="One stored test report; name is the full file name.",
        mime_type="text/plain",
    )
    def test_report(name: str) -> str:
        with guarded(ctx, "resource.test-report", {"name": name}, error=ResourceError):
            _check_name(name)
            return _read(_find(ctx.reports_dir, name, [TXT]))
