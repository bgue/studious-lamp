"""A ledger and the people who act on it, for the requisitions tests and ``dev/accept/P2-I4A/S2.py``.

``ada`` (admin), ``uma`` (user: raises requests), ``rob`` (user: another requester, may not approve)
and ``sue`` (the requisitions superuser: approves). Commands run as a person would run them: the
access word is checked first (``require_command_access``), then the intent (``check_intent``), then
the handler, one unit of work each, as the API dispatcher does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.intent import check_intent, intent_scope
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS
from tl_mod_requisitions.names import KINDS, TABLES

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
ROOT = Path(__file__).resolve().parents[4]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"
SPEC = {c.model.__name__: c for c in REQUISITIONS_COMMANDS}
IWP, CWP = "awp.IWP", "awp.CWP"

LABOR = {
    "kind": "labor",
    "subject": "Six pipefitters",
    "craft": "Pipefitter",
    "headcount": 6,
    "start_date": "2026-11-02",
    "end_date": "2026-11-13",
}


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
                        module="requisitions",
                        role=grant,
                        reason="test",
                    ),
                )

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("uma", ("user",))
        self.person("rob", ("user",))
        self.person("sue", ("user",), grant="superuser")

    def editions(self) -> None:
        """The standards editions the code lists come from (``GeneralRequisitionType``)."""
        with use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")):
            for name in ("co.acme.standards@1.0.0.yaml", "co.acme.awp@1.0.0.yaml"):
                doc = load_standards_file(STANDARDS / name)
                with open_uow(self.db) as uow:
                    load_standards(uow, doc, actor="user:seed", source="test")

    def record(self, record_type: str, key: str, scope: str = SCOPE) -> str:
        """An envelope-only record of another module's type (an IWP, a cost code, an item)."""
        cmd = Command(actor="user:uma", source="test", scope=scope)
        with open_uow(self.db) as uow:
            return create_module_record(
                uow, cmd, record_type=record_type, title=key, key=key
            ).stream_id

    def hidden_record(self) -> str:
        """The id of a restricted correspondence item (the lowest-clearance viewer cannot read it)."""
        cmd = Command(actor="user:sue", source="test", scope=SCOPE)
        with cf.system_view(), frozen_today("2026-10-19"), open_uow(self.db) as uow:
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

    # --- commands and reads ----------------------------------------------------------------

    def call(self, who: str, name: str, **fields: Any) -> Any:
        """Run command ``name`` as ``who`` the way the dispatcher does (access, intent, handler)."""
        spec = SPEC[name]
        cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
        with open_uow(self.db) as uow:
            require_command_access(uow.conn(), cmd)
            cmd = check_intent(cmd, uow.conn(), cf.viewer_for_actor(uow.conn(), cmd.actor))
            with intent_scope(cmd.intent):
                return spec.handler(uow, cmd)

    def raise_labor(self, who: str = "uma", **more: Any) -> str:
        body = {**LABOR, **more.pop("body", {})}
        return str(self.call(who, "RaiseRequisition", requisition=body, **more).stream_id)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str) -> str:
        return str(self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record))

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    def row(self, record_type: str, record: str) -> dict[str, Any]:
        table = TABLES[record_type]
        return self.rows(f"SELECT * FROM {table} WHERE id = :i", i=record)[0]

    def requisition(self, record: str) -> dict[str, Any]:
        for record_type in KINDS.values():
            found = self.rows(f"SELECT * FROM {TABLES[record_type]} WHERE id = :i", i=record)
            if found:
                return found[0]
        raise LookupError(record)

    def work_order_of(self, requisition: str) -> str:
        return str(self.requisition(requisition)["work_order_id"])

    def approved(self, who: str = "uma", approver: str = "sue") -> tuple[str, str]:
        """A labour requisition raised and approved: ``(requisition id, work order id)``."""
        rid = self.raise_labor(who)
        self.call(approver, "ApproveRequisition", requisition=rid, expected_version=self.version(rid))
        return rid, self.work_order_of(rid)

    def scheduled(self) -> tuple[str, str]:
        rid, wid = self.approved()
        self.call(
            "sue",
            "ScheduleWorkOrder",
            work_order=wid,
            expected_version=self.version(wid),
            planned_start="2026-11-02",
            planned_finish="2026-11-13",
        )
        return rid, wid
