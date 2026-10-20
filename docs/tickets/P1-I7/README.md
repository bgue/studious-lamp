# Increment plan — P1-I7 workstream A: actions, rules, inbound endpoints, enrichment

Status: in-progress
Supervisor session: 2026-10-17
Brief sections: §18.5 (inbound), §18.7 (actions), §18.8 (rules), §18.9 (enrichment), §18.13 (governance, kill switch), §19.2 and §19.3 (integration classes), §10.6 sketch 13 (threads, workstream B)
Branch: `p1/i7a` (base: `p1/i7`, which holds the fanout plan and the two frozen contracts). Workstream B (record threads with dispatch) is `p1/i7b`.
Fanout plan: [FANOUT.md](FANOUT.md) (decisions D1 to D20 are binding). Decisions: ADR-0008 (decisions 6 and 8), ADR-0010 (+ addenda), ADR-0011, ADR-0013, ADR-0014 section 8, and the new [ADR-0017](../../adr/0017-integration-layer.md).

## Objective
External systems, rules and enrichers act on the ledger through one guarded seam. An admin registers actions, rules, inbound endpoints and enrichers. Each runs as a declared service actor that can only produce allow-listed commands, within a declared access, bounded per event and per request, and every write it makes is ledgered with a server-set source. The contract is `tl_core/integration/contract.py` (frozen); this plan builds what it describes.

## Demo
`just demo P1-I7` (SQLite and Postgres; `dev/demos/P1-I7.sh`), FANOUT D20, clauses 1 to 3 and 5 are workstream A's:
1. an admin creates the inbound endpoint `acme-nde/results` (HMAC); its dry run shows the plan; enabled, a signed POST is 202 and the records change with source `inbound:acme-nde/results`; the same POST again, an unsigned one and a wrong endpoint give 401, 401 and 404;
2. rule `hse-notify`: a post that carries `#safety` makes the feed post "HSE notified" (act mode); its dry run over recent events lists what it would have done; a looping rule stops at depth 3;
3. `doc_classifier` proposes a `doc_type` for a registered document; a person accepts it from the review queue and it reads back from `psets.enrich.doc_classifier.doc_type`;
5. action `send_to_nde` (webhook to the loopback dev receiver, allow-listed), run from a thread's `/dispatch` (workstream B's clause 4 uses the same action).

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1a | Reserved identifiers: `tl_core.services.reserved` (sources, correlation and causation prefixes), `thread_dispatch` a system link source, the narrow `system_source` keyword of `AddLink`/`SuggestLink` (FANOUT D2) | Security: a client posing as automation | fresh-context security review | done (03fc462) |
| S1b | T01 schema: `integration.yaml` (seven records), `integration_ops.yaml` (seven operational tables), 33 event classes in `events.yaml`, `integration.kill_switch`, projectors, `INTEGRATION_*` event sets, internal events never delivered by webhooks, `int_secret` denied to the dev tools, contract-to-LinkML slot test | Schema (human-gated, SCHEMA_APPROVALS) | orchestrator | done |
| S1c | The command runner `tl_api.commands.command_runner()` (D14) and `proposals.propose_for_rule` with the `svc:rule-<slug>` proposer (D3) | Permissions | fresh-context security review | done |
| S2 | T03 rules engine: cursor, match, depth, self-trigger, budgets, firing rows, act and propose, dry run, authoring commands | Engine (`01-tiers.md` §3), loop protection | security review | done (56a3ea1; fixes 8608be3) |
| S3 | T02 core: registry service, `InvokeAction`, lifecycle, job kind `action`, webhook executor with egress and signing, `int_secret` | Outbound call, secrets | security review | done (56a3ea1; fixes 8608be3) |
| S4 | T04 verification: route (`tl_api/inbound.py`), rate bound, body cap, HMAC, JWT, replay, secrets, fixed answers, queueing; mapping runtime (profile, envelope); the `inbound.map` worker's allow-list, access, key resolution; retry and dry run | Inbound signing and a sandbox (delegated gates) | security review | built (9c32d40, 8608be3); review pending |
| S5 | T05 enrichment: registry, pipeline and policies, the Python-only layer write, the dispatcher, the commands | Writes the `enrich.*` layer | security review | built (9c32d40); review pending |
| S6 | Kill switch in every engine (rules, actions and `InvokeAction`, inbound route and worker, enrichment); the access rows of the new commands in `COMMANDS` | Permissions | security review | built; review pending |

