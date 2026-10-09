# Build spec 05 — Phase 0 plan: increments and tickets

Phase 0 builds the platform core (§16, §29.3). Eight increments. Increments 1 and 3 are single-workstream
(supervisor only). Increments 2, 4, 5, 6, 7 have an orchestrator fanout. Increment 8 is orchestrator-led hardening.

Ticket IDs: `P0-I<inc>-T<nn>`. Tier `S` = supervisor builds it, `H` = implementer ticket.
"Depends" lists tickets that must be merged first. Each increment folder `docs/tickets/P0-I<n>/` holds the
plan README and one file per ticket; the tables below are the seed the supervisor expands.

Phase 0 exit (§16): create, link, and set psets on any generic record in TUI, API, and MCP; live updates between
two TUIs; a signed webhook delivered for a filtered subscription; full restore from backup verified.

---

## Increment 1 — Foundations

**Goal:** monorepo, LinkML core, codegen pipeline, SQLite ledger, current-state table, `tl` CLI.
**Demo:** `tl record create --project P123 --key DEMO-0001 --title "First record"` then `tl record show DEMO-0001`
shows the `cur_core_record` row, and `tl events tail` shows the `Record.Created` event with its hash.
**Workstreams:** one. **Orchestrator:** not needed (interfaces come from `03` §7).
**Supervisor builds first:** T02 (core LinkML), T04b (DDL generator core), T07 (projector engine + UnitOfWork).

| ID | Title | Tier | Depends | Allowed paths | Acceptance (summary) |
|---|---|---|---|---|---|
| T01 | Monorepo scaffold: uv workspace, package skeletons, justfile, ruff/pyright/pytest config, CI workflow | H | — | `pyproject.toml`, `justfile`, `.python-version`, `.github/workflows/ci.yml`, `packages/*/pyproject.toml`, `packages/*/src/*/__init__.py`, `tests/conftest.py` | `uv sync`; `just check` passes on empty packages; `just test` runs 1 placeholder test |
| T02 | Core LinkML: `schema/core/record.yaml` (envelope §6.2 minimal), `ledger.yaml` (Event §5.1), annotations namespace | S | T01 | `schema/core/**` | `linkml-lint` clean; `gen-pydantic` succeeds |
| T03 | Codegen wiring: `tl_schema.generate` runs gen-pydantic + gen-json-schema into `generated/`; `just gen`; drift check in `just check` | H | T02 | `packages/tl-schema/src/tl_schema/generate.py`, `generated/`, `justfile` | `just gen` idempotent; `just check` fails on a deliberate edit to generated output, passes after regen |
| T04a | DDL type mapping: LinkML slot → SQLite and Postgres column types, nullability, JSON columns, with table-driven tests | H | T02 | `packages/tl-schema/src/tl_schema/generators/ddl_types.py`, its tests | 100% of mapping table cases pass on both dialects |
| T04b | DDL generator core: class → `cur_<module>_<class>` DDL per dialect, unique index on (scope,key), deterministic output; reproduces `03` §9 exactly for `core.Record` | S | T04a | `packages/tl-schema/src/tl_schema/generators/ddl.py`, `generated/ddl/` | golden-file test equals `03` §9 |
| T05 | Ledger types and hashing: `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`, `event_hash`, canonical JSON | H | T01 | `packages/tl-core/src/tl_core/ledger/types.py`, `hashing.py`, tests | hash vectors test; canonical JSON stable under key order |
| T06 | SQLite ledger adapter: `events` table, append with optimistic concurrency, per-scope hash chain, `read_stream`, `read_after`, `head_seq`; append-only enforced by triggers | H | T05 | `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py`, `schema.sql`, tests | provided test file passes incl. concurrency, chain continuity, trigger rejects UPDATE/DELETE |
| T07 | Projector engine + SQLite `UnitOfWork`: single transaction for append + inline projectors; registry; `reset`; in-process bus publish on commit | S | T05, T06 | `packages/tl-core/src/tl_core/projection/**`, `uow.py`, `bus.py`, `tl_adapters/sqlite/uow.py` | property test: replay twice → identical `cur_` rows |
| T08 | `core.Record` projector: handlers for `Record.Created/Updated/Voided/Corrected` into `cur_core_record` using generated DDL | H | T04b, T07 | `packages/tl-core/src/tl_core/projection/record.py`, tests | each event type updates the row as specified; voided flag set, row never deleted |
| T09 | `CreateRecord`, `UpdateRecord`, `VoidRecord` command handlers | H | T07, T08 | `packages/tl-core/src/tl_core/services/commands.py`, `services/records.py`, tests | handler emits the right events; second create with same key raises; void requires reason |
| T10 | `tl` CLI: `tl init`, `tl record create/show/void`, `tl events tail`, `tl projections rebuild` | H | T09 | `packages/tl-cli/**` | CLI e2e test runs the demo sequence against a temp ledger |
| T11 | Query helper: `get_record(uow, scope, key)` and `list_records(scope, filters)` over `cur_core_record` | H | T08 | `packages/tl-core/src/tl_core/services/queries.py`, tests | filters by status/voided; returns envelope dict |
| T12 | Demo script, module READMEs, `packages/*/AGENTS.md` stubs, increment report scaffold | H | T10 | `dev/demos/P0-I1.sh`, `packages/*/README.md`, `packages/*/AGENTS.md` | `just demo P0-I1` runs clean on a fresh clone |

