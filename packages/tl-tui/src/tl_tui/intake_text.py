"""The text of the intake log (V3-F4; I05; skill ``tui-layout``), as pure functions.

The values come from ``tl_mod_forms.intake_views`` (``ItemRow``) and ``tl_mod_forms.intake_read``
(``ItemDetail``) and nothing else: no client call, no I/O, no ``textual`` import. No row holds a
code, a hash, a salt or a stored body. The answers of a Pending item are in its page only; the
phone number is read from them as any other answer, as the controller sees what the sender typed.
An item has no number: it is named by the tail of its id, the whole id in technical mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from tl_tui.awp_text import date_text
from tl_tui.details import DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY, Page, join_facts, state_line

if TYPE_CHECKING:
    from tl_mod_forms.intake_read import ItemDetail
    from tl_mod_forms.intake_views import ItemRow

INTAKE_COLUMNS = ("Item", "State", "Received", "Outcome")
INTAKE_DROP = ("Outcome", "Received")  # dropped first at narrow width
STATES = ("Pending", "Accepted", "Rejected")
NOUN = "intake item"
RECEIVED = "Received"
OUTCOME = "Outcome"
ANSWERS = "Answers"
TAIL = 8


def _val(value: object) -> str:
    if value is None:
        return EMPTY
    found = str(value)
    return found if found.strip() else EMPTY


def _who(labels: Labels | None, actor: str | None, technical: bool) -> str:
    if not actor:
        return EMPTY
    return actor if technical else actor_label(labels or Labels(), actor)


def item_name(row: ItemRow, technical: bool = False) -> str:
    """The tail of the item's id (the whole id in technical mode)."""
    return row.id if technical else row.id[-TAIL:]


def outcome_text(row: ItemRow) -> str:
    """What was decided: ``as SubmitForm``, ``spam``; ``—`` while Pending."""
    if row.accepted_as:
        return f"as {row.accepted_as}"
    return _val(row.rejected_reason)


def intake_count(total: int) -> str:
    return f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"


def intake_cells(row: ItemRow) -> tuple[str, ...]:
    """The cells in the order of ``INTAKE_COLUMNS``."""
    return (item_name(row), humanize(row.state), date_text(row.received_at[:10]), outcome_text(row))


def intake_summary(counts: Mapping[str, int], total: int, shown: int, state: str | None) -> str:
    """``5 intake items: 2 Pending, 2 Accepted, 1 Rejected``; with a filter ``2 of 5 intake items,
    state Pending``."""
    if state is not None:
        return f"{shown} of {intake_count(total)}, state {humanize(state)}"
    if total == 0:
        return intake_count(0)
    return f"{intake_count(total)}: " + ", ".join(f"{counts.get(s, 0)} {s}" for s in STATES)


def counts_of(rows: Sequence[ItemRow]) -> dict[str, int]:
    found: dict[str, int] = {}
    for row in rows:
        found[row.state] = found.get(row.state, 0) + 1
    return found


def answer_text(answer: Mapping[str, Any]) -> str:
    value = answer.get("value")
    return _val(", ".join(str(v) for v in value) if isinstance(value, list) else value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def intake_page(
    detail: ItemDetail, labels: Labels | None = None, technical: bool = False, panel: bool = False
) -> Page:
    """The item as a page: its name, the state line, Received (when, size), Outcome (accepted as,
    by, on, the sender's claim; or the rejected reason; purged) and, for a Pending item, Answers."""
    row = detail.row
    rows: list[DetailRow] = [
        DetailRow("Received", date_text(row.received_at[:10]), section=RECEIVED),
        DetailRow("Size", f"{row.body_bytes} bytes", section=RECEIVED),
        DetailRow("Code", row.code_id, section=RECEIVED, technical=True),
    ]
    if row.accepted_as:
        rows += [
            DetailRow("Accepted as", row.accepted_as, section=OUTCOME),
            DetailRow(
                "Accepted by",
                _val(join_facts(_who(labels, row.accepted_by, technical), row.accepted_on)),
                section=OUTCOME,
            ),
            DetailRow(
                "Sender",
                _val(join_facts(row.claim_name, row.claim_company)),
                section=OUTCOME,
            ),
        ]
    if row.rejected_reason:
        rows += [
            DetailRow("Rejected", humanize(row.rejected_reason), section=OUTCOME),
            DetailRow("Rejected by", _who(labels, row.rejected_by, technical), section=OUTCOME),
        ]
    if row.purged_at:
        rows.append(DetailRow("Text removed", date_text(row.purged_at[:10]), section=OUTCOME))
    for answer in detail.answers or []:
        rows.append(DetailRow(_val(answer.get("q")), answer_text(answer), section=ANSWERS))
    state = join_facts(humanize(row.state), f"received {date_text(row.received_at[:10])}")
    return rows_page(
        rows,
        identity=f"Intake item · {item_name(row, technical)}",
        state=state_line(state),
        summary=join_facts(
            outcome_text(row) if row.state != "Pending" else "", f"{row.body_bytes} bytes"
        ),
        technical=technical,
        panel=panel,
    )
