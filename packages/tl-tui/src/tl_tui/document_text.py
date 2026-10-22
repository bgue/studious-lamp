"""What the document screens show, as pure functions (P1-I2; brief 9 M1).

The register rows, the detail panel, the re-pin summary and the transmittal choices are text built
from ``tl_mod_documents.views`` values and nothing else, so the tests check them without a terminal.
None of it decides anything: which revision is current, which link is stale and what changed
between two revisions are the module's findings, shown here as they come.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_mod_documents.errors import UnknownSchemeError
from tl_mod_documents.schemes import load_scheme_file
from tl_mod_documents.views import (
    DocumentLinkView,
    DocumentView,
    RevisionDiffView,
    RevisionView,
)

from tl_tui.details import TECHNICAL_SECTION, DetailRow, plain_code, rows_page, table_rows
from tl_tui.display import Labels, code_label, humanize, type_label
from tl_tui.layout import Cell, Page, identity_line, join_facts, plain_lines, state_style
from tl_tui.text import EMPTY

COLUMNS = ("Number", "Title", "State", "Current", "Type", "Discipline")
DROP = ("Discipline", "Type")  # left out, least needed first, when the log would not fit
FACTS = "Key facts"
REVISIONS = "Revisions"
REVISION_COLUMNS = ("Rev", "State", "Purpose", "Date", "Files")
LINKS = "Links"
LINK_COLUMNS = ("Record", "Type", "Pin", "Status")
ALL = "all"


def current_text(view: DocumentView) -> str:
    """``B(IFC)``, or ``—`` while no revision is issued (the code form, technical mode)."""
    if view.current_revision_code is None:
        return EMPTY
    return f"{view.current_revision_code}({view.current_revision_status or EMPTY})"


def status_labels() -> dict[str, str]:
    """The issue statuses of the revision scheme file in words (``IFR`` is ``Issued for review``).
    Empty when the file cannot be read: a code then reads as itself."""
    try:
        return {code: status.label for code, status in load_scheme_file().statuses.items()}
    except UnknownSchemeError:
        return {}


def revision_words(code: str | None, status: str | None, words: dict[str, str]) -> str:
    """``B, Issued for construction``; ``B`` alone for a revision with no issue status; ``—`` for
    no revision."""
    if code is None:
        return EMPTY
    return f"{code}, {words.get(status, status)}" if status else code


def current_words(view: DocumentView, words: dict[str, str] | None = None) -> str:
    """The current revision in words, ``A, Issued for review``; ``—`` while none is issued."""
    return revision_words(
        view.current_revision_code,
        view.current_revision_status,
        status_labels() if words is None else words,
    )


def row_cells(
    view: DocumentView, labels: Labels | None = None, *, technical: bool = False
) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``: labels, not codes; technical
    mode shows the type and discipline codes."""
    if labels is None or technical:
        labels = Labels()
    return (
        view.number,
        view.title,
        humanize(view.state),
        current_text(view) if technical else current_words(view),
        code_label(labels, "doc_type", view.doc_type),
        code_label(labels, "discipline", view.discipline),
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


def file_revision(view: DocumentView) -> RevisionView | None:
    """The revision whose files are shown and opened: the current one, else the newest."""
    current = [rev for rev in view.revisions if rev.is_current]
    if current:
        return current[0]
    return view.revisions[-1] if view.revisions else None


def links_heading(view: DocumentView) -> str:
    """``Links (3)``, or ``Links (3, 1 stale)``; ``Links`` alone when there are none."""
    if not view.links:
        return LINKS
    stale = len(stale_links(view))
    return (
        f"{LINKS} ({len(view.links)}, {stale} stale)" if stale else f"{LINKS} ({len(view.links)})"
    )


def revision_rows(view: DocumentView, words: dict[str, str]) -> list[DetailRow]:
    """The ``Revisions (n)`` section as a small table: revision, state (the current one reads
    ``Current``), purpose (the issue status in words, else the stated purpose), date, files."""
    if not view.revisions:
        return [DetailRow("", "No revisions yet", section=REVISIONS)]
    table = []
    for rev in view.revisions:
        state = "Current" if rev.is_current else rev.state
        purpose = (
            words.get(rev.issue_status, rev.issue_status)
            if rev.issue_status
            else rev.purpose or words.get(rev.intended_status or "", rev.intended_status or "")
        )
        files = ", ".join(sorted({r.kind for r in rev.renditions if r.is_current}))
        table.append(
            (
                rev.code,
                Cell(state, state_style(state)),
                purpose or EMPTY,
                rev.issued_on or rev.revision_date or EMPTY,
                files or EMPTY,
            )
        )
    return table_rows(f"{REVISIONS} ({len(view.revisions)})", REVISION_COLUMNS, table)


def document_head_rows(view: DocumentView, labels: Labels) -> list[DetailRow]:
    """The sections above the files: the description, the key facts (the current revision first)
    and the revisions."""
    words = status_labels()
    rows: list[DetailRow] = []
    if view.description:
        rows.append(DetailRow("", view.description, section="Description"))
    rows += [
        DetailRow("Current revision", current_words(view, words), section=FACTS),
        DetailRow("Document type", code_label(labels, "doc_type", view.doc_type), section=FACTS),
        DetailRow("Discipline", code_label(labels, "discipline", view.discipline), section=FACTS),
    ]
    if view.originator:  # a document whose type has no originator shows no row
        rows.append(DetailRow("Originator", view.originator, section=FACTS))
    rows.append(
        DetailRow(
            "Confidentiality",
            plain_code(labels, "confidentiality", view.confidentiality),
            section=FACTS,
        )
    )
    if view.superseded_by:
        rows.append(DetailRow("Replaced by", view.superseded_by, section=FACTS))
    return rows + revision_rows(view, words)


def link_status(link: DocumentLinkView) -> str:
    """The link's state in words: ``Current``, ``Floating``, ``! Stale: now B``."""
    if link.link_status == "stale":
        return "! Stale: the document was voided or replaced"
    if link.pin_state == "stale":
        newer = ", ".join(link.newer_codes)
        return f"! Stale: now {link.current_code or EMPTY}" + (f" (newer {newer})" if newer else "")
    if link.pin_state == "current":
        return "Current"
    return humanize(link.pin_state)


def document_link_rows(view: DocumentView, labels: Labels) -> list[DetailRow]:
    """The ``Links (n)`` section as a small table (record, type, pin, status); a stale link is
    marked ``!`` and red. ``No links`` when there is none."""
    if not view.links:
        return [DetailRow("", "No links", section=LINKS)]
    table = []
    for link in view.links:
        status = link_status(link)
        table.append(
            (
                link.from_key or link.from_title,
                type_label(labels, link.from_type),
                link.pin or "floating",
                Cell(status, state_style(status)),
            )
        )
    return table_rows(links_heading(view), LINK_COLUMNS, table)


def document_technical_rows(
    view: DocumentView, record: dict[str, Any] | None = None
) -> list[DetailRow]:
    """Scheme, version and record id (a panel), or the envelope rows (the Details tab)."""
    rows = [DetailRow("Revision scheme", view.revision_scheme, True, TECHNICAL_SECTION)]
    if record is None:
        rows += [
            DetailRow("Record id", view.id, True, TECHNICAL_SECTION),
            DetailRow("Version", str(view.version), True, TECHNICAL_SECTION),
        ]
    return rows


def document_state_line(view: DocumentView) -> str:
    """``Issued``, with ``· replaced by ISO-1002`` when the document was superseded."""
    line = humanize(view.state)
    return f"{line} · replaced by {view.superseded_by}" if view.superseded_by else line


def document_panel_pages(
    view: DocumentView, labels: Labels | None = None, *, technical: bool = False
) -> tuple[Page, Page]:
    """The panel of a document in two parts, because the files list sits between them: the
    identity, state, key facts and revisions; then the links."""
    labels = labels or Labels()
    top = rows_page(
        [*document_head_rows(view, labels), *document_technical_rows(view)],
        identity=identity_line(view.number, view.title),
        state=document_state_line(view),
        summary=join_facts(
            f"Revision {current_words(view)}" if view.current_revision_code else "",
            code_label(labels, "doc_type", view.doc_type) if view.doc_type else "",
            code_label(labels, "discipline", view.discipline) if view.discipline else "",
        ),
        technical=technical,
        panel=True,
    )
    links = rows_page(document_link_rows(view, labels), panel=True)
    return top, links


def detail_lines(
    view: DocumentView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the table for the highlighted document, as plain lines (the files list is
    a widget of its own, between the revisions and the links).

    The scheme, the record id and the version are technical: they show only when ``technical``.
    """
    top, links = document_panel_pages(view, labels, technical=technical)
    return [*plain_lines(top), "", *plain_lines(links)]


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
