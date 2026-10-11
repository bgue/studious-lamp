# Phase 0 report: foundations (core platform)

Purpose: the record of what Phase 0 built, what it deviated from, where each gate stands, and everything that is left for a human or for engineering. Written 2026-10-11 by the P0-I8 workstream E supervisor as a draft for the orchestrator, who fills the final gate numbers (§3) after the last merge. Companion documents: `docs/reports/PHASE-0-AUDIT.md` (each §16 bullet against the code), `docs/reports/RISKS.md` (the register), `docs/reports/P0-I8.md` (the exit increment), `docs/reports/STATUS.md`, `docs/reports/APPROVALS.md`.

## 1. Outcome

The four clauses of the §16 Phase 0 exit are met and demonstrated by one script on a simulated project, `just demo P0-I8` (about 90 seconds, a PASS line per clause): a record is created, linked and given psets through the TUI (headless pilot), the REST API and MCP (an agent proposes, a person accepts); a second TUI repaints a change in about 0.1 s; an independent loopback receiver verifies every signed event of a filtered subscription and receives none of the unmatched ones; the ledger archive restores into SQLite and into a scratch Postgres database with equal state and verified hash chains. The audit finds 16 of 22 rows done, 3 partial (ledger on two adapters but services on SQLite only, ops/upgrade tooling, cross-reference operations) and 3 deviations (comments, MinIO, simulator through MCP). Nothing is deployable: real authentication, permissions and secrets handling are human gates that were not crossed.

## 2. What was built, by increment

Each paragraph links the increment report; its workstream reports and ticket reports hang off it.

- **P0-I1 Foundations** (`docs/reports/P0-I1.md`). A uv workspace of seven packages behind `just`; the LinkML core model with deterministic codegen (Pydantic, JSON Schema, SQLite and Postgres DDL) and a drift gate; the append-only SQLite ledger with a per-scope hash chain; the projector engine and unit of work (events and projections commit together, an ordered in-process bus); `core.Record` commands and queries; the `tl` CLI. 12 tickets, 284 tests.
- **P0-I2 Layered psets, schema registry v0, effective schema, TUI shell** (`P0-I2.md`, `P0-I2-A.md`). A company standard pset plus a project extension compile into a hashed effective schema; `Pset.ValuesSet` is validated, conformance-evaluated and projected; a Textual shell with grid, record view and generated forms in embedded mode. 27 tickets across two workstreams, 812 tests.
- **P0-I3 Links, numbering, workflow** (`P0-I3.md`). Links as streams with a lifecycle and a relation vocabulary; expected links; numbering allocated in the creating transaction; a declarative workflow engine with guards; the palette, link picker, links tab, reference tray, back/forward, trace, workflow menu; an atomic `EditRecord`. 16 tickets, 1424 tests.
- **P0-I4 Files, REST API, MCP read tools, change feed, live TUI** (`P0-I4.md`, `P0-I4-A.md`, `-B.md`, `-C.md`). One query language for TUI, API and MCP; a content-addressed object store (`fs` and moto-tested `s3`) with an upload service; FastAPI with SSE, an OpenAPI drift check and the dev identity stub (ADR-0005); MCP read tools; a remote TUI over HTTP and SSE with live marks and a conflict banner (20 to 200 ms measured). 25 tickets merged, 2941 tests.
- **P0-I5 Postgres, parity, outbox and webhooks, event catalog** (`P0-I5.md`, `P0-I5-A.md`). A Postgres adapter on `pg8000` (psycopg refused: LGPL) with advisory-lock writers and an identical-behaviour parity suite (1234 tests on both adapters); the outbox written in the event's transaction; Standard Webhooks signing, per-subject ordering, retries, DLQ, replay, rotation and an SSRF-safe egress policy; the generated event catalog with contract tests. 20 tickets, 2580 tests.
- **P0-I6 Feed, MCP write tools, simulator v0** (`P0-I6.md`, `-A.md`, `-B.md`, `-C.md`). Posts, hashtags, aggregated event cards and the TUI feed pane; propose-only MCP write tools with a review queue (`tl proposal`), an agent budget and the rule that an `agent:` token never changes a record (B15); a deterministic seeded team that plays working days through the API and MCP, with ground truth and `sim_assert`. About 12 tickets plus supervisor pieces, 3893 tests.
- **P0-I7 Backup, archive, restore, DuckLake** (`P0-I7.md`, `-A.md`, `-B.md`). Signed hash-chained archive segments, `tl archive verify`, `tl restore --from-archive` into SQLite or Postgres, `tl ledger verify`; Litestream and pgBackRest drilled with measured RPO and RTO; a DuckLake copy (bronze events, silver current state) synced by seq and queried through a guarded read-only `lake_query`. 12 tickets, 3307 tests, parity 1451.
- **P0-I8 Hardening and exit** (`P0-I8.md`; workstreams `P0-I8-A.md` settings, `P0-I8-B.md` extension types, `P0-I8-C.md` agent-dev, `P0-I8-D.md` and `P0-I8-perf.md` performance, E this exit). About:config settings v1 with layering, locks, scheduled changes and a TUI screen; extension record types from a directory of packages (validated, registered by one event or quarantined, managed or object-backed with hash-verified bodies, usable through the generic API, MCP, grid and forms, with namespaced settings keys); the dev MCP server, `tl new` scaffolders, a documentation audit and a CI review; a measured performance pass at 100k records; the exit demo, audit, risk register and this report.

