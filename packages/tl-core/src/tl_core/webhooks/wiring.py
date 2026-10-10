"""Small constructors that wire the engine from the environment, for the CLI and the demo.

Keeps the CLI free of logic: it asks for an engine or a dispatcher and calls one method. The egress
allow-list comes from ``--allow-host`` options and ``TL_WEBHOOK_ALLOWLIST`` (comma separated), the
stand-in for the ``webhooks.egress.allowlist`` setting until about:config exists (P0-I8).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

from tl_core.webhooks.base import UowFactory
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import RetryPolicy
from tl_core.webhooks.transport import HttpxTransport, Transport

ALLOWLIST_ENV = "TL_WEBHOOK_ALLOWLIST"


def allowlist_from(
    extra: Iterable[str] = (), env: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """Allow-list entries from ``extra`` plus the environment variable, order kept, no repeats."""
    source = os.environ if env is None else env
    listed = [part.strip() for part in source.get(ALLOWLIST_ENV, "").split(",") if part.strip()]
    return tuple(dict.fromkeys([*extra, *listed]))


def make_engine(
    factory: UowFactory,
    *,
    allow_hosts: Iterable[str] = (),
    transport: Transport | None = None,
    retry: RetryPolicy | None = None,
    worker_id: str | None = None,
) -> DeliveryEngine:
    """A delivery engine with the egress allow-list given and the real HTTP transport."""
    return DeliveryEngine(
        factory,
        transport if transport is not None else HttpxTransport(),
        egress=EgressPolicy(allowlist_from(allow_hosts)),
        retry=retry,
        worker_id=worker_id,
    )


def make_dispatcher(factory: UowFactory) -> Dispatcher:
    return Dispatcher(factory)
