"""The Insights tab as text (P2-INS T03; brief 21.6, spec A2, A2.1, A3).

Pure functions: no client call, no I/O, no ``textual`` import. The findings come from
``CheckFinding`` and nothing else; the tab's widget draws the lines this module returns.
Checks are facts read from the record's own sources. They are never called suggestions, machine
output, or anything named after a model or a provider.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.insights.checks import SOURCE_ORDER
from tl_core.insights.types import CheckFinding
from tl_core.readiness.types import RecordRef

from tl_tui.display import Labels, humanize, type_label

SUBTABS = ("checks", "suggestions", "analysis", "ask")
SUBTAB_TITLES = {
    "checks": "Checks",
    "suggestions": "Suggestions",
    "analysis": "Analysis",
    "ask": "Ask",
}
NOTHING_TO_SHOW = "Nothing needs attention."
UNAVAILABLE = {
    "suggestions": "Suggestions are not available yet.",
    "analysis": "Analyses are not available yet.",
    "ask": "Ask is not available yet.",
}
# The telemetry request kind each unavailable subtab writes (never "check": Checks writes nothing).
REQUEST_KIND = {"suggestions": "suggestion", "analysis": "analysis", "ask": "ask"}
SOURCE_TITLES = {
    "readiness": "Readiness",
    "constraints": "Constraints",
    "expected_links": "Expected links",
    "clocks": "Response clocks",
    "shortages": "Shortages",
}
BLOCKING_MARK = "!"
NO_MARK = " "
INDENT = "    "


def trigger_of(subtab: str) -> str:
    """The telemetry trigger of a subtab: ``screen:insights.<subtab>``."""
    return f"screen:insights.{subtab}"


def subtab_line(current: str) -> str:
    """``[Checks]  Suggestions  Analysis  Ask``: the open subtab in brackets."""
    return "  ".join(
        f"[{SUBTAB_TITLES[name]}]" if name == current else SUBTAB_TITLES[name] for name in SUBTABS
    )


def unavailable_line(subtab: str) -> str:
    """The one plain line a subtab that is not built yet shows."""
    return UNAVAILABLE[subtab]


def source_title(source: str) -> str:
    """The plain source word for a heading; an unknown source is humanized."""
    return SOURCE_TITLES.get(source) or humanize(source)


def grouped(findings: Sequence[CheckFinding]) -> list[tuple[str, list[CheckFinding]]]:
    """The findings by source, the sources in ``SOURCE_ORDER``; a source not named there comes
    after them, in the order it first appears. Findings keep their order inside a source."""
    groups: dict[str, list[CheckFinding]] = {}
    for finding in findings:
        groups.setdefault(finding.source, []).append(finding)

    def rank(source: str) -> int:
        return SOURCE_ORDER.index(source) if source in SOURCE_ORDER else len(SOURCE_ORDER)

    ordered = sorted(groups, key=rank)  # a stable sort keeps first-appearance order for the rest
    return [(source, groups[source]) for source in ordered]


def finding_line(finding: CheckFinding, *, technical: bool = False) -> str:
    """``! blocked  text  (since 2026-11-07)``; a warning has a space where the ``!`` is.

    Technical mode adds the source name and the subject id in brackets at the end.
    """
    mark = BLOCKING_MARK if finding.severity == "blocking" else NO_MARK
    line = f"{mark} {finding.state}  {finding.text}"
    if finding.since:
        line += f"  (since {finding.since[:10]})"
    if technical:
        line += f"  [{finding.source} {finding.subject_id}]"
    return line


def reference_line(ref: RecordRef, labels: Labels) -> str:
    """``    Control valve FV-1001``: a related record by its display key, never by its id."""
    return f"{INDENT}{type_label(labels, ref.record_type)} {ref.key}"


def ordered_findings(findings: Sequence[CheckFinding]) -> list[CheckFinding]:
    """The findings in the order the Checks subtab shows them (the cursor counts in this order)."""
    return [finding for _source, items in grouped(findings) for finding in items]


def checks_rows(
    findings: Sequence[CheckFinding], labels: Labels | None = None, *, technical: bool = False
) -> list[tuple[int | None, str]]:
    """The Checks subtab as ``(finding index, line)`` pairs. The index is the finding's place in
    ``ordered_findings``; headings, blank lines and reference lines carry ``None``."""
    if not findings:
        return [(None, NOTHING_TO_SHOW)]
    lab = Labels() if labels is None else labels
    rows: list[tuple[int | None, str]] = []
    index = 0
    for position, (source, items) in enumerate(grouped(findings)):
        if position:
            rows.append((None, ""))
        rows.append((None, source_title(source)))
        for finding in items:
            rows.append((index, finding_line(finding, technical=technical)))
            rows.extend((None, reference_line(ref, lab)) for ref in finding.resolve_via)
            index += 1
    return rows


def checks_lines(
    findings: Sequence[CheckFinding], labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The Checks subtab: one block per source, headed by its word, or the one line for none."""
    return [line for _index, line in checks_rows(findings, labels, technical=technical)]


def reference_of(finding: CheckFinding) -> RecordRef | None:
    """The record a finding points to first (``resolve_via[0]``), or None."""
    return finding.resolve_via[0] if finding.resolve_via else None


def first_reference(findings: Sequence[CheckFinding]) -> RecordRef | None:
    """The first record a finding points to, in the order the Checks subtab shows them."""
    for finding in ordered_findings(findings):
        ref = reference_of(finding)
        if ref is not None:
            return ref
    return None
