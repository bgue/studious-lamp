# Report — P1-I7 workstream A (the integration layer)

Branch `p1/i7a` (base `p1/i7`). Plan: [docs/tickets/P1-I7/README.md](../tickets/P1-I7/README.md). Fanout: [docs/tickets/P1-I7/FANOUT.md](../tickets/P1-I7/FANOUT.md) (D1 to D20). Decision record: [ADR-0017](../adr/0017-integration-layer.md) (stays `proposed`). Runbook: [docs/runbooks/integration.md](../runbooks/integration.md). Workstream B (record threads) has its own report.

## Outcome
Objective met: yes, for the parts that do not need workstream B. External systems, rules and enrichers act on the ledger through one guarded seam.

- **Actions.** An admin defines an action (`job` or `webhook` executor; the webhook is signed, egress-checked, bounded by a total deadline). A person invokes it with the access the definition declares; `requires_approval` makes it a proposal. The signing secret is shown once.
- **Rules.** `when / if / then` over the ledger, run by a worker that follows the outbox. A rule starts disabled and in propose mode; it has a dry run over past events; it is bounded (depth 3, 5 steps, 20 commands per event) and never fires on its own work. Each firing is a row.
- **Inbound endpoints.** `POST /in/<app>/<endpoint>` verifies an HMAC or an HS256 token, a replay window and a body cap, answers fixed codes (404, 401, 202), and queues the delivery. A restricted JSONata mapping, run in a child process under the ADR-0014 envelope, turns the payload into allow-listed commands; all of them apply or none do. Failed deliveries are an admin's error queue with retry and a corrected payload.
- **Enrichment.** A framework with three acceptance policies (`auto`, `propose`, `shadow`), a dispatcher, a Python-only layer write into `enrich.<name>.*`, and the first deterministic enricher `doc_classifier` (accuracy 1.0 on its 26-case golden set).
- **Every write is attributed.** A service actor per rule, endpoint, enricher and action (`svc:rule-<key>`, `svc:inbound-<app>.<endpoint>`, ...), source `rule:`, `inbound:`, `enricher:`, `action:`, set by the server; a client cannot pose as one. The command runner checks what each actor holds in the ledger, so automation never runs with more than its owner's switches allow. One kill switch (`integration.kill_switch`) stops all of it.
- **Entry points.** CLI `tl integration|endpoint|rule|delivery|enricher|enrich|action`; API `tl_api/inbound.py` and `routes/integration.py`; TUI `Ctrl+R` review queue and `Ctrl+E` registry.

Demo path verified: `just demo P1-I7` on SQLite and Postgres: GATE_DEMO. Verified on a fresh clone: no; the gates ran on a clean worktree of the final commit.

## Tickets
| ID | Outcome (merged / taken-over / abandoned) | Review rounds | Notes |
|---|---|---|---|
| S1 to S6 | merged (supervisor) | orchestrator, two security passes | reserved identifiers, schema, runner and access, rules engine, actions core, inbound, enrichment, kill switch |
| T06 `doc_classifier` | merged (58d6b7c) | 1 (pass) | a `layout` keyword was added to DRW |
| T02a `job` executor, example job `echo` | merged (852b28c) | 1 (pass) | |
| T04a key resolution for mappings | merged (376e4eb) | 1 (pass) | the message of an unknown key now names its length only |
| T03b `tl rule` | merged (a53d9fa) | 1 (pass) | `mode` and `dry-run` are admin-gated |
| T04b `tl endpoint` | merged (860680d) | 1 (pass) | reads are not gated (D12) |
| T04d `tl delivery` | merged (045b641) | 1 (pass) | the payload is never printed |
| T05a `tl enricher`, `tl enrich` | merged (39fa8fe) | 1 (pass) | |
| T02b `tl action` | merged (eac15a2) | blocked once by a stale `openapi.json` on the base, then green; review-only pass by the orchestrator | |
| T04c endpoint views (TUI) | folded into T07 | | |
| T05c review-queue screen | merged (c47e4fb) | 1 (pass) | |
| T07 registry screen | merged (a68087b) | 1 (pass) | |
| T08 golden contract cases | merged (c6a79ce) | 1 (pass) | a case for an over-limit answer without the truncated flag was added by the supervisor |

No ticket was taken over or abandoned. Every Haiku-tier ticket was a stub-plus-provided-test pair; the provided tests were mutation-checked against the reference (L-P1-I7A-9).

## Gates
| Gate | Result |
|---|---|
GATE_ROWS

