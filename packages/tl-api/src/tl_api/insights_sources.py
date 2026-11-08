"""The one list of check sources the Checks read uses (ADR-0028). The route and the embedded
client both call ``record_checks`` with ``sources_for``; a module is imported here and nowhere in
core.

The constraint source is read only by a viewer who holds ``core.constraint.view`` on the scope
(P2-INS-T05, orchestrator decision Q5): for anyone else it is left out of the list, so hidden
looks exactly like nothing there (no error, no count, no placeholder)."""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.auth.module_roles import Holder, holds_word, normalise_word
from tl_core.constraints.commands import ACCESS_MODULE, VIEW_WORD
from tl_core.insights.checks import CheckSource, constraint_findings, expected_link_findings
from tl_mod_awp import insight_checks as awp_checks
from tl_mod_correspondence import insight_checks as correspondence_checks
from tl_mod_materials import insight_checks as materials_checks

#: In display order: readiness, constraints, expected links, clocks, shortages.
SOURCES: tuple[CheckSource, ...] = (
    awp_checks.findings,
    constraint_findings,
    expected_link_findings,
    correspondence_checks.findings,
    materials_checks.findings,
)


def sources_for(conn: Connection, holder: Holder, scope: str) -> tuple[CheckSource, ...]:
    """``SOURCES`` less the constraint source when ``holder`` lacks the view word on ``scope``."""
    if holds_word(conn, holder, scope=scope, module=ACCESS_MODULE, word=normalise_word(VIEW_WORD)):
        return SOURCES
    return tuple(s for s in SOURCES if s is not constraint_findings)