**Escalation triggers:** generated DDL cannot be dialect-neutral for a needed type; hash-chain design conflicts with per-scope partitioning; CLI needs numbering (defer to I3, use explicit keys).

Worked example tickets for T01, T05, T06, T10 are in `docs/tickets/P0-I1/`.

---

## Increment 2 — Layered psets, schema registry v0, effective schema, TUI shell

**Goal:** company standard pset with enforcement + project extension (§6.3 example), compiled into an effective
schema with a hash; `Pset.ValuesSet` validated and projected; TUI shell with grid and record view in embedded mode.
**Demo:** load `co.acme.engineering@3.2.0` and `x.P123@1.4.0` fixtures; `tl schema hash P123`; set `valve_data.size_in`
and `valve_data.x.fat_witness_by` on a record in the TUI; see conformance warning for a missing advisory property.
**Fanout (orchestrator):** two workstreams, WS-A schema, WS-B TUI. Shared contract: the `ClientInterface` Protocol
(`tl_tui/client.py`) and the form/grid metadata JSON shape, written by the orchestrator before fanout.

WS-A schema (supervisor A)

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Package loader: read `schema/fixtures/*.yaml` packages, validate structure, version pins | H | — |
| T02 | Pset LinkML annotations (`tl:enforcement`, `tl:value_list_policy`, `tl:materialize`, `custom_section`, `adoption`) and compile psets to classes | S | T01 |
| T03 | Effective schema compiler: `SchemaView` merge of core + company + project packages; content hash; cache by hash | S | T02 |
| T04 | JSON Schema per record type from the effective schema; runtime validator | H | T03 |
| T05 | Conformance evaluator: enforcement levels, required-in-states, value-list policy with crosswalk, lenient/strict modes → `ok/warning/nonconformant/waived` | H (rules pasted) | T04 |
| T06 | `SetPsetValues` command + `Pset.ValuesSet` event with `effective_schema_hash`; layer-aware paths | H | T04 |
| T07 | `cur_pset_values` long-form projector + promoted columns for `materialize: true` via DDL generator extension | S | T06 |
| T08 | `tl schema lint|hash|validate` CLI; `tl pset set/get` | H | T05, T06 |
| T09 | Fixture packages from §6.3 example + tests that reproduce every row of the "projects can / cannot" table | H | T02 |
| T10 | `Schema.EffectiveChanged` event and hot reload hook on the bus | H | T03 |

WS-B TUI (supervisor B)

