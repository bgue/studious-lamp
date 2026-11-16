"""A ledger and the people who act on it, for the forms command tests.

``ada`` and ``bea`` (admins: the controllers who publish and review), ``uma`` and ``rob`` (users:
fill forms), ``dora`` (the document controller: reads restricted records) and ``vera`` (a viewer).
Commands run as a person would run them: the access word is checked first
(``require_command_access``), then the intent (``check_intent``), then the handler as that person's
viewer, one unit of work each, as the API dispatcher does. A restricted record is made through
the correspondence module's own commands.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.intent import check_intent, intent_scope
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_forms.module import FORMS_COMMANDS
from tl_mod_forms.names import SUBMISSION_TABLE, TEMPLATE_TABLE

_API_TESTS = str(Path(__file__).resolve().parents[3] / "tl-api" / "tests")
if _API_TESTS not in sys.path:
    sys.path.insert(0, _API_TESTS)

from harness import grant_filing  # noqa: E402

SCOPE = "project:P123"
COMPANY = "company"
PASSWORD = "correct horse battery"
SPEC = {c.model.__name__: c for c in FORMS_COMMANDS}
MARKER = "zq-marker-7731"


def field(fid: str, kind: str = "text", *, required: bool = True, **more: Any) -> dict[str, Any]:
    """One format 2 question with every key written out."""
    base: dict[str, Any] = {
        "id": fid,
        "text": f"Question {fid}",
        "kind": kind,
        "required": required,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
        "section": None,
        "help": None,
        "visible_when": None,
    }
    base.update(more)
    return base


def two_fields() -> list[dict[str, Any]]:
    return [field("topic"), field("count", "number", required=False, min=0, max=100)]


def answer(q: str, value: Any, note: str | None = None) -> dict[str, Any]:
    return {"q": q, "value": value, "note": note}


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    # --- people and data -------------------------------------------------------------------

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with open_uow(self.db) as uow:
            accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=list(roles),
                password=prepare_password(PASSWORD, username=name),
                by="svc:test",
            )

    def agent(self, name: str) -> None:
        """The agent's account and its explicit grant: an agent files only under one (P2-X2 S1)."""
        with open_uow(self.db) as uow:
            grant_filing(uow, name)

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("bea", ("admin",))
        self.person("uma", ("user",))
        self.person("rob", ("user",))
        self.person("dora", ("user", "document_controller"))
        self.person("vera", ("user",))

    def record(self, record_type: str, key: str, scope: str = SCOPE) -> str:
        """An envelope-only record of another module's type: its id."""
        cmd = Command(actor="user:uma", source="test", scope=scope)
        with open_uow(self.db) as uow:
            return create_module_record(
                uow, cmd, record_type=record_type, title=key, key=key
            ).stream_id

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

    def setting(self, key: str, value: Any) -> None:
        with open_uow(self.db) as uow:
            handle_change_setting(
                uow,
                ChangeSetting(
                    actor="user:ada",
                    source="test",
                    scope="company",
                    key=key,
                    layer="company",
                    value=value,
                    reason="test",
                ),
            )

    # --- commands and reads ----------------------------------------------------------------

    def command(self, who: str, name: str, scope: str | None = None, **fields: Any) -> Command:
        default = COMPANY if name.endswith("FormTemplate") else SCOPE
        return SPEC[name].model(
            actor=f"user:{who}", source="test", scope=scope or default, **fields
        )

    def call(self, who: str, name: str, scope: str | None = None, **fields: Any) -> Any:
        """Run command ``name`` as ``who`` the way the dispatcher does: access, intent, handler,
        reading as that person's viewer."""
        spec = SPEC[name]
        cmd = self.command(who, name, scope, **fields)
        with open_uow(self.db) as uow:
            conn = uow.conn()
            require_command_access(conn, cmd)
            viewer = cf.viewer_for_actor(conn, cmd.actor)
            cmd = check_intent(cmd, conn, viewer)
            with cf.use_viewer(viewer), intent_scope(cmd.intent):
                return spec.handler(uow, cmd)

    def template(self, *, publish: bool = True, fields: list[dict[str, Any]] | None = None,
                 **more: Any) -> str:  # fmt: skip
        """A new template (its id), published by default."""
        made = self.call(
            "ada", "DraftFormTemplate", title="Toolbox talk", fields=fields or two_fields(), **more
        )
        if publish:
            self.call("ada", "PublishFormTemplate", template_id=made.stream_id)
        return str(made.stream_id)

    def save(self, who: str = "uma", template: str | None = None, **more: Any) -> Any:
        more.setdefault("answers", [answer("topic", "Ladders")])
        if "draft_id" not in more:
            more["template_id"] = template
        return self.call(who, "SaveFormDraft", **more)

    def submit(self, who: str = "uma", template: str | None = None, **more: Any) -> Any:
        more.setdefault("answers", [answer("topic", "Ladders")])
        if "draft_id" not in more:
            more["template_id"] = template
        return self.call(who, "SubmitForm", **more)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str) -> str:
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record)
        return "Draft" if found is None else str(found)

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    def key(self, record: str) -> str | None:
        return self.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record)

    def submission(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {SUBMISSION_TABLE} WHERE id = :i", i=record)[0]

    def template_row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {TEMPLATE_TABLE} WHERE id = :i", i=record)[0]

    def events(self, stream: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT event_type, stream_id, actor, source, causation_id, correlation_id, payload "
            "FROM events"
        )
        where: list[str] = []
        params: dict[str, Any] = {}
        if stream:
            where.append("stream_id = :s")
            params["s"] = stream
        if kind:
            where.append("event_type = :k")
            params["k"] = kind
        if where:
            sql += " WHERE " + " AND ".join(where)
        found = self.rows(sql + " ORDER BY seq", **params)
        return [{**e, "payload": json.loads(str(e["payload"]))} for e in found]

    def count(self, table: str = "events") -> int:
        return int(self.scalar(f"SELECT count(*) FROM {table}"))


__all__ = ["COMPANY", "MARKER", "SCOPE", "World", "answer", "field", "two_fields"]
