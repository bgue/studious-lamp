# ADR-0015 — M11: cost snapshots and P6 schedule snapshots

Status: accepted 2026-10-17 by the orchestrator under ADR-0008 decision 6 (proposed by the P1-I4 supervisor)
Date: 2026-10-17
Deciders: P1-I4 supervisor (proposal); accepted by the orchestrator
Brief sections: §9 M11, §7.2 and §7.3 (links by stable id, orphans), §9 M1 (derivation, shared with ADR-0014), §28 (lake bronze and silver), §8 and §18 (access, agents propose)

## Context
P1-I4 builds M11: a mirror of the cost system's codes with period snapshots, and P6 schedules read from XER files, each upload an immutable snapshot, compared with the one before, published as the current schedule, and linked to by stable activity id.

An XER file is **untrusted input** from a person's tool, as the PDF and spreadsheet extractors of P1-I3 were. Everything P1-I3 learned about those readers applies (L-P1-I3B-1 to 8, L-P1-I3-10): bound every dimension and refuse instead of cutting, no clock, no unpickling, fixed messages, the resource envelope of ADR-0014.

## Decision

### 1. Two modules, `cost` and `schedule`
Module name equals record-type prefix (ADR-0010), so M11 is two modules. Record types:

| Type | Key | Notes |
|---|---|---|
| `cost.CostCode` | the code (`4210-PIP-WLD`) | hierarchy, unit of measure, and the latest measure matrix: {hours, quantity, amount} x {budget, actual, earned, forecast to complete, estimate at completion} with the period and the as-of date |
| `cost.CostSnapshot` | `<period>@<revision>` (`2026-09@1`) | one imported period; a corrected file is the next revision |
| `schedule.Schedule` | its code (`MAIN`) | the series of snapshots of one P6 project; points at the current snapshot |
| `schedule.ScheduleSnapshot` | `<schedule>#<n>` (`MAIN#2`) | one XER upload; also the **job record** of its build |
| `schedule.ActivityRef` | `<schedule>/<activity id>` (`MAIN/A1230`) | the stable target of links to one activity |

Figures per cost code per snapshot are kept (`cur_cost_snapshot_value`), so a report can say what the matrix was in an earlier period. A late snapshot (an earlier as-of date) adds history and leaves the matrix of a later one alone.

### 2. Reading an XER file (`packages/tl-xer`)
The reader is pure Python (stdlib only; no PyPI XER library is used, so no new licence). It is a security-reviewed parser of untrusted input:

- **Refuse, never cut.** Bytes (50 MiB), tables (300), columns (200), rows per table (400 000), cells over the file (6 million), characters per field (32 000), and the typed rows (60 000 activities, 200 000 relationships, 60 000 WBS nodes, 2 000 calendars, 300 000 codes, 300 000 user field values) are bounds; a file over any is refused with a fixed code. A tab count is taken before a line is split.
- **Encoding is decided once.** UTF-16 is refused; a UTF-8 byte-order mark or valid UTF-8 means UTF-8; plain ASCII is ASCII; anything else is Windows-1252 (what P6 writes by default); a byte Windows-1252 leaves undefined is refused. NUL, other control characters, line and paragraph separators and text-direction marks refuse the file (a NUL crashes Postgres, a mark spoofs a screen).
- **No clock, no state.** The same bytes give the same result, byte for byte (`process` is a pure function; the gzip of the raw bundle carries no time stamp).
- **Runs in the D9 envelope** (`tl_core.derivation.envelope.run_in_envelope`): a child process with a scrubbed environment, address-space and CPU limits and a wall clock. The answer is three frames (metadata JSON, typed snapshot JSON, gzip bytes) and **nothing is unpickled**. The parent does not believe the child: lengths, the report's fields, the SHA-256 of the typed frame, every cell of every typed row against its column kind, and the inflated hash of the raw bundle are checked before a result exists (`tl_xer.wire`). A breach, a crash or a malformed answer is `XerLimitError` with fixed text.
- **Messages are fixed text.** The only values in them are table and column names that passed a name pattern, activity ids that passed the id check, project names that passed the length check, and counts. No path, no cell, no exception text.
- Measured (SQLite and the envelope): a file of 20 MB with 60 000 activities and 3.1 million cells reads in 9 s with 330 MB in the child; a file at 47.5 MB and 5.9 million cells in 12 s with 550 MB (limits: 60 s, 1 GiB).

