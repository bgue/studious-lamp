"""A ledger, people and a fake scan-card provider for the QR module tests.

``ada`` (admin: controller words), ``uma`` and ``rob`` (users), ``dora`` (the document controller:
reads restricted records) and ``vera`` (a viewer). Commands run as the dispatcher runs them: the
access word first (``require_command_access``), then the handler as that person's viewer in one
unit of work. The provider is injected by replacing ``registry.load_scan_cards`` (no entry-point
install).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.qr.types import ScanCard, ScanCardProvider
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
from tl_mod_qr.module import COMMANDS

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
BASE = "https://tl.example.com"
CARDED = "quality.PunchItem"  # the fake provider answers for this type
CARDLESS = "awp.IWP"  # no provider
SECRET = "correspondence.Correspondence"  # hidden items; a second fake answers for it
NOW = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
ROWS = {row.model.__name__: row for row in COMMANDS}


class FakeProvider:
    """Answers a card for any record the viewer can read; counts calls."""

    view_word = "quality.view"

    def __init__(self, record_type: str = CARDED) -> None:
        self.record_type = record_type
        self.calls = 0
        self.raises = False

    def card(
        self, conn: Connection, record_id: str, viewer: cf.Viewer, now: datetime
    ) -> ScanCard | None:
        self.calls += 1
        if self.raises:
            raise RuntimeError("provider failed")
        if cf.is_hidden(conn, record_id, viewer):
            return None
        return ScanCard(
            record_type=self.record_type,
            key="K-1",
            title="Fake card",
            banner="OK",
            tone="go",
            as_of=now,
        )


def providers_of(*items: ScanCardProvider) -> dict[str, ScanCardProvider]:
    return {p.record_type: p for p in items}


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.public = ""
        self.made = 0

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
        self.person("uma", ("user",))
        self.person("rob", ("user",))
        self.person("dora", ("user", "document_controller"))
        self.person("vera", ("user",))

    def base(self, value: str = BASE) -> None:
        """Set ``api.public_base_url``. It is a platform default only (no layer takes it), so the
        tests stand in for the platform file: ``conftest`` makes the service read this value."""
        self.public = value

    def cap(self, value: int) -> None:
        with open_uow(self.db) as uow:
            handle_change_setting(
                uow,
                ChangeSetting(
                    actor="user:ada",
                    source="test",
                    scope="company",
                    key="qr.codes_per_record_max",
                    layer="company",
                    value=value,
                    reason="test",
                ),
            )

    def record(self, record_type: str = CARDED, key: str | None = None, scope: str = SCOPE) -> str:
        self.made += 1
        key = key or f"T-{self.made}"
        cmd = Command(actor="user:uma", source="test", scope=scope)
        with open_uow(self.db) as uow:
            return create_module_record(
                uow, cmd, record_type=record_type, title=key, key=key
            ).stream_id

    def hidden_record(self, to_class: Literal["restricted", "privileged"] = "restricted") -> str:
        """A correspondence item of class ``to_class`` (hidden from the lowest viewer)."""
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

    def command(self, who: str, name: str, scope: str | None = None, **fields: Any) -> Command:
        return ROWS[name].model(actor=f"user:{who}", source="test", scope=scope or SCOPE, **fields)

    def call(self, who: str, name: str, scope: str | None = None, **fields: Any) -> Any:
        """Run command ``name`` as ``who`` the way the dispatcher does."""
        cmd = self.command(who, name, scope, **fields)
        with open_uow(self.db) as uow:
            conn = uow.conn()
            require_command_access(conn, cmd)
            with cf.use_viewer(cf.viewer_for_actor(conn, cmd.actor)):
                return ROWS[name].handler(uow, cmd)

    def serve(self, fn: Any, who: str, name: str, *, check: bool = True, **fields: Any) -> Any:
        """Run service function ``fn`` (``issue``, ``rotate``) for ``who``: its return value.
        ``check=False`` skips the access word (to reach the handler's own visibility rule)."""
        cmd = self.command(who, name, None, **fields)
        with open_uow(self.db) as uow:
            conn = uow.conn()
            if check:
                require_command_access(conn, cmd)
            with cf.use_viewer(cf.viewer_for_actor(conn, cmd.actor)):
                return fn(uow, cmd)

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]
