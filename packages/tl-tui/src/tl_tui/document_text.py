"""What the document screens show, as pure functions (P1-I2; brief 9 M1).

The register rows, the detail panel, the re-pin summary and the transmittal choices are text built
from ``tl_mod_documents.views`` values and nothing else, so the tests check them without a terminal.
None of it decides anything: which revision is current, which link is stale and what changed
between two revisions are the module's findings, shown here as they come.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_documents.views import (
    DocumentLinkView,
    DocumentView,
    RevisionDiffView,
    RevisionView,
)

from tl_tui.display import Labels, code_label, humanize, type_label

COLUMNS = ("Number", "State", "Current", "Type", "Discipline", "Title")
ALL = "all"


def current_text(view: DocumentView) -> str:
    """``B(IFC)``, or ``-`` while no revision is issued."""
    if view.current_revision_code is None:
        return "-"
    return f"{view.current_revision_code}({view.current_revision_status or '-'})"


def row_cells(
    view: DocumentView, labels: Labels | None = None, *, technical: bool = False
) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``: labels, not codes; technical
    mode shows the type and discipline codes."""
    if labels is None or technical:
        labels = Labels()
    return (
        view.number,
        humanize(view.state),
        current_text(view),
        code_label(labels, "doc_type", view.doc_type),
        code_label(labels, "discipline", view.discipline),
        view.title,
    )


def revision_line(rev: RevisionView) -> str:
    """``B  Issued  IFC construction 2026-10-14  current  pdf, signed``."""
    status = " ".join(part for part in (rev.issue_status, rev.status_class, rev.issued_on) if part)
    kinds = ", ".join(sorted({r.kind for r in rev.renditions if r.is_current})) or "no files"
    parts = [rev.code, rev.state]
    if status:
        parts.append(status)
    if rev.is_current:
        parts.append("current")
    if rev.superseded_by:
        parts.append(f"replaced by {rev.superseded_by}")
    parts.append(kinds)
    return "  ".join(parts)


def link_line(link: DocumentLinkView, labels: Labels | None = None) -> str:
    """One link: ``! 47-FV-1001 (Record) pin A, current B`` (``!`` marks a stale link)."""
    if labels is None:
        labels = Labels()
    mark = "!" if link.link_status == "stale" or link.pin_state == "stale" else " "
    who = link.from_key or link.from_title
    pin = f"pin {link.pin}" if link.pin else "floats"
    line = f"{mark} {who} ({type_label(labels, link.from_type)}) {pin}"
    if link.pin_state == "stale":
        newer = ", ".join(link.newer_codes)
        line += f", current {link.current_code or '-'} (newer {newer})" if newer else ""
    elif link.link_status == "stale":
        line += ", stale (the document was voided or replaced)"
    return line


def stale_links(view: DocumentView) -> list[DocumentLinkView]:
    """The links of a document that can be re-pinned: stale, and pinned to a revision."""
    return [
        link
        for link in view.links
        if link.pin is not None and (link.link_status == "stale" or link.pin_state == "stale")
    ]


def detail_lines(
    view: DocumentView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the table for the highlighted document.

    The scheme, the record id and the version are technical: they show only when ``technical``.
    """
    if labels is None:
        labels = Labels()
    head = (
        f"state {humanize(view.state)}  |  type {code_label(labels, 'doc_type', view.doc_type)}"
        f"  |  discipline {code_label(labels, 'discipline', view.discipline)}"
    )
    if technical:
        head += f"  |  scheme {view.revision_scheme}"
    lines = [f"{view.number}  {view.title}", head]
    if technical:
        lines.append(f"record {view.id}")
        lines.append(f"version {view.version}")
    lines.append(
        f"current {current_text(view)}"
        + (f"  |  replaced by {view.superseded_by}" if view.superseded_by else "")
    )
    if view.revisions:
        lines.append("revisions:")
        lines.extend(f"  {revision_line(rev)}" for rev in view.revisions)
    else:
        lines.append("no revisions yet")
    if view.links:
        stale = len(stale_links(view))
        lines.append(f"links ({stale} stale):" if stale else "links:")
        lines.extend(f"  {link_line(link, labels)}" for link in view.links)
    return lines


def repin_lines(link: DocumentLinkView, diff: RevisionDiffView) -> list[str]:
    """The re-pin dialog body: who is linked, the move, then what changed (the module's words)."""
    who = link.from_key or link.from_title
    lines = [
        f"Re-pin {who} to {diff.document_number}",
        f"from {diff.from_code} ({diff.from_status or '-'}) to {diff.to_code} "
        f"({diff.to_status or '-'})",
        "",
        "What changed:",
    ]
    facts = diff.summary[1:]
    lines.extend(f"  {fact}" for fact in facts)
    if not facts:
        lines.append("  nothing is different")
    return lines


def issued_choices(view: DocumentView) -> list[tuple[str, str]]:
    """``(label, revision id)`` for each issued revision of a document, newest first.

    The label is ``ISO-1234@B IFC``. A transmittal carries issued revisions, current or since
    replaced; a draft, a revision in review and a void one are not offered.
    """
    return [
        (f"{view.number}@{rev.code} {rev.issue_status or '-'}", rev.id)
        for rev in reversed(view.revisions)
        if rev.state in ("Issued", "Superseded")
    ]


def parse_recipients(text: str) -> list[tuple[str, str | None, str | None]]:
    """Recipients written ``Name:Org:email; Name2`` as ``(name, organisation, email)`` triples."""
    found: list[tuple[str, str | None, str | None]] = []
    for part in text.split(";"):
        piece = part.strip()
        if not piece:
            continue
        name, org, email = ([*(p.strip() for p in piece.split(":", 2)), None, None])[:3]
        found.append((name, org or None, email or None))
    return found


def next_choice(current: str | None, choices: Sequence[str]) -> str | None:
    """The filter after ``current``: ``None`` (all), then each distinct choice, then ``None``."""
    cycle: list[str | None] = [None, *sorted(set(choices))]
    if current not in cycle:
        return None
    return cycle[(cycle.index(current) + 1) % len(cycle)]


def summary_line(
    shown: int,
    total: int,
    *,
    state: str | None,
    doc_type: str | None,
    include_void: bool,
    text: str,
    labels: Labels | None = None,
) -> str:
    """The status line under the table. The type shows its label; the filter compares codes."""
    if labels is None:
        labels = Labels()
    parts = [f"{shown} of {total} documents"]
    if state is not None:
        parts.append(f"state {state}")
    if doc_type is not None:
        parts.append(f"type {code_label(labels, 'doc_type', doc_type)}")
    if include_void:
        parts.append("incl. void")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)
