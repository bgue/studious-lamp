"""The job kind ``action``: run an invocation through its executor (brief §18.7; FANOUT D8, D11).

One attempt is the three transactions of ``tl_core.jobs.runner`` around one step that holds none:

1. **started** appends ``Action.Running`` (the attempt number) in the claim's transaction.
2. **prepare** (read only) loads the invocation and its definition, refuses when the kill switch is
   on, the action is retired or switched off, or its app is off (all final: ``JobFailure`` with
   ``retryable=False``), and builds the ``ActionRequest``. **run** calls the executor with no
   transaction open. This is the one job kind that may use the network, and only through the
   webhook executor's egress-checked transport (ADR-0017 amends the note of ``JobKind.run``).
3. **settle** writes ``Action.Completed`` (and the feed post when the definition says
   ``post_to_feed``), or ``Action.Failed`` for a failure that will not be retried; a retryable
   failure with attempts left raises ``JobFailure`` so the queue tries again and nothing is
   written. ``failed`` writes ``Action.Failed`` when the job fails for good (final); ``expired``
   does the same for a lease that ran out.

Every event the kind writes is stamped as the action's service actor: ``actor``
``svc:action-<name>``, ``source`` ``action:<name>@<version>``, ``correlation_id``
``action:<invocation id>`` and ``causation_id`` the request event (FANOUT D2). A feed post made for
``post_to_feed`` is caused by the completion, so a rule that reacts to it sees the chain
(``rules.engine.causal_chain``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from tl_core.integration.contract import (
    ActionExecutor,
    ActionOutcome,
    ActionRequest,
    JobExecutorConfig,
    Problem,
    RecordRef,
    WebhookExecutorConfig,
)
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.streams import (
    ACTION_COMPLETED,
    ACTION_FAILED,
    ACTION_INVOCATION_STREAM_TYPE,
    ACTION_RUNNING,
)
from tl_core.jobs.runner import JobFailure
from tl_core.jobs.types import Claim, Expired
from tl_core.ledger import NewEvent
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.uow import UnitOfWork
from tl_core.webhooks.rows import as_list, as_object, load_json

KIND = "action"
MAX_MESSAGE = 500

_INVOCATION_SQL = text(
    "SELECT i.invocation_id, i.scope, i.action, i.action_version, i.definition_id, i.status, "
    "i.targets_json, i.parameters_json, i.invoked_by "
    "FROM cur_action_invocation i WHERE i.invocation_id = :id"
)
_DEFINITION_SQL = text(
    "SELECT d.label, d.executor, d.executor_config_json, d.retired, d.enabled, "
    "d.result_handling_json, d.integration_app FROM cur_action_definition d "
    "WHERE d.definition_id = :id"
)
_APP_SQL = text("SELECT enabled FROM cur_integration_app WHERE name = :n")
_STREAM_SQL = text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s")
_REQUEST_EVENT_SQL = text("SELECT event_id FROM events WHERE stream_id = :s AND stream_version = 1")


def actor_of(action: str) -> str:
    return f"svc:action-{action}"


def source_of(action: str, version: int) -> str:
    return f"action:{action}@{version}"


class ActionJobKind:
    """The ``JobKind`` for invocations. ``executors`` maps ``"job"`` and ``"webhook"``."""

    kind = KIND

    def __init__(self, executors: Mapping[str, ActionExecutor]) -> None:
        self._executors = dict(executors)

    # --- the claim --------------------------------------------------------------------------

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        row = self._invocation(uow, claim.job_id)
        if row is None or row["status"] in ("completed", "failed"):
            raise JobFailure(
                "invocation_missing", "The invocation is gone or done.", retryable=False
            )
        self._append(
            uow, row, ACTION_RUNNING, {"invocation_id": claim.job_id, "attempt": claim.attempt}
        )

    def prepare(self, uow: UnitOfWork, claim: Claim) -> ActionRequest:
        if kill_switch_on(uow.conn()):
            raise JobFailure("killed", "The integration kill switch is on.", retryable=False)
        row = self._invocation(uow, claim.job_id)
        if row is None:
            raise JobFailure("invocation_missing", "The invocation is gone.", retryable=False)
        definition = (
            uow.conn().execute(_DEFINITION_SQL, {"id": row["definition_id"]}).mappings().first()
        )
        if definition is None or bool(definition["retired"]) or not bool(definition["enabled"]):
            raise JobFailure(
                "action_disabled", "The action is retired or switched off.", retryable=False
            )
        app = definition["integration_app"]
        if app is not None:
            on = uow.conn().execute(_APP_SQL, {"n": app}).first()
            if on is None or not bool(on.enabled):
                raise JobFailure(
                    "app_disabled", "The action's app is switched off.", retryable=False
                )
        config_raw = as_object(load_json(definition["executor_config_json"]))
        config: JobExecutorConfig | WebhookExecutorConfig = (
            JobExecutorConfig.model_validate(config_raw)
            if config_raw.get("kind") == "job"
            else WebhookExecutorConfig.model_validate(config_raw)
        )
        return ActionRequest(
            invocation_id=row["invocation_id"],
            action=row["action"],
            action_version=int(row["action_version"]),
            scope=row["scope"],
            targets=[RecordRef.model_validate(t) for t in as_list(load_json(row["targets_json"]))],
            parameters=as_object(load_json(row["parameters_json"])),
            invoked_by=row["invoked_by"],
            attempt=claim.attempt,
            config=config,
        )

    # --- the work (no transaction) ----------------------------------------------------------

    def run(self, work: ActionRequest) -> ActionOutcome:
        executor = self._executors.get(work.config.kind)
        if executor is None:
            return _failed("executor_unavailable", "No executor is installed for this action.")
        try:
            return executor.execute(work)
        except Exception as exc:  # an executor never raises; if one does, only its type is kept
            return _failed("executor_error", f"The executor failed ({type(exc).__name__}).")

    # --- the settlement ---------------------------------------------------------------------

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: ActionOutcome) -> None:
        row = self._invocation(uow, claim.job_id)
        if row is None:
            return
        if outcome.status == "completed":
            self._complete(uow, claim, row, outcome)
            return
        problem = (
            outcome.problems[0] if outcome.problems else Problem(code="failed", message="Failed.")
        )
        if outcome.retryable and claim.attempt < claim.max_attempts:
            raise JobFailure(problem.code, problem.message, retryable=True)
        self._fail(uow, claim, row, outcome.problems, outcome.http_status)

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
        row = self._invocation(uow, claim.job_id)
        if row is None or row["status"] in ("completed", "failed"):
            return
        problem = Problem(code=failure.code, message=failure.message[:MAX_MESSAGE])
        self._fail(uow, claim, row, [problem], None)

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        row = self._invocation(uow, item.job_id)
        if row is None or row["status"] in ("completed", "failed"):
            return
        problem = Problem(code="lease_expired", message="The worker stopped before it finished.")
        self._append(
            uow,
            row,
            ACTION_FAILED,
            {
                "invocation_id": item.job_id,
                "attempt": item.attempt,
                "problems": [problem.model_dump()],
            },
        )

    # --- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _invocation(uow: UnitOfWork, invocation_id: str) -> dict[str, Any] | None:
        found = uow.conn().execute(_INVOCATION_SQL, {"id": invocation_id}).mappings().first()
        return None if found is None else dict(found)

    def _complete(
        self, uow: UnitOfWork, claim: Claim, row: dict[str, Any], outcome: ActionOutcome
    ) -> None:
        payload: dict[str, Any] = {
            "invocation_id": claim.job_id,
            "attempt": claim.attempt,
            "result": outcome.result,
        }
        if outcome.http_status is not None:
            payload["http_status"] = outcome.http_status
        event_id = self._append(uow, row, ACTION_COMPLETED, payload)
        definition = (
            uow.conn().execute(_DEFINITION_SQL, {"id": row["definition_id"]}).mappings().first()
        )
        handling = (
            [] if definition is None else as_list(load_json(definition["result_handling_json"]))
        )
        if "post_to_feed" in handling and definition is not None:
            count = len(as_list(load_json(row["targets_json"])))
            handle_post(
                uow,
                PostToFeed(
                    actor=actor_of(row["action"]),
                    source=source_of(row["action"], int(row["action_version"])),
                    scope=row["scope"],
                    body=f"{definition['label']}: done for {count} record(s)"[:500],
                    correlation_id=f"action:{claim.job_id}",
                    causation_id=event_id,
                ),
            )

    def _fail(
        self,
        uow: UnitOfWork,
        claim: Claim,
        row: dict[str, Any],
        problems: list[Problem],
        http_status: int | None,
    ) -> None:
        payload: dict[str, Any] = {
            "invocation_id": claim.job_id,
            "attempt": claim.attempt,
            "problems": [p.model_dump() for p in problems],
        }
        if http_status is not None:
            payload["http_status"] = http_status
        self._append(uow, row, ACTION_FAILED, payload)

    @staticmethod
    def _append(
        uow: UnitOfWork, row: dict[str, Any], event_type: str, payload: dict[str, Any]
    ) -> str:
        stream = row["invocation_id"]
        version = int(uow.conn().execute(_STREAM_SQL, {"s": stream}).scalar_one())
        requested = uow.conn().execute(_REQUEST_EVENT_SQL, {"s": stream}).scalar_one_or_none()
        result = uow.append(
            stream_id=stream,
            stream_type=ACTION_INVOCATION_STREAM_TYPE,
            scope=row["scope"],
            expected_version=version,
            events=[NewEvent(event_type=event_type, payload=payload)],
            actor=actor_of(row["action"]),
            source=source_of(row["action"], int(row["action_version"])),
            correlation_id=f"action:{stream}",
            causation_id=None if requested is None else str(requested),
        )
        return result.events[0].event_id


def _failed(code: str, message: str) -> ActionOutcome:
    return ActionOutcome(status="failed", problems=[Problem(code=code, message=message)])
