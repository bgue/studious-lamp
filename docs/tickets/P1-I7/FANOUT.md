# Fanout plan: P1-I7 (integration layer and record threads)

Status: active. Both workstreams start now from `p1/i7`, in parallel with P1-I4 and P1-I5.
Orchestrator session: 2026-10-17
Plan: `docs/build-spec/07-phase1-plan.md` Increment 7. Brief: §18.5 (inbound), §18.7 (actions), §18.8 (rules), §18.9
(enrichment), §18.13 (governance, kill switch), §19.2 and §19.3 (integration classes), §21.5 (threads with dispatch),
§10.6 sketch 13. Owner decisions: ADR-0008 (decision 6 delegation; decision 8: no model call, no spend). Access:
ADR-0011, ADR-0013, ADR-0014 section 8. Records and modules: ADR-0010 and its addenda.

## Objective
External systems, rules and enrichers can act on the ledger through one guarded seam, and people can discuss a
record and dispatch work from its thread. An admin registers actions, rules, inbound endpoints and enrichers; each
runs as a declared service actor that can only produce allow-listed commands within a declared access, bounded per
event and per request; every write is ledgered with a server-set source. A thread is one stream per record; a
slash command is parsed, previewed with the caller's own access and run as existing commands.

## Exit criteria
- [ ] **Contract.** `tl_core/integration/contract.py` and `tl_core/threads/contract.py` are implemented as written.
  The mapping runtime passes `check_mapping_runtime_contract`; the `job` and `webhook` executors pass
  `check_executor_contract`; the first enricher passes `check_enricher_contract`; the dispatch parser passes
  `check_parser_contract`; every planner test calls `check_preview_shape` (`tests/contract/test_integration_contract.py`,
  `tests/contract/test_dispatch_contract.py`).
- [ ] **Records.** `IntegrationApp`, `ActionDefinition`, `ActionInvocation`, `Rule`, `InboundEndpoint`, `Enricher`,
  `EnrichmentValue` and `ThreadMessage` are LinkML classes with the contract's slot names, each record on a stream of
  its own (D13). Their events are in the catalog. Webhooks deliver `Action.Requested/Completed/Failed`,
  `Enrichment.Proposed/Accepted`, `Thread.MessagePosted` and `Thread.Dispatched`.
- [ ] **Actions.** Define, invoke, run by `job` or `webhook`, with the lifecycle `Requested → Running →
  Completed/Failed` ledgered and linked to the targets. The webhook executor is refused private, loopback, link-local
  and metadata addresses before any connect (D8).
- [ ] **Rules.** When/if/then; `act` and `propose`; causation depth limit; self-trigger and per-event budgets; dry run
  against history; kill switch (D7, D11).
- [ ] **Inbound.** HMAC-SHA256 (Standard Webhooks) and JWT (HS256 only); replay window; body cap; rate bound; fixed
  404 and 401; restricted, bounded mapping; key resolution; dry run; error queue with fix and retry (D4, D5).
- [ ] **Enrichment.** The `enrich.<enricher>` pset layer, proposed links, provenance, acceptance policy, review queue;
  the deterministic `doc_classifier` reaches its floor on the golden set (D6).
- [ ] **Threads.** Stream per record, messages, participants, settings; all eleven verbs parse; the Phase 1 targets
  preview and run with the caller's access; MCP `read_thread`, `post_thread_message`, `propose_dispatch`; TUI thread
  tab (D9, D10).
- [ ] **Security.** The reserved-identifier walk covers every new entry point (D2); the fresh-context security review
  of every item in D18 passed.
- [ ] **Demo.** `just demo P1-I7` on SQLite and Postgres (D20).
- [ ] **Gates.** `just check`, `just test`, the scoped parity runs of the touched packages, `just test-tui`.

## Workstreams
| WS | Name | Branch · worktree | Base | Supervisor builds | Tickets (plan IDs) |
|---|---|---|---|---|---|
| A | Integration: actions, rules, inbound, enrichment | `p1/i7a` · `/home/user/wt/p1-i7a` | `p1/i7` | see D15 | T01–T08; demo; increment report |
| B | Record threads with dispatch | `p1/i7b` · `/home/user/wt/p1-i7b` | `p1/i7` | see D15 | T09–T12 |

Each supervisor makes its own worktree and installs the workspace before anything else:

```
git worktree add -b p1/i7a /home/user/wt/p1-i7a p1/i7
cd /home/user/wt/p1-i7a && uv sync --all-packages
```

(`p1/i7b` and `/home/user/wt/p1-i7b` for WS-B.) Ticket branches are siblings, `p1/i7a-t02-<slug>` (L-P0-SETUP-10).

Learnings to read before planning (IDs in `docs/memory/LEARNINGS.md`):

| WS | Entries |
|---|---|
| Both | L-P0-I6A-1, L-P1-I3-4, L-P0-I8C-6, L-P1-I0A-19, L-P1-I0B-5, L-P0-I8-O1, L-P1-I3-5, L-P1-I3-12, L-P1-I1-9, L-P1-I3-3, L-P1-I2-1, L-P0-I8B-7, L-P1-I0A-21, L-P1-I0A-11, L-P0-I8A-7, L-P1-I0A-4, L-P1-I1-1, L-P1-I2-6, L-P1-I2-18, L-P1-I3-9, L-P1-I1-10, L-P1-I0B-3, L-P1-I3-8, L-P0-I5-B1, L-P1-I3-10, L-P1-I3-11, L-P1-I2-12, L-P1-I2-11, L-P1-I2-17 |
| A | L-P0-I5-O1, L-P0-I4-B6, L-P1-I0A-7, L-P1-I0A-8, L-P1-I0A-9, L-P1-I0A-14, L-P1-I0A-22, L-P1-I0B-9, L-P1-I2b-1, L-P1-I1-8, L-P1-I2-4, L-P1-I2-8, L-P1-I3B-7, L-P1-I3B-8, L-P0-I8A-9, L-P0-I1-11, L-P1-I3-13 |
| B | L-P0-I3-7, L-P1-I2b-3, L-P0-I8A-10, L-P1-I3-6, L-P0-TOUR-3, L-P1-I2b-6, L-P1-I2-9, L-P0-I4-B8, L-P1-I3-7, L-P1-I2b-2, L-P0-I8A-4, L-P1-I0A-22, L-P1-I1-8, L-P1-I2-8 |

