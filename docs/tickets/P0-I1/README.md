# Increment plan — P0-I1 Foundations

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §5.1, §5.2, §5.4, §6.1, §6.2, §14, §25.2
Branch: `p0/i1` (trunk: `claude/wizardly-allen-m2v96s`)

## Objective
Stand up the monorepo and the first vertical slice of the platform: a `uv` workspace with seven package skeletons and a
`just` interface, the core LinkML schema with a deterministic codegen pipeline (Pydantic, JSON Schema, SQLite and
Postgres DDL for `cur_core_record`), an append-only SQLite ledger with a per-scope hash chain, a projector engine and
unit of work that update `cur_core_record` in the same transaction as the events, record command handlers and queries,
and a `tl` CLI that drives all of it. Out of scope: numbering (explicit keys only), psets, links, TUI, API, Postgres
adapters (their DDL is generated and golden-tested but not executed).

## Demo
```
just demo P0-I1
```
which runs `dev/demos/P0-I1.sh` against a temporary ledger:
```
tl init
tl record create --project P123 --key DEMO-0001 --title "First record"
tl record show --project P123 DEMO-0001      # the cur_core_record row: title, status, version 1, voided false
tl events tail --project P123 -n 5           # one Record.Created line with a 64-hex hash
tl record void --project P123 DEMO-0001 --reason demo ; tl record show ... # voided: true, version 2
tl projections rebuild                       # rebuilt from the ledger; show output unchanged
```

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| T02 | Core LinkML: `schema/core/{annotations,record,ledger,core}.yaml` | Schema semantics (`01-tiers.md` §3, human gate on `schema/**`) | Orchestrator approves schema | built, committed (needs `SCHEMA_APPROVALS`) |
| T04b | DDL generator core: LinkML class to `cur_<module>_<class>` DDL per dialect, golden test equals `03` §9 | Cross-dialect generator core (§5.4) | Orchestrator or human | built on `p0/i1-t04b-ddl-core` (`b74d268`); registration in `generate.py` and generated output land after T03/T04a merge |
| T07 | Projector engine, `UnitOfWork` Protocol and SQLite implementation, in-process bus, rebuild | Ledger append plus inline projector transaction (§5) | Orchestrator or human | built on `p0/i1-t07-projector-engine` (`537e866`); verified against a scratch T05/T06; merge after T06 |
| Demo | `dev/demos/P0-I1.sh`, wired to `just demo` | Supervisor deliverable | Orchestrator | planned (after T10) |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Monorepo scaffold | H | — | merged | Blocked once on ruff docs check (fixed by D9, supervisor); reviewer: report-only findings fixed by supervisor; 1 implementer round |
| T02 | Core LinkML | S | T01 | built | committed on `p0/i1`; awaiting schema approval |
| T03 | Codegen wiring (pydantic, JSON Schema, `--check` drift gate) | H | T01, T02 | merged | Review pass round 1 |
| T04a | DDL type mapping | H | T01 | merged | Review pass round 1; supervisor added non-finite rejection |
| T04b | DDL generator core | S | T04a, T03 | merged | Registered in `generate.py`; generated DDL committed; awaiting orchestrator review |
| T05 | Ledger types and hashing | H | T01 | merged | Review pass round 1 |
| T06 | SQLite ledger adapter | H | T05 | ready | |
| T07 | Projector engine + SQLite UnitOfWork | S | T05, T06 | half merged | Contracts, registry, bus merged; SQLite UoW on side branch until T06 |
| T08 | `core.Record` projector | H | T04b, T07 (projection types) | ready | |
| T09 | Record command handlers | H | T07, T08 | planned | |
| T10 | `tl` CLI | H | T09, T11 | planned | |
| T11 | Query helpers | H | T08 | planned | |
| T12 | Package READMEs and AGENTS.md | H | T10 (interfaces known) | planned | |

Haiku-ability notes (`01-tiers.md` §6): T01 exceeds the 5-file guideline (about 25 near-identical boilerplate files, every
one given verbatim) and names dependencies; both are intentional and the ticket pastes the exact content, so a reviewer
verifies it from the diff and commands alone. All other tickets pass all seven questions; any that fails is split or
taken over (recorded here). T12 is split by package group if the file count exceeds 5.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| D1 | Shared fixtures go in a root `conftest.py`, not `tests/conftest.py` | pytest only applies a conftest to tests beneath it; package tests live in `packages/*/tests` (`03` §10 says "conftest.py at root") |
| D2 | `just check` runs `python -m tl_schema.generate --check` (compare generated files with generator output) instead of `just gen` + `git diff --exit-code` | Same gate (§25.4), but it also works on a dirty tree and catches untracked or stale files, which implementers hit before committing |
| D3 | `Event` is a standalone model with `NewEvent`'s field names, not a subclass | pyright strict rejects narrowing `effective_at` in a subclass; field names and types match `03` §7 |
| D4 | All Increment 1 dependencies are declared in T01 | Keeps `pyproject.toml` and `uv.lock` out of every later ticket (checklist item 6) |
| D5 | JSON columns are LinkML `range: Any` plus slot annotation `tl:json: true`; column name gets `_json` suffix | gen-json-schema renders a custom dict type as `string`; `Any` renders as any JSON value |
| D6 | pyright strict covers `packages/*/src` for `tl_core`, `tl_schema`, `tl_adapters`; tests are checked in standard mode | Tests stay cheap to write; engines stay strict |
| D7 | Modules that import `linkml` start with `# pyright: basic` | linkml has no type stubs |
| D8 | `SqliteLedger` exposes `append_in(conn, ...)`; `make_engine` begins write transactions with `BEGIN IMMEDIATE` | The unit of work needs ledger append and projectors in one transaction |
| D10 | Supervisor-provided test files for a ticket live in `docs/tickets/<inc>/provided/*.txt`; the ticket says `cp` them into place and the reviewer diffs | A failing test file on the base breaks pyright (`just check`) for every other ticket branch |
| D9 | `[tool.ruff] include = ["*.py", "*.pyi", "**/pyproject.toml"]` | ruff 0.16 formats Markdown too and flagged three docs files; ruff governs Python only (orchestrator decision after the T01 implementer stopped, correctly) |

## Order of work (relay rounds)
| Round | Ticket batch | Supervisor work in the same turn |
|---|---|---|
| 1 | T01 | Plan, T02, tickets T03/T04a/T05 |
| 2 | T05, T04a, T03 | Merge T01; T04b and T07 were already built on side branches (round 1 interim) |
| 3 | T06, T08 | Merge round 2; finish T04b; projection types; provided test for T06 |
| 4 | T09, T11 | Merge round 3; finish T07 (SQLite UnitOfWork) |
| 5 | T10, T12 | Merge round 4; demo script |
| Final | — | Merge, run all gates, fresh-clone demo, report |

## Risks and escalation triggers
- Generated DDL cannot be dialect-neutral for a needed type: escalate (listed trigger). So far the mapping table covers every Phase 0 slot type.
- Hash-chain per scope conflicts with a future partitioned Postgres events table: out of scope here; note in the report.
- Projector SQL touching JSONB or BOOLEAN columns needs Postgres casts: the Record projector uses bound parameters only; the Postgres run belongs to Increment 5 parity work. Not executed here.
- SQLite transaction handling through SQLAlchemy is subtle (pysqlite legacy transaction control). T06 pastes the exact engine recipe.
- Supervisor pieces cannot be reviewed by an agent in this harness (ADR-0004): T02, T04b, T07 are marked for orchestrator review.

## Blocked / Decision
(none)
