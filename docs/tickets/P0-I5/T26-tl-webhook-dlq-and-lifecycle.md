# P0-I5-T26 — `tl webhook dlq ls | dlq redrive | disable | enable | rotate-secret`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (services, helpers, the stub and the provided test are on the base branch; the test does not use T25's commands)
Branch: `p0/i5b-t26-webhook-ops-cli`

## Goal
Five more `tl webhook` subcommands call the webhook services and print: `dlq ls` lists dead-lettered deliveries, `dlq redrive` re-enqueues
them, `disable` and `enable` pause and resume a subscription, `rotate-secret` issues a new signing secret (printed once) while the old one
keeps signing for an overlap. `register(app)` and all options exist in the stub; the five bodies raise `NotImplementedError`. A provided
test file (6 tests) must pass.

## Brief references (pasted)
> **18.4 Outbound webhooks.** Security: HMAC-SHA256 signatures (Standard Webhooks headers). **Secret rotation with overlap.**
> Retries: exponential backoff with jitter over ~24 h, then dead-letter queue. Auto-disable after sustained failure, with owner notified.
> Replay: replay by `seq` range, time range, or DLQ selection. Receivers dedupe on the event `id`.

### Specification (the provided test checks it)
Same conventions as T25: `with service_errors(), factory(ctx) as opened:` (helpers in `tl_cli.webhook_common`), scope from
`scope_of(project, company)` where the command takes `--project` / `--company`. The command functions are nested in `register`, so the
imports go at the top of the module.

- `dlq ls`: `opened(readonly=True)` unit of work, `queries.list_dlq(uow, subscription)`; print one line per row of tab-separated
  `delivery_id, subscription_id, seq, event_id, attempts, last_status, dead_reason, dead_at`.
- `dlq redrive <subscription_id> [--delivery ID]...`: `Dispatcher(opened).redrive(subscription_id, delivery)` (`delivery` is the list or
  `None` for all); print `redriven <count>`.
- `disable <subscription_id>`: `scope = scope_of(project, company)`, a write unit of work, `disable_subscription(uow,
  DisableWebhookSubscription(actor=ACTOR, source=SOURCE, scope=scope, subscription_id=subscription_id))`; print `disabled <id>`.
- `enable <subscription_id>`: same with `enable_subscription` / `EnableWebhookSubscription`; print `enabled <id>`.
- `rotate-secret <subscription_id>`: `rotate_secret(uow, RotateWebhookSecret(actor=ACTOR, source=SOURCE, scope=scope,
  subscription_id=subscription_id, overlap_hours=overlap_hours))`; print `secret_id <id>` and `secret <whsec_...>` on stdout and
  `keep the secret: it is not shown again` on **stderr**. A negative overlap is refused by the command model (a pydantic
  `ValidationError`, which `service_errors` turns into `error:`).
- The services raise for an unknown subscription, a wrong scope, or a subscription already in the requested state; `service_errors` prints
  them. Do not catch anything yourself.
- **Name clash:** the stub names the rotate command function `rotate_secret_command` so it does not shadow the service `rotate_secret` you
  import. Keep the names.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- `CliRunner.invoke` catches exceptions and returns them on the result: the provided tests assert `exit_code` and `result.exception`.
- pyright is `standard` for `tl-cli`; ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints
  "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Remove the `STUB (P0-I5-T26)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/webhook_common.py (use as is)
ACTOR = "user:dev"; SOURCE = "cli"
def fail(message: str) -> NoReturn: ...
def factory(ctx: typer.Context) -> ContextManager[SqliteUowFactory]: ...   # opened(), opened(readonly=True) give a unit of work
def service_errors() -> ContextManager[None]: ...
def scope_of(project: str | None, company: bool) -> str: ...
```
```python
# tl_core.webhooks (use as is)
tl_core.webhooks.queries.list_dlq(uow, subscription_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]
    # keys: delivery_id subscription_id seq event_id subject_id attempts last_status last_error dead_at dead_reason
Dispatcher.redrive(subscription_id: str, delivery_ids: Sequence[str] | None = None) -> int     # tl_core.webhooks.dispatch
tl_core.webhooks.subscriptions:
    class DisableWebhookSubscription(SubscriptionCommand): reason: str = "owner"; detail: str | None = None
    class EnableWebhookSubscription(SubscriptionCommand): ...
    class RotateWebhookSecret(SubscriptionCommand): overlap_hours: float = 24.0      # ge=0
    class SubscriptionCommand(Command): subscription_id: str                          # Command: actor, source, scope
    def disable_subscription(uow, cmd) -> SubscriptionResult: ...
    def enable_subscription(uow, cmd) -> SubscriptionResult: ...
    def rotate_secret(uow, cmd) -> SecretIssued: ...                                  # .secret_id .secret
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/AGENTS.md`
- `packages/tl-cli/src/tl_cli/webhook_ops.py`
- `packages/tl-cli/src/tl_cli/webhook_common.py`
- `docs/tickets/P0-I5/provided/test_cli_webhook_ops.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/webhook_ops.py` (edit)
- `packages/tl-cli/tests/test_cli_webhook_ops.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T26.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_cli_webhook_ops.py.txt packages/tl-cli/tests/test_cli_webhook_ops.py`
2. Implement the five bodies and the imports; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_webhook_ops.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_cli_webhook_ops.py.txt packages/tl-cli/tests/test_cli_webhook_ops.py
```
Expected: 6 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