## Shared contracts
- `packages/tl-core/src/tl_core/integration/contract.py`: access levels, `CommandRunner`, `PlannedCommand`,
  `Problem`, `RecordRef`, the reserved prefixes, `AUTOMATION_COMMANDS`, every bound; `ActionDefinition`,
  `InvokeAction`, `ActionRequest`, `ActionOutcome`, `ActionExecutor`, `ActionJob`; `Rule`, `RuleStep`, `RuleFiring`;
  `InboundEndpoint`, `MappedCommand`, `MappingOutcome`, `MappingRuntime`; `Enricher`, `EnrichmentSubject`,
  `EnrichmentResult`, `EnrichmentValue`.
- `packages/tl-core/src/tl_core/threads/contract.py`: stream and event names, settings keys, MCP tool names, the
  command-line grammar, `ParsedDispatch` and the per-verb argument models, `ParseProblem`, `DispatchParser`,
  `DispatchTarget`, `DispatchContext`, `DispatchPreview`, `DispatchOutcome`, `ThreadMessageView`, `DispatchPlanner`.
- `tests/contract/test_integration_contract.py` and `tests/contract/test_dispatch_contract.py`: conformance helpers
  and the rules the models enforce.
- WS-B imports `tl_core.integration.contract` (for `InvokeAction`, `PlannedCommand`, `CommandRunner`) and nothing
  else of WS-A. WS-A never imports `tl_core.threads`. Neither edits a contract file: a change is an escalation (D1).
- When the increment integrates, WS-A adds a pointer to both modules in `docs/build-spec/03-repo-and-toolchain.md` §7.

## Orchestrator decisions

### D1. Branches, base, ADRs, freezing
- Integration branch `p1/i7`; workstream branches `p1/i7a` and `p1/i7b` from its head when the supervisors start.
- ADR-0015 is P1-I4's and ADR-0016 is left to P1-I5. WS-A drafts **ADR-0017** "Integration layer: actions, rules,
  inbound endpoints, enrichment"; WS-B drafts **ADR-0018** "Record threads and dispatch". Both start as `proposed`;
  the orchestrator accepts them. If a number is taken at the trunk merge, WS-A renumbers and fixes the references.
- The two contract files are frozen. A supervisor that needs a change writes it under *Blocked* in its increment plan
  and escalates; the decision is logged at the end of this file.

### D2. Reserved identifiers (security)
- WS-A, in its first supervisor piece and before WS-B merges, extends `tl_core.services.reserved` with the contract's
  `RESERVED_SOURCE_PREFIXES` and `RESERVED_CORRELATION_PREFIXES`, so every existing command route, upload route and
  proposal refuses them from a client (the `request_model` validator, L-P1-I3-10), and adds `thread_dispatch` to
  `tl_core.services.links.SYSTEM_LINK_SOURCES` (an amendment to ADR-0010 second addendum item 3, recorded in ADR-0017).
- The server sets these, never a client and never a mapping or a rule step:

  | Path | `source` | `correlation_id` | `causation_id` | Link source |
  |---|---|---|---|---|
  | Inbound | `inbound:<app>/<endpoint>` | `inbound:<delivery id>` | none | `mapping` |
  | Rule | `rule:<key>@<version>/d<depth>` | the triggering event's | the triggering event id | `rule` |
  | Action | `action:<name>@<version>` | `action:<invocation id>` | the request event id | none |
  | Enrichment | `enricher:<name>@<version>` | the triggering event's, or new | the triggering event id | `enricher` |
  | Dispatch | `thread:<record id>` | `dispatch:<message id>` | the message event id | `thread_dispatch` |

- The enrichment layer `psets.enrich.*` stays unwritable by `SetPsetValues` (`READ_ONLY_ROOTS`, Phase 0); only the
  enrichment service's Python-only path writes it (D6).
- A mapping's or a rule step's `args` never name a field in `SERVER_SET_FIELDS`, at any depth (the contract models
  refuse it). The built command then runs its own model validation (including the NUL refusal).
- Each workstream adds one walking test: it lists every new entry point that takes client input (WS-A: inbound POST,
  inbound retry with a corrected payload, endpoint, rule and action definitions, rule dry run, `InvokeAction`, enrichment
  accept; WS-B: thread post, edit, dispatch preview and confirm, `propose_dispatch`, the MCP tools), asserts the count
  and a few known members first (L-P1-I3-11), then sends a reserved source, correlation id, link source and an
  `enrich.` pset to each and asserts the refusal.

### D3. Service actors and automation access
- Rules, inbound endpoints, enrichers and action executors act as `svc:<kind>-<slug>` actor strings
  (`SERVICE_ACTOR_RE`), not accounts. Each rule, endpoint and enricher declares `access`: `user` or `controller`
  (`AutomationAccess`). **Automation never runs an `admin` command in Phase 1.**
