# Schedule display and commenting

Brief §13 ("schedule frontend"), §9 M11 (XER snapshots, built in P1-I4 with compare and look-ahead), §12, §16
Phase 5. Plan `11-phase5-plan.md` I2 (display, comments, statusing export) and I3 (P6 XML and EPPM connector).
Status: design v0.1. Reads only data that exists today; **(proposed)** the list, Gantt and comments can be built
beside the Phase 2 weekly cycle, which already shows the look-ahead (README §2 row 11).

## Users and stories
Scheduler or planner, workface planner, superintendent, PM, foreman (reads the look-ahead), commercial lead (delay
notices by activity), client (progress reports).
- As a **planner** I see the current snapshot's activities for my area as a list and a text Gantt, filtered by WBS and
  activity codes, with each activity's IWPs and their readiness beside it.
- As a **superintendent** I compare this week's snapshot with last week's and see what slipped and why float eroded.
- As a **PM** I leave a comment on an activity for the schedule review.
- Later, as a **planner** I status activities for the period and export the statusing back to P6.

## Records and states
| Record | States |
|---|---|
| `Schedule`, `ScheduleSnapshot`, activities, WBS, relationships, calendars, codes (M11, built) | Immutable snapshots; Valid → Published → Superseded |
| `ActivityRef` (built; `LinkActivity`) | The stable link from a record to an activity id |
| Comments | **(proposed)** the record thread of the `ActivityRef` (one per activity id and schedule) with the snapshot named in the message; no new record type |
| `ProgressStatusing` (later) | Draft → Submitted → Approved → Exported; one per schedule and period with rows per activity (% complete, remaining duration, actual dates) |

## Logs and record screens (log standard)
**Activity list** (home) over the current snapshot of the chosen schedule. Columns: Activity, Name, State (not
started, in progress, complete), Start, Finish, Float, % complete, IWPs (`2 ready / 3`), Open constraints. Filters:
WBS path, activity code, `c` critical, `w` window (weeks), `r` with unready IWPs, mine (my area). Panel: identity
`A1230 · Install rack 12 piping`; state `In progress · 40% · float 3 d`; summary `WBS 1.4.2 · 2026-11-03 to 11-21 ·
critical`; sections Dates (table Early, Late, Baseline, Actual), Logic (predecessors and successors as a table),
Linked records (IWPs with readiness, CWPs, subsystems, correspondence), Movement since previous snapshot, Comments,
Links. Actions: Open thread, Comment, Link record (`l`), Compare snapshots, Open look-ahead for this window. Later:
Status activity.
**Text Gantt**: the same rows with a week-grid of Unicode bars (planned, actual, baseline shading, critical in red by
meaning), horizontal scroll by week, the readiness overlay as a marker per bar; a row's Enter opens its record screen.
**Snapshot compare** (built: date shifts, float erosion, critical path changes) reached from the list.
**Look-ahead** (built in M11; M3 adds IWP readiness) reused here as a filter, not a second screen.
**Statusing entry** (later): a grid per period with % complete and remaining duration per activity, prefilled from
IWP progress and PPC (M3), submitted for approval, exported as XER or XML.
**Tiles:** activities starting in two weeks with unready IWPs, float eroded this snapshot, activities with open
constraints, orphaned links after a snapshot.

## Workflows and approvals
Snapshot upload, validation and publish are built (controller). Comments are thread posts. Statusing later: draft by
a planner, approved by the PM, exported; the export is a file a person sends until the EPPM connector exists, and
write-back is a human gate (Phase 5 I3).

## Links to other modules
M3 (CWP and IWP activity links, look-ahead, readiness, PPC into statusing), M8 (subsystem RFC dates vs activities),
M10 (delay and early-warning notices referencing activities), cost (activities by cost code), documents (the XER as a
document revision), models (4D overlay later, **proposed**).

## Integrations
XER upload (built); P6 XML import and EPPM API connector producing the same snapshot structure (Phase 5 I3);
statusing export (XER or XML); MCP read tools (activity, window, slips); webhooks `Schedule.SnapshotPublished`
(built) and `Statusing.Exported`; feed card per published snapshot with the slip summary **(proposed)**.

## Reports (§12)
IWPs vs P6 activity dates; activities with open constraints; slip and float trend (lake `mart_float_trend`,
`mart_schedule_history`, built); unscheduled records; comments by review.

## Confidentiality and roles
Schedules are `internal`; a subcontractor party sees the activities linked to its CWPs only (Phase 3 scope). Read:
`user`; comment: `user`; publish a snapshot: `controller`; statusing: a planner (`user` today, a role if the owner
wants) with PM approval; export and write-back: admin with the connector gate. Agents read only.

## First increment vs later
First (Phase 5 I2, or beside Phase 2 I5): activity list, filters, text Gantt, readiness overlay, comments as threads,
compare and look-ahead wiring, tiles, reports. Later: statusing entry and export; P6 XML and EPPM (I3); 4D overlay in
the model workspace; baseline management beyond compare.

## Open questions for the owner
Q2 is decided (XER first). New: is a text Gantt in the terminal useful enough, or should the Gantt wait for the web
client (README §4)? Who statuses activities, the planner from IWP progress or the foremen through the weekly plan?
Are comments as threads enough for the schedule review? Should the list and Gantt be built beside the Phase 2 weekly
cycle rather than in Phase 5 **(proposed)**?