## Tickets
Numbers follow the plan (07-phase1-plan.md); suffixes split a plan ticket by file set. Tickets T01 to T03 of the plan are supervisor pieces (S1 to S3). Ticket files: [T06-doc-classifier.md](T06-doc-classifier.md), [T02a-job-executor.md](T02a-job-executor.md), [T04a-inbound-keys.md](T04a-inbound-keys.md); provided tests in [provided/](provided/).
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T06 | `doc_classifier` enricher, golden set (26 cases), evaluation | H | — | merged | 58d6b7c; accuracy 1.0 on both properties (a `layout` keyword was added to DRW) |
| T02a | `job` action executor and the example job `echo` | H | — | merged | 852b28c |
| T04a | Key resolution for inbound mappings (`resolve_keys`) | H | — | merged | 376e4eb |
| T03b | `tl rule` CLI | H | — | merged | a53d9fa (merge 87a8fe8); `mode` is admin-gated; `create` refuses actor, source and scope in the file |
| T04b | `tl endpoint` CLI | H | — | merged | 860680d (merge 42a7c0b); reads are not gated (D12: reads are `user`) |
| T04d | `tl delivery` CLI (error queue, dry run) | H | — | merged | 045b641 (merge 496f796) |
| T05a | `tl enricher` and `tl enrich` CLI (review queue) | H | — | merged | 39fa8fe (merge 14faa67) |
| T02b | `tl action` CLI | H | — | review-only | eac15a2, base merged (98537b1); acceptance green |
| T04c | Inbound endpoint registry views (TUI) | H | S4 | folded into T07 | the endpoints table and detail are one of the registry screen's seven tables |
| T05c | Review-queue screen (TUI) | H | S5 | merged | c47e4fb (merge 48d1fd8); first attempt |
| T07 | Integration registry screen (apps, endpoints, rules, actions, enrichers, kill switch) | H | S2 to S6 | merged | a68087b (merge 2728090); first attempt |
| T08 | Contract tests for inbound mappings and action results | H | S4 | ready | [T08](T08-golden-contracts.md); runners provided, the golden JSON is the work |

The batch-3 tickets (T05c, T07, T08) are stub-plus-provided-test pairs too. `provided/supervisor-test_app_integration.py.txt` is the supervisor's app wiring test (Ctrl+R and Ctrl+E); it needs both screens; it joined `packages/tl-tui/tests/` when T05c and T07 were merged (48d1fd8). The suffixes split a plan ticket by file set. The plan's T05b (dispatcher wiring) and the API routes of T03b, T04b and T05a are supervisor pieces (`tl integration serve`, `tl_api/routes/integration.py`). The batch-2 tickets are stub-plus-provided-test pairs: the stub is the reference implementation with its bodies replaced, and the provided test passed against the reference (reference commit c9117ea) with mutation checks.

## Order of work
1. S1 (done), then the first batch of tickets that need only the contract: T06, T02a, T04a.
2. S2 (rules), S3 (actions), then the orchestrator's review and the merge of `p1/i7a` into `p1/i7` (D16 step 1). Workstream B merges after.
3. After merging `p1/i7` back: S4, S5, S6 and tickets T02b, T04b/c, T05a/b, T07, T08; the security review; the trunk catch-up (D17); the demo and report.

## Risks and escalation triggers
- `jsonata-python` is a beta port: semantic gaps show up as contract-test failures. Its replacement is the orchestrator's call (D5).
- One child process per mapping evaluation costs 100 to 300 ms; the rate bounds keep it affordable.
- Pinned counts and lists break whenever a command, tool, event or table is added (L-P0-I8A-7, L-P1-I2-6): run `pytest packages/tl-schema packages/tl-api tests/contract tests/services` after each registry edit.
- Known red until workstream B merges: `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` finds the `Thread.*` names of `tl_core/threads/contract.py` (committed with the fanout) and no catalog class for them; B adds the classes.
- Escalate (write under *Blocked*, then stop): any change to a contract file; the library is rejected; the confidentiality filters of P1-I5 do not fit D3 or D9; automation needing an `admin` command; a change to an existing class, event or table; any migration.

## Blocked / Decision
(none yet)
