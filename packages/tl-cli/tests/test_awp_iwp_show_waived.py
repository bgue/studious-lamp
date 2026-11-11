"""P2-I5-T12a: `tl awp iwp show` lists each waived constraint with who waived it and why."""

# ruff: noqa: F811
from __future__ import annotations

from test_awp_progress import Built, built  # noqa: F401
from tl_adapters.db import open_uow
from tl_core.constraints import raise_constraint
from tl_core.constraints.commands import ClearConstraint
from tl_core.constraints.handlers import handle_clear_constraint


def raise_check(b: Built) -> str:
    with open_uow(b.w.db) as uow:
        made = raise_constraint(
            uow,
            subject_id=b.iwp,
            phase="start",
            severity="blocking",
            category="materials",
            source="check",
            check_name="t12a",
            facts_hash="a" * 64,
            by_module="awp",
        )
    return str(made.constraint_id)


def clear(b: Built, constraint: str, who: str, reason: str) -> None:
    cmd = ClearConstraint(
        actor=f"user:{who}",
        source="test",
        scope="project:P123",
        constraint=constraint,
        reason=reason,
    )
    with open_uow(b.w.db) as uow:
        handle_clear_constraint(uow, cmd)


def test_a_waived_constraint_is_listed_with_who_and_why(built: Built) -> None:
    lines = built.cli.ok("iwp", "show", built.number)
    assert "waived constraints 0" in lines
    assert "open constraints 0" in lines
    cid = raise_check(built)
    assert "open constraints 1" in built.cli.ok("iwp", "show", built.number)
    clear(built, cid, "ada", "accepted risk, pipe is lined")
    lines = built.cli.ok("iwp", "show", built.number)
    assert "open constraints 0" in lines
    at = lines.index("waived constraints 1")
    assert lines[at + 1].endswith("waived by user:ada: accepted risk, pipe is lined")
    assert lines[at + 1].startswith("  P123-")
    assert lines[at + 2].startswith("signoffs ")


def test_a_cleared_constraint_that_was_not_waived_is_not_listed(built: Built) -> None:
    with open_uow(built.w.db) as uow:
        made = raise_constraint(
            uow,
            subject_id=built.iwp,
            phase="start",
            severity="blocking",
            category="materials",
            source="manual",
            check_name=None,
            facts_hash=None,
            by_module="awp",
            owner="user:uma",
        )
    clear(built, str(made.constraint_id), "ada", "done")
    lines = built.cli.ok("iwp", "show", built.number)
    assert "waived constraints 0" in lines
    assert not [ln for ln in lines if "waived by" in ln]
