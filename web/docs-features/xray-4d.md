# xray-4d: 4D from a P6 schedule

`xray-4d` is the command line tool for the 4D feature: an animation in which every element appears when its activity runs,
driven by a Primavera P6 export (`.xer`). The design is in [docs/design/4d-xer-animation.md](../../docs/design/4d-xer-animation.md).
This document covers what exists today: the schedule reader and `xray-4d inspect`. The other commands (`link`, `plan`,
`script`, `render`, `pack`, `all`) are added to the same tool later and will be documented here.

Run it from `web/`:

```
node tools/xray-4d.mjs inspect schedule.xer
npm run 4d -- inspect schedule.xer --json
```

## inspect

```
xray-4d inspect <schedule.xer> [--project NAME] [--depth N] [--json]
```

| Option | Meaning |
| --- | --- |
| `--project NAME` | The project to read, by short name. Needed when the file holds several projects; the error lists them. |
| `--depth N` | WBS levels to show below the project (default 2; `0` shows only the top level). |
| `--json` | Print a JSON summary (schema `xray-4d-inspect/1`) instead of the report. |

The report shows: the project, its data date, the file hash and encoding; activity counts by type and status; relation counts
by type; every activity code type with its values and counts (and how many activities have none); the user fields of
activities; the calendars (working hours by weekday, holidays, part days); the WBS tree with the number of activities in each
node; and the warnings. The JSON has the same facts, plus the full warning list.

Exit codes: `0` ok, `1` unexpected internal error, `2` usage (unknown command or option, missing file argument), `3` input
(file missing or unreadable, not an XER file, or a project that cannot be chosen).

Example, on the fixture `web/tests/fixtures/xer/building.xer` (41 activities, two calendars, a UDF):

```
Project      BLD-A  Tower A
Data date    2027-03-12T08:00
Activities   41  (task 32, milestone 2, level of effort 2, WBS summary 1, finish milestone 4)
Status       complete 15, active 4, not started 22
Activity codes
  Level (6 values, 0 activities without)
    SITE 6, L00 10, L01 11, L02 5, ROOF 6, EXT 3
...
```

## What is read from the XER

Fields are looked up by name in each table's `%F` line, so the column order of a P6 version does not matter, and a field
that is missing leaves its value empty. Unknown tables and fields are ignored.

| Table | Fields | Used for |
| --- | --- | --- |
| `PROJECT` | `proj_id`, `proj_short_name`, `proj_name`, `last_recalc_date`, `clndr_id` | the project, its data date, its default calendar |
| `CALENDAR` | `clndr_id`, `clndr_name`, `day_hr_cnt`, `clndr_data` | working week, exceptions (holidays, part days) |
| `PROJWBS` | `wbs_id`, `parent_wbs_id`, `proj_id`, `wbs_short_name`, `wbs_name`, `seq_num`, `proj_node_flag` | the WBS tree; the node flagged `Y` is the project root |
| `TASK` | `task_id`, `proj_id`, `wbs_id`, `clndr_id`, `task_code`, `task_name`, `task_type`, `status_code`, the target, early, late, actual and remaining dates, `total_float_hr_cnt`, `driving_path_flag`, `phys_complete_pct` | the activities |
| `TASKPRED` | `task_id`, `pred_task_id`, `pred_type`, `lag_hr_cnt` | relations (FS, SS, FF, SF; lag in hours) |
| `ACTVTYPE`, `ACTVCODE`, `TASKACTV` | code types, their values (`short_name`), the assignment of a value to an activity | activity codes, keyed by the type name |
| `UDFTYPE`, `UDFVALUE` | `table_name` (only `TASK` is used for activities), `udf_type_label`, `udf_text`, `udf_number`, `udf_date` | user fields of activities |

Task types: `TT_Task` (task), `TT_Rsrc` (resource), `TT_Mile` (milestone), `TT_FinMile` (finish milestone), `TT_LOE` (level of
effort), `TT_WBS` (WBS summary). Statuses: `TK_NotStart`, `TK_Active`, `TK_Complete`; a missing status is derived from the actual
dates.

## Rules the reader follows

- **Encoding.** The bytes are read as UTF-8 when they are valid UTF-8, otherwise as Windows-1252, which is what P6 writes. A byte
  order mark is removed. The Windows-1252 table is written out in the parser, not taken from the runtime.
- **Dates.** P6 dates (`2027-03-14 08:00`) become ISO local times (`2027-03-14T08:00`). They carry no time zone.
- **Projects.** One file can hold several projects. `--project` picks one by short name (case-insensitive). Without it, a file with
  one project is read as it is; a file with several throws and lists them. Tasks and WBS nodes are filtered to the chosen
  project; calendars are kept when they are shared or belong to it; relations are kept when both activities are in the project.
- **WBS path.** An activity's path is the short names from the top WBS node under the project down to its own node. The project
  root itself is not in the path, so an activity directly under the root has an empty path.
- **Calendars.** The `clndr_data` string is read for the working week (day 1 = Sunday) and the exceptions (`d|<serial>` = days
  since 1899-12-30, with hours when the exception is a part day). When it cannot be read, Mon to Fri from 08:00 is assumed for
  `day_hr_cnt` hours (17:00 when that is missing), and a warning says so.
- **Warnings, not errors.** Data problems (a bad date, an unknown type, a relation outside the project, a duplicate activity,
  an unreadable calendar) are listed in `warnings` and the rest of the file is still read. Only a file that is not an XER and a
  project choice that cannot be made stop the tool.
- **Hash.** `sourceHash` is the SHA-256 of the input bytes, computed in plain JavaScript so it is the same in the browser and in
  node. The films and reports carry it, so a viewer can see which schedule they are looking at.

## Code

- `web/src/schedule/xer.ts`: `parseXer(input, { project })` returns the `Schedule` of [web/src/schedule/types.ts](../src/schedule/types.ts);
  `decodeXer` and `parseCalendarData` are exported for tests and tools.
- `web/src/schedule/calendar.ts`: working-time helpers on a calendar: `isWorking`, `workingMinutesBetween`, `addWorkingMinutes`
  (plan times are milliseconds of `Date.UTC` of the local wall time, so there are no time-zone or DST steps).
- `web/src/schedule/sha256.ts`: synchronous SHA-256.
- `web/tools/xray-4d.mjs`: the command table and `inspect`. It loads the TypeScript reader by bundling `web/tools/xray-4d/entry.ts`
  with vite (ssr, one ES module) into `web/tools/xray-4d/schedule.bundle.mjs` on first use. The bundle is rebuilt when
  `web/src/schedule` is newer and is not committed (listed in `.gitignore`). No dependencies are added.

Tests: `web/tests/schedule-xer.test.ts`, `web/tests/schedule-calendar.test.ts` and `web/tests/schedule-cli.test.ts` (the CLI run
on the fixtures in `web/tests/fixtures/xer/`: `building.xer`, one realistic project; `two-projects.xer`; `windows-1252-names.xer`,
non-ASCII names in Windows-1252 with a broken calendar).
