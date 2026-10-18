"""Putting the action executors together for a worker (FANOUT D8, D14).

A process that runs the job kind ``action`` (the CLI worker, the demo, a test) builds its executors
here: the ``job`` executor, and the ``webhook`` executor with the egress policy, the transport and
a source of signing secrets that opens a short read-only unit of work for each attempt (the
secret is read inside the attempt, with no transaction left open while the request is out).
"""

from __future__ import annotations

from tl_core.integration.actions.jobs import ActionJobKind
from tl_core.integration.contract import ActionExecutor
from tl_core.integration.executors.job import JobExecutor
from tl_core.integration.executors.webhook import SecretSource, WebhookExecutor
from tl_core.integration.secrets import live_secrets, owner_of
from tl_core.jobs.types import UowFactory
from tl_core.util import utcnow
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.signing import SigningSecret
from tl_core.webhooks.transport import Transport


def secret_source(open_uow: UowFactory) -> SecretSource:
    """Live signing secrets (newest first) of the action that owns a secret id."""

    def read(secret_id: str) -> list[SigningSecret]:
        with open_uow(readonly=True) as uow:
            owner = owner_of(uow.conn(), secret_id)
            if owner is None or owner[0] != "action":
                return []
            return live_secrets(uow.conn(), "action", owner[1], now=utcnow())

    return read


def action_executors(
    open_uow: UowFactory, *, policy: EgressPolicy, transport: Transport
) -> dict[str, ActionExecutor]:
    """``{"job": ..., "webhook": ...}``, the executors Phase 1 builds."""
    return {
        "job": JobExecutor(),
        "webhook": WebhookExecutor(
            policy=policy, transport=transport, secrets=secret_source(open_uow)
        ),
    }


def action_job_kind(
    open_uow: UowFactory, *, policy: EgressPolicy, transport: Transport
) -> ActionJobKind:
    """The job kind a ``JobRunner`` needs to run invocations."""
    return ActionJobKind(action_executors(open_uow, policy=policy, transport=transport))