## 3. Gates on the final trunk

The supervisor of workstream E ran each gate once on `p0/i8e` (results in `docs/reports/P0-I8.md` §Gates); the orchestrator fills the right-hand column after the last merge (commands from `docs/build-spec/04-gates.md` §1). The third column holds the numbers from `p0/i8e` (the tip after workstreams A to E), which are the reference point for the trunk run.

| Gate | Command | Last number seen on a branch | Final trunk |
|---|---|---|---|
| Lint, format, types | `just check` | green on `p0/i8e` (final run) | green (trunk 843809c) |
| Codegen drift | inside `just check` (`tl_schema.generate --check`, `tl_api.openapi --check`) | green | green (130 generated files up to date) |
| Licences | inside `just check` (`dev/tools/check_licences.py`) | `licences ok` | `licences ok` |
| Unit and integration tests (SQLite) | `just test` | 5302 passed, 1 skipped, 16 deselected (p0/i8e, 19 m 22 s) | 5302 passed, 1 skipped, 16 deselected (19 m 49 s) |
| Parity (SQLite and Postgres) | `just test-parity` | 2166 passed on SQLite and Postgres, no skips (p0/i8e, 31 m 43 s) | 2166 passed on SQLite and Postgres (32 m 39 s) |
| Projection determinism | `uv run pytest tests/property -k projection` | 3 passed, 1 deselected | 3 passed, 1 deselected |
| TUI snapshots | `just test-tui` | 608 passed, 26 snapshots (p0/i8e) | 608 passed, 26 snapshots (3 m 56 s) |
| Contract tests | `uv run pytest tests/contract` | 6 passed | 6 passed |
| Schema classification | `tl schema classify --base origin/main` | not built (no command) | not applicable until Phase 1 |
| Secret scan | `just scan-secrets` | 0 findings | 0 findings |
| Dependency audit | `just audit-deps` | no known vulnerabilities | no known vulnerabilities |
| CI workflow | GitHub Actions | never run on a runner | not run: no workflow run exists for the repository (human follow-up H-list) |
| Exit demo | `just demo P0-I8` | nine PASS lines, exit 0 in 1 m 57 s (p0/i8e) | nine PASS lines, exit 0 in 84 s |
| Performance benches | `just bench` (not in `just test`; `just bench-rebuild` for the 100k rebuild) | 14 passed, 2 skipped (13 m 18 s), repeated 12 m 14 s; rebuild 100k: SQLite 332 s, Postgres 2,299 s (P0-I8-D) | not re-run on the trunk; the trunk carries the p0/i8d code unchanged (numbers in the third column) |

The detailed gate-by-gate check on `p0/i8e` is `docs/reports/P0-I8.md` §Gates.

## 4. Deviations from the plan and the brief