## Security
- **Pass 1** (of 1972934): changes requested, 9 findings (one HIGH among them): per-actor access in the runner, a non-injective inbound actor name (unique index on `service_actor`), mid-batch switches, JWT claims, the transport deadline, `by_module` and others. All fixed with tests that fail without the fix (8608be3 and its parents); the second pass verified them.
- **Pass 2** (d806770..049717e): changes requested, 9 findings. Fixed on `p1/i7a`:
  1. HIGH, a client could write the enrichment layer through `CreateRecord.psets` or `UpdateRecord`: 744a95e (services/records.py; tests through the services, a rule, a mapping and the API).
  2. MEDIUM, a stale enricher snapshot and no live access check: the dispatcher re-reads each enricher per event and `run_enricher` needs `held_access`: 3ffa040 (small, so built here).
  3. MEDIUM, shadow values readable by anyone: a88475f.
  4. MEDIUM, `admin_gate` failed open with no session: fails closed outside a dev, test or ci file: 2bbbc8e.
  5. MEDIUM, the transport deadline missed the header phase: a watchdog closes the client: ec33033 (test with a header-dripping server).
  6. LOW, replays left objects: refused before the body is stored: 811248d.
  7. LOW, `tl rule create` and the embedded client passed server-set fields through: refused: 2bbbc8e.
  8. LOW, `tl rule dry-run` ungated, and the inbound worker now reads the endpoint's mode when it applies (dry-run is an emergency stop): 2bbbc8e, ab663db.
  9. LOW/INFO, `Inbound.Failed` named a payload-derived key (now its length): ce5b4c4; the accepted trade-offs are in the runbook; the old `-`-joined actor names are a non-issue before release.
  Fix commits: 744a95e, 3ffa040, a88475f, 2bbbc8e, ec33033, 811248d, ab663db, ce5b4c4.
- **Re-check of 3e71e5d**: changes requested, five items, fixed:
  1. MEDIUM, shadow values leaked through the event log (`Enrichment.Proposed` carries the value): hidden by the change-feed filter (`/events`, `/stream`, `tl events`; `show_shadow` for an admin only), never sent by a webhook (live or replay), no feed card: fix commit "shadow enrichment proposals stay out of /events...".
  2. LOW, the unchanged-layer exemption used Python equality (`1 == 1.0 == True`): canonical JSON.
  3. MEDIUM, a propose-mode rule with a versioned command always failed on accept: a rule's proposal reads the record version when a person accepts it (tests for `SetPsetValues`, `UpdateRecord`, `TransitionWorkflow`, each with the record changed in between).
  4. Decision on the version rule: automation is last-writer-wins (acceptable for `SetPsetValues` and transitions); automation `UpdateRecord` may change only title and description (`psets_not_automated`); ADR-0017 section 7d says so.
  5. LOW, payload-derived text in failure messages: an unknown argument is counted, a validation error names the model field and nothing below it.
  6. INFO, a delivery stopped by the dry-run re-read ends in state `dry_run` and is not retryable: in the runbook.

## Deviations from plan
- The plan's T05b (dispatcher wiring) and the API routes are supervisor pieces (`tl integration serve`, `routes/integration.py`).
- `tl integration app add|ls|enable|disable` was added (the demo showed there was no way to register an app from the command line). No schema change.
- Found by the demo: a mapped or rule `SetPsetValues` could not be built because it needs `expected_version`. Automation now changes a record as it is when the command runs (ADR-0017 section 7d, `integration/automation.py`). A core-engine change, marked for orchestrator review.
- `Ctrl+R` and `Ctrl+E` open the two screens because every function key was taken across P1-I4, P1-I5 and P1-I7.

## Escalations and decisions
- The unique `service_actor` key and the injective inbound actor name (schema; approved).
- The per-actor runner access (design change inside D14; coordinator decision, logged in APPROVALS).
- jsonata-python 0.7.0 and PyJWT (approved in the kickoff, logged).

## Learnings
L-P1-I7A-1 to L-P1-I7A-12 appended. No implementer proposals were declined.

