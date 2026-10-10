# P0-I8-T06 — Webhook egress allow-list and retry window follow the settings

Status: merged
Tier: haiku
Labels: core
Depends on: — (the engine takes policy providers; the reader is on the base)
Branch: `p0/i8a-t06-webhook-settings`

## Goal
`webhooks.egress.allowlist` and `webhooks.retry.max_hours` drive the delivery engine of the CLI and the demo: `wiring.make_engine` builds an engine whose egress policy and retry policy are read from the settings each time they are used (through a `SettingsReader` that looks at the tables again every 5 seconds), so a change reaches a running `tl webhook run` with no restart. The operator's `--allow-host` flags and `TL_WEBHOOK_ALLOWLIST` still add to the allow-list; an explicit `retry` argument still wins. A provided test file (9 tests) must pass and the existing webhook tests must stay green.

## Brief references (pasted)
> **30.5** `webhooks.retry.max_hours` = 24; `webhooks.egress.allowlist` = [] ("Dangerous to widen"). **30.3** Changes apply live.
> **18.4** Webhook delivery retries with backoff until a deadline (`created_at + max_hours`), then dead-letters; the egress guard allows public addresses over https only, plus the allow-list.

### Specification
The whole target of `wiring.py` is below (reference shapes with their docstrings); `allowlist_from`, `make_dispatcher` and the imports it already has stay. The engine already accepts `egress=` and `retry=` as a policy **or a function returning one** and reads it once per attempt (`DeliveryEngine`), and it falls back safely if the function raises; you only build the functions. `reader.get(key)` returns the effective company value (no project: webhooks are company-wide). Keep the SSRF rules of `egress.py` untouched; this ticket changes where the allow-list comes from, not how it is applied.

`clock`, `resolver` and `reader` are parameters of `make_engine` so tests can control time, DNS and the settings read; production callers (`tl_cli/webhook.py`, the demo) pass none of them and need no change.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/webhooks/wiring.py` (the stub you complete):
```python
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
```
```python
# Target shape: the new parts of wiring.py (reference; write your own, keep these signatures and docstrings)
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
```
```python
# already implemented (read only)
# SettingsReader(conn_factory, *, clock=..., max_age_s=30.0, monotonic=...); .get(key, *, project=None, user=None) -> value
# conn_factory_from(factory) -> ConnFactory     # factory(readonly=True) -> context manager yielding a UnitOfWork
# EgressPolicy(allowlist: tuple[str, ...] = (), resolver=system_resolver)      # frozen dataclass
# RetryPolicy(max_hours=24.0, base_s=5.0, factor=2.0, max_delay_s=3600.0, jitter=0.5)
# DeliveryEngine(open_uow, transport, *, egress=policy_or_function, retry=policy_or_function, health=None, clock=utc_now, rng=None, worker_id=None, ...)
# tl_core.webhooks.base: Clock, UowFactory, utc_now
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/webhooks/wiring.py`
- `packages/tl-core/tests/test_webhook_wiring.py` (the existing test of `allowlist_from`; must stay green)
- `docs/tickets/P0-I8/provided/t06-test_webhook_settings_wiring.py.txt`
- `tests/webhooks/world.py` (what the provided test builds on; read only)
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/webhooks/wiring.py` (edit)
- `tests/webhooks/test_settings_wiring.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T06.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t06-test_webhook_settings_wiring.py.txt tests/webhooks/test_settings_wiring.py`
2. Add `settings_reader`, `egress_from_settings`, `retry_from_settings`, the two key constants and the reader interval; extend `make_engine` as shown.
3. Run the acceptance commands (also `uv run pytest packages/tl-cli/tests/test_cli_webhook.py packages/tl-cli/tests/test_cli_webhook_run.py -q`), write the report, commit both.

## Acceptance
```
uv run pytest tests/webhooks/test_settings_wiring.py packages/tl-core/tests/test_webhook_wiring.py -q
uv run pytest tests/webhooks packages/tl-cli/tests/test_cli_webhook.py packages/tl-cli/tests/test_cli_webhook_ops.py packages/tl-cli/tests/test_cli_webhook_run.py -q
just check
```
Expected: 9 new tests pass; every existing webhook and CLI webhook test stays green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Note that this is a security-relevant change (where the egress allow-list comes from); say that no rule of `egress.py` changed.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or an existing webhook test fails because of your change and the fix would be outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
Reviewed in a fresh context: pass. Merged into p0/i8a as 9fe5587.
