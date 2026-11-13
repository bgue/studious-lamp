"""P2-I5-T11a1: the IWP log counts (Ready checks, open blocking constraints, state-since), each
checked against a recount from the tables, and the hidden IWP left out."""

from __future__ import annotations

import pytest
from awp_world import SCOPE, World
from progress_world import ProgressWorld
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services.commands import Command
from tl_mod_awp.common import move
from tl_mod_awp.iwp_counts import IwpCountRow, iwp_counts
from tl_mod_awp.names import IWP


@pytest.fixture
def w(world: World) -> World:
    return world


def issue(w: World, iwp: str) -> None:
    """Walk an IWP to Issued along the real workflow (Draft, In development, Constraint check,
    Ready, Issued)."""
    w.call("uma", "StartIwpDevelopment", iwp=iwp)
    w.call("uma", "SendIwpToConstraintCheck", iwp=iwp)
    with open_uow(w.db) as uow:
        cmd = Command(actor="user:uma", source="test", scope=SCOPE)
        move(uow, cmd, iwp, "ready")
        move(uow, cmd, iwp, "issue")


def evaluated(w: World, iwp: str, states: tuple[str, ...]) -> None:
    """A readiness evaluation as the projector would hold it (one check per state)."""
    with open_uow(w.db) as uow:
        conn = uow.conn()
        ready = all(s in ("ok", "n_a") for s in states)
        conn.execute(
            text(
                "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, "
                "facts_hash, as_of_seq) VALUES (:i, :s, '2026-10-05T00:00:00+00:00', "
                "'2026-10-05', :r, 'h', 0)"
            ),
            {"i": iwp, "s": SCOPE, "r": ready},
        )
        for n, state in enumerate(states):
            conn.execute(
                text(
                    "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, "
                    "version, state, detail, count_ok, count_total, resolve_via_json, "
                    "as_of_seq) VALUES (:row, :s, :i, :n, '1', :st, '', 0, 0, '[]', 0)"
                ),
                {"row": f"{iwp}-{n}", "s": SCOPE, "i": iwp, "n": f"check{n}", "st": state},
            )


def counts(w: World) -> dict[str, IwpCountRow]:
    with open_uow(w.db, readonly=True) as uow:
        return {r.number: r for r in iwp_counts(uow.conn(), SCOPE)}


def number(w: World, iwp: str) -> str:
    return str(w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))


def test_counts_equal_a_recount(w: World) -> None:
    pw = ProgressWorld(w)
    a = w.iwp("Rack A", planned_start="2026-12-01", foreman="user:uma")
    b = w.iwp("Rack B", planned_start="2026-12-08", foreman="user:uma")
    issue(w, a)
    issue(w, b)
    evaluated(w, a, ("ok", "ok", "unknown"))  # ready 2 of 3, not ready
    evaluated(w, b, ("ok", "n_a"))
    pw.raise_blocking(a, "complete")  # one open blocking constraint on A

    rows = counts(w)
    ra, rb = rows[number(w, a)], rows[number(w, b)]
    assert (ra.evaluated, ra.ready_ok, ra.ready_total, ra.open_blocking) == (True, 2, 3, 1)
    assert (rb.evaluated, rb.ready_ok, rb.ready_total, rb.open_blocking) == (True, 2, 2, 0)

    # the recount straight from the tables
    recount_ok = w.scalar(
        "SELECT COUNT(*) FROM cur_awp_readiness_check WHERE iwp_id = :i AND state IN ('ok','n_a')",
        i=a,
    )
    recount_open = w.scalar(
        "SELECT COUNT(*) FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.subject_id = :i AND c.severity = 'blocking' "
        "AND COALESCE(r.status, 'Open') IN ('Open', 'Assigned')",
        i=a,
    )
    assert (ra.ready_ok, ra.open_blocking) == (recount_ok, recount_open)


def test_state_since_is_the_transition_date_and_a_draft_has_none(w: World) -> None:
    draft = w.iwp("Rack D")
    issued = w.iwp("Rack E", planned_start="2026-12-01", foreman="user:uma")
    issue(w, issued)
    entered = str(
        w.scalar("SELECT entered_at FROM cur_workflow_state WHERE record_id = :i", i=issued)
    )
    rows = counts(w)
    assert rows[number(w, issued)].state_since == entered[:10]
    assert rows[number(w, draft)].state_since is None
    assert rows[number(w, draft)].evaluated is False
    assert (rows[number(w, draft)].ready_ok, rows[number(w, draft)].ready_total) == (0, 0)


def test_a_hidden_iwp_is_absent(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    shown = w.iwp("Rack F")
    secret = w.iwp("Rack G")
    with open_uow(w.db) as uow:
        conn = uow.conn()
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS ic_iwp_class (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text("DELETE FROM ic_iwp_class"))
        for row in w.rows("SELECT id FROM cur_awp_iwp"):
            cls = "restricted" if row["id"] == secret else "internal"
            conn.execute(
                text("INSERT INTO ic_iwp_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
            )
    source = ConfidentialSource(
        record_types=frozenset({IWP}),
        table="ic_iwp_class",
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    rows = counts(w)
    assert number(w, shown) in rows
    assert number(w, secret) not in rows


def test_the_same_call_twice_is_equal(w: World) -> None:
    issue(w, w.iwp("Rack H", planned_start="2026-12-01", foreman="user:uma"))
    w.iwp("Rack I")
    first = counts(w)
    assert counts(w) == first
    with open_uow(w.db, readonly=True) as uow:
        listed = [r.number for r in iwp_counts(uow.conn(), SCOPE)]
    assert listed == sorted(first)  # by number
