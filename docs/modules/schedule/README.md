# Module spec: schedule (M11, P6 snapshots)

Status: accepted (built in P1-I4). Brief sections: §9 M11, §7.2 and §7.3 (links by stable id, orphans), §28 (lake bronze and silver). Decisions: ADR-0015 (this module), ADR-0014 (the job queue and the resource envelope), ADR-0010 (module storage), ADR-0011 and ADR-0013 (access).

## Purpose
The schedule module keeps the series of Primavera P6 schedules a project receives as XER files. Every upload is an immutable **snapshot**; one is published as the **current** schedule. The module compares any two snapshots (date shifts, float erosion, logic changes), answers a look-ahead from the current one, and lets any record link to an activity by its **stable activity id**, so the link survives the next upload and can be read as of an earlier snapshot. Operations are in the runbook [schedule-snapshots](../../runbooks/schedule-snapshots.md); the reader is `packages/tl-xer`; the increment report is `docs/reports/P1-I4.md`.

## Record types
| Type | Key | Table | Workflow |
|---|---|---|---|
| `schedule.Schedule` | its code (`MAIN`) | `cur_schedule_schedule` | none (it points at the current snapshot) |
| `schedule.ScheduleSnapshot` | `<schedule>#<n>` (`MAIN#2`) | `cur_schedule_schedule_snapshot` | `schedule.schedule-snapshot`: Uploaded, Processing, Invalid or Valid, Published, Superseded, Void |
| `schedule.ActivityRef` | `<schedule>/<activity id>` (`MAIN/A1230`) | `cur_schedule_activity_ref` | none (a presence flag) |

The typed rows of a snapshot are **operational tables**, not projections: `sched_activity`, `sched_relationship`, `sched_wbs`, `sched_calendar`, `sched_activity_code`, `sched_udf_value`. The build job writes them, a projection rebuild never clears them, the archive and the webhooks never read them, and `tl xer reconcile` writes them again from the source files after a restore (ADR-0015 §4).

## Events
| Event type | Meaning |
|---|---|
| `Schedule.Defined` | A schedule was registered (code, title, type, owner, P6 project) |
| `ScheduleSnapshot.Defined` | The next snapshot was opened; its file is attached in the slot `xer` |
| `ScheduleSnapshot.Queued` | The build was queued (the snapshot id is the job id) |
| `ScheduleSnapshot.BuildStarted` / `BuildFailed` | One attempt of the job; a failure that can be retried leaves the snapshot Processing |
| `ScheduleSnapshot.Built` | The file was valid: counts and the SHA-256 of the canonical typed rows |
| `ScheduleSnapshot.Rejected` | The file was read but is not a valid schedule; the report says why |
| `ScheduleSnapshot.MadeCurrent` | The snapshot became current (`orphan_check_queued`) |
| `Schedule.SnapshotPublished` | The schedule now points at the snapshot |
| `Schedule.OrphansChecked` | One run of the flagging job: references changed, links flagged, links restored, complete or not |
| `ActivityRef.Defined` / `PresenceChanged` | A reference was made by the first link; its activity left or came back |

The catalog is `schema/modules/schedule/events.yaml` (generated: `packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md`).

## Lifecycle of a snapshot
1. `OpenScheduleSnapshot` opens snapshot *n* (Uploaded) and the file is attached in the slot `xer`; `StartScheduleSnapshot` queues the build. The same file is never queued twice for a schedule.
2. A worker reads the file in the resource envelope (a child process with address-space, CPU and wall-clock limits), checks it against the XER document schema and settles in one transaction: the typed rows, the report, the raw bundle (every table, gzip JSON lines, slot `raw`) and the events. A merely bad file leaves the snapshot **Invalid** with a report; a breach of the envelope fails the job for good.
3. A **Valid** snapshot can be published by the document controller: the previous current one becomes Superseded and the schedule points at the new one. A data date more than 31 days after today is refused, and so is a data date not after the current one.
4. A snapshot that is not Published can be voided with a reason. Published and Superseded snapshots are history and are never changed.

