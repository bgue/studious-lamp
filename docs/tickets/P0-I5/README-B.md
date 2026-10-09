# Increment plan — P0-I5 workstream B: Outbox, webhooks, event catalog

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §18.2 (integration points, `SubscriptionFilter`), §18.3 (event catalog, CloudEvents envelope, payload modes), §18.4 (outbound webhooks), §19.1 to §19.2 (URIs, LinkML sketch), §30.5 (`webhooks.retry.max_hours`, `webhooks.egress.allowlist`)
Branch: `p0/i5b` (integration branch `p0/i5`; trunk `claude/wizardly-allen-m2v96s`). Ticket branches `p0/i5b-t<nn>-<slug>`. Fanout: `docs/tickets/P0-I5/FANOUT.md` (contracts C1 to C3).

## Objective
Every committed event is written to a transactional outbox by a projector that handles all event types, and is delivered as a signed
CloudEvents 1.0 webhook to the subscriptions whose filter selects it. Delivery is at-least-once with per-subject ordering (event N+1 of
a record never goes out before N is delivered or dead-lettered) and parallel across subjects, exponential backoff with jitter capped by
`webhooks.retry.max_hours`, a dead-letter queue, replay by `seq` range or time range, redrive of dead letters, auto-disable after
sustained failure, secret rotation with overlap, and an egress policy (SSRF allow-list with DNS pinning). The event catalog (JSON Schema
per event type, sample payloads, an AsyncAPI 3 document and a browsable page) is generated from LinkML under the codegen drift check, and
contract tests validate delivered payloads against it. `tl webhook add|ls|test|replay|dlq` drives it from the command line.
Out of scope for Phase 0 (follow-ups listed at the end): batching, rate limits, mTLS, per-company egress lists, JSON-LD `@context`,
restricted-confidentiality classes (a hook forces `thin`), owner notifications beyond the `Disabled` event, TUI and web screens for the
delivery log, a real HTTP receiver service in `tl-api`.

## Demo
```
just demo P0-I5
```
`dev/demos/P0-I5.sh` builds a temporary ledger, starts the dev receiver on 127.0.0.1 (allow-listed), subscribes with a filter
(`Workflow.Transitioned` into `Issued`, delta mode), commits matching and non-matching events, runs the worker, and prints the receiver's
verified deliveries (signature checked with the secret, event ids, `tlseq`); then it replays a `seq` range and shows the receiver
deduplicating on the event id. It also shows a failing endpoint going through retries to the DLQ and a redrive.