| Deviation | Where it is decided | Consequence |
|---|---|---|
| **ADR-0002, the build environment:** no Docker daemon, native Postgres 16, `fs` object store as the default and `s3` tested with moto, Litestream from a release tarball, DuckLake extensions from PyPI wheels, no MinIO | `docs/adr/0002-build-environment-constraints.md` | MinIO and object lock have never run; services that need Docker are documentation |
| **ADR-0006, licences:** `pg8000` instead of psycopg (LGPL); `jsonschema[format-nongpl]` override; MPL-2.0 transitive, unmodified packages allowed (certifi, tqdm, fqdn, hypothesis), confirmed by the owner on 2026-10-09; a licence gate in `just check` | `docs/adr/0006-dependency-licences.md`, APPROVALS.md | A pure-Python driver costs about 0.5 ms per statement (X6 in RISKS) |
| **ADR-0004, relay orchestration:** subagents cannot spawn subagents, so supervisors returned DISPATCH blocks and the top-level session ran the ticket workflow | `docs/adr/0004-relay-orchestration.md` | Slower batches (two agents at a time on four CPUs); usage limits hit three times |
| **ADR-0005, dev-only API identity:** static tokens, allow-all `authorize`, loopback only | `docs/adr/0005-dev-only-api-identity.md` | Nothing is deployable (human gate) |
| **`query_db` is SQLite only** (C4): a function deny-list cannot guard Postgres (`ts_stat` runs a SQL string); a guard stricter than D12 (local Postgres host, `TL_ENV` dev, test or ci) | `docs/reports/P0-I8-C.md`, L-P0-I8C-1 | The dev MCP server cannot read a Postgres database until a reader role exists |
| **about:config opens on `F9`, not `Ctrl+,`** (terminals do not deliver `Ctrl+,`); screen omits diff against another project, boolean toggle on Enter, scheduled changes and company bounds (use `tl config`); no `schema.conformance.mode` key; `lake.sync.interval` needed a new `tl lake sync --watch`; `ai.agents.default_mode` is stored but nothing reads it | `docs/reports/P0-I8-A.md` (A20, D2 notes) | Ten platform keys, none with a non-live effect |
| **MCP writes are propose-only; an `agent:` token is refused every record-changing command** (B15), so the simulator's role actors use the API | `docs/reports/P0-I6.md` | "Simulator driving the suite through MCP" is met for proposals only |
| **Comments are feed posts that tag a record**; no comment or thread entity | `PHASE-0-AUDIT.md` 3f | Threads with dispatch are Phase 1 |
| **Link counts are in `cur_link_counts`**, not columns of `cur_core_record` (build spec 03 §9 freezes that DDL) | `docs/tickets/P0-I3/README.md` D5 | Grid link-count column waits |
| **No `Webhook.Delivered/Failed` events** (delivery state is `wh_*` rows, so a `*` subscription cannot feed on itself); the delivery engine lives in `tl_core.webhooks` | `docs/reports/P0-I5.md` | Delivery history is operational, not ledgered |
| **Postgres:** `events.seq` is `MAX(seq)+1` under the advisory lock, `events.payload` is TEXT; parity selected by marker and `--adapters` (build spec 03 §3 amended) | `docs/reports/P0-I5-A.md` | Writers queue on one lock (X8) |
| **CI schema classification gate is missing** (`tl schema classify` has no command) | `docs/reports/P0-I8-C.md` CI review | Gate row 04-gates §1 not enforced |
| **Performance, brief §15 at 100,000 records (two runs, SQLite and Postgres):** grid scroll, TUI grid render, realtime and rebuild meet their targets on both dialects (scroll p95 2.6 and 14 ms; render 108 and 72 ms; realtime 9 and 41 ms through the API, 254 ms from another process; rebuild 332 s and 2,299 s). **Misses, recorded as D1 to D6 in `docs/reports/P0-I8-perf.md`:** D1 `linked`, `count(linked)` and `missing(link)` filters 365 to 1017 ms (both dialects; the fix changes which table answers and needs a contract decision); D2 one pset-property sort on SQLite 163 ms then 129 ms; D3 text search on SQLite 194 ms (FTS5 later); D4 cold-cache outliers (no fix needed); D5 a live update reloads up to 5,000 rows (200 and 340 ms); D6 the 100k rebuild is one measurement per dialect | `docs/reports/P0-I8-D.md`, `P0-I8-perf.md` | Filters over link counts and text are not interactive at 100k rows; the feed projector lost its unique key (D-S65) and existing databases keep the old one (H2). Build spec 03 §9 was amended for the extra indexes |
| **Extension types v0 (workstream B):** directory-backed storage and the external `incoming/` write path are refused (`unsupported`, D11); `type.lock` is not signed (D9); discovery is a polling watcher, not bucket events (D8); a package's setting keys must be the type's prefix (`<namespace>.<snake_type>`) and exactly one more segment (D15); `store_body` gained an optional `expected_version` and a new 503 `body_store_unavailable` | `docs/reports/P0-I8-B.md`, `docs/tickets/P0-I8/README-B.md` | No permission design for who registers a type |
| **Several Sonnet-tier pieces were built by the supervisor rather than ticketed** (as the tiers rule says) and reviewed in a fresh context; the supervisor-authored engines were not merged by their authors | per-increment reports | Orchestrator or human review of engines is recorded in the increment reports |