| ID | Title | Tier | Depends |
|---|---|---|---|
| T11 | `ClientInterface` embedded implementation over `tl_core` services (contract from orchestrator) | S | — |
| T12 | App shell: header, nav tree, main area, context panel, footer; panel collapse; narrow mode (§10.1, sketch 11) | H | T11 |
| T13 | Data grid widget: virtualised rows from `list_records`, column chooser, sort, multi-select, copy TSV | S core, H polish | T11 |
| T14 | Record view: header + Details tab + History tab from `read_stream` | H | T12 |
| T15 | Psets tab: layer-grouped rendering with enforcement markers (sketch 2) from form metadata | H | T14, WS-A T05 |
| T16 | Generated forms: field widgets per LinkML type, validation errors inline, Save → `SetPsetValues` | H | T15 |
| T17 | Snapshot tests for shell, grid, record view, psets tab; key map for `n e Ctrl+S Esc [ ]` | H | T16 |
| T18 | `just tui` recipe, demo script, report | H | T17 |

Merge order: WS-A T01–T07 → WS-B T11–T14 → WS-A T08–T10 → WS-B T15–T18.

---

## Increment 3 — Links, numbering, workflow; palette, link picker, trace

**Goal:** link lifecycle (§7.1), key detection, reference tray, numbering patterns, declarative workflows with guards.
**Demo:** `tl record create --type core.Record --title "NCR"` gets key `P123-REC-0001` from a pattern; link two
records by key in the picker; transition blocked by a missing expected link, then allowed after linking.
**Workstreams:** one (supervisor). The engines dominate; implementer tickets fill in around them.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Link model, relation vocabulary with inverses and per-type-pair defaults (§7.1), events | H | — |
| T02 | Link commands: suggest/add/accept/decline/repin/verify/flag/retract; never delete | H | T01 |
| T03 | `cur_links` projector (both directions, status, pin) + link counts on `cur_core_record` | H | T02 |
| T04 | Expected links (`tl:expects_link`) evaluation → missing list per record | H | T03 |
| T05 | Numbering pattern parser (`{project}-{type}-{seq:4}` segments, regex compile, parse back) | H | — |
| T06 | Numbering allocator: per-pattern sequence table, transactional, optional gap-free, reserved ranges stub | S | T05 |
| T07 | Key detection: scan text for keys matching registered patterns → suggestion chips | H | T05 |
| T08 | Workflow definition loader (YAML/LinkML): states, transitions, guards (required psets, required links, roles) | H | — |
| T09 | Workflow engine: evaluate transition, run guards, emit `Workflow.Transitioned`, update `status`/`state_entered_at` | S | T08, T04 |
| T10 | `TransitionWorkflow` command + CLI `tl wf transition` | H | T09 |
| T11 | Command palette widget (fuzzy over commands, types, keys) | H | I2 shell |
| T12 | Link picker modal (sketch 4): search, relation, pin, create-and-link | H | T02, T11 |
| T13 | Links tab (sketch 12) + reference tray overlay + back/forward history | H | T03, T12 |
| T14 | Trace view: n-hop tree over `cur_links` | H | T03 |
| T15 | Workflow action menu (`w`) + guard failure display | H | T10 |
| T16 | Snapshot tests, demo, report | H | T15 |

---

## Increment 4 — Files/uploads, REST API, MCP read tools, change feed, live TUI

**Fanout (orchestrator):** four workstreams. Shared contracts: query-language AST + `QuerySpec` (orchestrator writes
with the supervisor of WS-A), `Bus` subscription semantics (`03` §7), REST resource naming from LinkML.

| WS | Workstream | Supervisor builds | Implementer tickets (summary) |
|---|---|---|---|
| A | Query language + change feed | Parser and SQL compiler for the filter language (§10.2); `seq` cursor polling subscriber | AST dataclasses with tests; operator table; `read_after` poller; subscription registry; bus tests |
| B | Files | File slots in LinkML; upload service (hash verify, dedupe); multipart | `ObjectStore` MinIO adapter against Protocol; `File.*` events + `cur_files` projector; docker compose MinIO; CLI `tl file put/get`; quarantine flag |
| C | API + MCP | FastAPI app factory, auth stub (local accounts), generated route registration, error model | per-resource routes (`/records`, `/records/{id}/links`, `/events?after=`), commands endpoint, SSE endpoint, OpenAPI check test; MCP server skeleton; read tools `search_records`, `get_record`, `get_links`, `trace`; resources |
| D | Live TUI | Remote `ClientInterface` over HTTP + SSE; conflict detection via `stream_version` | grid live row highlight; record view "updated by X" banner; filter bar wired to query language; `F6` panels; snapshot tests |

