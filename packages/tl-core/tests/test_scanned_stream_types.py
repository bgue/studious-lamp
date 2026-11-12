"""The streams whose events are scanned for hidden record ids (SR3 F3 pin)."""

from __future__ import annotations

from tl_core.confidentiality import SCANNED_STREAM_TYPES


def test_a_weekly_plan_event_naming_an_iwp_is_scanned() -> None:
    assert SCANNED_STREAM_TYPES == frozenset(
        {
            "numbering.Counter",
            "core.Proposal",
            "documents.Transmittal",
            "core.Thread",
            "awp.IWP",
            "awp.WeeklyPlan",
        }
    )
