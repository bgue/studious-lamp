"""P2-I5-S4b: a person clears a check-raised constraint only with ``core.constraint.waive``.

No new event and no new payload key: the clear is ``Constraint.Cleared`` with ``suppress`` true
(R-P2-11), and ``waived`` is derived from the row (Cleared, source check, suppress hash kept).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-I2"
sys.path.insert(0, str(ACCEPT))
import c2_checks as c2  # noqa: E402  # pyright: ignore[reportMissingImports]
from awp_world import SCOPE, hidden_record, refuses  # noqa: E402  # pyright: ignore
from tl_adapters.db import rebuild_projections  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from tl_core.constraints import queries, raise_constraint  # noqa: E402
from tl_core.constraints.errors import MSG_WAIVE_WORD  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402

H1, H3 = c2.H1, c2.H3


@pytest.fixture
def w(tmp_path: Path) -> c2.C2:
    return c2.build(tmp_path / "waive.db")[0]


@pytest.fixture
def iwp(w: c2.C2) -> str:
    return c2.iwp_in_check(w)


def check_constraint(w: c2.C2, iwp: str, facts: str = H1) -> Any:
    return w.mod(
        lambda u: raise_constraint(
            u,
            subject_id=iwp,
            phase="start",
            severity="blocking",
            category="materials",
            source="check",
            check_name="c2",
            facts_hash=facts,
            by_module="awp",
        )
    )


def status(w: c2.C2, cid: str) -> str:
    return str(w.scalar("SELECT COALESCE(status, 'Open') FROM cur_core_record WHERE id = :i", i=cid))


def waived(w: c2.C2, who: str, cid: str) -> bool:
    return w.read(queries.get_constraint, who, cid).waived


def test_plain_user_is_refused_with_the_fixed_text(w: c2.C2, iwp: str) -> None:
    made = check_constraint(w, iwp)
    err = refuses(
        ForbiddenError,
        lambda: w.run("user", "ClearConstraint", constraint=made.constraint_id, reason="seen"),
    )
    assert str(err) == MSG_WAIVE_WORD
    assert "core.constraint.waive" in MSG_WAIVE_WORD
    assert status(w, made.constraint_id) == "Open"


def test_holder_with_reason_clears_and_the_row_reads_waived(w: c2.C2, iwp: str) -> None:
    made = check_constraint(w, iwp)
    assert waived(w, "admin", made.constraint_id) is False
    w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason="accepted risk")
    assert status(w, made.constraint_id) == "Cleared"
    assert waived(w, "admin", made.constraint_id) is True
    listed = w.read(queries.list_constraints, "admin", SCOPE, subject_id=iwp)
    assert [r.waived for r in listed] == [True]


@pytest.mark.parametrize("reason", ["", "   ", "x" * 301])
def test_reason_is_required_and_capped_at_300(w: c2.C2, iwp: str, reason: str) -> None:
    made = check_constraint(w, iwp)
    refuses(  # the command model refuses it before the handler runs
        ValidationError,
        lambda: w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason=reason),
    )
    assert status(w, made.constraint_id) == "Open"
    w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason="y" * 300)


def test_manual_constraint_clears_with_the_edit_word_alone(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp)
    w.run("user", "ClearConstraint", constraint=made.stream_id, reason="done")
    assert waived(w, "admin", made.stream_id) is False


def test_module_clear_needs_no_word_and_is_not_waived(w: c2.C2, iwp: str) -> None:
    from tl_core.constraints import clear_constraint

    made = check_constraint(w, iwp)
    w.mod(
        lambda u: clear_constraint(
            u,
            constraint_id=made.constraint_id,
            reason="facts changed",
            by_module="awp",
            cleared_at=None,
            resolved_by=None,
        )
    )
    assert status(w, made.constraint_id) == "Cleared"
    assert waived(w, "admin", made.constraint_id) is False


def test_agent_is_refused_the_word(w: c2.C2, iwp: str) -> None:
    with c2.open_uow(w.db) as uow:
        accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
    made = check_constraint(w, iwp)
    spec = c2.CMDS["ClearConstraint"]
    cmd = spec.model(
        actor="agent:bot", source="test", scope=SCOPE, constraint=made.constraint_id, reason="r"
    )

    def clear() -> Any:
        with c2.open_uow(w.db) as uow:
            return spec.handler(uow, cmd)

    err = refuses(ForbiddenError, clear)
    assert str(err) == MSG_WAIVE_WORD
    assert status(w, made.constraint_id) == "Open"


def test_waived_clear_keeps_the_suppress_hash(w: c2.C2, iwp: str) -> None:
    made = check_constraint(w, iwp)
    w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason="seen")
    assert w.row(made.constraint_id)["suppress_hash"] == H1
    again = w.modraise(iwp, "check", phase="start", check_name="c2", facts_hash=H1)
    changed = w.modraise(iwp, "check", phase="start", check_name="c2", facts_hash=H3)
    assert (again.action, changed.action) == ("suppressed", "raised")


def test_hidden_constraint_reads_as_missing_and_never_as_waived(w: c2.C2) -> None:
    secret = hidden_record(w)
    with cf.system_view():
        made = w.modraise(secret, "check", check_name="c9", facts_hash=H1)
    # a person without the word (and without sight of the subject) gets the missing answer, not
    # the word's refusal: the word check comes after the visibility check
    refuses(
        RecordNotFoundError,
        lambda: w.run("user", "ClearConstraint", constraint=made.constraint_id, reason="r"),
    )
    refuses(  # even a holder of the word, if the subject is hidden from them
        RecordNotFoundError,
        lambda: w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason="r"),
    )
    w.run("ada", "ClearConstraint", constraint=made.constraint_id, reason="r")  # sees it
    assert waived(w, "admin", made.constraint_id) is True
    for who in ("default", "user", "agent"):
        assert w.read(queries.get_constraint, who, made.constraint_id) is None
        assert w.read(queries.list_constraints, who, SCOPE, subject_id=secret) == []


def test_rebuild_equals_incremental_after_a_waived_clear(w: c2.C2, iwp: str) -> None:
    made = check_constraint(w, iwp)
    w.run("waiver", "ClearConstraint", constraint=made.constraint_id, reason="seen")
    tables = ("cur_core_constraint", "cur_core_record")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    assert before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    assert waived(w, "admin", made.constraint_id) is True
