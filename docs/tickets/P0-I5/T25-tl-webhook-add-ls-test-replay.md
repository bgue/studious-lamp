# P0-I5-T25 — `tl webhook add | ls | test | replay`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (services, helpers, the stub, the registration in `main.py` and the provided test are on the base branch)
Branch: `p0/i5b-t25-webhook-cli`

## Goal
Four `tl webhook` subcommands call the webhook services and print: `add` creates a subscription and prints its id and signing secret (once),
`ls` lists subscriptions, `test` sends a signed catalog sample to a subscription's URL, `replay` re-sends a `seq` range or a time range. The
options, helpers and registration exist in the stub; the four command bodies raise `NotImplementedError`. A provided test file (10 tests)
must pass. The CLI holds no rules (`packages/tl-cli/AGENTS.md`): every command makes one service call and prints.

## Brief references (pasted)
> **18.4 Outbound webhooks.** Subscription record: owner, target URL, filter (18.2), payload mode, event schema version pin, secret(s),
> status, expiry. Security: HMAC-SHA256 signatures (Standard Webhooks headers). Secret rotation with overlap. Egress allow-list per
> company. Replay: replay by `seq` range, time range, or DLQ selection. Testing: "Send test event" with sample payload from the catalog.

### Specification (the provided test checks it)
Common: every command opens a factory with `with factory(ctx) as opened:` (helper from `tl_cli.webhook_common`, it disposes the engine),
wraps the service calls in `with service_errors():` (helper: a `ServiceError`, `LookupError`, `ValueError` or pydantic `ValidationError`
becomes `error: <message>` on stderr and exit code 1), and resolves the scope with `scope_of(project, company)` (helper: exactly one of
`--project` and `--company`, else `error: give exactly one of --project <ID> and --company`). Stdout lines are `name value`
pairs unless stated; stderr carries `error:` lines and hints.

- `add`: `scope = scope_of(project, company)`. Build the filter dict from the options that were given (skip `None` and empty lists):
  `event_types` (from `--event-type`), `record_selector` (`--selector`), `record_ids` (`--record-id`), `changed_fields`
  (`--changed-field`), `transitions` (`--transition`), `link_relations` (`--link-relation`), `file_slots` (`--file-slot`), `hashtags`
  (`--hashtag`), `scope_selector` (`--scope-selector`). Open a write unit of work (`with opened() as uow:`), call
  `create_subscription(uow, CreateWebhookSubscription(actor=ACTOR, source=SOURCE, scope=scope, name=name, target_url=url,
  filter=<dict>, payload_mode=mode, expires_at=<datetime or None>))`. `--expires` is an ISO-8601 time parsed with
  `datetime.fromisoformat`; a time without an offset is UTC (`_moment` is written for you). Print `subscription <id>`,
  `secret_id <id>`, `secret <whsec_...>` on stdout and, on **stderr**, `keep the secret: it is not shown again`. Validation
  (mode, URL, filter, selector, transition syntax) is the service's: let its errors surface through `service_errors`. An unparseable
  `--expires` also becomes `error:` (it is a `ValueError`).
- `ls`: with `--project` or `--company` filter by that scope, with neither list everything (`scope_of` only when one of them is given).
  Open a read unit of work (`opened(readonly=True)`), call `queries.list_subscriptions(uow, scope_or_None)`, and print one line per
  subscription of tab-separated `subscription_id, status, payload_mode, name, target_url, delivered_total, pending, dead`. No header, no
  secret.
- `test`: call `make_engine(opened, allow_hosts=allow_host or ()).send_test(subscription_id, event_type)` (from
  `tl_core.webhooks.wiring`; it adds `TL_WEBHOOK_ALLOWLIST` from the environment). Print `event_id <id>`, `status <code or ->`,
  `latency_ms <n>`. Then: if `result.blocked`, fail with `the target is blocked by the egress policy; allow-list it with --allow-host or
  TL_WEBHOOK_ALLOWLIST`; else if `not result.ok`, fail with `result.error or f"the receiver answered HTTP {result.status}"`
  (`fail(...)` from `webhook_common` prints `error:` and exits 1). An unknown subscription or event type surfaces as `error:` through
  `service_errors` (`LookupError` / `KeyError`).
- `replay`: the call is either a seq range (`--from-seq` and `--to-seq`, both) or a time range (`--since` and `--until`, both); any other
  combination (none, one half, or both ranges) is `fail("give --from-seq and --to-seq, or --since and --until")`. Do that check **before**
  opening anything. Then `make_dispatcher(opened)` and `.replay(subscription_id, from_seq, to_seq)` or
  `.replay_between(subscription_id, _moment(since), _moment(until))`; print `replayed <count>`.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- `CliRunner.invoke` catches exceptions and returns them on the result: a command that crashes still "runs". The provided tests assert
  `exit_code` and `result.exception`; make your commands pass them honestly.
- pyright is `standard` for `tl-cli`; ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints
  "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Remove the `STUB (P0-I5-T25)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/webhook_common.py (use as is)
ACTOR = "user:dev"; SOURCE = "cli"
def fail(message: str) -> NoReturn: ...                       # prints "error: <message>" to stderr, exit 1
def factory(ctx: typer.Context) -> ContextManager[SqliteUowFactory]: ...   # opened(), opened(readonly=True) give a unit of work
def service_errors() -> ContextManager[None]: ...
def scope_of(project: str | None, company: bool) -> str: ...
```
```python
# tl_core.webhooks (use as is)
def create_subscription(uow, cmd: CreateWebhookSubscription) -> SecretIssued: ...   # .subscription_id .secret_id .secret
class CreateWebhookSubscription(Command):   # actor, source, scope + below
    name: str; target_url: str; filter: dict[str, Any] = {}; payload_mode: str = "thin"
    owner: str | None = None; integration_app: str | None = None; expires_at: datetime | None = None
def list_subscriptions(uow, scope: str | None = None) -> list[dict[str, Any]]:      # tl_core.webhooks.queries
    # keys: subscription_id status payload_mode name target_url delivered_total pending dead ...
def make_engine(factory, *, allow_hosts: Iterable[str] = ()) -> DeliveryEngine: ...  # tl_core.webhooks.wiring
def make_dispatcher(factory) -> Dispatcher: ...
DeliveryEngine.send_test(subscription_id: str, event_type: str = "Record.Created") -> TestResult
    # TestResult: event_id status ok latency_ms error excerpt blocked
Dispatcher.replay(subscription_id, from_seq, to_seq) -> int
Dispatcher.replay_between(subscription_id, since: datetime, until: datetime) -> int
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/AGENTS.md`
- `packages/tl-cli/src/tl_cli/webhook.py`
- `packages/tl-cli/src/tl_cli/webhook_common.py`
- `docs/tickets/P0-I5/provided/test_cli_webhook.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/webhook.py` (edit)
- `packages/tl-cli/tests/test_cli_webhook.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T25.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_cli_webhook.py.txt packages/tl-cli/tests/test_cli_webhook.py`
2. Implement the four bodies and `import` what you use; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_webhook.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_cli_webhook.py.txt packages/tl-cli/tests/test_cli_webhook.py
```
Expected: 10 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

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