## 5. Learnings

The run appended about 165 learnings (`docs/memory/LEARNINGS.md`). Those that change how the next phase should be run: batch only independent tickets and run `just check` on the base before relaying it (L-P0-I6A-5, L-P0-I8C-6); cap concurrent supervisors (L-P0-I5-O4); an independent review of every remote door finds a security defect the first time (L-P0-I8C-1, L-P0-I7-B4, L-P0-I6C-10); mutate the code under a test and diff a rewrite against the old one (L-P0-I6A-2, L-P0-I8D-6); write fakes from real runs (L-P0-I6C-4); count statements before optimising Postgres (L-P0-I8D-1). The orchestrator curates and archives the list at phase exit (skill rule §3).

## 6. Follow-ups

### (a) Human gates

None of these may be done by an agent under the KICKOFF delegation.

| # | Item | Why it is a gate | Where it came from |
|---|---|---|---|
| H1 | **T99, `tl migrate --from sqlite --to postgres`** (and a named approver and an ADR for it). Interim path that exists and is verified: `tl restore --from-archive` into a Postgres URL gives equal events and `cur_*` tables (exit demo, `tests/archive/test_restore.py`), but it is not a migration tool and does not copy objects | data-migration job (04-gates §2) | `docs/tickets/P0-I5/T99-migrate-sqlite-to-postgres.md` |
| H2 | **Drop `ux_cur_feed_items_open_scope` on existing databases** (`DROP INDEX`, or rebuild into a fresh database). New databases do not create it (D-S65, accepted by the orchestrator); old ones stay correct but keep the hot unique key that makes a Postgres rebuild slow | migration (data-migration gate) | L-P0-I8D-7, `P0-I8-D.md` |
| H3 | **Secrets at rest:** envelope-encrypt `wh_secret` under a per-company KMS key; a vault, then lift the `secret_setting_unavailable` refusal for `sensitivity: secret` settings; token storage beyond plaintext in a 0600 file | security (04-gates §2) | P0-I5 D15, P0-I8 D4, ADR-0005 |
| H4 | **The real authentication and permission model** (replaces ADR-0005): OIDC/SAML, RBAC and ABAC, confidentiality filters. It decides who may change or lock which setting (and approve dangerous ones), who may accept which proposal, who may register or retire an extension type, whether an MCP direct-write mode exists at all, per-agent identity and budgets, and the roles guard in workflows | auth (04-gates §2) | ADR-0005, P0-I6, P0-I8 A and B reports, D3 |
| H5 | **Production key custody, retention classes and object lock** for the ledger archive, and object versioning and lock for files; the PostgreSQL catalog for the production lake | security, retention (Q8) | `docs/reports/P0-I7.md` Needs human |
| H6 | **CI parity job unverified on a runner:** push, enable Actions and watch the first run of all six jobs (the Postgres service image locale, the 20 to 30 minute budget) | cannot run in the build container | `docs/reports/P0-I5-A.md`, `P0-I8-C.md`; no workflow run exists for the repository (2026-10-11) |
| H7 | **Locked-value clearing:** may a user clear a value in a `locked` pset? Today it is allowed and shows nonconformant; clearing the last value of an optional pset also hides its missing required properties | product question (Q14) | P0-I2 A22 |
| H8 | **Review of the delegated approvals** in `docs/reports/APPROVALS.md` (schema merges, dependencies, the ADR-0005 stub, the `pip-audit` CI tool) | the orchestrator acted under delegation | APPROVALS.md |
| H9 | **Decisions the brief leaves open that Phase 1 will meet:** Q1, Q3 to Q6, Q8, Q10 to Q18 (see RISKS.md §1); contractual workflows and clocks (M10); signing of extension type packages; the approval workflow for dangerous settings | owner and commercial/legal | RISKS.md |

### (b) Engineering follow-ups

