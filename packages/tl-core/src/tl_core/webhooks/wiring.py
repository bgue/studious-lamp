"""Small constructors that wire the engine from the environment, for the CLI and the demo.

Keeps the CLI free of logic: it asks for an engine or a dispatcher and calls one method. The egress
allow-list is the ``webhooks.egress.allowlist`` setting (the company's, read again every few
seconds) plus the ``--allow-host`` options and ``TL_WEBHOOK_ALLOWLIST`` (comma separated), which are
the operator's flags for one process (P0-I8). The retry window is ``webhooks.retry.max_hours``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping

from tl_core.settings.reader import SettingsReader, conn_factory_from
from tl_core.webhooks.base import Clock, UowFactory, utc_now
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.egress import EgressPolicy, Resolver
from tl_core.webhooks.retry import RetryPolicy
from tl_core.webhooks.transport import HttpxTransport, Transport

ALLOWLIST_ENV = "TL_WEBHOOK_ALLOWLIST"
READER_MAX_AGE_S = 5.0
EGRESS_KEY = "webhooks.egress.allowlist"
RETRY_KEY = "webhooks.retry.max_hours"


def allowlist_from(
    extra: Iterable[str] = (), env: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """Allow-list entries from ``extra`` plus the environment variable, order kept, no repeats."""
    source = os.environ if env is None else env
    listed = [part.strip() for part in source.get(ALLOWLIST_ENV, "").split(",") if part.strip()]
    return tuple(dict.fromkeys([*extra, *listed]))


def settings_reader(factory: UowFactory) -> SettingsReader:
    """A reader over ``factory`` that looks at the setting tables again every few seconds.

    A worker runs beside a server (another process, so no shared bus); the short expiry is what
    makes a setting change reach it without a restart.
    """
    return SettingsReader(conn_factory_from(factory), max_age_s=READER_MAX_AGE_S)


def egress_from_settings(
    reader: SettingsReader,
    allow_hosts: Iterable[str] = (),
    *,
    resolver: Resolver | None = None,
) -> Callable[[], EgressPolicy]:
    """A function that returns the egress policy in force, read from the settings each time.

    The allow-list is the entries of ``allow_hosts`` and ``TL_WEBHOOK_ALLOWLIST`` (the operator's
    flags for this process, via ``allowlist_from``) followed by the company-wide setting
    ``webhooks.egress.allowlist`` (``reader.get``), without repeats, in that order. ``resolver``,
    when given, is the policy's resolver (tests); otherwise the policy keeps its default.
    """
    operator = allowlist_from(allow_hosts)

    def policy() -> EgressPolicy:
        configured = [str(entry) for entry in reader.get(EGRESS_KEY)]
        entries = tuple(dict.fromkeys([*operator, *configured]))
        return EgressPolicy(entries) if resolver is None else EgressPolicy(entries, resolver)

    return policy


def retry_from_settings(reader: SettingsReader) -> Callable[[], RetryPolicy]:
    """A function that returns the retry policy in force: ``RetryPolicy(max_hours=<the setting
    webhooks.retry.max_hours as a float>)``, read through ``reader`` each time; every other number
    of the policy keeps its default.
    """

    def policy() -> RetryPolicy:
        return RetryPolicy(max_hours=float(reader.get(RETRY_KEY)))

    return policy


def make_engine(
    factory: UowFactory,
    *,
    allow_hosts: Iterable[str] = (),
    transport: Transport | None = None,
    retry: RetryPolicy | None = None,
    worker_id: str | None = None,
    reader: SettingsReader | None = None,
    resolver: Resolver | None = None,
    clock: Clock = utc_now,
) -> DeliveryEngine:
    """A delivery engine whose egress allow-list and retry window follow the settings.

    ``allow_hosts`` and ``TL_WEBHOOK_ALLOWLIST`` add to ``webhooks.egress.allowlist``; an explicit
    ``retry`` policy wins over ``webhooks.retry.max_hours``. ``reader`` defaults to
    :func:`settings_reader`; ``resolver`` and ``clock`` are for tests.
    """
    source = reader if reader is not None else settings_reader(factory)
    return DeliveryEngine(
        factory,
        transport if transport is not None else HttpxTransport(),
        egress=egress_from_settings(source, allow_hosts, resolver=resolver),
        retry=retry if retry is not None else retry_from_settings(source),
        worker_id=worker_id,
        clock=clock,
    )


def make_dispatcher(factory: UowFactory) -> Dispatcher:
    return Dispatcher(factory)