## Links by stable activity id
`LinkActivity` makes the reference `<schedule>/<activity id>` the first time and then adds a core link (relation `references`). A link **floats** (resolves to the current snapshot) or is **pinned** to a snapshot number. `resolver.resolve_activity` reads the activity in the current snapshot, in a numbered one, or in the latest published snapshot on or before a date. At most 100 links may point at one reference and at most 60 000 references belong to one schedule.

### Orphans and the "flagging in progress" window
When a published snapshot lacks an activity that links point at, those links are **flagged stale** with the fixed reason *activity is not in the published snapshot*; when the activity is back, the links *this module* flagged are restored. The work is a queued job (`schedule.flag_orphans`, runs of at most 500 operations) and not part of the publish command, so:

- Right after a publish, a link to a removed activity still reads as current until the job has run. While the job has work left, the schedule's detail view says `links_being_checked: true` (`tl xer publish` says so, and the reads of the CLI and the TUI show it).
- The job is state-derived: a lost or repeated run changes nothing wrong. If the queue was lost (a restore), `tl xer reconcile` queues it again.
- Flags are written with the actor and event source `svc:schedule`. A flag a person made is never restored by the job.
- Nothing is flagged while the typed rows of the current snapshot are missing (before `tl xer reconcile` has written them); the job fails with a clear error instead.

## Who can do what (ADR-0011, ADR-0013, ADR-0015 §7)
| Act | Who |
|---|---|
| Open a snapshot, attach the file, queue the build, link a record | any signed-in person |
| `DefineSchedule`, `PublishScheduleSnapshot`, `VoidScheduleSnapshot` | document controller or admin (`control.command.<Name>`) |
| `tl xer worker`, `tl xer reconcile` | admin |
| Reads: schedules, snapshots, activities, comparison, resolution, look-ahead | `document.read` (agents may read) |
| Agents | propose only (`PublishScheduleSnapshot` is proposable) |

## Reading a comparison
Between any two snapshots (default: the built snapshot with the latest earlier data date): activities added and removed by id; date shifts of the eight dates in calendar days (positive is later); total-float change in days of the activity's own calendar (negative is erosion); relationships added, removed or changed (type, lag); percent complete, status, remaining and original duration; activities that entered or left the critical set; the shift of the latest early finish as a stand-in for the project finish. Lists are sorted; a view cuts them at a limit and says how many there were.

## Reading it
| Surface | What | Where |
|---|---|---|
| CLI | `tl xer ls`, `show`, `activities`, `activity`, `resolve`, `health`, `compare`, `look-ahead`, `trend`, `unscheduled` | `tl_cli.xer_read`, `xer_compare`, `xer_report` |
| TUI | `F12`: schedules, snapshots, look-ahead, orphans; `c` the comparison, `a` the activities with relationships and float trend, `p` publish | `tl_tui.widgets.schedule_screen`, `compare_screen`, `activity_screen` |
| API | `GET /projects/{project}/schedules`, `.../{code}`, `.../activities`, `.../comparison`, `.../look-ahead`, `.../orphans`, `.../activity-details/{id}`, `.../activity-trends/{id}`, `.../activity-resolutions/{id}`, `GET /projects/{project}/records/{id}/activity-links` | `tl_api.routes.schedule` |
| MCP | thirteen read tools (schedules, activities, comparison, look-ahead, resolution, float trend, orphans, a record's activity links, cost codes and snapshots) and the proposal `propose_publish_schedule_snapshot` | `tl_mcp.schedule_read_tools`, `schedule_tools` |
| Lake | silver `schedule_snapshot`, `schedule_activity`; bronze `xer_<table>`; mart `mart_float_trend` | `tl_lake.xer` (second pass of `tl lake sync`) |
| Report | records of a type with no activity (`unscheduled_records`) | `tl_mod_schedule.reports` |

Every surface calls the module's views (`tl_mod_schedule.views`); none decides what moved or eroded.

## Limits worth knowing
See ADR-0015 §2 for the bounds of the XER reader (file, tables, rows, cells, text, typed rows, dates) and §4 for the measured times. A snapshot at the limits settles in about 13 s on SQLite and 25 s on Postgres; the worker's claim is 600 s.