Deduplicated from every increment report and from LEARNINGS. Items already listed in (a) are not repeated. Grouped by area; none is blocking the exit.

**Ledger, services, schema**
- `idempotency_key` is accepted and ignored on every command (`services/commands.py:21`); implement or remove (P0-I1, I3).
- `Record.Corrected` has a projector but no command; no `tl record update`; `tl events tail` reads a whole scope to find the last N events (add a tail method); `tl link` and `tl wf` print plain text (JSON waits for the API).
- `TransitionWorkflow` checks `expected_version` after the guards; the roles guard trusts the caller (D12); voiding a record does not flag its links stale (D16); `reserve_range` is a stub; relation defaults per type pair exist for `core.Record` only.
- Class binding for `class_filter` and pset engagement by class (P1-I1); waiver records and a waived list in the conformance report (P1-I8); re-evaluate stored `conformance` when the effective schema changes; keep records validating against the schema they were opened with (`effective_by_hash`).
- `tl schema classify --base origin/main` and its CI job; event upcasting and a compatibility matrix (§24.2); change classification between versions of one extension type (§27.5).
- Envelope fields `discipline`, `area`, `due` so the brief's example filter parses; `path(...)` and full-text search in the query language; `~` on numeric pset values; project time zone from about:config into the query clock; saved-query subscription filters; an index on `cur_links(status)` if a bench shows the need.
- Performance (from `P0-I8-perf.md`): decide how `count(linked)`, `linked` and `missing(link)` are answered at scale (D1: `cur_link_counts` or a counts column with the existence rule, with a parity proof); sort a pset property by its typed column using the form metadata (D2); full-text search, FTS5 on SQLite and a trigram or full-text index on Postgres (D3); a live update should re-read the changed rows, not the whole loaded page (D5); the Postgres rebuild is bound by statements (feed about 2.5 ms, links 2.7 ms, outbox 1.2 ms per event): cache the open card and the tag existence checks inside a replay, or batch the replay's inserts; run `ANALYZE` (or `PRAGMA optimize`) after a bulk load or a rebuild on SQLite (0.2 ms with statistics, 12 ms without); the API's feed hub does not use the Postgres `LISTEN/NOTIFY` wake-up; measure concurrent-writer throughput (X8); re-run the benches on dedicated hardware before committing to the figures.

**Postgres and adapters**
- Switch `tl serve`, `tl tui`, the webhook worker, `tl file`, `tl lake` and the root `--db` to `tl_adapters.db` so they run on a `postgresql://` URL; an `EmbeddedFeed` for Postgres; `render_screen` for a Postgres ledger.
- A unique constraint on `cur_files (record_id, slot, revision)` after a service review; confirm the gap-free `seq` the lake sync requires after rolled-back Postgres transactions.
- Parity run time (11 to 26 minutes): run the Hypothesis property tests on SQLite only in the PR job and on both nightly if the budget needs it.
- Think about the single advisory write lock before a load test at 300 users (X8).

**API and MCP**
- A head endpoint (`GET /events/head`) to replace the bisection in `find_head`; cursor pagination and ETags; presigned download URLs; the `PUT /uploads/{id}/content` cap from the registered size; `void_record` as a command; MCP change notifications and MCP over HTTP; MCP `follow`, `propose_links`, `add_external_ref`.
- `guarded` in `tl_mcp.errors` should catch any exception, log it server-side and return a fixed sentence, so path safety does not depend on the SDK (L-P0-I7-O1).
- A sweep of every `@app.command` docstring so `--help` is user help, not implementation steps (L-P0-I8A-11).

**TUI**
- Run the remote client's grid load, record-view reads, filter calls and commands on workers (3 s UI-thread timeout; D11, D16, L-P0-I4-O1) and add the missing tests for `RemoteFeed.head()` against an unreachable server and for concurrent in-flight commands.
- A grid link-count column and link filters (D22); inline key-detection chips with `Tab` to accept; `Shift+Enter`, `Ctrl+Enter` and `Ctrl+O` navigation; bulk paste of keys; persistence of the reference tray; an attachments view; a proposal review-queue screen with `RemoteClient` proposal methods; about:config: scheduled changes, company bounds and diff against another project in the form; open-edit rebase after a conflict; cache `form_metadata` in the grid; collapse the context panel on the wide Psets tab.
- Textual traps to keep in the AGENTS.md of `tl-tui`: markup in `Static`, DOM property names, `Select.Changed` ordering.