### 3. The XER document schema (validation)
`tl_xer.typed.analyse` checks, and reports with codes (`error` blocks the snapshot, `warning` does not): a supported P6 version (8.x to 30.x); the tables `PROJECT`, `PROJWBS`, `CALENDAR`, `TASK`, `TASKPRED` and their required columns; **one project**: a file with several needs the one to read named (`Schedule.p6_project` or the snapshot's option), a named project the file lacks is an error, relationships to other projects are left out with a warning; a data date (`last_recalc_date`); unique non-empty activity ids of at most 60 characters; dates written `YYYY-MM-DD HH:MM` and real; plain decimal numbers; known task types and statuses; every reference resolving (WBS, calendar, predecessor); a WBS tree with no loop, at most 100 deep and with no path over 500 characters. Optional tables (activity codes, user fields) missing or partial are warnings. The typed rows are activities, relationships, WBS, calendars, activity codes and user fields; every other table lives in the raw bundle only.

Units: durations and floats are hours as P6 writes them; a day is the activity's calendar `day_hr` (8 when unknown). Dates are ISO local date-times without a zone. `critical` means total float zero or less and not complete.

### 4. A snapshot is a job and its rows are operational tables
- **The build is a job** in the ADR-0014 queue (`job_queue`, kind `schedule.build`); the **job id is the snapshot's id** and the snapshot is the job record, so its attempts are events on its own stream (`BuildStarted`, `BuildFailed`, then `Built` or `Rejected`). A worker (`tl xer worker`) claims, reads the file in the envelope, and settles in one transaction. A merely bad file is not a failed job: the snapshot is `Invalid` and its report says why. A breach of the envelope fails the job for good and leaves the snapshot `Invalid` (FANOUT D9).
- **Workflow** `schedule.schedule-snapshot`: Uploaded, Processing, Invalid or Valid, Published, Superseded, Void. Moves are made by the module's commands and the job, never by the generic `TransitionWorkflow`.
- **The typed rows are operational tables** (`sched_activity`, `sched_relationship`, `sched_wbs`, `sched_calendar`, `sched_activity_code`, `sched_udf_value`), like `job_queue`: no event produces them, a projection rebuild never clears them, the archive and webhooks never read them. 20 000 activities of up to 100 columns would make events of megabytes (ADR-0014 alternatives); the ledger holds the facts (`Built`: counts and the SHA-256 of the canonical typed rows) and the rows come from the source file. After a restore `tl xer reconcile` reads the source file again, checks the typed hash against the one recorded and writes the rows. The rows of a snapshot are written once and never updated: a snapshot is immutable.
- **Bronze** is the verbatim tables of the file, every one, as gzip-compressed JSON lines in the slot `raw` of the snapshot (SHA-256 of the uncompressed text recorded). The lake sync loads them into `xer_<table>` (T11); the Parquet files are DuckLake's own. (The plan's "Parquet via the lake bronze loader" is met by the lake: the ledger path writes no Parquet and needs no `pyarrow`, which is not locked.)

### 5. Links by stable activity id (brief 7.2, 7.3)
A record links to an activity with `LinkActivity`, which makes the **reference record** `schedule.ActivityRef` for `<schedule>/<activity id>` the first time and then the core `AddLink` (relation `references`, the activity told by the type of the target). A link is **floating** (resolves to the current snapshot) or **pinned to a snapshot number** (resolves to that snapshot). `resolver.resolve_activity(..., as_of)` reads the activity of the current snapshot, of a numbered snapshot, or of the latest published snapshot on or before a date; only Published and Superseded snapshots are history. Publishing a snapshot checks every reference of the schedule against it: a reference whose activity is gone is marked absent and its active links are **flagged stale** with a fixed reason (`activity is not in the published snapshot`), one whose activity is back is marked present and the links *this module* flagged are **restored** (`Link.Repinned`); a link a person flagged stays flagged. A link to an activity absent from the current snapshot cannot be made.

