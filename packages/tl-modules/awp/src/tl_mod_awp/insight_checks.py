"""The readiness source of the Checks read: an IWP's last evaluation, shown to one viewer."""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_core.insights.types import CheckFinding, RecordFacts

from tl_mod_awp.names import IWP
from tl_mod_awp.readiness.views import readiness, visible_readiness

#: Said when the viewer may not read some of the records a check names. Never carries a key.
HIDDEN_LINE = "Some blocking records are not available to you."
_SHOWN = ("blocked", "pending", "unknown")


def findings(conn: Connection, facts: RecordFacts, viewer: Viewer | None) -> list[CheckFinding]:
    """A finding per check that is blocked, pending or unknown (never ok or n_a).

    The state word and counts stay. ``resolve_via`` keeps the records the viewer can read; when
    any was dropped the detail is replaced by a fixed line, because a detail may name keys.
    """
    if facts.record_type != IWP:
        return []
    full = readiness(conn, facts.scope, facts.key)
    seen = visible_readiness(conn, facts.scope, facts.key, viewer)
    if full is None or seen is None:
        return []
    before = {c.name: len(c.resolve_via) for c in full.checks}
    out: list[CheckFinding] = []
    for check in seen.checks:
        if check.state not in _SHOWN:
            continue
        dropped = len(check.resolve_via) < before.get(check.name, 0)
        detail = HIDDEN_LINE if dropped else check.detail
        counts = (
            f" ({check.count_ok} of {check.count_total})"
            if check.count_ok is not None and check.count_total is not None
            else ""
        )
        out.append(
            CheckFinding(
                source="readiness",
                subject_id=facts.record_id,
                state=check.state,
                text=f"{check.name.replace('_', ' ')}{counts}: {detail}".strip(": "),
                since=seen.evaluated_at,
                severity="blocking" if check.state == "blocked" else "warning",
                resolve_via=list(check.resolve_via),
            )
        )
    return out