Merge order: A → B → C → D. Exit demo: two TUIs (one embedded, one remote) and an MCP agent see the same record change within 2 s.

---

## Increment 5 — Postgres adapter, parity suite, outbox + webhooks, event catalog

**Fanout:** two workstreams. Contracts: parity fixture interface; outbox table shape; CloudEvents envelope (§18.3) as LinkML.

| WS | Supervisor builds | Implementer tickets (summary) |
|---|---|---|
| A Postgres | Postgres ledger with triggers forbidding UPDATE/DELETE, JSONB, LISTEN/NOTIFY wake-ups; `tl migrate --from sqlite --to postgres` | Postgres UoW; Postgres projector DDL dialect via generator; parity fixtures; compose Postgres; CI parity job |
| B Webhooks | Outbox written in the same transaction; HMAC signing (Standard Webhooks); per-subject ordering; retry policy | `WebhookSubscription` record + filter model (§18.2) in LinkML; delivery worker loop; DLQ + replay by `seq`; test receiver in `dev/`; event catalog generator (JSON Schema + samples + AsyncAPI); contract tests payload-vs-catalog |

---

## Increment 6 — Feed core + hashtags, MCP write tools, simulator v0

**Fanout:** three workstreams. Contracts: `ActivityPost`/`EventCard` LinkML (§19.2), MCP tool permission model (propose vs write), simulator actor interface.

| WS | Supervisor builds | Implementer tickets (summary) |
|---|---|---|
| A Feed | Hashtag parser with Standards-pattern resolution; event-card aggregation rules | `Feed.*` events + projector; feed query (project, record one-hop, hashtag); TUI feed pane (sketch 6); composer autocomplete; `#hold` → constraint proposal stub |
| B MCP write | Propose-only mode, review queue, `source=mcp:<agent>` tagging, budgets | tools `create_record`, `update_psets`, `link_records`, `transition_workflow`, `post_feed`; agent identity record; contract tests |
| C Simulator | Orchestrator loop (`sim_create/advance/inject/status/assert`), deterministic actor base class, ground-truth log | scenario loader; actors: document controller, planner, crew (generic records in Phase 0); seed template; `just seed`; assertions over `cur_` tables |

---

## Increment 7 — Backup, ledger archive, restore, DuckLake v0

**Fanout:** two workstreams. Contracts: archive segment format (NDJSON + Parquet + signed manifest, §24.3); lake sync watermark.

| WS | Supervisor builds | Implementer tickets (summary) |
|---|---|---|
| A Ops | Archive sealer continuing the hash chain; verify tool; restore-from-archive replay | Litestream config; pgBackRest config + compose; `tl archive seal/verify`; `tl restore --from-archive`; restore drill script and report template; runbooks |
| B Lake | DuckLake catalog bootstrap; `tl lake sync` incremental by `seq` with snapshot watermark | bronze `events` loader; silver `cur_core_record`, `links`, `pset_values` from generated schema; `lake_query` MCP tool (read-only, row limit); DuckDB demo queries |

---

## Increment 8 — Hardening and Phase 0 exit

Orchestrator-led. Supervisors take: (a) exit-criteria demo on a simulated project, (b) about:config v1 (`SettingDefinition`, `Setting.Changed`, TUI screen sketch 14) and extension-type registry v0 (§31 `TypeRegistration`, directory watcher), (c) docs, AGENTS.md per package, dev MCP server (§25.3) with `run_tests`, `gen`, `query_db`, `render_screen`, (d) performance pass against §15 targets at 100k records, (e) risk register and phase report.

Exit checklist is the §16 Phase 0 exit plus `04-gates.md` §1 all green on `main`.