## Design decisions (supervisor)
| # | Decision | Why |
|---|---|---|
| D1 | The engine lives in `tl_core.webhooks` (SQLAlchemy Core and a `Transport` Protocol); only `transport.py` imports `httpx`. New dependency: `httpx` in `tl-core` | `tl-api` is an empty stub and the CLI must run the same code; keeping the engine in `tl_core` keeps it dialect-neutral for WS-A's Postgres UoW |
| D2 | The outbox is one global row per event (`outbox_events`, projector `outbox`, `handles_all`, registered last in `default_registry`). Fan-out to subscriptions is a separate step (`Dispatcher`) that writes `wh_delivery` rows | A projector must be deterministic and rebuildable; per-subscription rows would depend on subscription state. The event is still never missed: the row commits with the event |
| D3 | A subscription is a ledger stream (`core.WebhookSubscription`, events `WebhookSubscription.Created / Updated / Disabled / Enabled / SecretRotated`) projected into `cur_webhook_subscription`. Secrets live in `wh_secret`, never in events or logs; events carry `secret_id` only | Config changes are auditable and replicate with the ledger; a secret in an immutable ledger could never be removed |
| D4 | Delivery attempts, outcomes and health are **operational rows** (`wh_delivery`, `wh_attempt`, `wh_health`, `wh_cursor`), not ledger events. The spec's `Webhook.Delivered / Failed` ops events (03 section 8) are not written. A dead-letter is in the DLQ table; auto-disable is a `WebhookSubscription.Disabled` event | One event per attempt would amplify writes and, for a `*` subscription, feed back on itself. The decision is reported to the orchestrator as a deviation from 03 section 8 |
| D5 | The ordering key is the **subject**: the record an event is about (link events: the `from` record; file events: the file's record; numbering: the numbered record; otherwise the stream) | The brief orders "per subject (record)"; a link event's stream is the link |
| D6 | A delivery's body is built once, when the delivery row is created (payload mode, confidentiality hook, immediate links, record projection for `full`), and re-sent unchanged on every retry. The signature and timestamp are redone per attempt | Receivers see one stable message per event id; a 20-hour-old retry still passes a 5-minute timestamp window |
| D7 | `data.detail` (the ledger payload) is added to delta and full envelopes, and `datacontenttype` is `application/json` (no `@context` yet) | Events such as `File.Uploaded` and `Workflow.Transitioned` carry facts that are not field changes; claiming JSON-LD without a context document would be false |
| D8 | `Pset.ValuesSet` changes are `[null, new]`: the event does not carry the old value | Documented in the catalog; a versioned reader can fill it later |
| D9 | Claims use a lease taken by compare-and-set `UPDATE`; no `SKIP LOCKED`. The dispatcher re-reads `lag_window` rows before its cursor (default 0 on SQLite) and the unique `(subscription, dedupe key)` index drops repeats | Works unchanged on SQLite and Postgres; answers LEARNINGS L-P0-I4-A2 without a second mechanism |
| D10 | A subscription receives events with `active_from_seq < seq <= active_until_seq` (creation or enable to disable). Events missed while disabled are recovered by replay | No surprise flood when a subscription is re-enabled after weeks |
| D11 | Egress: public addresses only unless the host (name, `host:port`, IP or CIDR) is on `webhooks.egress.allowlist`; `http` only for allow-listed hosts; DNS resolved once per attempt and the IP pinned; redirects never followed. A refusal dead-letters at once (`egress_denied`) | Brief 18.4 and 30.5; the dev receiver is allow-listed explicitly in dev and tests |
| D12 | Retry: base 5 s, factor 2, cap 1 h, "equal jitter" (50 percent to 100 percent of the ceiling), deadline `created_at + webhooks.retry.max_hours` (24 h), `Retry-After` honoured up to the cap, `410 Gone` dead at once. Auto-disable at 5 dead letters since the last success or 72 h failing. All constants until P0-I8 settings; `RetryPolicy.from_settings` is the plug point | Brief 18.4 "~24 h"; thresholds are documented defaults |
| D13 | Restricted confidentiality: `ConfidentialityPolicy` (`forced_mode`, `allows`) in `envelope.py`, default open, applied before any body is built; a policy may lower the mode, never raise it | Brief 18.3; classes arrive in Phase 1 |
| D15 | `wh_secret` holds signing secrets in plaintext, which HMAC needs. Accepted for Phase 0 dev only. Before any non-dev deployment wrap them with envelope encryption under a per-company KMS key (brief 24.1); this is a human-gate follow-up next to ADR-0005 | Secrets must never be in the ledger or logs; at-rest protection needs a key service that does not exist yet |
| D14 | The record selector of a filter is a query-language expression evaluated against the subject record's current state at dispatch time | Cheap and uses the P0-I4 compiler; point-in-time matching is a follow-up |

## Supervisor-built pieces (in order)
REVIEW-SUPERVISOR-PIECES: items 2 to 8 are in the Sonnet-authored list (webhook signing, outbox delivery ordering) or are security code (egress) and need orchestrator or human review before WS-B merges.

| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| 1 | `handles_all` support in `InMemoryRegistry` / `Projector` docs | Registry contract, FANOUT C1 | orchestrator | built |
| 2 | LinkML: `integration.yaml` (SubscriptionFilter, WebhookSubscription, CloudEvent), `outbox.yaml` (outbox and `wh_*` tables), `events.yaml` (one payload class per event type); regenerated artefacts | `schema/**` (see SCHEMA_APPROVALS) | orchestrator | built |
| 3 | `OutboxProjector`, subject resolution, changes flattening | Outbox, FANOUT C1 | orchestrator | built |
| 4 | `signing.py` Standard Webhooks (verified against the published reference vector) | Webhook signing, 01 section 3 | orchestrator | built |
| 5 | `Dispatcher` fan-out, replay, redrive; `DeliveryEngine` claim / attempt / settle; `retry.py` | Delivery ordering, 01 section 3 | orchestrator | built |
| 6 | `egress.py` (SSRF) and `transport.py` (pinned IP, no redirects) | Security | orchestrator | built |
| 7 | `subscriptions.py` (commands, secrets, rotation overlap) and the subscription projector | Secrets | orchestrator | built |
| 8 | Envelope builder, payload modes, confidentiality seam | Contract used by every consumer | orchestrator | built |
| 9 | Catalog generator core (`tl_schema.generators.catalog`) and the generated files | Generator logic, 01 section 7 | reviewer | planned (round 2) |
| 10 | `tl_adapters.sqlite.factory.SqliteUowFactory` | Adapter-boundary helper; WS-A provides the same call shape for Postgres | reviewer | built |
| 11 | Outbox and delivery parity tests after WS-A lands | Needs `p0/i5` | reviewer | planned (after WS-A) |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I5-T20 | AsyncAPI 3 document builder (pure function) | haiku | pieces 9 types | merged | merged (1 review round); operation-key collisions raise ValueError, added by the supervisor with a new test file |
| P0-I5-T21 | Markdown catalog page renderer (pure function) | haiku | pieces 9 types | merged | merged (1 review round) |
| P0-I5-T22 | `WebhookFilter.matches_row` | haiku | piece 2, 3 | merged | merged (1 review round) |
| P0-I5-T23 | Dev webhook receiver (verifies signatures, dedupes, scripted failures) | haiku | piece 4 | merged | merged (1 review round) |
| P0-I5-T24 | Worker loop: `WebhookWorker` (threads, dispatch plus deliver cycles) | haiku | piece 5 | planned (round 2) | |
| P0-I5-T25 | `tl webhook add\|ls\|test\|replay\|dlq` | haiku | pieces 5, 7, T24 | planned (round 2) | |
| P0-I5-T26 | Contract tests: delivered payloads against the catalog | haiku | piece 9 | planned (round 2) | |

### Haiku-ability checklist (01-tiers.md section 6)
| Ticket | 1 files (at most 6) | 2 interfaces in repo | 3 test or commands | 4 size (400 lines, 5 files) | 5 avoids Sonnet table | 6 no schema, deps, interface change | 7 verifiable | Reference check |
|---|---|---|---|---|---|---|---|---|
| T20 | 3 | yes | provided, 11 tests | about 110 lines, 2 files | yes | yes | yes | passes ruff, pyright, tests |
| T21 | 3 | yes | provided, 11 tests | about 110 lines, 2 files | yes | yes | yes | passes tests; ruff clean after format |
| T22 | 3 | yes | provided, 31 tests | about 40 lines, 2 files | yes (a subscription filter, not a confidentiality filter) | yes | yes | passes ruff, pyright, tests |
| T23 | 3 | yes | provided, 9 tests | about 170 lines, 2 files | yes (uses `verify`, does not sign) | yes | yes | passes ruff, pyright, tests |

## Order of work
1. Round 1 (this relay): plan, registry extension, LinkML, outbox projector, signing, egress, retry, dispatcher, delivery engine, subscriptions, envelope, tests for each; tickets T20 to T23 with provided tests verified against scratch references.
2. Round 2: catalog generator core and generated files; T24 to T26 (worker, CLI, contract tests); query helpers for the CLI.
3. After WS-A lands in `p0/i5` (the orchestrator tells me): merge it, add parity tests for the outbox and the delivery tables.
4. Demo script, runbook, READMEs and AGENTS.md, learnings, report `docs/reports/P0-I5.md`.

## Risks and escalation triggers
- WS-A's Postgres UoW must run the registry exactly as SQLite's does (C2) and provide a `UowFactory` with the same call shape as `SqliteUowFactory`; if either differs, escalate as a cross-workstream contract change.
- JSONB columns return parsed values on Postgres and text on SQLite; the webhook code reads JSON through `rows.load_json`. `services.queries._envelope` still calls `json.loads` on `psets_json` (full-mode bodies use `get_record_by_id`); WS-A owns that fix.
- A schema change in the catalog events shifts the generated file list; two tests enumerate it (L-P0-I3-3).
- Escalate if a restricted-confidentiality rule is needed before Phase 1, or if the orchestrator rejects D4.

## Blocked / Decision
(none yet)

## Follow-ups (candidate next-increment tickets)
Human gate: envelope-encrypt `wh_secret` under per-company KMS keys before any non-dev deployment (D15, next to ADR-0005).
Batching (single or N / T seconds), per-subscription rate limit, mTLS, per-company egress lists, JSON-LD `@context`, point-in-time `record` for `full` mode, `old` values for `Pset.ValuesSet`, owner notification channel for auto-disable, delivery-log screens (TUI and web), receiver service in `tl-api`, `Webhook.*` ops events if ever wanted, saved-query / module / correspondence-domain selectors, hashtag events once `Feed.*` exists, an index on `wh_delivery (subscription_id, subject_id, status)` if the 100k measurement needs it.
