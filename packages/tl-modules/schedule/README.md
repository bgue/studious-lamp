# tl-mod-schedule (`tl_mod_schedule`)

The schedule module (M11): P6 schedules as immutable XER snapshots, built by a job, published as the current schedule, compared, looked ahead and linked to by stable activity id (§9 M11, §7.2, §7.3). Decisions: ADR-0015, ADR-0014, ADR-0010. Spec: `docs/modules/schedule/README.md`. Runbook: `docs/runbooks/schedule-snapshots.md`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_schedule.module.spec` | function | The entry point `throughline.modules` / `schedule` (record types, projectors, guards) |
| `tl_mod_schedule.names` | module | Record types, events, states, slots, the job kinds, `ORPHAN_REASON` and `SERVICE` |
| `tl_mod_schedule.handlers` | package | `DefineSchedule`, `OpenScheduleSnapshot`, `StartScheduleSnapshot`, `PublishScheduleSnapshot`, `VoidScheduleSnapshot`, `LinkActivity` |
| `tl_mod_schedule.build` | module | The job kinds `schedule.build` (read the file in the envelope, settle the typed rows) and `schedule.flag_orphans` |
| `tl_mod_schedule.worker` | module | `build_worker`: the runner over a ledger and a file service (lease `BUILD_LEASE_S`) |
| `tl_mod_schedule.orphans` | module | `run_once` (one bounded run of the flagging job), `outstanding`, `queue_check` |
| `tl_mod_schedule.reconcile` | module | After a restore: `requeue` (builds and flagging jobs) and `reconcile_tables` (typed rows from the source files) |
| `tl_mod_schedule.resolver` | module | `resolve_activity`: current, a numbered snapshot, or as of a date; orphaned links |
| `tl_mod_schedule.compare` / `lookahead` | module | Comparison of two snapshots; the look-ahead of the current one |
| `tl_mod_schedule.registry` / `views` | module | Reads (frozen rows) and the views the API, CLI, TUI and MCP return |
| `tl_mod_schedule.reports` | module | `unscheduled_records`: records of a type with no active link to an activity (of one schedule or any), read-only and bound to a project scope |
| `tl_mod_schedule.typed_store` | module | Writes and clears the typed `sched_*` rows (JSON-per-chunk on Postgres, `executemany` on SQLite) |
| `tl_mod_schedule.projectors` | package | The three record projectors and `ScheduleTables` (the operational tables, never cleared by a rebuild) |
| `tl_mod_schedule.commands` | module | `API_COMMANDS` with their access (`user` or `controller`) |
| `tl_mod_schedule.limits` | module | Command bounds, the link and reference caps, `FLAG_BATCH`, `MAX_DATA_DATE_AHEAD_DAYS`, `BUILD_LEASE_S` |
| `tl_mod_schedule.testing` | module | `ScheduleWorld`: a ledger, an object store and the commands, for tests of other packages |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, links, job queue, envelope, `tl_core.text`), `tl_xer`, `tl_schema`, `tl_adapters`, `pydantic`, `sqlalchemy`.
- Used by: the platform through its entry point; `tl_cli` (`tl xer`), `tl_api`, `tl_tui`, `tl_mcp`, `tl_sim`.

## Commands
```
just test -- packages/tl-modules/schedule
uv run pytest packages/tl-modules/schedule -q --adapters sqlite,postgres   # needs TL_PG_URL
uv run tl xer upload week1.xer --project P123 --schedule MAIN
uv run tl xer worker --once
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `tl xer worker --timeout` | 60 s | Wall clock of reading one file |
| `limits.BUILD_LEASE_S` | 600 s | How long a worker holds a claim |
| `limits.FLAG_BATCH` | 500 | Operations of one run of the flagging job |
| `limits.MAX_DATA_DATE_AHEAD_DAYS` | 31 | Furthest data date a publish accepts |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I4. Last interface change: P1-I4 (ADR-0015; `Schedule.OrphansChecked`).