**Webhooks and integrations**
- Batching, per-subscription rate limits, mTLS, per-company egress lists, JSON-LD `@context`, point-in-time `record` for `full` mode and old values for `Pset.ValuesSet`, an owner notification for auto-disable, delivery-log screens and a receiver service in `tl-api`, selectors for module, domain, saved query, clock and action, hashtag events; an index on `wh_delivery (subscription_id, subject_id, status)` if a bench needs it; an integration registry with owners (R6).
- The `docs` text of `webhooks.egress.allowlist` in `schema/settings/platform.yaml` should name the tunnel ranges the validator refuses (a schema edit, so a delegated approval).

**Files**
- EXIF GPS stripping, thumbnails, OCR, conversion pipelines (`processing` in slots is declared, nothing runs it); a ClamAV scanner behind the `Scanner` Protocol and its worker; multipart upload with resume; bulk upload by filename pattern; `attachments[]` on the envelope; a lifecycle rule for `staging/`.

**Feed and proposals**
- Follow, thread and saved-query feeds, mutes and digests (§21.3); a feed rate limit; an agent identity record (display name, owner, enabled, per-agent budget); `tl proposal show` empty containers.

**Simulator**
- LLM role agents behind the `Actor` interface; per-seed output caching; simulated time on MCP and decision events; more record types as modules arrive; calibrate rates from legacy data (R14).

**Ops, backup, lake**
- Drill pgBackRest point-in-time recovery, incremental and differential backups, the encrypted S3 repository and a MinIO Litestream replica; a shadow-rebuild tool with cut-over; per-project export and restore bundles (§24.4); compensate-by-correlation (§24.5); time-travel reads.
- Lake: load bronze straight from archive Parquet; partition bronze by company, project and date; compaction and snapshot expiry; gold marts and `hist_*` tables; the lake property test (about a minute) behind a marker.

**Extension types (workstream B)**
- A long-running server sees another process's new settings keys at its next effective-schema read, not at once (a hook in the settings registry would make it immediate); a package quarantined for a `settings` clash stays quarantined until its files change, even if the other owner leaves.
- Full ReDoS hardening of package patterns (cap is 200 characters); guard `tl types watch` against an unguarded `on_change` error (a database outage); the embedded client's `_store_errors` also wraps the unit of work, so a stray SQLite `OSError` reads as "object store unavailable"; `type_warning` calls `list_types` on the UI thread at mount.
- An embedded body save returns no events, so the TUI shows the user's own body edit as foreign (`store_record_body` should return them).
- Directory-backed storage and the external `incoming/` write path (D11); signing `type.lock` (D9, a human gate when it ships); a change-classification gate between versions of one type (§27.5); activating `workflow.yaml` in a package; proposable `store_body` for agents; an `s3://` package location; a TUI grid column for body-only slots.

**Agent-dev, docs and process**
- A non-superuser `tl_dev_reader` role and a function allow-list before `query_db` may read Postgres; `tl new` kinds (correspondence domain, action, rule, enricher, connector, report, extractor) and an automatic `module.yaml` edit when a record type is added; dev MCP resources not served (module specs, screen snapshots listing, sample payloads) and tools not built (LinkML change validation, workflow and clock simulation, extraction evaluation); `just seed` scale costs unmeasured and a timed-out seed audited as `ok`; run `audit_docs.py --strict` in CI.
- Widen or poll the timing of `test_stream_events_without_a_cursor_is_live_only`; first key with a non-live effect gets an end-to-end `pending_effect` test.
- Curate and archive LEARNINGS (orchestrator, skill rule §3); the root `README.md` still says nothing under `packages/` exists.

## 7. Where to look

| Question | Open |
|---|---|
| Is the exit met? | `just demo P0-I8`, `docs/reports/PHASE-0-AUDIT.md` §2 |
| What is missing against §16? | `docs/reports/PHASE-0-AUDIT.md` §1, §3, §4 |
| What could go wrong? | `docs/reports/RISKS.md` |
| What did each increment do and decide? | `docs/reports/P0-I1.md` to `P0-I8.md` and the plans in `docs/tickets/` |
| What approvals were given on the owner's behalf? | `docs/reports/APPROVALS.md` |
| What will cost us again? | `docs/memory/LEARNINGS.md` |
