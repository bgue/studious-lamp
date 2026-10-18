"""The job kind ``inbound.map``: map a received delivery and run its commands (FANOUT D4, D5, D11).

One attempt is the transactions of ``tl_core.jobs.runner`` around one step that holds none:

1. **started** counts the attempt on the delivery (an operational row; no ledger event).
2. **prepare** (read only) refuses when the kill switch is on or the endpoint or its app was
   switched off since the delivery was received (final, ``JobFailure`` with ``retryable=False``:
   the delivery waits in the error queue for an admin), and loads the endpoint **version the
   delivery was received under**: a later revision of the mapping does not change a delivery in
   flight, an admin's retry does.
3. **run** (no transaction) reads the stored body, parses it and evaluates the mapping in the
   ADR-0014 envelope (``mapping.JsonataRestricted``).
4. **settle** (one unit of work) resolves ``{"$key": ...}`` references inside the delivery's scope,
   builds every command with the server-set fields (actor the endpoint's service actor, source
   ``inbound:<app>/<endpoint>``, correlation ``inbound:<delivery id>``, link source ``mapping``)
   through ``automation.plan_command``, and runs **all** of them in that one unit of work through
   the runner. Any refusal rolls the whole delivery back: the commands, the queue row and the
   delivery row. A ``dry_run`` endpoint plans and writes nothing but the delivery state.
   ``Inbound.Applied`` and the delivery row are written in the same unit of work.
5. **failed** (final) records ``Inbound.Failed`` with a fixed code and a bounded message that never
   holds a payload excerpt, and the delivery row ``failed`` (or ``killed``): the error queue.

A retry by an admin queues a new job for the same delivery (its id is ``<delivery id>:<ulid>``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, text

from tl_core.files.types import ObjectNotFound, ObjectStore
from tl_core.integration.automation import (
    Planned,
    ServerFields,
    plan_command,
    run_automation_command,
)
from tl_core.integration.contract import (
    INBOUND_HARD_MAX_BODY_BYTES,
    AutomationAccess,
    CommandRunner,
    MappingOutcome,
    MappingRuntime,
    PlannedCommand,
    Problem,
    RecordRef,
)
from tl_core.integration.inbound import store as body_store
from tl_core.integration.inbound.gate import InvalidPayload, parse_payload
from tl_core.integration.inbound.mapping import JsonataRestricted
from tl_core.integration.keys import resolve_keys
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.streams import (
    DELIVERY_STREAM_TYPE,
    INBOUND_APPLIED,
    INBOUND_FAILED,
)
from tl_core.jobs.runner import JobFailure
from tl_core.jobs.types import Claim, Expired, iso_z
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
from tl_core.webhooks.rows import as_list, as_object, load_json

KIND = "inbound.map"
MAX_MESSAGE = 300

_DELIVERY_SQL = text("SELECT * FROM int_delivery WHERE delivery_id = :id")
_ENDPOINT_SQL = text(
    "SELECT e.enabled, EXISTS (SELECT 1 FROM cur_integration_app a WHERE a.name = e.app "
    "AND a.enabled = :on) AS app_on FROM cur_inbound_endpoint e WHERE e.endpoint_id = :id"
)
_VERSION_SQL = text(
    "SELECT definition_json FROM cur_inbound_endpoint_version "
    "WHERE endpoint_id = :e AND version = :v"
)
_STREAM_SQL = text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s")
_FINISH = text(
    "UPDATE int_delivery SET state = :state, finished_at = :t, error_code = :code, "
    "error_message = :msg, command_count = :n WHERE delivery_id = :id"
)


def delivery_of(job_id: str) -> str:
    """The delivery id of a job id (a retry's job id is ``<delivery id>:<suffix>``)."""
    return job_id.split(":", 1)[0]


def plan_mapped(
    conn: Connection,
    runner: CommandRunner,
    outcome: MappingOutcome,
    *,
    definition: dict[str, Any],
    scope: str,
    delivery_id: str,
) -> list[Planned]:
    """Build every command of a mapping's outcome, in order: keys resolved inside ``scope``, the
    server-set fields from the endpoint, the allow-list, the access and the model checked. Nothing
    runs; a refused command is reported with its problem and the rest are still planned."""
    access: AutomationAccess = definition["access"]
    fields = ServerFields(
        actor=str(definition["service_actor"]),
        source=f"inbound:{definition['app']}/{definition['name']}",
        scope=scope,
        correlation_id=f"inbound:{delivery_id}",
        causation_id=None,
    )
    allowed = {str(c) for c in as_list(definition["allowed_commands"])}
    lookup = RecordKeyLookup(conn, scope)
    planned: list[Planned] = []
    for mapped in outcome.commands:
        args, problems = resolve_keys(mapped.args, lookup)
        if problems:
            planned.append(
                Planned(
                    None,
                    PlannedCommand(
                        command_type=mapped.command,
                        summary=mapped.command,
                        problem=problems[0],
                    ),
                )
            )
            continue
        planned.append(
            plan_command(
                runner,
                mapped.command,
                args,
                fields,
                declared=access,
                allowed=allowed,
                link_source="mapping",
            )
        )
    return planned


def _delivery(conn: Connection, job_id: str) -> Any:
    return conn.execute(_DELIVERY_SQL, {"id": delivery_of(job_id)}).mappings().first()


@dataclass(frozen=True)
class MapWork:
    """What ``run`` needs, read in ``prepare``."""

    delivery_id: str
    object_key: str
    mapping: str
    language: str


@dataclass(frozen=True)
class MapResult:
    """What ``run`` found: the mapping's outcome, or why there was none."""

    outcome: MappingOutcome | None = None
    problem: Problem | None = None


class RecordKeyLookup:
    """``KeyLookup`` over the projection, inside one scope: a mapping cannot reach another."""

    def __init__(self, conn: Connection, scope: str) -> None:
        self._conn = conn
        self._scope = scope

    def find(self, key: str, record_type: str | None) -> list[RecordRef]:
        sql = (
            "SELECT id, key, type, version FROM cur_core_record "
            "WHERE key = :k AND scope = :s AND voided = :v"
        )
        params: dict[str, Any] = {"k": key, "s": self._scope, "v": False}
        if record_type is not None:
            sql += " AND type = :t"
            params["t"] = record_type
        rows = self._conn.execute(text(sql + " LIMIT 3"), params)
        return [
            RecordRef(id=r.id, key=r.key, record_type=r.type, version=int(r.version)) for r in rows
        ]


def _short(exc: Exception, position: int, name: str) -> Problem:
    """A fixed-shape problem for an error a command raised; never the error's own text."""
    if isinstance(exc, ServiceError):
        what = f"Command {position} ({name}) was refused ({type(exc).__name__})."
        return Problem(code="command_refused", message=what[:MAX_MESSAGE])
    if isinstance(exc, ValidationError):
        return Problem(code="invalid_command", message=f"Command {position} ({name}) is invalid.")
    if isinstance(exc, ConcurrencyError):
        return Problem(code="stale", message="A record changed under the delivery.")
    return Problem(
        code="command_failed", message=f"Command {position} failed ({type(exc).__name__})."
    )


class InboundMapJobKind:
    """The ``JobKind`` for deliveries."""

    kind = KIND

    def __init__(
        self,
        runner: CommandRunner,
        store: ObjectStore | None = None,
        *,
        runtime: MappingRuntime | None = None,
    ) -> None:
        self._runner = runner
        self._store = store
        self._runtime: MappingRuntime = runtime or JsonataRestricted()

    # --- the claim --------------------------------------------------------------------------

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        row = (
            uow.conn().execute(_DELIVERY_SQL, {"id": delivery_of(claim.job_id)}).mappings().first()
        )
        if row is None or row["state"] != "queued":
            raise JobFailure("delivery_done", "The delivery is gone or done.", retryable=False)
        uow.conn().execute(
            text("UPDATE int_delivery SET attempts = attempts + 1 WHERE delivery_id = :id"),
            {"id": row["delivery_id"]},
        )

    def prepare(self, uow: UnitOfWork, claim: Claim) -> MapWork:
        conn = uow.conn()
        if kill_switch_on(conn):
            raise JobFailure("killed", "The integration kill switch is on.", retryable=False)
        delivery = _delivery(conn, claim.job_id)
        if delivery is None:
            raise JobFailure("delivery_done", "The delivery is gone.", retryable=False)
        endpoint = (
            conn.execute(_ENDPOINT_SQL, {"id": delivery["endpoint_id"], "on": True})
            .mappings()
            .first()
        )
        if endpoint is None or not bool(endpoint["enabled"]) or not bool(endpoint["app_on"]):
            raise JobFailure(
                "endpoint_off", "The endpoint or its app is switched off.", retryable=False
            )
        found = conn.execute(
            _VERSION_SQL, {"e": delivery["endpoint_id"], "v": delivery["endpoint_version"]}
        ).first()
        if found is None:
            raise JobFailure("version_missing", "The endpoint version is gone.", retryable=False)
        definition = as_object(load_json(found.definition_json))
        return MapWork(
            delivery_id=delivery["delivery_id"],
            object_key=delivery["corrected_object_key"] or delivery["object_key"],
            mapping=str(definition["mapping"]),
            language=str(definition.get("mapping_language", "")),
        )

    # --- the work (no transaction) ----------------------------------------------------------

    def run(self, work: MapWork) -> MapResult:
        store = self._store or body_store.configured()
        try:
            body = body_store.read_body(store, work.object_key, INBOUND_HARD_MAX_BODY_BYTES)
        except (ObjectNotFound, ValueError):
            return MapResult(
                problem=Problem(code="payload_missing", message="The stored payload is gone.")
            )
        try:
            payload = parse_payload(body)
        except InvalidPayload:
            return MapResult(
                problem=Problem(code="invalid_payload", message="The payload is not valid JSON.")
            )
        if work.language != self._runtime.language:
            return MapResult(
                problem=Problem(code="language", message="The mapping language is not supported.")
            )
        return MapResult(outcome=self._runtime.evaluate(work.mapping, payload))

    # --- the settlement ---------------------------------------------------------------------

    def settle(self, uow: UnitOfWork, claim: Claim, result: MapResult) -> None:
        conn = uow.conn()
        delivery = _delivery(conn, claim.job_id)
        if delivery is None or delivery["state"] != "queued":
            return
        if result.problem is not None:
            raise JobFailure(result.problem.code, result.problem.message, retryable=False)
        outcome = result.outcome
        assert outcome is not None
        if outcome.status != "ok":
            problem = (
                outcome.problems[0]
                if outcome.problems
                else Problem(code=outcome.status, message="The mapping gave no commands.")
            )
            raise JobFailure(
                f"mapping_{outcome.status}", problem.message[:MAX_MESSAGE], retryable=False
            )
        definition = self._definition(conn, delivery)
        access: AutomationAccess = definition["access"]
        built = plan_mapped(
            conn,
            self._runner,
            outcome,
            definition=definition,
            scope=str(delivery["scope"]),
            delivery_id=str(delivery["delivery_id"]),
        )
        commands: list[Any] = []
        for position, item in enumerate(built, start=1):
            if item.command is None:
                problem = item.planned.problem or Problem(code="refused", message="Refused.")
                message = f"Command {position}: {problem.message}"[:MAX_MESSAGE]
                raise JobFailure(problem.code, message, retryable=False)
            commands.append(item.command)
        dry = bool(definition.get("dry_run", False))
        if not dry:
            for position, command in enumerate(commands, start=1):
                try:
                    run_automation_command(
                        self._runner, uow, command, link_source="mapping", declared=access
                    )
                except JobFailure:
                    raise
                except Exception as exc:
                    problem = _short(exc, position, type(command).__name__)
                    retry = isinstance(exc, ConcurrencyError)
                    raise JobFailure(problem.code, problem.message, retryable=retry) from None
        self._finish(
            uow, delivery, definition, "dry_run" if dry else "applied", len(commands), dry=dry
        )

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        if not final:
            return
        self._fail(uow, delivery_of(claim.job_id), failure.code, failure.message)

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        self._fail(
            uow,
            delivery_of(item.job_id),
            "lease_expired",
            "The worker stopped before it finished.",
        )

    # --- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _definition(conn: Connection, delivery: Any) -> dict[str, Any]:
        found = conn.execute(
            _VERSION_SQL, {"e": delivery["endpoint_id"], "v": delivery["endpoint_version"]}
        ).first()
        if found is None:
            raise JobFailure("version_missing", "The endpoint version is gone.", retryable=False)
        return as_object(load_json(found.definition_json))

    def _finish(
        self,
        uow: UnitOfWork,
        delivery: Any,
        definition: dict[str, Any],
        state: str,
        count: int,
        *,
        dry: bool,
    ) -> None:
        now = utcnow()
        uow.conn().execute(
            _FINISH,
            {
                "state": state, "t": iso_z(now), "code": None, "msg": None, "n": count,
                "id": delivery["delivery_id"],
            },
        )  # fmt: skip
        self._append(
            uow,
            delivery,
            definition,
            INBOUND_APPLIED,
            {"delivery_id": delivery["delivery_id"], "command_count": count, "dry_run": dry},
        )

    def _fail(self, uow: UnitOfWork, delivery_id: str, code: str, message: str) -> None:
        conn = uow.conn()
        delivery = conn.execute(_DELIVERY_SQL, {"id": delivery_id}).mappings().first()
        if delivery is None or delivery["state"] != "queued":
            return
        state = "killed" if code == "killed" else "failed"
        text_ = message[:MAX_MESSAGE]
        conn.execute(
            _FINISH,
            {
                "state": state, "t": iso_z(utcnow()), "code": code[:64], "msg": text_, "n": None,
                "id": delivery_id,
            },
        )  # fmt: skip
        found = conn.execute(
            _VERSION_SQL, {"e": delivery["endpoint_id"], "v": delivery["endpoint_version"]}
        ).first()
        definition = {} if found is None else as_object(load_json(found.definition_json))
        self._append(
            uow,
            delivery,
            definition,
            INBOUND_FAILED,
            {"delivery_id": delivery_id, "code": code[:64], "message": text_},
        )

    @staticmethod
    def _append(
        uow: UnitOfWork,
        delivery: Any,
        definition: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        stream = str(delivery["delivery_id"])
        version = int(uow.conn().execute(_STREAM_SQL, {"s": stream}).scalar_one())
        uow.append(
            stream_id=stream,
            stream_type=DELIVERY_STREAM_TYPE,
            scope=str(delivery["scope"]),
            expected_version=version,
            events=[NewEvent(event_type=event_type, payload=payload)],
            actor=str(definition.get("service_actor") or "svc:inbound-unknown"),
            source=f"inbound:{definition.get('app', '?')}/{definition.get('name', '?')}",
            correlation_id=f"inbound:{stream}",
            causation_id=None,
        )


__all__ = ["KIND", "InboundMapJobKind", "MapResult", "MapWork", "RecordKeyLookup", "delivery_of"]