- A command automation would run must be (a) in `AUTOMATION_COMMANDS`, (b) in the record's own list (a rule's steps,
  an endpoint's `allowed_commands`), (c) covered by the declared access (`access_covers(declared,
  runner.access_of(type))`; `None` is refused), and (d) pass the module allow-lists and guards in the handler, as any
  client's command does. Automation passes `by_module=True` only to set its own link source.
- Rules in `propose` mode create proposals with the proposer `svc:rule-<key>`. `tl_core.services.proposals` widens its
  proposer pattern to that form only; accepting needs the command's access (ADR-0014 section 8). ADR-0017 records it.
- Long-running engines (rules worker, inbound worker, enrichment dispatcher, action jobs) read the record's enabled
  state and version and the kill switch per batch or per delivery, never once at start (L-P1-I0A-22).
- A service actor is cleared for no restricted confidentiality class: a rule does not match, an inbound key does not
  resolve, and an enricher does not run on a record of a restricted class. This is wired at the trunk merge, when
  P1-I5's filters are on the trunk (D17, D18).

### D4. Inbound webhooks (security; delegated gate "inbound signing")
Route `POST /in/{app}/{endpoint}`, checked in this order:
1. **Not accepting** (kill switch on, app disabled, endpoint unknown or disabled): 404 with `INBOUND_NOT_FOUND_BODY`,
   identical bytes and headers for every reason.
2. **Rate bound** before the body is read: the endpoint's `rate_per_minute`, a process-wide
   `INBOUND_GLOBAL_RATE_PER_MINUTE`, and a per-source bound keyed as in `tl_api.ratelimit` (last entry of
   `TL_TRUSTED_PROXY_HEADER`, IPv6 by /64, L-P1-I0A-14); more than `INBOUND_MAX_PENDING_PER_ENDPOINT` queued
   deliveries also refuses. 429 `rate_limited` with `Retry-After`. Process-local; the front-door limiter stays a
   release gate (ADR-0009).
3. **Body cap**: `Content-Length` first, then while reading (chunked too), at the endpoint's `max_body_bytes`
   (at most `INBOUND_HARD_MAX_BODY_BYTES`); 413 raised from the wrapped `receive` (L-P1-I0A-8).
4. **Verification**, both kinds constant-time on bytes:
   - `hmac_sha256`: the Standard Webhooks headers, verified by the existing `tl_core.webhooks.signing.verify`
     (HMAC-SHA256 over `id.timestamp.body`, up to two active secrets during a rotation, timestamp within
     `INBOUND_TOLERANCE_S` either way). Replay: the `webhook-id` is stored per endpoint in the operational table
     `int_replay` in the same transaction that queues the delivery; an id seen within `INBOUND_REPLAY_RETENTION_S` is
     refused. Older rows are pruned.
   - `jwt_hs256`: `Authorization: Bearer <token>` verified with PyJWT, `algorithms` fixed server side to
     `INBOUND_JWT_ALGORITHMS` (HS256 only, so `none` and algorithm confusion are refused), `audience` the endpoint path,
     required claims `INBOUND_JWT_REQUIRED_CLAIMS`, `exp - iat <= INBOUND_JWT_MAX_LIFETIME_S`, `iat` within the
     tolerance, `body_sha256` equal to the SHA-256 of the raw body, `jti` replay-checked in `int_replay`.
   - Every failure: 401 with `INBOUND_UNAUTHORIZED_BODY`. The reason goes to the server log as a fixed code and to a
     per-endpoint counter; never a header value, a claim or the body.
5. **Parse**: UTF-8 JSON, depth at most `INBOUND_MAX_JSON_DEPTH`; `RecursionError`, `ValueError` and hostile numbers
   are a fixed 422 `invalid_payload` (L-P0-I8A-9).
6. **Accept** (202 with the delivery id): the raw body is stored as an object (`inbound/<endpoint id>/<delivery id>`),
   then one write transaction writes the replay row, the operational `int_delivery` row, the job `inbound.map`
   (ADR-0014 queue) and `Inbound.Received` (delivery id, endpoint, SHA-256, size; never the payload or headers).
   An object left behind by a transaction that failed is swept by a reconcile pass (WS-A names it in its plan).
- **Secrets** live in the operational table `int_secret`, built like `wh_secret`: the text is returned once at create
  or rotate (the `SecretIssued` pattern), events carry `secret_id` only, rotation overlaps at most 24 h, nothing logs
  or echoes a secret. Operational tables are not archived: a restore re-issues secrets (runbook).
- **Worker** (`inbound.map`): evaluates the endpoint version the delivery was received under (D5), checks D3, resolves
  `{"$key": ...}` by record key and type within the endpoint's scope (not found or ambiguous: `key_not_found`;
  `external_ids` is not built in Phase 1), sets the D2 fields, and runs all commands in one unit of work through the
  runner as the service actor. Result: `Inbound.Applied` or `Inbound.Failed` (fixed code, bounded message); a failed
  delivery is the error queue. A `dry_run` endpoint plans and writes nothing but the delivery state.
- **Error queue**: admin only. `RetryInboundDelivery` re-runs a failed delivery through the same worker path with the
  current mapping, optionally with a corrected payload that is stored as a new object; the event names the admin and
  both hashes. **Dry run**: `DryRunInboundMapping` (admin) returns the planned commands for a sample or a stored
  delivery and writes nothing.
- `/in/*` is the only new route family without a session. The route-guard walker lists it as an explicit exception,
  with a test that every `/in/*` route refuses before reading past the cap and before verification succeeds.

### D5. Mapping language: restricted JSONata
- **Library: `jsonata-python` 0.7.0** (a pure Python port of jsonata-java; Apache-2.0; no dependencies; released
  2026-07-05), pinned `==0.7.0`. 0.7.1 (2026-10-10) is too recent; an upgrade is a ticket of its own. Not copyleft, no
  spend; the licence goes in APPROVALS.md and `dev/tools/check_licences.py` must pass.
- **Profile `jsonata-restricted@1`** (`MappingRuntime.check`): parse with the library, walk its AST (`Jsonata(expr).ast`)
  against an allow-list of node types; call only `MAPPING_ALLOWED_FUNCTIONS`; refuse function definitions and lambdas,
  regular expressions, partial application, `$eval`, `$now`, `$millis`, `$random` and higher-order functions;
  expressions at most `MAPPING_MAX_EXPRESSION_CHARS`. An endpoint stores a mapping only when `check` returns nothing.
- **Bounds** (`MappingRuntime.evaluate`): run in the ADR-0014 envelope (reuse `tl_core.derivation.envelope`, never a
  copy: a spawned child, scrubbed environment, `RLIMIT_AS` of `MAPPING_MAX_MEMORY_BYTES`, wall clock
  `MAPPING_MAX_SECONDS`, the process group killed on a breach), with the library's own time box
  (`MAPPING_TIMEBOX_MS`, `MAPPING_MAX_DEPTH`) inside. Input is the stored body; output is JSON bytes at most
  `MAPPING_MAX_OUTPUT_BYTES`, parsed in the parent (no pickle) into `MappingOutcome`. A breach is `limit`; a library
  error is `error` with the JSONata code and fixed text.
- **No network, no filesystem.** JSONata has no I/O function and the profile refuses `$eval`. The rlimits do not
  confine the filesystem or the network (ADR-0014 known limit); the risk register entry covers both uses.
- **Fallback**: if the licence gate or the security review rejects the library, the orchestrator decides on a
  declarative subset behind the same `MappingRuntime` protocol. A supervisor does not switch on its own.
- Rule steps do **not** use JSONata: their args are static JSON with `${binding}` placeholders (D7).

### D6. Enrichment
- **Namespace**: values live in the existing pset layer `psets.enrich.<enricher>.<property>` (`READ_ONLY_ROOTS` and
  `projection.pset.classify` already reserve it). An `Enricher` record declares its properties (name and kind) and the
  acceptance policy per property: `auto` (with a threshold, default `ENRICH_DEFAULT_AUTO_THRESHOLD`), `propose`
  (default) or `shadow`.
- **Values**: `EnrichmentValue` with provenance (enricher, version, confidence, inputs as record version and file
  hash, `model_ref`, time) in a projection `cur_enrichment_value`. Shadow values are stored and shown only in the
  evaluation report and to admins.
- **Accept and reject**: `AcceptEnrichment` writes the value into the enricher's layer through a Python-only path and
  runs the target type's `SetPsetValues` allow-list and guards (ADR-0010), so a closed type stays closed. It never
  writes an authoritative pset. `auto` accepts at once as `auto_accepted` by the enricher's service actor. Promoting a
  value to an authoritative field is the person's own `SetPsetValues` (the TUI pre-fills an edit).
- **Links**: a proposed link is a `SuggestLink` with link source `enricher`, accepted or declined through the
  existing link review.
- **Running**: an enrichment dispatcher follows the ledger with its own cursor and the enricher's `when` filter, plus
  `RunEnricher` on one record. Phase 1 enrichers are code shipped in the repository and run in process; a third-party
  enricher would run in the envelope (follow-up).
- **First enricher `doc_classifier`** (ADR-0008 decision 8; the plan's "via MCP client" is dropped): deterministic,
  `model_ref = None`. It reads the file facts (name, type, page count, title and author metadata) and the document
  title, proposes `doc_type` and `discipline` from a fixed keyword table checked against the sample company's code
  lists, and gives the confidence of the rule that matched. Golden set: at least 20 cases under
  `tests/golden/enrichment/` and an evaluation test that reports accuracy per property and fails below 0.8 on
  `doc_type`.

### D7. Rules engine
- **Off the write path**: a rules worker follows the ledger from the operational cursor `rule_cursor` in batches of
  `RULE_BATCH_EVENTS` (the webhook dispatcher's pattern). A rule never blocks or fails a person's write. Exactly-once
  effect: a firing row `rule_firing (rule id, rule version, event id)` is written in the same unit of work as the
  commands it runs.
- **When** reuses `tl_core.webhooks.filters.WebhookFilter` on events. **If** is a query-language expression on the
  subject record (compiled once per rule version). **Then** is `RuleStep` commands whose string args may hold
  `${name}` placeholders from `RULE_BINDINGS`, filled with `string.Template.safe_substitute` (never `str.format`).
- **Loop protection**: the depth is read from the triggering event's source (`rule:…/d<n>`; any other source is depth
  0). At `RULE_MAX_CAUSATION_DEPTH` the firing is `depth_limit` and runs nothing. A rule never fires on an event whose
  source names the same rule (`self_trigger`).
- **Budgets**: at most `RULE_MAX_RULES_PER_EVENT` matched rules per event (in key order), `RULE_MAX_STEPS` steps per
  rule and `RULE_MAX_COMMANDS_PER_EVENT` commands per event; the excess is recorded as `budget`.
- **Act or propose**: `act` runs all steps in one unit of work through the runner as the service actor; `propose`
  makes one proposal per command (D3). A refused, depth-limited or over-budget firing is a ledger event on the rule's
  stream (names in T01), so its owner can see it; successful firings are visible through their commands' source.
- **Dry run** (`DryRunRule`, admin): a stored or draft rule over a seq or time range, at most
  `RULE_DRY_RUN_MAX_EVENTS` events read and `RULE_DRY_RUN_MAX_FIRINGS` reported. `when` is exact on history; `if` is
  evaluated on the record as it is now (`condition_basis = "current"`; as-of evaluation waits for P1-I6's time-travel
  reads); planned commands are validated and access-checked, never run.
- **Authoring** is admin: create, revise, enable, disable. A rule starts disabled and in `propose` mode; switching to
  `act` is an admin revision with a reason.
- If P1-I6 has put a rules stub on the trunk (its T05) by the trunk merge, WS-A moves that rule onto this engine
  there (D17).

### D8. Actions and executors
- `ActionDefinition` (admin) and `InvokeAction`: the handler checks the definition's `access` with `holds`, its
  `applies_to` and its parameters. `requires_approval` turns the invocation into a proposal that another person with
  that access accepts. Agents have no action tool in Phase 1.
- Lifecycle on a `core.ActionInvocation` stream: `Action.Requested`, `Action.Running`, `Action.Completed` or
  `Action.Failed`, with the targets as `RecordRef`s; a feed card per §18.7.
- Execution goes through the job queue (job kind `action`, `ACTION_MAX_ATTEMPTS`, retried only when the outcome is
  `retryable`).
  - `job`: calls the `ActionJob` named in the config, found under `ACTION_JOB_ENTRY_POINT`; pure.
  - `webhook`: one POST of the canonical request (no secret in it), signed with Standard Webhooks headers using the
    action's secret from `int_secret`, through `tl_core.webhooks.egress.EgressPolicy` (setting
    `webhooks.egress.allowlist`; `https` only unless allow-listed; private, loopback, link-local including
    169.254.169.254, carrier-grade NAT, multicast, reserved and IPv4-mapped addresses refused; DNS resolved once and
    pinned per attempt; credentials and fragments refused) and `HttpxTransport` (no redirects, at most
    `ACTION_MAX_RESULT_BYTES` read, `ACTION_WEBHOOK_TIMEOUT_S`). `JobKind.run`'s "no network" note is amended for the
    kind `action` only: network only through this transport (ADR-0017).
- Not built: async result callbacks (§18.7), and the `mcp_tool`, `connector` and `agent` executors (a definition
  naming one is refused). Result handling is `store` (bounded, on the invocation) and `post_to_feed`.
- Tests use `ScriptedTransport`, a stubbed resolver, or the loopback dev receiver with an allow-list entry. Nothing
  leaves the machine. One test per refused range proves the refusal happens before any connect.
- TUI: the record palette lists the actions whose `applies_to` matches; invoking shows the parameter form and a
  confirmation by `side_effect_class`.

### D9. Threads
- Stream `thread:<record id>` (`core.Thread`, the record's scope), created by the first message. Events are
  `THREAD_EVENT_TYPES`. `Thread.MessagePosted` carries message id, record id, author, body, mentions, record refs and
  kind (`message`, `dispatch`, `summary`, `reminder`). Attachments (slot `thread_attachment`) are a follow-up.
- Projections `cur_thread`, `cur_thread_message`, `cur_thread_participant` (the record's creator, authors, mentioned
  people, dispatchers). Followers and assignees wait for their models.
- Settings in `schema/settings/platform.yaml`: `threads.enabled` (default false), `threads.enabled_types` (default
  `[]`), `threads.dispatch.enabled` (default true), `threads.dispatch.roles` (role names from `ROLES`; empty means any
  role), `threads.agents.can_dispatch` (`propose` or `none`; lockable).
- `PostThreadMessage` never dispatches, even when the body starts with `/`. `EditThreadMessage` and
  `RetractThreadMessage` are the author's (a retraction leaves a tombstone). Record keys in a message are detected
  with the feed's key detection and kept as `record_refs`.
- Messages do not appear in the activity stream; dispatch results do, as the commands' own events. Webhooks deliver
  `THREAD_WEBHOOK_EVENT_TYPES`; the catalog contract tests subtract the other two (L-P1-I0A-4).
- **Visibility is the record's**: every thread read (API, MCP, TUI) loads the record through the existing read path
  first, and a record the caller cannot read gives the record route's 404. P1-I5's confidentiality filters plug in
  at the trunk merge (D17).
- `/remind` queues a `thread.reminder` job (`run_after`); it posts a `reminder` message as `svc:threads` naming who.
  Mentions are recorded; inbox delivery waits for its model.

### D10. Dispatch parser and planner
- The parser follows the grammar in `tl_core/threads/contract.py`: pure, total, and it passes
  `check_parser_contract`.
- The planner resolves mentions (a person's username to `user:<id>`; crews and parties do not exist yet:
  `unknown_mention`) and keys (the record's scope; ambiguous is a problem). It builds `PlannedCommand`s through
  `DispatchTarget`s (entry points under `DISPATCH_TARGET_ENTRY_POINT`, most specific name first, then the core
  defaults), validates them with `runner.model_of`, checks access with `holds`, dry-runs them in a unit of work that
  is rolled back (the ADR-0014 dry-run pattern), and computes the token.
- Phase 1 targets:

  | Verb | Runs | Note |
  |---|---|---|
  | `link` | `AddLink` from the thread's record to each key (relation from `as`, else the vocabulary default) | link source `thread_dispatch` |
  | `status` | `TransitionWorkflow` on the thread's record | guards apply; a module may register its own command for its type |
  | `raise` | alias `record`: `CreateRecord` of `core.Record` (title from the text), `dispatched_from` to the thread's record, `raised_against` to the `#KEY` targets | modules add aliases (P1-I6 `rfi` when it is on the trunk) |
  | `dispatch` | `InvokeAction` (action = request type, target = the thread's record, parameters) | needs WS-A's handler (merge order) |
  | `notify` | no command: a message with mentions | not side-effecting |
  | `remind` | a `thread.reminder` job | previewed |
  | `summarise` | deterministic summary (counts, participants, dispatched commands, first lines of the last `SUMMARY_MAX_MESSAGES`), posted as `summary` by the caller on confirm | note ADR-0008 decision 8 |
  | `assign`, `due`, `hold`, `release` | nothing in Phase 1 (no assignee, due-date or constraint model): `dispatch_unavailable` | unless a module registers a target |

- **Confirm** (`DispatchFromThread`: record id, text, token): re-plans as the caller; a different plan or an expired
  token is 409 `dispatch_stale`. One unit of work holds the message (kind `dispatch`), the planned commands through
  the runner, a `dispatched_from` link from each created record to the thread's record (note: the message id), and
  `Thread.Dispatched` with the `DispatchOutcome`. Any refusal rolls everything back.
- **Access**: `threads.dispatch.enabled`, the caller's roles in `threads.dispatch.roles`, and each planned command's
  own access through `holds`: the caller's access, never more. An agent's direct `DispatchFromThread` is refused
  (`AGENT_MUST_PROPOSE`); `propose_dispatch` records a proposal; accepting it re-plans as the accepting person, needs
  every planned command permitted to that person and the plan unchanged, or the proposal fails. This extends
  `proposals._require_access` to a command whose access depends on its content (ADR-0018).
  `threads.agents.can_dispatch = none` refuses the tool.
- MCP `read_thread` (a read, at most `READ_THREAD_MAX_PAGE` per page) and `post_thread_message` (direct, like
  `post_feed`: a message changes no record and never dispatches).

### D11. Kill switch and integration registry
- Setting `integration.kill_switch` (bool; platform and company; lockable; default false). When on: inbound answers
  the fixed 404; the rules worker and the enrichment dispatcher record the events they pass over as `killed` and do
  not replay them later; action jobs fail with `killed`, not retried. `IntegrationApp.enabled` (admin) switches off an
  app's endpoints, rules, actions and enrichers together.
- Registry screen (T07): apps, webhook subscriptions (existing), endpoints, rules, actions, enrichers, owners, last
  use, failure counts, switches. Admin only for changes; it calls the same commands as the API.

### D12. Access for every new command (ADR-0011, ADR-0013, ADR-0014 section 8)
| Command or route | Access | Agents |
|---|---|---|
| `RegisterIntegrationApp`, `ReviseIntegrationApp`, `SetIntegrationAppEnabled` | admin | no |
| `DefineAction`, `ReviseAction`, `RetireAction`, `RotateActionSecret` | admin | no |
| `InvokeAction` | the definition's `access`, through `holds`; `requires_approval` makes it a proposal | no |
| `CreateRule`, `ReviseRule`, `EnableRule`, `DisableRule`, `DryRunRule` | admin | no |
| `CreateInboundEndpoint`, `ReviseInboundEndpoint`, `SetInboundEndpointEnabled`, `RotateInboundSecret`, `DryRunInboundMapping`, `RetryInboundDelivery`, error queue and stored payloads | admin | no |
| `POST /in/{app}/{endpoint}` | the signature; runs as the endpoint's service actor and access | n/a |
| `RegisterEnricher`, `ReviseEnricher`, `SetEnricherEnabled` | admin | no |
| `RunEnricher`, `AcceptEnrichment`, `RejectEnrichment` | user (the target type must allow `SetPsetValues`) | no |
| Reads: registry, invocations, review queue | user; secrets never; inbound payloads admin | no |
| `PostThreadMessage`; `EditThreadMessage`, `RetractThreadMessage` (author only) | user | yes, direct |
| `read_thread` (`thread.read`) | user, when the record is readable | yes |
| Dispatch preview | user | through `propose_dispatch` only |
| `DispatchFromThread` | user, `threads.dispatch.roles`, and each planned command's access | no; `propose_dispatch` |
| `integration.kill_switch` | admin (`ChangeSetting`, company layer) | no |

Admin commands use the action `admin.command.<Name>` and the CLI's `require_admin`. No `control.*` action is added.
`AGENT_ACTIONS` gains `thread.read`, `command.PostThreadMessage`, `command.EditThreadMessage`,
`command.RetractThreadMessage`; `MCP_ACTIONS` gains `mcp.read_thread`, `mcp.post_thread_message`,
`mcp.propose_dispatch`; `PROPOSABLE_TOOLS` gains `propose_dispatch` → `DispatchFromThread`. These lists are edited by
the supervisor only (permission code, never an implementer ticket).

### D13. Storage and schema placement
- New records are streams of their own with their own `cur_*` projection, as `core.WebhookSubscription` (P0-I5):
  `core.IntegrationApp`, `core.ActionDefinition`, `core.ActionInvocation`, `core.Rule`, `core.InboundEndpoint`,
  `core.Enricher`, the enrichment values, `core.Thread`. They are configuration and activity, not project records: no
  `cur_core_record` row, no psets, no workflow.
- WS-A extends `schema/core/integration.yaml` (§19.2's home) and adds `schema/core/integration_ops.yaml` for the
  operational tables (`int_secret`, `int_replay`, `int_delivery`, `rule_cursor`, `rule_firing`, the enrichment
  cursor). WS-B adds `schema/core/threads.yaml`. Events go in `schema/core/events.yaml`. All additive; no migration of
  existing data.
- Operational tables are not projections: a rebuild never clears them; the archive, the lake and webhooks never read
  them.
- No event carries a secret, a raw inbound payload or header, or a webhook response beyond the bounded result.

### D14. The command runner
WS-A builds `tl_api.commands.command_runner()` in its first supervisor piece: `model_of` and `run` from `COMMANDS`
(module tables included), `access_of` from `CommandSpec.access`. Entry points pass it into the rules worker, the
inbound worker and the dispatch planner; `tl_core` never imports `tl_api`. WS-B uses a fake runner in core tests
until it merges `p1/i7`, then wires the real one into its API, CLI, TUI and MCP paths.

### D15. Supervisor-built pieces and implementer tickets
Supervisors build the engines of `docs/build-spec/01-tiers.md` §3 and every security piece; implementers get the rest
as stub-plus-provided-test tickets (L-P1-I2-1, L-P1-I3B-6). Anything another piece cannot be tested without is built,
not stubbed (L-P1-I3-5).

| WS | Supervisor builds | Implementer tickets |
|---|---|---|
| A | S1: T01 LinkML and events (schema gate), D2 wiring, D14 runner, the `svc:rule-` proposer, the contract-to-LinkML slot test. S2: T03 rules engine (cursor, match, depth, budgets, firing rows, act and propose, dry run). S3: T02 core (registry service, `InvokeAction`, lifecycle, job kind `action`, webhook executor with egress and signing). S4: T04 verification (route, rate, cap, HMAC, JWT, replay, secrets, fixed answers, queueing), the mapping runtime (profile and envelope), the `inbound.map` worker's allow-list and access checks. S5: T05 enrichment write path and acceptance policy. S6: kill switch in every engine; access rows in `COMMANDS` | T02 `job` executor and an example `ActionJob`; T02 TUI action menu and CLI; T04 key resolution; T04 dry-run and error-queue API and CLI; endpoint CLI; T05 review-queue screen, API and CLI; enrichment dispatcher wiring; T06 `doc_classifier`, golden set and evaluation; T07 registry screen; T08 contract tests for inbound mappings and action results |
| B | S1: T09 LinkML, events and settings keys (schema gate), thread commands and projector. S2: T10 parser, planner, core targets frame, confirm, token. S3: `propose_dispatch` accept check, `AGENT_ACTIONS`, `MCP_ACTIONS`, `PROPOSABLE_TOOLS`, access rows in `COMMANDS` | Core targets `link`, `status`, `raise`, `dispatch` once the frame exists; `/remind` job kind; `/summarise` stub; T11 thread tab, composer completion of `/` verbs, `@` and `#`, result cards (split by screen, L-P1-I3-6); T12 catalog and webhook scenario additions; MCP `read_thread` and `post_thread_message`; API thread routes; CLI `tl thread show`, `post`, `dispatch` |

### D16. Merge order and conflict owner
1. WS-A finishes S1, S2 and S3 (the plan's T01–T03); the orchestrator reviews the supervisor-built pieces and
   approves the schema; WS-A merges `p1/i7a` into `p1/i7`.
2. WS-B merges `p1/i7` into `p1/i7b` (WS-B resolves), wires the real runner and `/dispatch`, finishes, passes its
   security review, and merges into `p1/i7`. If WS-B is ready before step 1, it waits; only a logged orchestrator
   decision changes the order.
3. WS-A merges `p1/i7` into `p1/i7a` (WS-A resolves), does T04–T08, passes its security review, and merges into
   `p1/i7`.
4. Trunk catch-up (D17): WS-A merges the trunk into `p1/i7` and resolves; full gates; demo; report. The orchestrator
   merges `p1/i7` into the trunk.

Merge commits only. `uv.lock` is regenerated with `uv lock`, generated artefacts with `just gen`, the OpenAPI document
with `uv run python -m tl_api.openapi`; none is merged by hand.

### D17. Concurrency with P1-I4 and P1-I5
P1-I4 (cost and schedule) and P1-I5 (correspondence) are built at the same time on other branches and merge into the
trunk before P1-I7. **The WS-A supervisor (the later-merging workstream) resolves the registry conflicts** at step 4
of D16, after a textual merge greps the other side's new code for broken assumptions (L-P1-I0B-5).

Shared registries; edits are **additive only**: append in a block commented `# P1-I7 WS-A` or `# P1-I7 WS-B`, never
reorder, rename or reformat existing entries, and resolve a conflict by keeping both sides.

| Registry | Path |
|---|---|
| API command table | `packages/tl-api/src/tl_api/commands.py` (`COMMANDS`) |
| Agent actions | `packages/tl-core/src/tl_core/auth/provider.py` (`AGENT_ACTIONS`) |
| MCP actions | `packages/tl-mcp/src/tl_mcp/identity.py` (`MCP_ACTIONS`) |
| Proposable tools | `packages/tl-core/src/tl_core/proposals/types.py` (`PROPOSABLE_TOOLS`) |
| TUI key map | `packages/tl-tui/src/tl_tui/keymap.py`, with the palette snapshot and `test_keymap.py` contexts |
| CLI root registration | `packages/tl-cli/src/tl_cli/main.py` (`add_typer`) |
| API routers and errors | `packages/tl-api/src/tl_api/app.py`, `tl_api/errors.py`; the OpenAPI document (regenerate) |
| Event catalog | `schema/core/events.yaml` and the generated catalog (`just gen`) |
| Settings | `schema/settings/platform.yaml` |
| Projector registry and operational tables | `default_registry()`, the operational table lists |
| Pinned lists in tests | L-P0-I8A-7, L-P1-I2-6, `tests/webhooks/scenario.py` (L-P1-I1-1) |
| Docs | `AGENTS.md` (*Where things go*), `docs/build-spec/03-repo-and-toolchain.md` §7, `docs/memory/LEARNINGS.md` (union merge, append only) |
| Dependencies | `uv.lock`, the root and package `pyproject.toml` files |

`tl_core.services.reserved` and `SYSTEM_LINK_SOURCES` are WS-A's alone. At step 4 WS-A also wires P1-I5's
confidentiality filters into the thread read paths and the automation reads (D3, D9) and, if P1-I6 is on the trunk,
moves its rules stub onto the engine (D7) and registers its `rfi` dispatch alias if P1-I6 did not.

### D18. Security review (delegated gates; the orchestrator runs it fresh before DONE)
Each relay lists under `SECURITY_REVIEW:` every supervisor piece that adds or changes a route, an access level, an
allow-list, an agent action, a secret, an outbound call or a sandbox:
- WS-A: D2 wiring; the runner; the `svc:rule-` proposer; the rules engine (depth, budgets, access, bindings); the
  webhook executor (egress, signing, secret handling); the inbound route (order of checks, verification, replay, cap,
  rate, fixed answers, secrets); the mapping profile and envelope; the inbound worker (allow-list, access, key
  resolution); the enrichment write path; the kill switch.
- WS-B: thread read visibility; `PostThreadMessage` never dispatching; the planner (access through `holds`, token,
  rolled-back dry run, never more than the caller); the `propose_dispatch` accept check; the agent and MCP list edits;
  the `thread_dispatch` link source.
- Step 4: the confidentiality wiring of D17.

### D19. Dependencies
- `jsonata-python==0.7.0` (Apache-2.0, no dependencies) in `tl-core` for the mapping runtime (D5).
- `PyJWT` (MIT; 2.15.1 is already locked through `mcp`) as a direct dependency of the package that verifies JWTs (D4).
- Nothing else. A copyleft licence or anything that costs money stops the run (KICKOFF); name every licence in the
  relay and in APPROVALS.md.

### D20. Demo (`just demo P1-I7`, WS-A owns it)
1. An admin creates inbound endpoint `acme-nde/results` (HMAC) whose mapping turns NDE results into `SetPsetValues` on
   `core.Record`s found by key (an `nde` pset in the sample package, added by WS-A under the schema gate if missing);
   the dry run shows the plan; enabled, a signed POST is 202 and the records change with source
   `inbound:acme-nde/results`; the same POST again, an unsigned one and a wrong endpoint give 401, 401 and 404.
2. Rule `hse-notify`: when a post carries `#safety`, post "HSE notified" to the feed (`act`); its dry run over recent
   events lists what it would have done; a looping rule stops at depth 3.
3. `doc_classifier` proposes a `doc_type` for a registered document; a person accepts it from the review queue and it
   reads back from `psets.enrich.doc_classifier.doc_type`.
4. On a record's thread: a message, `/link`, then `/raise rfi` when P1-I6 is on the trunk, else `/raise record`:
   preview, confirm, a linked record with `dispatched_from`; `/summarise` (deterministic); an agent's
   `propose_dispatch` accepted by a person.
5. Action `send_to_nde` (webhook to the loopback dev receiver, allow-listed) run from `/dispatch send_to_nde`.

## Merge order and conflict owner
WS-A (T01–T03) → WS-B → WS-A (T04–T08) → trunk catch-up. Conflicts inside P1-I7: the supervisor of the merging side
(D16). Registry conflicts with P1-I4 and P1-I5: the WS-A supervisor (D17). Merge commits only.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|
| Schema merges: `schema/core/integration.yaml`, `integration_ops.yaml`, `threads.yaml`, `events.yaml`, `schema/settings/platform.yaml`, fixture psets | orchestrator under ADR-0008 decision 6 (SCHEMA_APPROVALS in the relay) | `docs/reports/APPROVALS.md` |
| Inbound signing (D4) and the mapping sandbox (D5) | orchestrator under ADR-0008 decision 6, after the D18 review | APPROVALS.md |
| Permission design: D3, D12, the proposal accept extension (D10) | orchestrator under ADR-0008 decision 6 | APPROVALS.md, ADR-0017, ADR-0018 |
| Confidentiality filters on thread and automation reads (step 4) | orchestrator under ADR-0008 decision 6 | APPROVALS.md |
| New dependencies (D19) | licence gate; delegated for permissive licences | APPROVALS.md |
| Copyleft licence, spend (a real model enricher), migration of existing data | **owner**: stop and ask | `docs/reports/STOPPED.md` |

## Risks and escalation triggers
- `jsonata-python` is beta: semantic gaps show up as contract-test failures; D5's fallback is the orchestrator's call.
- One child process per mapping evaluation costs about 100–300 ms; the D4 rate bounds keep it affordable. A warm
  worker pool is a follow-up.
- Pinned counts and lists break whenever a command, tool, event or table is added (L-P0-I8A-7, L-P1-I2-6): run
  `pytest packages/tl-schema packages/tl-api tests/contract tests/services` right after each registry edit.
- WS-A is about twice WS-B. If WS-A slips, the orchestrator may move T07 or T08 to WS-B by a logged decision.
- Four supervisors at once (P1-I4, P1-I5, WS-A, WS-B) is above the about-3 cap of L-P0-I8-O1: each supervisor keeps
  at most two implementers running.
- Escalate (write under *Blocked*, then stop): any contract change; the library is rejected; P1-I5's filter API does
  not fit D3 or D9; a need for automation to run an `admin` command; a change to an existing class, event or table;
  any migration.

## Decisions log
| Date | Raised by | Question | Decision | ADR |
|---|---|---|---|---|
| 2026-10-17 | orchestrator | Fanout decisions D1–D20 | as above | ADR-0017, ADR-0018 (to draft) |
