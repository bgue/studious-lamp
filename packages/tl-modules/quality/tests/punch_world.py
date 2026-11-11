"""A ledger and the people who act on it, for the quality module tests and the S2 acceptance script.

``ada`` (admin), ``uma`` (user: raises items), ``rob`` (user, and a superuser grant, so he holds
the verify word and the actor rule is what stops him), ``sue`` (the quality superuser by
``grant_module_role``), ``dora`` (the document controller: reads restricted records) and ``vera``
(a viewer). Commands run as a person would run them: the access word is checked first
(``require_command_access``), then the intent (``check_intent``), then the handler as that person's
viewer, one unit of work each, as the API dispatcher does. A restricted record is made through the
correspondence module's own commands, never by a projection write.
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
from tl_core.services.records import create_module_record
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_quality.module import PUNCH_COMMANDS
from tl_mod_quality.names import PUNCH_ITEM, PUNCH_ITEM_TABLE

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
SPEC = {c.model.__name__: c for c in PUNCH_COMMANDS}
IWP = "awp.IWP"


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
                        module="quality",
                        role=grant,
                        reason="test",
                    ),
                )

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("uma", ("user",))
        self.person("rob", ("user",), grant="superuser")
        self.person("sue", ("user",), grant="superuser")
        self.person("dora", ("user", "document_controller"))
        self.person("vera", ("user",), grant="viewer")

    def record(self, record_type: str, key: str, scope: str = SCOPE) -> str:
        """An envelope-only record of another module's type (an IWP, say): its id."""
        cmd = Command(actor="user:uma", source="test", scope=scope)
        with open_uow(self.db) as uow:
            return create_module_record(
                uow, cmd, record_type=record_type, title=key, key=key
            ).stream_id

    def hidden_record(self) -> str:
        """The id of a restricted correspondence item (the lowest viewer cannot read it): an item
        made through ``create_item``, then set restricted by ``handle_set_confidentiality``."""
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
                received_on="2026-10-19",
                received=True,
            )
        with cf.system_view(), frozen_today("2026-10-19"), open_uow(self.db) as uow:
            handle_set_confidentiality(
                uow,
                SetCorrespondenceConfidentiality(
                    actor="user:dora",
                    source="test",
                    scope=SCOPE,
                    stream_id=made.stream_id,
                    to_class="restricted",
                    reason="test",
                ),
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

    def core_call(self, who: str, command: Any) -> Any:
        """Run a core constraint command (``RaiseConstraint``) as ``who``."""
        from tl_core.constraints.commands import command_table

        spec = next(c for c in command_table() if c.model is type(command))
        with open_uow(self.db) as uow:
            conn = uow.conn()
            require_command_access(conn, command)
            with cf.use_viewer(cf.viewer_for_actor(conn, command.actor)):
                return spec.handler(uow, command)

    def advisory(self, record: str, who: str = "sue") -> str:
        """An advisory constraint of phase ``start`` on ``record`` (its id)."""
        from tl_core.constraints.commands import RaiseConstraint

        made = self.core_call(
            who,
            RaiseConstraint(
                actor=f"user:{who}",
                source="test",
                scope=SCOPE,
                subject=record,
                phase="start",
                severity="advisory",
                category="other",
                description="Check the guard",
                owner=f"user:{who}",
            ),
        )
        return str(made.stream_id)

    def raise_item(self, who: str = "uma", subject: str = "Guard missing", **more: Any) -> str:
        """A new punch item (its id)."""
        return str(self.call(who, "RaisePunchItem", subject=subject, **more).stream_id)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str) -> str:
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record)
        return "Open" if found is None else str(found)

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    def row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {PUNCH_ITEM_TABLE} WHERE id = :i", i=record)[0]

    def count(self, table: str = "events") -> int:
        return int(self.scalar(f"SELECT count(*) FROM {table}"))

    def links_from(self, record: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT relation, to_id, source FROM cur_links WHERE from_id = :i "
            "AND status <> 'retracted'",
            i=record,
        )


__all__ = ["IWP", "PUNCH_ITEM", "SCOPE", "World"]
