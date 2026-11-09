"""A stand-in world for the rules-of-credit engine and the progress commands (P2-I5 S2).

``ProgressWorld`` wraps ``awp_world.World`` (the people ``ada``, ``uma``, ``sue``, ``vera``) with
the pieces a progress test needs: an IWP with scope items, the moves of items and of the IWP, a
project edition, a blocking constraint and a hidden item. ``checks`` is what
``dev/accept/P2-I5/S2.py`` runs (one ``PASS`` line each). Nothing here reuses a real module name.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from awp_world import SCOPE, World, refuses
from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor
from tl_core.constraints.commands import RaiseConstraint
from tl_core.constraints.handlers import handle_raise_constraint
from tl_core.modules import ConfidentialSource
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError, RecordNotFoundError, ServiceError
from tl_core.settings.service import set_setting
from tl_mod_awp import errors
from tl_mod_awp.commands import RecordManualProgress
from tl_mod_awp.names import SCOPE_ITEM
from tl_mod_awp.progress import engine

EDITION = "awp.rules_of_credit.set"
PROGRESS = "IWP.ProgressRecorded"
TABLES = (
    ("cur_awp_iwp_progress", "iwp_id"),
    ("cur_awp_weekly_plan", "id"),
    ("cur_awp_week_commitment", "row_id"),
    ("cur_awp_iwp", "id"),
    ("cur_core_record", "id"),
)


class ProgressWorld:
    def __init__(self, w: World) -> None:
        self.w = w

    # --- building --------------------------------------------------------------------------

    def package(self, hours: Sequence[str], **more: Any) -> tuple[str, list[str]]:
        """A Draft IWP holding one piping scope item per entry of ``hours`` (ids)."""
        iwp = self.w.iwp(planned_start="2026-12-01", foreman="user:uma", **more)
        items = self.w.items(list(hours))
        self.w.call("uma", "AddIwpScope", iwp=iwp, items=items)
        return iwp, items

    def set_edition(self, value: str) -> None:
        with open_uow(self.w.db) as uow:
            set_setting(
                uow,
                key=EDITION,
                layer=f"project:{SCOPE[8:]}",
                value=value,
                actor="user:ada",
                source="test",
                reason="t",
                accept_risk=True,
            )

    def raise_blocking(self, iwp: str, phase: str) -> None:
        cmd = RaiseConstraint(
            actor="user:sue",
            source="test",
            scope=SCOPE,
            subject=iwp,
            phase=phase,
            severity="blocking",
            category="other",
            owner="user:uma",
        )
        with open_uow(self.w.db) as uow:
            handle_raise_constraint(uow, cmd)

    def set_hours(self, item: str, hours: str | None) -> None:
        """Set the estimate of an item by hand (a projection write: the command wants a value)."""
        with open_uow(self.w.db) as uow:
            uow.conn().execute(
                text("UPDATE cur_awp_scope_item SET est_hours = :h WHERE id = :i"),
                {"h": hours, "i": item},
            )

    # --- acting ----------------------------------------------------------------------------

    def move(self, name: str, item: str, who: str = "uma") -> Any:
        return self.w.call(who, name, record_id=item, expected_version=self.w.version(item))

    def manual(self, iwp: str, item: str, done: bool = True, who: str = "uma") -> Any:
        return self.w.call(
            who,
            "RecordManualProgress",
            iwp_id=iwp,
            steps=[{"scope_item_id": item, "step": "Material received", "done": done}],
            expected_version=self.w.version(iwp),
        )

    def field(self, name: str, iwp: str, who: str = "uma", **more: Any) -> Any:
        return self.w.call(who, name, iwp_id=iwp, expected_version=self.w.version(iwp), **more)

    # --- reading ---------------------------------------------------------------------------

    def row(self, iwp: str) -> dict[str, Any] | None:
        rows = self.w.rows("SELECT * FROM cur_awp_iwp_progress WHERE iwp_id = :i", i=iwp)
        return rows[0] if rows else None

    def pct(self, iwp: str) -> str:
        row = self.row(iwp)
        return "none" if row is None else str(row["earned_pct"])

    def count(self, iwp: str, event_type: str = PROGRESS) -> int:
        return int(
            self.w.scalar(
                "SELECT COUNT(*) FROM events WHERE stream_id = :i AND event_type = :t",
                i=iwp,
                t=event_type,
            )
        )

    def earned(self, iwp: str, viewer: cf.Viewer | None = None) -> engine.Earned:
        with open_uow(self.w.db, readonly=True) as uow:
            return engine.earned_fraction(uow.conn(), iwp, viewer=viewer)

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {t: self.w.rows(f"SELECT * FROM {t} ORDER BY {o}") for t, o in TABLES}

    def rebuild(self) -> None:
        rebuild_projections(self.w.db)

    @contextmanager
    def hidden(self, *items: str) -> Iterator[None]:
        """The items are restricted to everyone below a person with clearance (a test source over
        a table of this test): the lowest viewer cannot open them."""
        with open_uow(self.w.db) as uow:
            uow.conn().execute(
                text("CREATE TABLE IF NOT EXISTS pw_item_class (id TEXT PRIMARY KEY, cls TEXT)")
            )
            uow.conn().execute(text("DELETE FROM pw_item_class"))
            rows = self.w.rows("SELECT id FROM cur_awp_scope_item")
            for row in rows:
                cls = "restricted" if row["id"] in items else "internal"
                uow.conn().execute(
                    text("INSERT INTO pw_item_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
                )
        source = ConfidentialSource(
            record_types=frozenset({SCOPE_ITEM}),
            table="pw_item_class",
            id_column="id",
            class_column="cls",
        )
        real = cf.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[assignment]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[assignment]


def ok(name: str, cond: bool = True) -> None:
    if not cond:
        sys.exit(f"FAIL {name}")
    print(f"PASS {name}")


def build(db: Path) -> ProgressWorld:
    w = World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    return ProgressWorld(w)


def checks(pw: ProgressWorld) -> None:
    w = pw.w
    lowest = cf.Viewer()

    with open_uow(w.db, readonly=True) as uow:
        rules = engine.edition_for(uow.conn(), SCOPE)
    ok(
        "the standard edition resolves",
        rules.edition == "co.acme.awp@1.1.0" and "piping" in rules.by_commodity,
    )

    # worked example: 10, 10 and 20 hours and a 1 hour item; steps 30 / 60 / 10
    iwp, (a, b, c, d) = pw.package(["10.0", "10.0", "20.0", "20.0"])
    pw.move("InstallScopeItem", a)  # 60
    pw.move("InstallScopeItem", b)
    pw.move("VerifyScopeItem", b)  # 70
    pw.manual(iwp, c)  # 30
    # (10*60 + 10*70 + 20*30 + 20*0) / 60 = 31.666... -> 31.7
    ok("four items of 10, 10, 20, 20 hours earn 31.7", pw.pct(iwp) == "31.7")
    ok(
        "the item figures are 60.0, 70.0, 30.0, 0.0",
        [str(i.pct) for i in sorted(pw.earned(iwp).items, key=lambda i: i.key)]
        == [
            "60.0",
            "70.0",
            "30.0",
            "0.0",
        ]
        or sorted(str(i.pct) for i in pw.earned(iwp).items) == ["0.0", "30.0", "60.0", "70.0"],
    )

    # half-up at .05: 30 / 600 = 0.05 -> 0.1
    half, (h1, h2) = pw.package(["1.0", "599.0"])
    pw.manual(half, h1)
    ok("0.05 rounds half-up to 0.1", pw.pct(half) == "0.1")

    # rule 1: a hidden item is absent on the viewer's read, counted in the stored figure
    with pw.hidden(a):
        seen = pw.earned(iwp, lowest)
    ok(
        "a hidden item is absent from the viewer's read",
        a not in {i.item_id for i in seen.items} and "some items not shown" in seen.notes,
    )
    ok(
        "the viewer's figure equals the stored figure (rule 1)",
        str(seen.pct) == pw.pct(iwp) == "31.7",
    )
    with pw.hidden(a):
        refuses(RecordNotFoundError, lambda: pw.earned("0" * 26, lowest))

    # rule 2: null est_hours weighs the mean; all null weigh 1
    nulls, (n1, n2, n3) = pw.package(["10.0", "30.0", "20.0"])
    pw.set_hours(n3, None)
    pw.move("InstallScopeItem", n3)  # 60 on a weight of the mean, 20
    ok(
        "a null weighs the mean of the others (rule 2)",
        str(pw.earned(nulls).pct) == "20.0"
        and "hours missing on 1 items" in pw.earned(nulls).notes,
    )
    for item in (n1, n2):
        pw.set_hours(item, None)
    ok("all null weigh 1 each (rule 2)", str(pw.earned(nulls).pct) == "20.0")

    # rule 3: largest remainder
    parts = engine.largest_remainder(Decimal("10.0"), [Decimal("33"), Decimal("33"), Decimal("34")])
    ok(
        "10.0 over 33/33/34 gives 3.3/3.3/3.4 (rule 3)",
        [str(p) for p in parts] == ["3.3", "3.3", "3.4"],
    )
    third = engine.largest_remainder(Decimal("10.0"), [Decimal("1")] * 3)
    ok("a split always sums to the total", sum(third) == Decimal("10.0"))

    # rule 4: PPC
    ok(
        "3 done of 4 is 75.0; none committed is null with a note (rule 4)",
        engine.ppc(3, 4) == (Decimal("75.0"), [])
        and engine.ppc(0, 0) == (None, ["nothing committed"]),
    )

    # an unknown edition refuses
    pw.set_edition("co.acme.nope@9.9.9")
    with open_uow(w.db, readonly=True) as uow:
        refuses(errors.RulesOfCreditError, lambda: engine.edition_for(uow.conn(), SCOPE))
    ok("a project setting to an unknown edition refuses")
    pw.set_edition("")

    # an unknown record_state type adds a note, never an error (the weld rule names awp.Weld)
    welds, (w1, w2) = pw.package(["10.0", "10.0"])
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_awp_scope_item SET commodity = 'weld' WHERE id = :i"), {"i": w1}
        )
    pw.move("InstallScopeItem", w2)
    seen_welds = pw.earned(welds)
    ok(
        "an unknown record_state type is skipped with a note and no error",
        engine.NOTE_NO_TYPE in seen_welds.notes and str(seen_welds.pct) == "30.0",
    )

    # Installed twice refused by the workflow; a stale version refused
    refuses(ServiceError, lambda: pw.move("InstallScopeItem", a))
    stale = w.version(d)
    pw.move("InstallScopeItem", d)
    refuses(
        errors.StaleVersionError,
        lambda: w.call("uma", "ReturnScopeItem", record_id=d, expected_version=stale),
    )
    ok("Installed twice and a stale expected_version are refused")

    # ProgressRecorded once per change, none on a no-op
    before = pw.count(iwp)
    pw.manual(iwp, c)
    ok("a manual entry that changes nothing writes no event", pw.count(iwp) == before)

    # manual entries move the figure
    pw.manual(iwp, c, done=False)
    ok("manual entries move the figure", pw.pct(iwp) != "none" and pw.count(iwp) == before + 1)

    # start and complete
    pw.w.set_status(iwp, "Issued")
    pw.raise_blocking(iwp, "complete")
    pw.field("StartIwpWork", iwp)
    ok("StartIwpWork moves Issued to In progress", w.state(iwp) == "In progress")
    refuses(ServiceError, lambda: pw.field("CompleteIwpField", iwp))
    ok(
        "CompleteIwpField is refused while a blocking constraint is open",
        w.state(iwp) == "In progress",
    )
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_constraint SET severity = 'advisory' WHERE subject_id = :i"),
            {"i": iwp},
        )
    pw.field("CompleteIwpField", iwp)
    ok("CompleteIwpField completes and writes a last figure", w.state(iwp) == "Field complete")

    # an agent proposes progress; only a person holding the word accepts
    prop_iwp, (p1,) = pw.package(["10.0"])
    command = RecordManualProgress(
        actor="agent:bot",
        source="mcp:bot",
        scope=SCOPE,
        iwp_id=prop_iwp,
        steps=[{"scope_item_id": p1, "step": "Material received", "done": True}],  # type: ignore[list-item]
        expected_version=w.version(prop_iwp),
    )
    with open_uow(w.db) as uow:
        filed = proposals.propose(
            uow, tool="propose_progress", agent="agent:bot", command=command, summary="Material in"
        )

    def accept(by: str) -> Any:
        with open_uow(w.db) as uow:
            holder = holder_for_actor(uow.conn(), f"user:{by}")
            return proposals.accept_proposal(
                uow, proposal_id=filed.proposal_id, by=f"user:{by}", holder=holder
            )

    refuses(ProposalAccessError, lambda: accept("vera"))
    ok("a person without awp.progress.record cannot accept", pw.pct(prop_iwp) == "none")
    accept("uma")
    ok("a person holding the word accepts the proposal", pw.pct(prop_iwp) == "30.0")
    refuses(
        ForbiddenError, lambda: w.call("vera", "InstallScopeItem", record_id=p1, expected_version=1)
    )

    # rebuild equality for this module's tables
    before_rows = pw.snapshot()
    pw.rebuild()
    ok("a rebuild equals the progress and week tables", pw.snapshot() == before_rows)
