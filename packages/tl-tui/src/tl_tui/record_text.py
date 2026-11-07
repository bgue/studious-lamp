"""The record screen's text, apart from Textual (P2-WEB1-S6; moved from ``widgets/record_view``).

The terminal's record view and the web record page both build their header, Details text, badges
and History rows here, so the two share one implementation. This module imports neither ``textual``
nor ``rich``: ``details_lines`` reaches the layout (which draws with ``rich``) only when it is
called.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tl_tui.display import Labels, actor_label, humanize
from tl_tui.text import EMPTY, conformance_mark, timestamp

if TYPE_CHECKING:
    from tl_core.ledger import Event
    from tl_core.services.link_queries import LinkCounts

    from tl_tui.details import DetailRow


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _sorted_keys(value: Any) -> str:
    return ", ".join(sorted(str(k) for k in value)) if isinstance(value, dict) else ""


def details_lines(rows: list[DetailRow]) -> str:
    """The Details rows as text: named sections, each a heading and its lines, one blank line
    between them; a property line is ``Label  value`` with the values of a section lined up after
    its longest label (``tl_tui.layout``). The rows are already filtered for the display mode."""
    from tl_tui.details import rows_page  # noqa: PLC0415 - the layout draws with rich
    from tl_tui.layout import plain_lines  # noqa: PLC0415

    return "\n".join(plain_lines(rows_page(rows, technical=True), identity=False))


_EVENT_WORDS: dict[str, str] = {
    "Record.Created": "Created",
    "Record.Updated": "Changed",
    "Record.Corrected": "Corrected",
    "Record.Voided": "Voided",
    "Pset.ValuesSet": "Properties set",
}


def event_label(event_type: str) -> str:
    """The History "What" column in plain mode: a word for each known event type."""
    return _EVENT_WORDS.get(event_type) or humanize(event_type)


def _plain_keys(value: Any) -> str:
    """The sorted keys of a dict as words (``size_in`` becomes ``Size in``), joined by commas."""
    if not isinstance(value, dict):
        return ""
    return ", ".join(humanize(str(k)) for k in sorted(str(k) for k in value))


def event_summary(event: Event, labels: Labels | None = None, *, technical: bool = True) -> str:
    """One line for the History table, by event type. Other event types have no summary.

    ``technical=True`` (the default, and what the tests pin) is the raw text; plain mode uses
    words for the property names and the pset, and no layer.
    """
    payload = event.payload
    kind = event.event_type
    if not technical:
        if kind == "Record.Created":
            return f"created: {payload.get('title') or ''}"
        if kind == "Record.Updated":
            return f"changed: {_plain_keys(payload.get('changes'))}"
        if kind == "Record.Corrected":
            return f"corrected: {_plain_keys(payload.get('changes'))}"
        if kind == "Record.Voided":
            return f"voided: {payload.get('reason') or ''}"
        if kind == "Pset.ValuesSet":
            pset = humanize(str(payload.get("pset") or ""))
            return f"{pset}: {_plain_keys(payload.get('values'))}"
        return ""
    if kind == "Record.Created":
        return f"created: {payload.get('title') or ''}"
    if kind == "Record.Updated":
        return f"changed: {_sorted_keys(payload.get('changes'))}"
    if kind == "Record.Corrected":
        return f"corrected: {_sorted_keys(payload.get('changes'))}"
    if kind == "Record.Voided":
        return f"voided: {payload.get('reason') or ''}"
    if kind == "Pset.ValuesSet":
        pset = payload.get("pset") or ""
        layer = payload.get("layer") or ""
        return f"{pset} ({layer}): {_sorted_keys(payload.get('values'))}"
    return ""


@dataclass(frozen=True)
class HeaderParts:
    """The header's two lines in pieces, so a screen can style the state and the mark.

    Line one is ``identity``; line two is ``status + version + " · " + mark + rest``."""

    identity: str  # ``<key> · <title>``
    status: str
    version: str  # ``" · v3"`` in technical mode, else ``""`` (D20: the version is technical)
    mark: str  # the conformance level with its symbol
    rest: str  # `` · voided`` and `` · <badges>``, each only when there is one


def header_parts(record: dict[str, Any], badges: str = "", *, technical: bool) -> HeaderParts:
    """The header of ``record`` as ``HeaderParts``."""
    return HeaderParts(
        identity=f"{record['key']} · {record['title']}",
        status=_or_empty(record.get("status")),
        version=f" · v{record['version']}" if technical else "",
        mark=conformance_mark(record.get("conformance")),
        rest=(" · voided" if record.get("voided") else "") + (f" · {badges}" if badges else ""),
    )


def badges_text(entered_at: str | None, counts: LinkCounts | None) -> str:
    """``since <time> · 3 links · 1 stale`` for the header; empty when nothing is known.

    ``entered_at`` is the workflow state's entry time (``None``: it could not be read); ``counts``
    the record's link counts (``None``: none read). The two reads stay with the caller."""
    parts: list[str] = []
    if entered_at is not None:
        parts.append(f"since {timestamp(entered_at)}")
    if counts is not None:
        if counts.active:
            parts.append(f"{counts.active} link{'' if counts.active == 1 else 's'}")
        for label, number in (
            ("stale", counts.stale),
            ("broken", counts.broken),
            ("suggested", counts.suggested),
        ):
            if number:
                parts.append(f"{number} {label}")
    return " · ".join(parts)


def history_columns(technical: bool) -> tuple[str, ...]:
    """The History table's headers: technical columns in technical mode, plain words otherwise."""
    if technical:
        return ("#", "When", "Event", "Actor", "Summary")
    return ("When", "What", "By", "Summary")


def history_cells(event: Event, labels: Labels, *, technical: bool) -> tuple[str, ...]:
    """One History row as cell texts, matching ``history_columns(technical)``."""
    when = event.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
    if technical:
        return (
            str(event.stream_version),
            when,
            event.event_type,
            event.actor,
            event_summary(event),
        )
    return (
        when,
        event_label(event.event_type),
        actor_label(labels, event.actor),
        event_summary(event, labels, technical=False),
    )