### 6. Comparison (`compare.py`)
Between any two snapshots of a schedule (default: the built snapshot with the latest earlier data date): activities added and removed by id; date shifts (the eight dates, in calendar days, positive is later; the time of day is ignored; a date that appears or goes has no shift); total float change in days of each activity's own calendar (a negative change is erosion); logic changes (relationships added, removed, changed in type or lag); percent complete, status and remaining duration; original duration; activities that entered or left the critical set; the shift of the latest early finish as a stand-in for the project finish. Lists are sorted so the same rows give the same comparison; a view cuts them to a limit and says how many there were.

### 7. Access (ADR-0011, ADR-0013)
| Act | Who | Why |
|---|---|---|
| Open a snapshot, attach the XER file (slot `xer`, `Uploaded` only), queue the build, link a record to an activity | any signed-in person | They create an unpublished, immutable snapshot or a link and change nothing a reader of the current schedule sees. Starting an extraction is open for the same reason (ADR-0014 D6). A file is queued once and the same file never twice for a schedule. |
| `DefineSchedule`, `PublishScheduleSnapshot`, `VoidScheduleSnapshot` | document controller or admin (`control.command.<Name>`) | What the project's current schedule is must not be changed by anyone signed in; publishing flags links. The controller role exists for controlling acts (ADR-0013); a planner who is to publish holds it. |
| `ImportCostSnapshot` (apply) | admin | The figures are money and Phase 1 has no cost role; a follow-up if the owner wants one. The preview (the plan) writes nothing and is open to any signed-in person. |
| `tl xer worker`, `tl xer reconcile` | admin (a process that writes as the service) | Operations, not planning acts. |
| Reads (schedules, snapshots, comparison, resolution, look-ahead, cost codes) | `document.read`, so agents may read | |
| Agents | propose only | `PublishScheduleSnapshot` is a proposable command (access `controller` for the person who accepts). No agent tool changes a record. |

The upload slots `report` and `raw` are written by the module only (the snapshot's upload guard, as ADR-0014 for derived documents).

## Consequences
- Contracts: none changed in `tl_core`. New: two entry points `throughline.modules`, the workspace package `tl-xer`, the job kind `schedule.build` in the existing queue, `ScheduleTables` (an operational-table projector like `JobQueueTables`).
- Schema (all additive, ADR-0008 decision 6): `schema/modules/cost/**`, `schema/modules/schedule/**`, the snapshot workflow and file-slot fixtures. Eleven event types; tables `cur_cost_costcode`, `cur_cost_cost_snapshot`, `cur_cost_snapshot_value`, `cur_schedule_schedule`, `cur_schedule_schedule_snapshot`, `cur_schedule_activity_ref`, and the six `sched_*` tables.
- Security review: the XER reader, its envelope and wire checks, the job kind, the access table, the upload guard, the orphan flagging at publication, the commands and routes.
- Known limits: no re-pinning of a link by a person to another snapshot in the TUI (use `RepinLink`); moving a mirrored cost code to another parent is refused; XML and API imports of P6 are later connectors that produce the same snapshot structure; the settle transaction holds the writer lock while it writes the typed rows (seconds on SQLite, tens of seconds on Postgres at 60 000 activities; measured in the report); resource assignments (`TASKRSRC`) and baselines inside one XER file are in the raw bundle only; an XER with several P6 projects reads one of them.

## Alternatives considered
| Option | Why not |
|---|---|
| One module for cost and schedule | Record types must start with the module name; `m11.*` names would not match the brief's records |
| Parse inside the upload request | Up to 60 s of CPU in a request; a worker holds the limits and the retry rules (ADR-0014) |
| Typed rows as event payloads | Megabytes per event and per snapshot; every projector and the lake would carry them (ADR-0014) |
| Typed rows as projections that read the file | A projection must be a function of events; reading object storage during a rebuild is neither deterministic nor fast |
| A PyPI XER library | A new dependency with its own parsing limits to audit; the format is small and the bounds are the point |
| Links to the snapshot row | The row changes every upload; the stable id is the brief's requirement |
| A new link relation `scheduled_by` | The vocabulary is the thirteen of brief 7.1 and is not yet extensible by modules; `references` plus the type of the target says the same |
