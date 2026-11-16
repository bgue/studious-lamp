"""PTW S2: the ten permit commands are hooked from the module's own package, marked and decided."""

from __future__ import annotations

from ip_rules import problems

NAMES = {"RequestPermit", "ApprovePermit", "RejectPermit", "IssuePermit", "RevalidatePermit"}
NAMES |= {"SuspendPermit", "ResumePermit", "HandBackPermit", "ClosePermit", "CancelPermit"}
NAMES |= {"ApplyIsolation", "VerifyIsolation", "RemoveIsolation", "LinkIsolation"}  # P2-PTW S3
NAMES |= {"UnlinkIsolation", "RecordGasTest"}


def test_the_permit_rows_pass_every_rule() -> None:
    assert problems("permits", NAMES) == []
