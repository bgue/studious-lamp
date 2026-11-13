"""C2: the four constraint commands, module sources, links, guard and reads (P2-I2-C2).

The world and helpers are the acceptance harness ``dev/accept/P2-I2/c2_checks.py`` (a ledger with
people, the S2 seed and documents); each test builds its own world on SQLite.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-I2"
sys.path.insert(0, str(ACCEPT))
import c2_checks as c2  # noqa: E402  # pyright: ignore[reportMissingImports]
from awp_world import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    SCOPE,
    hidden_record,
    refuses,
)
from tl_adapters.db import rebuild_projections  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.constraints import (  # noqa: E402
    ConstraintRuleError,
    ConstraintSourceError,
    ConstraintStateError,
    PhaseNotGatedError,
    clear_constraint,
    open_blocking,
    queries,
    raise_constraint,
)
from tl_core.services.errors import GuardFailedError, RecordNotFoundError  # noqa: E402

H1, H2, H3 = c2.H1, c2.H2, c2.H3
SOURCES = ("check", "rule", "feed_hold", "thread_hold")


@pytest.fixture
def built(tmp_path: Path) -> tuple[c2.C2, dict[str, str]]:
    return c2.build(tmp_path / "c2.db")


@pytest.fixture
def w(built: tuple[c2.C2, dict[str, str]]) -> c2.C2:
    return built[0]


@pytest.fixture
def iwp(w: c2.C2) -> str:
    return c2.iwp_in_check(w)


def links(w: c2.C2, relation: str, **ids: str) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in ids)
    return w.scalar(
        f"SELECT COUNT(*) FROM cur_links WHERE relation = :r AND {where}", r=relation, **ids
    )


def test_manual_raise_numbers_and_keeps_due_at(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp, effective_at="2020-01-01")
    assert made.key == "P123-CON-0001"
    assert w.row(made.stream_id)["due_at"] == "2026-12-01"
    assert w.raise_(iwp, severity="advisory").key == "P123-CON-0002"


def test_envelope_effective_at_is_capture_time(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp, effective_at="2020-01-01")
    assert all(e.effective_at.year >= 2026 for e in made.events)


@pytest.mark.parametrize(
    "name", ["RaiseConstraint", "AssignConstraint", "ClearConstraint", "WithdrawConstraint"]
)
def test_viewer_refused_every_command(w: c2.C2, iwp: str, name: str) -> None:
    made = w.raise_(iwp)
    fields: dict[str, Any] = {
        "RaiseConstraint": dict(subject=iwp, phase="ready", severity="advisory", category="other"),
        "AssignConstraint": dict(constraint=made.stream_id, owner="user:user"),
        "ClearConstraint": dict(constraint=made.stream_id, reason="r"),
        "WithdrawConstraint": dict(constraint=made.stream_id, reason="r"),
    }[name]
    refuses(ForbiddenError, lambda: w.run("viewer", name, **fields))


@pytest.mark.parametrize("source", SOURCES)
def test_person_refused_module_sources(w: c2.C2, iwp: str, source: str) -> None:
    refuses(ConstraintSourceError, lambda: w.raise_(iwp, severity="advisory", source_kind=source))


def test_module_raises_all_four_sources(w: c2.C2, iwp: str) -> None:
    outs = [
        w.modraise(
            iwp, s, **({"check_name": "c1", "facts_hash": H1} if s == "check" else {})
        ).action
        for s in SOURCES
    ]
    assert outs == ["raised"] * 4
    assert w.scalar("SELECT COUNT(*) FROM cur_core_constraint") == 4


def test_phase_not_gated_for_blocking_only(w: c2.C2, iwp: str) -> None:
    refuses(PhaseNotGatedError, lambda: w.raise_(iwp, "pour"))
    assert w.raise_(iwp, "pour", severity="advisory").key


def test_exists_for_same_subject_phase_and_check(w: c2.C2, iwp: str) -> None:
    w.modraise(iwp, "check", check_name="c1", facts_hash=H1)
    assert w.modraise(iwp, "check", check_name="c1", facts_hash=H2).action == "exists"


def _check_constraint(w: c2.C2, iwp: str) -> Any:
    return w.mod(
        lambda u: raise_constraint(
            u,
            subject_id=iwp,
            phase="start",
            severity="blocking",
            category="materials",
            source="check",
            check_name="c2",
            facts_hash=H1,
            by_module="awp",
        )
    )


def test_person_clear_keeps_suppress_hash_and_suppresses_equal_hash(w: c2.C2, iwp: str) -> None:
    chk = _check_constraint(w, iwp)
    w.run("waiver", "ClearConstraint", constraint=chk.constraint_id, reason="seen")
    assert w.row(chk.constraint_id)["suppress_hash"] == H1
    sup = w.modraise(iwp, "check", phase="start", check_name="c2", facts_hash=H1)
    new = w.modraise(iwp, "check", phase="start", check_name="c2", facts_hash=H3)
    assert (sup.action, new.action) == ("suppressed", "raised")


def test_module_clear_drops_hash_and_refuses_manual(w: c2.C2, iwp: str) -> None:
    chk = _check_constraint(w, iwp)
    w.mod(clear_constraint, constraint_id=chk.constraint_id, reason="ok", by_module="awp")
    assert w.row(chk.constraint_id)["suppress_hash"] is None
    manual = w.raise_(iwp)
    refuses(
        ConstraintSourceError,
        lambda: w.mod(
            clear_constraint, constraint_id=manual.stream_id, reason="x", by_module="awp"
        ),
    )


def test_targets_blocks_and_resolves_links(
    w: c2.C2, built: tuple[c2.C2, dict[str, str]], iwp: str
) -> None:
    docs = built[1]
    iso1, iso2 = c2.s2.ISO[0], c2.s2.ISO[1]
    manual = w.raise_(iwp)
    assert links(w, "blocks", from_id=manual.stream_id, to_id=iwp) == 1
    target = w.run(
        "user",
        "RaiseConstraint",
        subject=iwp,
        phase="ready",
        severity="advisory",
        category="rfi",
        owner="user:user",
        target=docs[iso1],
    )
    assert links(w, "targets", from_id=target.stream_id, to_id=docs[iso1]) == 1
    w.run(
        "user",
        "ClearConstraint",
        constraint=manual.stream_id,
        reason="r",
        resolved_by=docs[iso2],
        cleared_at="2026-01-01",
    )
    assert links(w, "resolves", to_id=manual.stream_id) == 1
    assert w.row(manual.stream_id)["cleared_at"] == "2026-01-01"


def test_cleared_at_before_effective_at_refused(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp, effective_at="2020-01-01")
    refuses(
        ConstraintRuleError,
        lambda: w.run(
            "user",
            "ClearConstraint",
            constraint=made.stream_id,
            reason="r",
            cleared_at="2019-01-01",
        ),
    )


def test_cleared_constraint_takes_no_withdraw(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp)
    w.run("user", "ClearConstraint", constraint=made.stream_id, reason="r")
    refuses(
        ConstraintStateError,
        lambda: w.run("user", "WithdrawConstraint", constraint=made.stream_id, reason="x"),
    )


def test_guard_blocks_ready_with_keys_only_message(w: c2.C2, iwp: str) -> None:
    block = w.raise_(iwp, description="Spool secret text")
    msg = str(refuses(GuardFailedError, lambda: w.move(iwp, "ready")))
    assert block.key in msg
    assert "secret" not in msg and "user:user" not in msg
    assert w.mod(lambda u: open_blocking(u.conn(), iwp, "ready")) == [block.key]


def test_guard_passes_after_clear_withdraw_and_with_advisory(w: c2.C2, iwp: str) -> None:
    block = w.raise_(iwp)
    refuses(GuardFailedError, lambda: w.move(iwp, "ready"))
    w.run("user", "ClearConstraint", constraint=block.stream_id, reason="done")
    w.raise_(iwp, severity="advisory")
    w.move(iwp, "ready")
    assert w.state(iwp) == "Ready"
    other = c2.iwp_in_check(w)
    w.run("user", "WithdrawConstraint", constraint=w.raise_(other).stream_id, reason="wrong")
    w.move(other, "ready")
    assert w.state(other) == "Ready"


def test_cwp_start_execution_guard(w: c2.C2) -> None:
    cwp = w.seed()["Rack 12 piping"]
    held = w.raise_(cwp, "start_execution")
    refuses(GuardFailedError, lambda: w.call("uma", "StartCwpExecution", cwp=cwp))
    w.run("user", "ClearConstraint", constraint=held.stream_id, reason="ok")
    w.call("uma", "StartCwpExecution", cwp=cwp)
    assert w.state(cwp) == "Executing"


def test_five_reader_walk_of_a_restricted_subject(w: c2.C2) -> None:
    secret = hidden_record(w)
    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    seen = {
        who: (
            len(w.read(queries.list_constraints, who, SCOPE, subject_id=secret)),
            w.read(queries.count_constraints, who, SCOPE, subject_id=secret),
            w.read(queries.get_constraint, who, made.stream_id) is not None,
        )
        for who in c2.VIEWERS
    }
    assert seen == {
        "default": (0, 0, False),
        "user": (0, 0, False),
        "agent": (0, 0, False),
        "controller": (1, 1, True),
        "admin": (1, 1, True),
    }
    refuses(RecordNotFoundError, lambda: w.raise_(secret, severity="advisory", owner="user:user"))
    refuses(
        RecordNotFoundError,
        lambda: w.run("user", "ClearConstraint", constraint=made.stream_id, reason="r"),
    )
    assert not w.read(
        queries.constraint_history, "user", w.mod(lambda u: u.ledger.read_stream(made.stream_id))
    )


def test_generic_reads_hide_the_constraint_like_a_missing_one(w: c2.C2) -> None:
    secret = hidden_record(w)
    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    c2.generic_walk(w, made.stream_id, secret)  # exits with FAIL on a leak


def test_hidden_target_reads_as_the_no_target_twin(w: c2.C2, iwp: str) -> None:
    secret = hidden_record(w)
    tgt = w.raise_(
        iwp, severity="advisory", who="controller", owner="user:controller", target=secret
    )
    twin = w.raise_(iwp, severity="advisory", who="controller", owner="user:controller")
    a, b = (w.read(queries.get_constraint, "user", x.stream_id) for x in (tgt, twin))
    skip = ("id", "key")
    assert {k: v for k, v in asdict(a).items() if k not in skip} == {
        k: v for k, v in asdict(b).items() if k not in skip
    }
    assert a.target_id is None
    seen = w.read(queries.get_constraint, "controller", tgt.stream_id)
    assert seen.target_id == secret and seen.target_kind == "record"


def test_rebuild_equals_incremental(w: c2.C2, iwp: str) -> None:
    made = w.raise_(iwp)
    w.modraise(iwp, "rule")
    w.run("user", "ClearConstraint", constraint=made.stream_id, reason="r", cleared_at="2026-11-01")
    tables = ("cur_core_constraint", "cur_core_record", "cur_links")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    assert before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
