"""What the evidence view shows, as pure functions (P1-I6; brief 9 M10, ADR-0019 section 6).

The trail is the chain of records around an item as the ledger knew it at the end of a day. A
record or link the reader cannot read today is not in it, and nothing here says how many were
left out. This module only formats what the client returned.

By default the text is plain words (type labels, humanized states, no record ids); ``technical``
gives the internal form back (P1-UX-T05, SCOPE clause 3).
"""

from __future__ import annotations

from datetime import date, timedelta

from tl_mod_correspondence.evidence import EvidenceNode, EvidenceTrail

from tl_tui.display import Labels, humanize, type_label

EVIDENCE_COLUMNS = ("Record", "Type", "State", "Reached by", "Title")


def _labels(labels: Labels | None) -> Labels:
    return labels if labels is not None else Labels()


def _state_text(node: EvidenceNode, *, technical: bool) -> str:
    """The state that day: the raw state for the technical form, its words otherwise."""
    if technical or not node.state:
        return node.state or "-"
    return humanize(node.state)


def node_cells(
    node: EvidenceNode, labels: Labels | None = None, *, technical: bool = True
) -> tuple[str, ...]:
    """The five cells of a row of the trail, in the order of ``EVIDENCE_COLUMNS``: the key is
    indented by depth; ``Reached by`` is ``derived from (active)`` or ``-`` for the root.
    Without ``technical`` the type is its label, the state and the link read as words, and a
    record with no number shows ``(no number)`` rather than its record id."""
    voided = " VOID" if node.voided else ""
    key = node.key or (node.record_id if technical else "(no number)")
    kind = node.type.rpartition(".")[2] if technical else type_label(_labels(labels), node.type)
    state = _state_text(node, technical=technical)
    if node.via is None:
        via = "-"
    else:
        label = node.via.label if technical else humanize(node.via.label)
        via = f"{label} ({node.via.status})"
    return (
        f"{'  ' * node.depth}{key}",
        kind,
        state + voided,
        via,
        node.title,
    )


def node_lines(
    node: EvidenceNode, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the trail: how the record was reached and what its events said that day.
    ``technical`` adds the record id when there is no number, the link's pin and the raw fact
    keys; without it the fact keys read as words."""
    key = node.key or (node.record_id if technical else "(no number)")
    state = _state_text(node, technical=technical)
    lines = [f"{key}  created {node.created_on}  state that day: {state}"]
    if node.via is not None:
        pin = f", pinned {node.via.pin}" if technical and node.via.pin else ""
        label = node.via.label if technical else humanize(node.via.label)
        lines.append(
            f"reached by {label} ({node.via.status}{pin}) since {node.via.since}"
            + (f": {node.via.note}" if node.via.note else "")
        )
    lines.extend(f"{k if technical else humanize(k)}: {v}" for k, v in node.facts.items())
    return lines


def node_line(node: EvidenceNode, labels: Labels | None = None, *, technical: bool = False) -> str:
    """One record of the trail: indented by depth, with how it was reached and its facts.
    ``technical`` gives the raw type in brackets, the record id when there is no number, the
    link's pin and the raw fact keys (the form the command line tool prints)."""
    via = ""
    if node.via is not None:
        pin = f" pinned {node.via.pin}" if technical and node.via.pin else ""
        label = node.via.label if technical else humanize(node.via.label)
        via = f" <- {label} ({node.via.status}{pin}, since {node.via.since})"
    voided = " VOID" if node.voided else ""
    key = node.key or (node.record_id if technical else "(no number)")
    kind = f"[{node.type}]" if technical else f"[{type_label(_labels(labels), node.type)}]"
    state = _state_text(node, technical=technical)
    facts = " ".join(
        f"{k if technical else humanize(k)}={v}"
        for k, v in node.facts.items()
        if k not in ("question", "answer")
    )
    return f"{'  ' * node.depth}{key} {kind} {state}{voided} {node.title}{via}" + (
        f" | {facts}" if facts else ""
    )


def evidence_lines(trail: EvidenceTrail) -> list[str]:
    """The whole trail, root first; a last line says when a bound cut the walk short."""
    lines = [node_line(n) for n in trail.nodes]
    if trail.truncated:
        lines.append("the walk was cut short by a bound; ask for less depth")
    return lines


def evidence_title(number: str, as_of: str) -> str:
    """``Evidence for P123-EW-0001 as of 2026-10-22 (Thursday)``."""
    return f"Evidence for {number} as of {as_of} ({date.fromisoformat(as_of):%A})"


def step_day(current: date, step: int, today: date) -> date:
    """``current`` moved by ``step`` days, never later than ``today``."""
    return min(current + timedelta(days=step), today)
