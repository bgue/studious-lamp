"""The one list of check sources the Checks read uses (ADR-0028). The route and the embedded
client both call ``record_checks`` with it; a module is imported here and nowhere in core."""

from __future__ import annotations

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
