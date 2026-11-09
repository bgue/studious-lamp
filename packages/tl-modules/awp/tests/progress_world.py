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
from tl_core import modules as core_modules
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor
from tl_core.constraints.commands import RaiseConstraint
from tl_core.constraints.handlers import handle_raise_constraint
from tl_core.modules import ConfidentialSource
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError, RecordNotFoundError, ServiceError
from tl_core.settings.service import set_setting
from tl_mod_awp import errors
from tl_mod_awp.commands import CommitIwpToWeek, RecordManualProgress
from tl_mod_awp.names import SCOPE_ITEM, WEEKLY_PLAN
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
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[attr-defined]


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


# --- weekly plan (P2-I5 S4a) ------------------------------------------------------------------

WEEK_PLAN_TABLES = (("cur_awp_weekly_plan", "id"), ("cur_awp_week_commitment", "row_id"))
OTHER_SCOPE = "project:P999"


class WeekWorld:
    """Weekly plan helpers over a ``ProgressWorld``: Issued IWPs, plans, commitments, outcomes."""

    def __init__(self, pw: ProgressWorld) -> None:
        self.pw = pw
        self.w = pw.w

    def standards(self) -> None:
        """The second awp edition: it holds the code list ``MissReason``."""
        from awp_world import ROOT, STANDARDS
        from tl_core.schema_provider import DirectorySchemaProvider, use_provider
        from tl_mod_engineering.document import load_standards_file
        from tl_mod_engineering.loader import load_standards

        with use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")):
            doc = load_standards_file(STANDARDS / "co.acme.awp@1.1.0.yaml")
            with open_uow(self.w.db) as uow:
                load_standards(uow, doc, actor="user:seed", source="test")

    def issued(self, state: str = "Issued", foreman: str | None = "user:uma") -> str:
        """An IWP in ``state`` (set by hand: a projection write, as the S2 checks do)."""
        iwp = self.w.iwp(planned_start="2026-12-01", foreman=foreman) if foreman else self.w.iwp()
        self.w.set_status(iwp, state)
        return iwp

    def open(self, day: str = "2026-11-02", who: str = "uma") -> str:
        from datetime import date

        return str(self.w.call(who, "OpenWeeklyPlan", week_start=date.fromisoformat(day)).stream_id)

    def commit(
        self, plan: str, iwp: str, hours: str = "40.0", who: str = "uma", **more: Any
    ) -> Any:
        return self.w.call(
            who,
            "CommitIwpToWeek",
            plan_id=plan,
            iwp_id=iwp,
            committed_hours=hours,
            expected_version=self.w.version(plan),
            **more,
        )

    def outcome(
        self, plan: str, iwp: str, outcome: str, reason: str | None = None, who: str = "uma"
    ) -> Any:
        return self.w.call(
            who,
            "RecordWeekOutcome",
            plan_id=plan,
            iwp_id=iwp,
            outcome=outcome,
            miss_reason=reason,
            expected_version=self.w.version(plan),
        )

    def close(self, plan: str, who: str = "sue") -> Any:
        return self.w.call(who, "CloseWeek", plan_id=plan, expected_version=self.w.version(plan))

    def plan_row(self, plan: str) -> dict[str, Any]:
        return self.w.rows("SELECT * FROM cur_awp_weekly_plan WHERE id = :i", i=plan)[0]

    def commitments(self, plan: str) -> list[dict[str, Any]]:
        return self.w.rows(
            "SELECT * FROM cur_awp_week_commitment WHERE plan_id = :p ORDER BY iwp_id", p=plan
        )

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {t: self.w.rows(f"SELECT * FROM {t} ORDER BY {o}") for t, o in WEEK_PLAN_TABLES}

    @contextmanager
    def hidden_plan(self, plan: str) -> Iterator[None]:
        """The plan is restricted to everyone below a person with clearance (a test source)."""
        with open_uow(self.w.db) as uow:
            conn = uow.conn()
            conn.execute(
                text("CREATE TABLE IF NOT EXISTS pw_plan_class (id TEXT PRIMARY KEY, cls TEXT)")
            )
            conn.execute(text("DELETE FROM pw_plan_class"))
            for row in self.w.rows("SELECT id FROM cur_awp_weekly_plan"):
                cls = "restricted" if row["id"] == plan else "internal"
                conn.execute(
                    text("INSERT INTO pw_plan_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
                )
        source = ConfidentialSource(
            record_types=frozenset({WEEKLY_PLAN}),
            table="pw_plan_class",
            id_column="id",
            class_column="cls",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[attr-defined]

    def other_project_iwp(self) -> str:
        """An Issued IWP of another project (made as the module would, by its own command)."""
        from tl_mod_awp.commands import CreateIwp
        from tl_mod_awp.handlers.iwp import handle_create_iwp

        cmd = CreateIwp(
            actor="user:sue", source="test", scope=OTHER_SCOPE, discipline="PIP", title="Other"
        )
        with open_uow(self.w.db) as uow:
            made = handle_create_iwp(uow, cmd)
        self.w.set_status(made.stream_id, "Issued")
        return str(made.stream_id)


def build_week_world(w: World) -> WeekWorld:
    """A ``WeekWorld`` over a ``World`` that already has its people and editions."""
    ww = WeekWorld(ProgressWorld(w))
    ww.standards()
    return ww


def build_week(db: Path) -> WeekWorld:
    ww = WeekWorld(build(db))
    ww.standards()
    return ww


def week_checks(ww: WeekWorld) -> None:
    from datetime import date

    from tl_mod_awp.week_views import week_detail

    w = ww.w
    plan = ww.open("2026-11-04")  # a Wednesday: its Monday is 2026-11-02
    refuses(errors.WeekRuleError, lambda: ww.open("2026-11-02"))
    ok("a second open of the same week is refused")
    row = ww.plan_row(plan)
    ok("a week of 2026-11-04 is 2026-W45 from Monday 2026-11-02", row["week"] == "2026-W45")
    ok(
        "the key is composed from the week",
        w.column("cur_core_record", "key", plan) == "P123-WK-2026W45",
    )
    ok("a new plan is Draft", w.state(plan) in ("Draft", "Planned"))

    a, b, c, d = (ww.issued() for _ in range(4))
    ww.commit(plan, a, "40.0")
    ok("a commit moves the plan to Committed", w.state(plan) == "Committed")
    ready = ww.issued("Ready")
    refuses(errors.WeekStateError, lambda: ww.commit(plan, ready))
    far = ww.other_project_iwp()
    refuses(RecordNotFoundError, lambda: ww.commit(plan, far))
    ok("a Ready IWP and an IWP of another project are refused", len(ww.commitments(plan)) == 1)
    ww.commit(plan, a, "32.5")
    rows = ww.commitments(plan)
    ok(
        "a re-commit replaces the hours (one row)",
        len(rows) == 1 and rows[0]["committed_hours"] == "32.5",
    )
    stale = w.version(plan)
    ww.commit(plan, b)
    refuses(
        errors.StaleVersionError,
        lambda: w.call(
            "uma",
            "CommitIwpToWeek",
            plan_id=plan,
            iwp_id=c,
            committed_hours="8.0",
            expected_version=stale,
        ),
    )
    ok("a stale expected_version is refused", len(ww.commitments(plan)) == 2)
    ww.commit(plan, c)
    ww.commit(plan, d)

    refuses(errors.WeekRuleError, lambda: ww.outcome(plan, a, "missed"))
    refuses(errors.WeekRuleError, lambda: ww.outcome(plan, a, "missed", "NoSuchReason"))
    refuses(errors.WeekRuleError, lambda: ww.outcome(plan, a, "done", "Weather"))
    ok(
        "missed without a reason, with an unknown reason, and done with a reason are refused",
        all(r["outcome"] is None for r in ww.commitments(plan)),
    )
    ww.outcome(plan, a, "done")
    refuses(errors.WeekRuleError, lambda: ww.close(plan))
    ok("a close with an unjudged commitment is refused", w.state(plan) == "Committed")
    ww.outcome(plan, b, "done")
    ww.outcome(plan, c, "done")
    ww.outcome(plan, d, "missed", "Weather")
    refuses(ForbiddenError, lambda: ww.close(plan, who="uma"))
    ok("a plain user cannot close (awp.week.close)", w.state(plan) == "Committed")
    ww.close(plan)
    ok(
        "3 done of 4 closes at 75.0 and the plan is Closed",
        ww.plan_row(plan)["ppc"] == "75.0" and w.state(plan) == "Closed",
    )
    refuses(errors.WeekStateError, lambda: ww.commit(plan, a))
    refuses(errors.WeekStateError, lambda: ww.outcome(plan, a, "done"))
    refuses(errors.WeekStateError, lambda: ww.close(plan))
    ok("a command on a Closed plan is refused", True)

    empty = ww.open("2026-11-09")
    refuses(errors.WeekRuleError, lambda: ww.close(empty))
    ok("a close of an empty plan is refused", w.state(empty) != "Closed")

    with open_uow(w.db, readonly=True) as uow:
        seen = week_detail(uow.conn(), plan, cf.Viewer(actor="user:uma", level=1, account="uma"))
        refuses(RecordNotFoundError, lambda: week_detail(uow.conn(), "0" * 26, cf.Viewer()))
    ok(
        "week_detail reads the plan with its commitments and ppc",
        seen.ppc == "75.0" and len(seen.commitments) == 4,
    )
    with ww.hidden_plan(plan):
        with open_uow(w.db, readonly=True) as uow:
            refuses(RecordNotFoundError, lambda: week_detail(uow.conn(), plan, cf.Viewer()))
    ok("a viewer who cannot open the plan gets not-found from week_detail")

    # an agent proposes a commitment; only a person holding awp.week.commit accepts
    plan2 = ww.open("2026-11-16")
    e = ww.issued()
    command = CommitIwpToWeek(
        actor="agent:bot",
        source="mcp:bot",
        scope=SCOPE,
        plan_id=plan2,
        iwp_id=e,
        committed_hours="12.0",
        expected_version=w.version(plan2),
    )
    with open_uow(w.db) as uow:
        filed = proposals.propose(
            uow,
            tool="propose_week_commitment",
            agent="agent:bot",
            command=command,
            summary="Commit",
        )

    def accept(by: str) -> Any:
        with open_uow(w.db) as uow:
            holder = holder_for_actor(uow.conn(), f"user:{by}")
            return proposals.accept_proposal(
                uow, proposal_id=filed.proposal_id, by=f"user:{by}", holder=holder
            )

    refuses(ProposalAccessError, lambda: accept("vera"))
    ok("a person without awp.week.commit cannot accept", not ww.commitments(plan2))
    accept("uma")
    ok("a person holding awp.week.commit accepts the proposal", len(ww.commitments(plan2)) == 1)

    before = ww.snapshot()
    pw_rebuild = ww.pw.rebuild
    pw_rebuild()
    ok("a rebuild equals the weekly plan tables, ppc included", ww.snapshot() == before)
    _ = date


# --- progress rollup and export (P2-I5 S3) -----------------------------------------------------


class RollRig:
    """CWPs with IWPs and a stored progress figure each, over the seed WBS tree.

    The rows of ``cur_awp_iwp_progress`` are put in by hand (a projection write) so a figure is
    exact; ``rebuild`` tests use the real commands instead. Nothing here writes ``cur_cost_*``.
    """

    def __init__(self, pw: ProgressWorld) -> None:
        self.pw = pw
        self.w = pw.w
        self.ids: dict[str, str] = {}
        w = self.w
        w.cost_codes(("4210-PIP-WLD", "Welding"), ("4210-PIP-ERC", "Erection"))
        w.wbs_tree()
        w.areas_and_path(("A1",))

    def cwp(self, hours: str, allocs: Sequence[tuple[str, str]]) -> str:
        cwp = self.w.new_cwp(
            "PIP",
            f"Package {hours}",
            "A1",
            planned_start="2026-11-02",
            planned_finish="2027-01-29",
            budget_hours=hours,
        )
        self.w.call(
            "uma",
            "AllocateCwpToWbs",
            cwp=cwp,
            allocations=[{"wbs_code": c, "percent": p} for c, p in allocs],
        )
        return cwp

    def map_codes(self, node: str, *lines: tuple[str, str]) -> None:
        from awp_world import line

        self.w.call(
            "sue",
            "MapWbsToCostCodes",
            node=self.w.id_of(node),
            allocations=[line(c, p) for c, p in lines],
        )

    def iwp(self, cwp: str, hours: Sequence[str | None], pct: str | None) -> str:
        """An IWP of ``cwp`` with one item per entry of ``hours`` (None: no estimate) and the
        stored figure ``pct`` (None: no stored row)."""
        iwp, items = self.pw.package([h or "1.0" for h in hours], cwp_id=cwp)
        for item, h in zip(items, hours, strict=True):
            if h is None:
                self.pw.set_hours(item, None)
        if pct is not None:
            with open_uow(self.w.db) as uow:
                uow.conn().execute(
                    text(
                        "INSERT INTO cur_awp_iwp_progress (iwp_id, scope, earned_pct, edition, "
                        "as_of_seq, last_seq) VALUES (:i, :s, :p, 'co.acme.awp@1.1.0', 1, 1)"
                    ),
                    {"i": iwp, "s": SCOPE, "p": pct},
                )
        return iwp

    def run_rollup(self) -> None:
        """Store the budget rollup (the awp job), so budget figures exist."""
        from tl_mod_awp import rollup
        from tl_mod_awp.worker import build_worker

        with open_uow(self.w.db) as uow:
            rollup.request(uow, SCOPE)
        with build_worker(self.w.db) as wk:
            wk.runner.run_once()

    def read(self, viewer: cf.Viewer | None = None) -> Any:
        from tl_mod_awp.progress.rollup import progress_rollup

        with open_uow(self.w.db, readonly=True) as uow:
            return progress_rollup(uow.conn(), SCOPE, viewer=viewer)

    def export(self, period: str = "2026-W45", viewer: cf.Viewer | None = None) -> str:
        from tl_mod_awp.progress.export import export_progress

        with open_uow(self.w.db, readonly=True) as uow:
            return export_progress(uow.conn(), SCOPE, period, viewer=viewer)

    def counts(self) -> tuple[int, int, int]:
        """Rows of ``cur_cost_*`` tables, and the ledger head: an export changes neither."""
        names = [
            str(r["name"])
            for r in self.w.rows(
                "SELECT name FROM sqlite_master WHERE name LIKE 'cur\\_cost\\_%' ESCAPE '\\'"
            )
        ]
        rows = sum(int(self.w.scalar(f"SELECT COUNT(*) FROM {n}")) for n in names)
        stored = int(self.w.scalar("SELECT COUNT(*) FROM cur_awp_rollup"))
        return rows, stored, int(self.w.scalar("SELECT COALESCE(MAX(seq), 0) FROM events"))

    @contextmanager
    def hidden(self, *ids: str, record_type: str) -> Iterator[None]:
        """``ids`` of ``record_type`` are restricted: the lowest viewer cannot open them."""
        with open_uow(self.w.db) as uow:
            conn = uow.conn()
            conn.execute(
                text("CREATE TABLE IF NOT EXISTS pw_roll_class (id TEXT PRIMARY KEY, cls TEXT)")
            )
            conn.execute(text("DELETE FROM pw_roll_class"))
            for row in self.w.rows("SELECT id FROM cur_core_record WHERE type = :t", t=record_type):
                cls = "restricted" if row["id"] in ids else "internal"
                conn.execute(
                    text("INSERT INTO pw_roll_class VALUES (:i, :c)"), {"i": row["id"], "c": cls}
                )
        source = ConfidentialSource(
            record_types=frozenset({record_type}),
            table="pw_roll_class",
            id_column="id",
            class_column="cls",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[attr-defined]


def build_roll(db: Path) -> RollRig:
    return roll_on(build(db))


def roll_on(pw: ProgressWorld) -> RollRig:
    """Worked scenario: package A (40 h: IWPs 10, 10, 20 h at 50.0, 100.0, 25.0 percent) on leaf
    1.1.1 mapped 60/40 to two cost codes; package B (10.0 earned) split 33/33/34 over three
    unmapped leaves; package C (a null hour weighs the mean) on 1.1.2. ``rr.ids`` names them."""
    rr = RollRig(pw)
    rr.map_codes("1.1.1", ("4210-PIP-WLD", "60.00"), ("4210-PIP-ERC", "40.00"))
    a = rr.cwp("40.0", [("1.1.1", "100.00")])
    a1, a2, a3 = (
        rr.iwp(a, ["10.0"], "50.0"),
        rr.iwp(a, ["10.0"], "100.0"),
        rr.iwp(a, ["20.0"], "25.0"),
    )
    b = rr.cwp("10.0", [("1.2.1", "33.00"), ("1.2.2", "33.00"), ("1.2.3", "34.00")])
    b1 = rr.iwp(b, ["10.0"], "100.0")
    c = rr.cwp("20.0", [("1.1.2", "100.00")])
    c1 = rr.iwp(c, ["10.0", None], "50.0")
    rr.ids.update(a=a, a1=a1, a2=a2, a3=a3, b=b, b1=b1, c=c, c1=c1)
    return rr
