"""The readiness of one IWP as text (P2-I2 T07a; spec §8 "IWP log, Readiness"; ``tui-layout``).

The checks of one evaluation as rows, a summary line and the panel's page, as pure functions: no
client call, no I/O, and no ``textual`` import, so the web client (TW3) can use the same words.
The values come from ``tl_api.routes.awp.ReadinessBody`` and nothing else. A reference the reader
may not open is already dropped by the read (D32), so nothing here filters or looks one up.

``n_a`` counts as passing (D9): ``PASSING`` from the awp engine is the set. ``pending`` is not in
the ticket's word list; it is written as it is and counted in the summary only when present.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from tl_mod_awp.readiness.engine import PASSING

from tl_tui.details import TECHNICAL_SECTION, DetailRow, rows_page, table_rows
from tl_tui.display import Labels, humanize, type_label
from tl_tui.layout import Page, cut_text, identity_line, state_line

if TYPE_CHECKING:
    from tl_api.routes.awp import CheckBody, ReadinessBody

READINESS_COLUMNS = ("Check", "State", "Passing", "Resolve via", "Detail")
READINESS_DROP = ("Detail", "Passing")  # dropped first at narrow width
CHECKS = "Checks"  # the section of the table
DASH = "-"  # a cell with nothing in it, in a table of checks (the ticket's mark)
DETAIL_CUT = 80
NOT_APPLICABLE = "n/a"
STATE_WORDS = {"n_a": NOT_APPLICABLE}  # every other state reads as it is stored
ALWAYS_COUNTED = ("ok", "n_a", "blocked")  # the summary names these even at zero
WHEN_PRESENT = ("unknown", "pending")  # the summary names these only when a check has them


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def state_text(state: str) -> str:
    """``ok``, ``blocked``, ``n/a`` (for ``n_a``), ``unknown``; another state reads as it is."""
    return STATE_WORDS.get(state, state)


def _passing(check: CheckBody) -> str:
    """``7/9`` as ``count_ok`` over ``count_total``; ``-`` when the check has no denominator."""
    if check.count_ok is None or check.count_total is None:
        return DASH
    return f"{check.count_ok}/{check.count_total}"


def readiness_rows(
    view: ReadinessBody, labels: Labels | None = None
) -> list[tuple[tuple[str, ...], str | None]]:
    """One row per check, or one row per reference of a check: the check's cells on the first
    row and ``-`` in them after it. Each row is ``(cells, record_id)``; the id is ``None`` for a
    check with no reference (its row opens nothing)."""
    lab = _labels(labels)
    rows: list[tuple[tuple[str, ...], str | None]] = []
    for check in view.checks:
        name = humanize(check.name)
        detail = cut_text(check.detail, DETAIL_CUT) if check.detail else DASH
        head = (name, state_text(check.state), _passing(check))
        if not check.resolve_via:
            rows.append(((*head, DASH, detail), None))
            continue
        for index, ref in enumerate(check.resolve_via):
            via = f"{type_label(lab, ref.record_type)} {ref.key}"
            if index == 0:
                rows.append(((*head, via, detail), ref.record_id))
            else:
                rows.append(((DASH, DASH, DASH, via, DASH), ref.record_id))
    return rows


def readiness_summary(view: ReadinessBody) -> str:
    """``7/9 passing (2 ok, 5 n/a, 2 blocked) · Ready: no · evaluated 2026-11-07``."""
    counts = Counter(check.state for check in view.checks)
    passing = sum(counts[state] for state in PASSING)
    parts = [f"{counts[state]} {state_text(state)}" for state in ALWAYS_COUNTED]
    parts += [f"{counts[state]} {state}" for state in WHEN_PRESENT if counts[state]]
    ready = "yes" if view.ready else "no"
    day = view.evaluated_at[:10]
    return (
        f"{passing}/{len(view.checks)} passing ({', '.join(parts)})"
        f" · Ready: {ready} · evaluated {day}"
    )


def readiness_page(
    number: str,
    view: ReadinessBody,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The IWP's readiness as a page: the identity and state lines, the summary (a panel only),
    the checks as one table, and in technical mode the version of each check."""
    rows = table_rows(
        CHECKS, READINESS_COLUMNS, [cells for cells, _ in readiness_rows(view, labels)]
    )
    rows += [
        DetailRow(humanize(check.name), f"v{check.version}", True, TECHNICAL_SECTION)
        for check in view.checks
    ]
    return rows_page(
        rows,
        identity=identity_line(number, "readiness"),
        state=state_line("Ready" if view.ready else "Not ready"),
        summary=readiness_summary(view),
        technical=technical,
        panel=panel,
    )


def not_evaluated_text(number: str) -> str:
    """The one text for an IWP that is missing, hidden or never evaluated."""
    return f"{number} has not been evaluated"
