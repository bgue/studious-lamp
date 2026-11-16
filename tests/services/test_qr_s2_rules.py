"""QR S2: the three commands are hooked from the module's own package, marked and decided."""

from __future__ import annotations

from ip_rules import problems


def test_the_qr_rows_pass_every_rule() -> None:
    assert problems("qr", {"IssueScanCode", "RevokeScanCode", "RotateScanCode"}) == []
