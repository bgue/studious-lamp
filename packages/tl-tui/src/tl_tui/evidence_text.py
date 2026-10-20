"""What the evidence view shows, as pure functions (P1-I6; brief 9 M10, ADR-0019 section 6).

The trail is the chain of records around an item as the ledger knew it at the end of a day. A
record or link the reader cannot read today is not in it, and nothing here says how many were
left out. This module only formats what the client returned.
"""

from __future__ import annotations

from datetime import date, timedelta

from tl_mod_correspondence.evidence import EvidenceNode, EvidenceTrail

EVIDENCE_COLUMNS = ("Record", "Type", "State", "Reached by", "Title")


def node_cells(node: EvidenceNode) -> tuple[str, ...]:
    """The five cells of a row of the trail, in the order of ``EVIDENCE_COLUMNS``: the key is
    indented by depth; ``Reached by`` is ``derived from (active)`` or ``-`` for the root."""
    via = "-" if node.via is None else f"{node.via.label} ({node.via.status})"
    voided = " VOID" if node.voided else ""
    return (
        f"{'  ' * node.depth}{node.key or node.record_id}",
        node.type.rpartition(".")[2],
        (node.state or "-") + voided,
        via,
        node.title,
    )


def node_lines(node: EvidenceNode) -> list[str]:
    """The panel under the trail: how the record was reached and what its events said that day."""
    lines = [
        f"{node.key or node.record_id}  created {node.created_on}  "
        f"state that day: {node.state or '-'}"
    ]
    if node.via is not None:
        pin = f", pinned {node.via.pin}" if node.via.pin else ""
        lines.append(
            f"reached by {node.via.label} ({node.via.status}{pin}) since {node.via.since}"
            + (f": {node.via.note}" if node.via.note else "")
        )
    lines.extend(f"{k}: {v}" for k, v in node.facts.items())
    return lines


def node_line(node: EvidenceNode) -> str:
    """One record of the trail: indented by depth, with how it was reached and its facts."""
    via = ""
    if node.via is not None:
        pin = f" pinned {node.via.pin}" if node.via.pin else ""
        via = f" <- {node.via.label} ({node.via.status}{pin}, since {node.via.since})"
    voided = " VOID" if node.voided else ""
    facts = " ".join(f"{k}={v}" for k, v in node.facts.items() if k not in ("question", "answer"))
    return (
        f"{'  ' * node.depth}{node.key or node.record_id} [{node.type}] {node.state or '-'}"
        f"{voided} {node.title}{via}" + (f" | {facts}" if facts else "")
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