## Docs
[ADR-0017](../adr/0017-integration-layer.md) (sections 7 to 7d), [docs/runbooks/integration.md](../runbooks/integration.md), `AGENTS.md` (pointer row), the READMEs of `tl-core`, `tl-cli` and `tl-tui`, `docs/tickets/P1-I7/` (plan, the ticket files, provided tests), `docs/reports/P1-I7/` (ticket reports), `docs/reports/APPROVALS.md`. Not done: `docs/reports/STATUS.md` (the orchestrator's).

## Follow-ups filed
- At the p1/i7 merge: WS-B's `AGENT_DIRECT_COMMANDS` and the settings pins (16 keys) conflict mechanically; `tl_tui/app.py` and `commands.py` take both sides' bindings.
- The trunk catch-up (D17): wire the P1-I5 confidentiality filters into the rules worker, the enrichment dispatcher and the registry reads; move P1-I6's rules stub onto the engine; add the `rfi` alias.
- Demo clause 4 (an action run from a thread's `/dispatch`) is added to `dev/demos/P1-I7.sh` when workstream B is merged.
- A real model-based enricher needs its own ADR (Phase 1 refuses `model_ref`).

## Showcase
The demo state is the ledger the script builds: `just demo P1-I7` (it removes its ledger afterwards). To look at it by hand run clauses 1 to 3 of `dev/demos/P1-I7.sh` against a dev ledger (`tl init --dev`, `tl login demo`, `tl serve`, `tl integration serve`); the samples are written by `dev/demos/p1_i7_demo.py prepare`.

1. **A contractor's inspection results land in the ledger, and nobody can pose as the contractor.**
   - Where: `tl integration app add acme-nde ...`, `tl endpoint create acme-nde/results --mapping-file map.jsonata --allow SetPsetValues`, `tl delivery dry-run`, `tl endpoint mode ... live`, `tl endpoint enable`, then a signed `POST /in/acme-nde/results`; `tl integration serve --once`; `tl pset get V-1001 --project P123`. TUI: `Ctrl+E`, key `1` (endpoints).
   - Standard activity: loading results a vendor sends into the project's records.
   - Novel approach: the sender writes nothing directly. A restricted mapping (a JSONata subset that runs in a resource-limited child process) turns the payload into a list of allow-listed commands, run as the endpoint's own service actor, all or none; the same signed message twice is refused, an unsigned one and an unknown path get fixed answers that say nothing.
   - Unique value: every field the vendor set carries `inbound:acme-nde/results` as its source and can be traced and dry-run before it is live; a bad delivery waits in an error queue an admin can fix and retry, and the payload is never shown in a message or an event.
2. **A rule that tells HSE, shown before it runs, and one that cannot run away.**
   - Where: `tl rule create --file hse.json`, `tl rule dry-run hse-notify` (lists what it would have done over past posts), `tl rule mode hse-notify act`, `tl rule enable`, `tl feed post "... #safety"`, `tl integration serve --once`, `tl feed ls`. The ping and pong rules of the demo answer each other and stop at the third level.
   - Standard activity: "when a safety issue is posted, tell HSE".
   - Novel approach: a rule is data, not code; it starts in propose mode, has a dry run over history, runs as `svc:rule-<key>` with a declared access that the runner checks against the ledger, and is bounded in depth, steps and commands.
   - Unique value: an admin can see exactly what a rule would have done last week before switching it on, and a loop is a recorded `depth_limit` firing, not an outage.
3. **A classifier proposes, a person decides.**
   - Where: `tl enricher register doc_classifier --file enricher.json`, `tl enricher enable`, `tl doc register ISD-001 --title "Piping isometric drawing, unit 47"`, `tl integration serve --once`, `tl enrich ls`, `tl enrich accept <id>` or the TUI `Ctrl+R`, then `tl pset get ISD-001`.
   - Standard activity: tagging a document with its type and discipline.
   - Novel approach: the enricher is a deterministic keyword table (no model); its values wait in a review queue with their evidence and confidence, and are written only into their own `enrich.doc_classifier.*` layer, never over an authoritative field. A rejection takes a reason and the same value is not proposed again.
   - Unique value: the classification is searchable like any pset yet always labelled as proposed by `doc_classifier@1.0.0` and accepted by a named person.
4. **An action that calls out, signed and bounded.**
   - Where: `tl action define --file action.json` (prints the signing secret once), `tl action invoke send_to_nde --target V-1001 --param method=RT`, `tl integration serve --once`, `tl action invocations`.
   - Standard activity: asking an NDE contractor to inspect a weld from the record.
   - Novel approach: the call goes only to an allow-listed host, resolved once and pinned, signed with the Standard Webhooks recipe, under a total deadline, and the answer is stored as the result; an action that needs approval becomes a proposal.
   - Unique value: the receiver can verify who asked, the ledger records the request and the answer, and one switch (`integration.kill_switch`) stops it all.

## Cost notes
Not tracked per call. Eleven Haiku-tier tickets ran through the relay (ten passed on the first attempt; T02b was blocked once by a stale generated file on its base); everything on the trust boundary, the engines and both rounds of security fixes were supervisor work. The full suite on both adapters takes about two hours on this container.
