"""A ledger and the people who act on it, for the awp module tests.

``ada`` (admin), ``vera`` (viewer by a grant), ``uma`` (the derived role: user) and ``sue`` (the awp
superuser). Commands run as a person would run them: the access word is checked first
(``require_command_access``), then the handler, one unit of work each.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.common import record_key
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_cost.testing import CostWorld, row
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
ROOT = Path(__file__).resolve().parents[4]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"
SPEC = {c.model.__name__: c for c in AWP_COMMANDS}
WBS, CWA, EWP, PWP = "awp.WBSNode", "awp.CWA", "awp.EWPRef", "awp.PWPRef"
COST = "cost.CostCode"


def line(cost_code: str, percent: str) -> dict[str, str]:
    return {"cost_code": cost_code, "percent": percent}


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    # --- people and data -------------------------------------------------------------------

    def person(self, name: str, roles: tuple[str, ...], grant: str | None = None) -> None:
        with open_uow(self.db) as uow:
            view = accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=list(roles),
                password=prepare_password(PASSWORD, username=name),
                by="svc:test",
            )
        if grant is not None:
            with open_uow(self.db) as uow:
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:ada",
                        source="test",
                        account_id=view.account_id,
                        project=SCOPE,
                        module="awp",
                        role=grant,
                        reason="test",
                    ),
                )

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("vera", ("user",), grant="viewer")
        self.person("uma", ("user",))
        self.person("sue", ("user",), grant="superuser")

    def editions(self) -> None:
        """The standards editions the lists come from (Discipline, units, the awp lists)."""
        with use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")):
            for name in ("co.acme.standards@1.0.0.yaml", "co.acme.awp@1.0.0.yaml"):
                doc = load_standards_file(STANDARDS / name)
                with open_uow(self.db) as uow:
                    load_standards(uow, doc, actor="user:seed", source="test")

    def cost_codes(self, *codes: tuple[str, str]) -> None:
        CostWorld(self.db).import_snapshot([row(code, name) for code, name in codes])

    # --- commands and reads ----------------------------------------------------------------

    def call(self, who: str, name: str, **fields: Any) -> Any:
        spec = SPEC[name]
        cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
        with open_uow(self.db) as uow:
            require_command_access(uow.conn(), cmd)
            return spec.handler(uow, cmd)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def id_of(self, code: str, kind: str = WBS) -> str:
        """The id of the record of ``kind`` with the typed ``code`` (awp keys are namespaced)."""
        return str(
            self.scalar(
                "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k",
                s=SCOPE,
                k=record_key(kind, code),
            )
        )

    def state(self, record: str) -> str:
        return str(
            self.scalar(
                "SELECT COALESCE(status, 'Planned') FROM cur_core_record WHERE id = :i", i=record
            )
        )

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    # --- IWP and scope pieces (P2-I2 S2) ---------------------------------------------

    def iwp(self, title: str = "Rack", discipline: str = "PIP", **more: Any) -> str:
        """A new IWP made by the user ``uma`` (the id)."""
        made = self.call("uma", "CreateIwp", discipline=discipline, title=title, **more)
        return str(made.stream_id)

    def items(self, hours: list[str], **more: Any) -> list[str]:
        """One new scope item per entry of ``hours`` (the ids)."""
        return [
            str(
                self.call(
                    "uma",
                    "CreateScopeItem",
                    commodity="piping",
                    description=f"Spool {n}",
                    qty="1",
                    uom="m",
                    est_hours=h,
                    **more,
                ).stream_id
            )
            for n, h in enumerate(hours)
        ]

    def column(self, table: str, column: str, record: str) -> Any:
        """One column of the typed or envelope row of ``record``."""
        return self.scalar(f"SELECT {column} FROM {table} WHERE id = :i", i=record)

    def set_status(self, record: str, status: str | None) -> None:
        """Set the workflow state of a record by hand (a projection write, never an event)."""
        with open_uow(self.db) as uow:
            uow.conn().execute(
                text("UPDATE cur_core_record SET status = :s WHERE id = :i"),
                {"s": status, "i": record},
            )

    def module_call(self, function: Callable[..., Any], **fields: Any) -> Any:
        """Run a plain function of the module as the module would."""
        cmd = Command(actor="user:uma", source="test", scope=SCOPE)
        with open_uow(self.db) as uow:
            return function(uow, cmd, **fields)

    def documents(self, objects: Path, *numbers: str) -> dict[str, str]:
        """Documents with an issued revision ``A`` (the ids by number)."""
        from tl_mod_documents.testing import DocumentsWorld

        docs = DocumentsWorld(self.db, objects)
        docs.people("u")
        for number in numbers:
            docs.register(number)
            docs.create_revision(number)
            docs.attach(number, "A")
            docs.issue(number, "A")
        return {n: str(docs.document(n).id) for n in numbers}

    # --- seed pieces -----------------------------------------------------------------------

    def wbs_tree(self) -> None:
        """3 levels, 6 leaves: 1 > (1.1, 1.2) > (1.1.1 .. 1.1.3, 1.2.1 .. 1.2.3)."""
        self.call("sue", "DefineWbsNode", code="1", title="Plant")
        for mid in ("1.1", "1.2"):
            self.call("sue", "DefineWbsNode", code=mid, title=f"Unit {mid}", parent_code="1")
            for n in (1, 2, 3):
                code = f"{mid}.{n}"
                self.call("sue", "DefineWbsNode", code=code, title=f"Area {code}", parent_code=mid)

    def areas_and_path(self, codes: tuple[str, ...] = ("A1", "A2", "A3", "A4")) -> None:
        for code in codes:
            self.call("uma", "DefineCwa", code=code, title=f"Area {code}", location_text="North")
        self.call("sue", "DefinePathOfConstruction", steps=[{"cwa_code": c} for c in codes])

    def new_cwp(self, discipline: str, title: str, cwa: str, **more: Any) -> str:
        made = self.call(
            "uma", "CreateCwp", discipline=discipline, title=title, cwa_code=cwa, **more
        )
        return str(made.stream_id)

    def full_cwp(self, discipline: str, title: str, cwa: str, node: str, hours: str) -> str:
        """A package that meets every precondition of a release, still Planned."""
        cwp = self.new_cwp(
            discipline,
            title,
            cwa,
            planned_start="2026-11-02",
            planned_finish="2027-01-29",
            budget_hours=hours,
        )
        self.call(
            "uma",
            "AllocateCwpToWbs",
            cwp=cwp,
            allocations=[{"wbs_code": node, "percent": "100.00"}],
        )
        return cwp

    def seed(self) -> dict[str, str]:
        """WBS (3 levels, 6 leaves, two mapped), 4 CWAs, path v1, 6 CWPs in 3 states.

        Returns the CWP ids by title.
        """
        self.cost_codes(
            ("4210-PIP-WLD", "Welding"),
            ("4210-PIP-ERC", "Erection"),
            ("4210-PIP-TST", "Test"),
            ("4210-CIV-CON", "Concrete"),
        )
        self.wbs_tree()
        self.call(
            "sue",
            "MapWbsToCostCodes",
            node=self.id_of("1.1.1"),
            allocations=[line("4210-PIP-WLD", "60.00"), line("4210-PIP-ERC", "40.00")],
        )
        self.call(
            "sue",
            "MapWbsToCostCodes",
            node=self.id_of("1.2.1"),
            allocations=[line("4210-CIV-CON", "100.00")],
        )
        self.areas_and_path()
        plan = [  # discipline, title, area, node, hours, how far it goes
            ("PIP", "Rack 12 piping", "A1", "1.1.1", "4200", "released"),
            ("PIP", "Rack 13 piping", "A1", "1.1.2", "1800", "released"),
            ("PIP", "Rack 14 piping", "A2", "1.1.3", "950", "development"),
            ("CIV", "Foundations unit 2", "A3", "1.2.1", "3100", "development"),
            ("CIV", "Slab unit 2", "A3", "1.2.2", "640", "planned"),
            ("PIP", "Tie-ins", "A4", "1.2.3", "400", "planned"),
        ]
        ids: dict[str, str] = {}
        for discipline, title, area, node, hours, goal in plan:
            cwp = self.full_cwp(discipline, title, area, node, hours)
            ids[title] = cwp
            if goal in ("development", "released"):
                self.call("uma", "StartCwpDevelopment", cwp=cwp)
            if goal == "released":
                self.call("sue", "ReleaseCwp", cwp=cwp, expected_version=self.version(cwp))
        return ids


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    """Run ``call`` and return the ``error`` it raises; fail the test otherwise."""
    try:
        call()
    except error as exc:
        return exc
    raise AssertionError(f"expected {error.__name__}")


def hidden_record(w: World) -> str:
    """The id of a restricted correspondence item (the lowest-clearance viewer cannot read it)."""
    cmd = Command(actor="user:sue", source="test", scope=SCOPE)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(w.db) as uow:
        made = create_item(
            uow,
            cmd,
            subject="Secret",
            direction="in",
            medium="letter",
            received_via="manual",
            to=[Recipient(name="Someone")],
            body="Body",
            confidentiality="restricted",
            received_on="2026-10-19",
            received=True,
        )
    return str(made.stream_id)


def link_activity(w: World, cwp: str, tmp: Path) -> str:
    """Publish a schedule and link its first activity to ``cwp``; returns the ActivityRef id."""
    from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
    from tl_mod_schedule.testing import ScheduleWorld
    from tl_xer.synth import make_xer, week_pair

    SCHEDULE_BASE["actor"] = "user:sue"  # an account, so the schedule words are read for her
    sw = ScheduleWorld(w.db, tmp / "objects")
    sw.define()
    first, _ = week_pair()
    snapshot = sw.upload(make_xer(first))
    sw.publish(snapshot)
    activity = sw.activities(snapshot)[0].activity_id
    made = sw.link(cwp, activity)
    return str(sw.link_row(made.stream_id)["to_id"])
