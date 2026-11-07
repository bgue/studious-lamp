"""A hidden record reads as one that never existed, in views and in commands (ADR-0016)."""

from __future__ import annotations

import acc_s3


def test_hidden_record_never_existed(world3: acc_s3.World) -> None:
    acc_s3.check_hidden(world3)
