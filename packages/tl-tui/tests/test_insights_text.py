"""The Insights tab's text (P2-INS T03): group order, the blocking mark, the empty text, plain
against technical lines, and no key or id in the plain text. Pure functions, no widget."""

from __future__ import annotations

from tl_core.insights.types import CheckFinding
from tl_core.readiness.types import RecordRef
from tl_tui.display import Labels, find_technical
from tl_tui.insights_text import (
    NOTHING_TO_SHOW,
    SUBTABS,
    checks_lines,
    checks_rows,
    first_reference,
    grouped,
    ordered_findings,
    subtab_line,
    unavailable_line,
)

REF = RecordRef(record_id="01HZZZZZZZZZZZZZZZZZZZZZZZ", record_type="core.Record", key="FV-1001")


def finding(
    source: str,
    *,
    subject: str = "01HAAAAAAAAAAAAAAAAAAAAAAA",
    state: str = "open",
    text: str = "Pressure test not logged",
    since: str | None = None,
    severity: str = "warning",
    refs: list[RecordRef] | None = None,
) -> CheckFinding:
    return CheckFinding(
        source=source,
        subject_id=subject,
        state=state,
        text=text,
        since=since,
        severity=severity,  # pyright: ignore[reportArgumentType]
        resolve_via=refs or [],
    )


def test_sources_come_in_the_spec_order_whatever_order_they_arrive() -> None:
    found = [
        finding("shortages"),
        finding("clocks"),
        finding("readiness"),
        finding("expected_links"),
        finding("constraints"),
    ]
    assert [source for source, _ in grouped(found)] == [
        "readiness",
        "constraints",
        "expected_links",
        "clocks",
        "shortages",
    ]
    lines = checks_lines(found)
    headings = [
        "Readiness",
        "Constraints",
        "Expected links",
        "Response clocks",
        "Shortages",
    ]
    assert [line for line in lines if line in headings] == headings


def test_an_unknown_source_comes_after_the_known_ones_in_first_seen_order() -> None:
    found = [finding("zeta"), finding("readiness"), finding("alpha")]
    assert [source for source, _ in grouped(found)] == ["readiness", "zeta", "alpha"]


def test_a_blocking_finding_has_a_bang_and_a_warning_does_not() -> None:
    lines = checks_lines(
        [
            finding("readiness", state="blocked", severity="blocking", text="Dry run failed"),
            finding("readiness", state="pending", text="Sign-off waiting"),
        ]
    )
    assert "! blocked  Dry run failed" in lines
    assert "  pending  Sign-off waiting" in lines


def test_a_finding_line_carries_the_since_date() -> None:
    lines = checks_lines([finding("clocks", state="overdue", since="2026-11-07T09:30:00Z")])
    assert "  overdue  Pressure test not logged  (since 2026-11-07)" in lines


def test_no_findings_is_the_one_plain_line() -> None:
    assert checks_lines([]) == [NOTHING_TO_SHOW]
    assert NOTHING_TO_SHOW == "Nothing needs attention."


def test_plain_text_has_no_key_or_id_and_no_technical_token() -> None:
    found = [
        finding("readiness", subject="01HAAAAAAAAAAAAAAAAAAAAAAA", refs=[REF]),
        finding("shortages", subject="01HBBBBBBBBBBBBBBBBBBBBBBB", state="short"),
    ]
    labels = Labels()
    plain = checks_lines(found, labels)
    for line in plain:
        assert "01HAAAAAAAAAAAAAAAAAAAAAAA" not in line
        assert "01HBBBBBBBBBBBBBBBBBBBBBBB" not in line
        assert find_technical(line, labels) == []
    # the display key of the related record is the one identifier the plain text shows
    assert any("FV-1001" in line for line in plain)


def test_technical_mode_adds_the_source_and_the_subject_id() -> None:
    found = [finding("readiness", subject="01HAAAAAAAAAAAAAAAAAAAAAAA", state="blocked")]
    plain = checks_lines(found)
    technical = checks_lines(found, technical=True)
    assert "[readiness 01HAAAAAAAAAAAAAAAAAAAAAAA]" not in " ".join(plain)
    assert technical[-1].endswith("[readiness 01HAAAAAAAAAAAAAAAAAAAAAAA]")


def test_resolve_via_is_shown_by_display_key() -> None:
    lines = checks_lines([finding("readiness", refs=[REF])])
    assert lines[-1] == "    Record FV-1001"


def test_first_reference_is_the_first_finding_with_one_in_display_order() -> None:
    other = RecordRef(record_id="01HCCCCCCCCCCCCCCCCCCCCCCC", record_type="core.Record", key="X-1")
    found = [
        finding("clocks", refs=[other]),
        finding("readiness"),
        finding("readiness", refs=[REF]),
    ]
    ref = first_reference(found)
    assert ref is not None and ref.key == "FV-1001"
    assert first_reference([finding("readiness")]) is None


def test_subtab_line_brackets_the_open_subtab() -> None:
    assert subtab_line("checks") == "[Checks]  Suggestions  Analysis  Ask"
    assert subtab_line("ask") == "Checks  Suggestions  Analysis  [Ask]"
    assert SUBTABS == ("checks", "suggestions", "analysis", "ask")


def test_the_three_unbuilt_lines_are_the_brief_wording() -> None:
    assert unavailable_line("suggestions") == "Suggestions are not available yet."
    assert unavailable_line("analysis") == "Analyses are not available yet."
    assert unavailable_line("ask") == "Ask is not available yet."


def test_checks_rows_tag_each_finding_with_its_place_in_display_order() -> None:
    found = [
        finding("clocks", state="overdue", text="Reply due"),
        finding("readiness", state="blocked", text="Dry run", severity="blocking", refs=[REF]),
    ]
    tagged = [(index, line) for index, line in checks_rows(found) if index is not None]
    assert [index for index, _line in tagged] == [0, 1]
    assert tagged[0][1] == "! blocked  Dry run"  # readiness comes first in the Checks subtab
    assert tagged[1][1] == "  overdue  Reply due"
    assert [item.source for item in ordered_findings(found)] == ["readiness", "clocks"]


def test_checks_rows_for_no_findings_is_one_line_with_no_finding() -> None:
    assert checks_rows([]) == [(None, NOTHING_TO_SHOW)]
