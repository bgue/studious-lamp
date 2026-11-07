"""Command words, offers per state and role, and the agent proposal."""

from __future__ import annotations

import acc_s3


def test_module_words_and_rules(world3: acc_s3.World) -> None:
    acc_s3.check_module(world3)


def test_offers_per_state_and_role(world3: acc_s3.World) -> None:
    acc_s3.check_offers(world3)


def test_agent_reservation_is_a_proposal(world3: acc_s3.World) -> None:
    acc_s3.check_proposal(world3)
