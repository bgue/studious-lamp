"""Projector of ``WBSNode.BudgetRolledUp`` into ``cur_awp_rollup`` (S5 fills this)."""

from __future__ import annotations

from tl_core.projection.types import Projector


def rollup_projectors() -> list[Projector]:
    """Fresh projectors of the rollup table; none until S5."""
    return []
