"""A ledger and the people who act on it, for the scaffold tests and the S1 acceptance script.

``ada`` (admin), ``uma`` (user: registers, designs, erects, inspects, releases), ``rob`` (user: no
grant), ``sue`` (superuser of scaffold and of requisitions: tags green, approves requests), ``dora``
(the document controller: reads restricted records) and ``vera`` (a viewer). Commands run as a
person would run them: the access word is checked first (``require_command_access``), then the
intent (``check_intent``), then the handler as that person's viewer, one unit of work each, as
the API dispatcher does. A restricted record is made through the correspondence module's own
commands. An IWP is an envelope-only ``awp.IWP`` record moved by ``by_module`` transitions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.intent import check_intent, intent_scope
from tl_core.services.commands import Command
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS
from tl_mod_scaffold.module import SCAFFOLD_COMMANDS
from tl_mod_scaffold.names import SCAFFOLD, SCAFFOLD_TABLE

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
SPEC = {c.model.__name__: c for c in (*SCAFFOLD_COMMANDS, *REQUISITIONS_COMMANDS)}
IWP = "awp.IWP"
#: The transitions from Draft to each IWP state the tests need.
IWP_PATH = {
    "Draft": [],
    "Ready": ["develop", "check_constraints", "ready"],
    "Issued": ["develop", "check_constraints", "ready", "issue"],
    "In progress": ["develop", "check_constraints", "ready", "issue", "start"],
    "On hold": ["develop", "check_constraints", "ready", "issue", "hold"],
    "Field complete": ["develop", "check_constraints", "ready", "issue", "start", "complete"],
    "Closed": ["develop", "check_constraints", "ready", "issue", "start", "complete", "close"],
}
SCAFFOLD_REQUEST = {
    "kind": "scaffold",
    "subject": "Scaffold at unit 4",
    "purpose": "Access to the valve",
    "elevation": "+12.0",
    "gridline": "C-4",
    "load_class": "Light",
    "duration_days": 14,
}


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    # --- people and data -------------------------------------------------------------------

    def person(
        self, name: str, roles: tuple[str, ...], grants: dict[str, str] | None = None
    ) -> None:
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
        for module, role in (grants or {}).items():
            with open_uow(self.db) as uow:
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:ada",
                        source="test",
                        account_id=view.account_id,
                        project=SCOPE,
                        module=module,
                        role=role,
                        reason="test",
                    ),
                )

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("uma", ("user",))
        self.person("rob", ("user",))
        self.person("sue", ("user",), {"scaffold": "superuser", "requisitions": "superuser"})
        self.person("dora", ("user", "document_controller"), {"scaffold": "superuser"})
        self.person("vera", ("user",), {"scaffold": "viewer"})

    def record(self, record_type: str, key: str, scope: str = SCOPE) -> str:
        """An envelope-only record of another module's type: its id."""
        cmd = Command(actor="user:uma", source="test", scope=scope)
        with open_uow(self.db) as uow:
            return create_module_record(
                uow, cmd, record_type=record_type, title=key, key=key
            ).stream_id

    def iwp(self, key: str, state: str = "Draft") -> str:
        """An IWP in ``state``, moved there by ``by_module`` workflow transitions."""
        made = self.record(IWP, key)
        for transition in IWP_PATH[state]:
            with open_uow(self.db) as uow:
                handle_transition_workflow(
                    uow,
                    TransitionWorkflow(
                        actor="user:uma",
                        source="test",
                        scope=SCOPE,
                        stream_id=made,
                        expected_version=self.version(made),
                        transition=transition,
                    ),
                    by_module=True,
                )
        return made

    def require(self, iwp: str, scaffold: str) -> None:
        """A live ``requires`` link from the IWP to the scaffold."""
        with cf.system_view(), open_uow(self.db) as uow:
            handle_add_link(
                uow,
                AddLink(
                    actor="user:uma",
                    source="test",
                    scope=SCOPE,
                    from_id=iwp,
                    to_id=scaffold,
                    relation="requires",
                ),
                by_module=True,
            )

    def hidden_record(self) -> str:
        """The id of a restricted correspondence item (the lowest viewer cannot read it)."""
        cmd = Command(actor="user:dora", source="test", scope=SCOPE)
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
        """Run command ``name`` as ``who`` the way the dispatcher does: access, intent, handler,
        reading as that person's viewer."""
        spec = SPEC[name]
        cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
        with open_uow(self.db) as uow:
            conn = uow.conn()
            require_command_access(conn, cmd)
            viewer = cf.viewer_for_actor(conn, cmd.actor)
            cmd = check_intent(cmd, conn, viewer)
            with cf.use_viewer(viewer), intent_scope(cmd.intent):
                return spec.handler(uow, cmd)

    def request(self, *, approve: bool = True, **more: Any) -> str:
        """A scaffold request raised by uma (and approved by sue unless ``approve`` is False)."""
        body = {**SCAFFOLD_REQUEST, **more.pop("body", {})}
        rid = str(self.call("uma", "RaiseRequisition", requisition=body, **more).stream_id)
        if approve:
            self.call(
                "sue", "ApproveRequisition", requisition=rid, expected_version=self.version(rid)
            )
        return rid

    def register(self, request: str | None = None, who: str = "uma", **more: Any) -> str:
        """A scaffold registered from ``request`` (a new approved one by default): its id."""
        rid = request or self.request()
        made = self.call(who, "RegisterScaffold", request_id=rid, title="Scaffold A", **more)
        return str(made.stream_id)

    def advance_as(self, scaffold: str, to: str, who: str) -> str:
        """Design and erect (as ``who``) up to ``Designed`` or ``Erecting``."""
        self.call(who, "DesignScaffold", scaffold=scaffold)
        if to == "Erecting":
            self.call(who, "ErectScaffold", scaffold=scaffold)
        return scaffold

    def advance(self, scaffold: str, to: str) -> str:
        """Drive a Requested scaffold to ``Designed``, ``Erecting``, ``Inspected`` or ``In Use``."""
        steps = ["Designed", "Erecting", "Inspected", "In Use"]
        for step in steps[: steps.index(to) + 1]:
            if step == "Designed":
                self.call("uma", "DesignScaffold", scaffold=scaffold)
            elif step == "Erecting":
                self.call("uma", "ErectScaffold", scaffold=scaffold)
            elif step == "Inspected":
                self.call("sue", "TagScaffoldGreen", scaffold=scaffold)
            else:
                self.call("uma", "ReleaseScaffold", scaffold=scaffold)
        return scaffold

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str) -> str:
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record)
        return "Requested" if found is None else str(found)

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    def row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {SCAFFOLD_TABLE} WHERE id = :i", i=record)[0]

    def event_types(self, record: str) -> list[str]:
        return [
            str(r["event_type"])
            for r in self.rows(
                "SELECT event_type FROM events WHERE stream_id = :i ORDER BY seq", i=record
            )
        ]

    def count(self, table: str = "events") -> int:
        return int(self.scalar(f"SELECT count(*) FROM {table}"))


__all__ = ["IWP", "SCAFFOLD", "SCOPE", "World"]
