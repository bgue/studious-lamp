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
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.intent import check_intent, intent_scope
from tl_core.ledger import NewEvent
from tl_core.qr.codes import code_hash, new_code
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.util import new_ulid, utcnow
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_forms.module import FORMS_COMMANDS
from tl_mod_forms.names import (
    INTAKE_BODY_TABLE,
    INTAKE_CODE,
    INTAKE_ITEM,
    SUBMISSION_TABLE,
    TEMPLATE_TABLE,
)

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

    def hidden_record(self, to_class: Literal["restricted", "privileged"] = "restricted") -> str:
        """The id of a correspondence item of class ``to_class``: ``restricted`` is hidden from
        the lowest viewer, ``privileged`` from the controllers (``ada``, ``bea``) too."""
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
                    to_class=to_class,
                    grant=["user:dora"] if to_class == "privileged" else [],
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

    # --- intake (S7c) ----------------------------------------------------------------------

    def intake_template(
        self, *, accepts_as: list[str] | None = None, publish: bool = True, **more: Any
    ) -> str:
        """A public intake template (its id): published by default, accepted as ``SubmitForm``."""
        fields = [
            field("topic"),
            field("claim_name", required=False),
            field("claim_company", required=False),
            field("claim_phone", required=False),
        ]
        return self.template(
            publish=publish,
            fields=fields,
            intake="public",
            purpose="request",
            accepts_as=accepts_as or ["SubmitForm"],
            **more,
        )

    def days_from_now(self, days: int) -> str:
        return (utcnow().date() + timedelta(days=days)).isoformat()

    def issue(self, template: str, *, who: str = "ada", **more: Any) -> tuple[str, str]:
        """Issue a code through the command: the code (printed once, never stored) and its id."""
        code = new_code()
        more.setdefault("heading", "Scaffold request")
        more.setdefault("controller_role", "controller")
        more.setdefault("expires_on", self.days_from_now(30))
        made = self.call(
            who, "IssueIntakeCode", code_hash=code_hash(code), template_id=template, **more
        )
        return code, str(made.stream_id)

    def _append_as_service(self, stream: str, record_type: str, events: list[NewEvent]) -> None:
        with open_uow(self.db) as uow:
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=SCOPE,
                expected_version=0,
                events=events,
                actor="svc:test",
                source="test",
                correlation_id=new_ulid(),
            )

    def stage_code(self, template: str, *, context_id: str | None = None) -> str:
        """An Active code written straight to the ledger (a context the issuer could not read can
        be given), bypassing the command: its id."""
        code_id = new_ulid()
        row = self.template_row(template)
        created = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": INTAKE_CODE,
                "key": None,
                "title": "Staged",
                "description": None,
                "psets": {},
            },
        )
        issued = NewEvent(
            event_type="IntakeCode.Issued",
            payload={
                "code_hash": code_hash(new_code()),
                "template_id": template,
                "template_version": row["template_version"],
                "template_hash": row["content_hash"],
                "context_id": context_id,
                "context_type": None,
                "heading": "Staged",
                "controller_role": "controller",
                "expires_on": self.days_from_now(30),
                "feed_policy": "none",
            },
        )
        self._append_as_service(code_id, INTAKE_CODE, [created, issued])
        return code_id

    def stage_item(self, code_id: str, body: str | None = None) -> str:
        """A received item as the intake service would stage it (S6 does not exist yet): a
        ``Received`` event by ``svc:intake`` and a body row. Returns the item id."""
        code = self.rows("SELECT * FROM cur_forms_intake_code WHERE id = :i", i=code_id)[0]
        item = new_ulid()
        text_body = body if body is not None else intake_body()
        created = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": INTAKE_ITEM,
                "key": None,
                "title": "Intake item",
                "description": None,
                "psets": {},
            },
        )
        received = NewEvent(
            event_type="IntakeItem.Received",
            payload={
                "item_id": item,
                "code_id": code_id,
                "template_id": code["template_id"],
                "template_version": code["template_version"],
                "template_hash": code["template_hash"],
                "body_mac": "cd" * 32,
                "body_bytes": len(text_body.encode()),
                "received_at": "2026-12-01T09:00:00Z",
                "feed_policy": "none",
            },
        )
        with open_uow(self.db) as uow:
            uow.append(
                stream_id=item,
                stream_type=INTAKE_ITEM,
                scope=SCOPE,
                expected_version=0,
                events=[created, received],
                actor="svc:intake",
                source=f"intake:{code_id}",
                correlation_id=new_ulid(),
            )
            uow.conn().execute(
                text(
                    f"INSERT INTO {INTAKE_BODY_TABLE} (item_id, code_id, salt, body, received_at) "
                    "VALUES (:i, :c, :s, :b, :r)"
                ),
                {
                    "i": item,
                    "c": code_id,
                    "s": "0f" * 16,
                    "b": text_body,
                    "r": "2026-12-01T09:00:00Z",
                },
            )
        return item

    def body_rows(self, item: str) -> int:
        return int(
            self.scalar(f"SELECT count(*) FROM {INTAKE_BODY_TABLE} WHERE item_id = :i", i=item)
        )

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str, initial: str = "Draft") -> str:
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record)
        return initial if found is None else str(found)

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


def intake_body(
    topic: str = "Need a ladder",
    name: str | None = "Sam Smith",
    company: str | None = "Acme Scaffolding",
    phone: str | None = "555-0100",
) -> str:
    """A staged body as S6 stores it: canonical JSON ``{"answers": [...]}``."""
    pairs = [("topic", topic), ("claim_name", name), ("claim_company", company)]
    pairs.append(("claim_phone", phone))
    answers = [answer(q, v) for q, v in pairs if v is not None]
    return json.dumps({"answers": answers}, sort_keys=True, separators=(",", ":"))


__all__ = [
    "COMPANY",
    "MARKER",
    "SCOPE",
    "World",
    "answer",
    "field",
    "intake_body",
    "two_fields",
]
