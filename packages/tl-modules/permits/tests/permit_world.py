"""A ledger, a clock and the people who act on it, for the permits module tests and the S2 script.

``uma`` (user: any person on the job), ``rob`` (user: the foreman who requests; holder "Rob"),
``sue`` and ``pam`` (permits superusers, so controllers: sue approves, pam issues), ``vera`` (a
viewer) and ``dora`` (reads restricted records; a controller too). Commands run as a person would
run them: the access word is checked first (``require_command_access``), then the intent, then
the handler as that person's viewer, one unit of work each, as the API dispatcher does. The clock
is ``world.at``; a test moves it. Gas tests and isolations are seeded through ledger events (S3 owns
their commands); a restricted record is made through the correspondence module's own commands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.intent import check_intent, intent_scope
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_permits.handlers.common import move
from tl_mod_permits.module import COMMANDS
from tl_mod_permits.names import GAS_TEST, ISOLATION, PERMIT, PERMIT_TABLE

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
SPEC = {c.model.__name__: c for c in COMMANDS}
IWP = "awp.IWP"
#: 07:00 UTC on a day whose shifts run 06:00-18:00 and 18:00-06:00 (the defaults).
START = datetime(2026, 12, 1, 7, 0, tzinfo=UTC)
ALL_TICKS = {
    "hot_work": ["fire_watch", "extinguisher", "combustibles_cleared", "spark_containment"],
    "general": ["jha_attached"],
    "confined_space": ["attendant", "rescue_plan", "ventilation", "entry_log"],
    "work_at_height": ["fall_protection", "exclusion_zone", "tool_lanyards", "scaffold_tag"],
}


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.at = START

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
                        module="permits",
                        role=grant,
                        reason="test",
                    ),
                )

    def people(self) -> None:
        self.person("ada", ("admin",))
        self.person("uma", ("user",))
        self.person("rob", ("user",))
        self.person("sue", ("user",), grant="superuser")
        self.person("pam", ("user",), grant="superuser")
        self.person("dora", ("user", "document_controller"), grant="superuser")
        self.person("vera", ("user",), grant="viewer")

    def record(self, record_type: str, key: str, scope: str = SCOPE) -> str:
        """An envelope-only record of another module's type (an IWP, say): its id."""
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

    def request(self, who: str = "rob", permit_type: str = "general", **more: Any) -> str:
        """A new permit (its id)."""
        fields: dict[str, Any] = {
            "permit_type": permit_type,
            "area": "A1",
            "location_text": "Pump room",
            "work_description": "Weld repair, rack 12",
            "holder": "Rob",
            "needed_from": "2026-12-01",
            "needed_until": "2026-12-31",
        }
        return str(self.call(who, "RequestPermit", **{**fields, **more}).stream_id)

    def approved(self, permit_type: str = "general", **more: Any) -> str:
        permit = self.request(permit_type=permit_type, **more)
        self.call("sue", "ApprovePermit", permit=permit)
        return permit

    def issue(self, permit: str, who: str = "pam", **more: Any) -> Any:
        fields: dict[str, Any] = {"precautions": ALL_TICKS[self.row(permit)["permit_type"]]}
        return self.call(who, "IssuePermit", permit=permit, **{**fields, **more})

    def active(self, permit_type: str = "general", **more: Any) -> str:
        """A permit made Active (general and the types that need nothing else)."""
        permit = self.approved(permit_type, **more)
        self.issue(permit)
        return permit

    # --- seeded facts (the commands of S3 are not here yet) ---------------------------------

    def _make(self, record_type: str, key: str, first: NewEvent) -> str:
        cmd = Command(actor="user:pam", source="test", scope=SCOPE)
        with open_uow(self.db) as uow:
            probe = create_module_record(uow, cmd, record_type=record_type, title=key, key=key)
            payload = {"record_id": probe.stream_id, "feed_policy": "none", **first.payload}
            uow.append(
                stream_id=probe.stream_id,
                stream_type=record_type,
                scope=SCOPE,
                expected_version=probe.version,
                events=[NewEvent(event_type=first.event_type, payload=payload)],
                actor="user:pam",
                source="test",
                correlation_id="corr-seed",
            )
            return str(probe.stream_id)

    def gas_test(self, permit: str, *, result: str = "pass", at: datetime | None = None) -> str:
        """A gas test of ``permit`` taken at ``at`` (the clock by default)."""
        self._gas = getattr(self, "_gas", 0) + 1
        taken = self.at if at is None else at
        return self._make(
            GAS_TEST,
            f"P123-GAS-{self._gas:04d}",
            NewEvent(
                event_type="GasTest.Recorded",
                payload={
                    "permit_id": permit,
                    "taken_at": iso_utc(taken),
                    "tester": "user:uma",
                    "o2_pct": "20.9",
                    "result": result,
                },
            ),
        )

    def isolation(self, permit: str | None = None, *, verified: bool = False) -> str:
        """An isolation, linked to ``permit`` when given, Verified when asked."""
        self._isl = getattr(self, "_isl", 0) + 1
        made = self._make(
            ISOLATION,
            f"P123-ISL-{self._isl:04d}",
            NewEvent(
                event_type="Isolation.Applied",
                payload={
                    "point_text": "Pump P-101 breaker",
                    "energy": "electrical",
                    "applied_at": iso_utc(self.at),
                },
            ),
        )
        if verified:
            self.verify_isolation(made)
        if permit is not None:
            self.link(permit, made)
        return made

    def verify_isolation(self, isolation: str) -> None:
        cmd = Command(actor="user:sue", source="test", scope=SCOPE)
        with open_uow(self.db) as uow:
            version = int(
                uow.conn()
                .execute(
                    text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": isolation}
                )
                .scalar_one()
            )
            uow.append(
                stream_id=isolation,
                stream_type=ISOLATION,
                scope=SCOPE,
                expected_version=version,
                events=[
                    NewEvent(
                        event_type="Isolation.Verified",
                        payload={
                            "record_id": isolation,
                            "feed_policy": "none",
                            "verified_at": iso_utc(self.at),
                        },
                    )
                ],
                actor="user:sue",
                source="test",
                correlation_id="corr-seed",
            )
            move(uow, cmd, isolation, "verify")

    def link(self, permit: str, isolation: str, *, unlink: bool = False) -> None:
        kind = "Permit.IsolationUnlinked" if unlink else "Permit.IsolationLinked"
        with open_uow(self.db) as uow:
            version = int(
                uow.conn()
                .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": permit})
                .scalar_one()
            )
            uow.append(
                stream_id=permit,
                stream_type=PERMIT,
                scope=SCOPE,
                expected_version=version,
                events=[
                    NewEvent(
                        event_type=kind,
                        payload={
                            "record_id": permit,
                            "isolation_id": isolation,
                            "feed_policy": "none",
                        },
                    )
                ],
                actor="user:pam",
                source="test",
                correlation_id="corr-seed",
            )

    # --- reads -----------------------------------------------------------------------------

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def state(self, record: str) -> str:
        """The workflow state (the initial one while no transition has run: Applied for an
        isolation, Requested for a permit)."""
        row = self.rows("SELECT status, type FROM cur_core_record WHERE id = :i", i=record)[0]
        if row["status"] is not None:
            return str(row["status"])
        return "Applied" if row["type"] == ISOLATION else "Requested"

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))

    def row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {PERMIT_TABLE} WHERE id = :i", i=record)[0]

    def count(self, table: str = "events") -> int:
        return int(self.scalar(f"SELECT count(*) FROM {table}"))


__all__ = ["ALL_TICKS", "IWP", "SCOPE", "START", "World"]
