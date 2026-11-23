# xray-4d: 4D from a P6 schedule

`xray-4d` is the command line tool for the 4D feature: an animation in which every element appears when its activity runs,
driven by a Primavera P6 export (`.xer`). The design is in [docs/design/4d-xer-animation.md](../../docs/design/4d-xer-animation.md).
This document covers the schedule reader and the commands `inspect`, `link`, `plan`, `render`, `pack` and `all`, and the IFC 4D
write-back. `script` is the camera director: it writes a directed `.xrayanim` film from a plan and its model ([4d-director.md](4d-director.md)).

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

## The pipeline

```
schedule.xer + model.ifc --link--> links.json (+ link-report.html, + model.4d.ifc)
links.json --plan--> build.4d.json --render--> build.mp4
                                   --pack----> build.html (kiosk, autoplay)
xray-4d all ... -o out/   every step, stopping at the first failure
```

Common rules: progress and warnings go to stderr, results to `-o` (or standard output when `-o` is left out, for `link` and `plan`).
Exit codes: `0` ok, `1` unexpected internal error, `2` usage, `3` input (a file missing, unreadable or of the wrong kind),
`4` link coverage below `--min-coverage`, `5` render failure (no Playwright or Chromium, the viewer did not start, the export failed).
Every command has `--help`. The model is read with the same IFC reader as `xray-pack`; the pure modules of `web/src/schedule` do the
rest. Everything is deterministic: the same inputs give the same files, so a weekly schedule update can run in CI.

### The config

`--config map.4d.json` is a `FourDConfig` (`xray-4d-config/1`, see `web/public/samples/fzk-haus.4d.json` and
[4d-linking.md](4d-linking.md)): which activity codes, user fields or WBS levels mean location and trade, where the model holds them
(`Xray_4D.Location` and `Xray_4D.Trade` written by the 4D mapping tool, the storey, the zone, the classifier), value translations, trade
queries and the film style. **JSON only**: no YAML parser is installed in `node_modules`, and none is added; a `.yaml` config is
refused with exit 3.

### link

```
xray-4d link model.ifc schedule.xer --config map.4d.json [--assignments a.json] [--prior links.json]
             [--id-property P] [--min-coverage 0.9] [--project NAME] [--write-ifc out.ifc] [--report r.html] -o links.json
```

Links activities to elements by the tiers of the design: native IFC 4D (below), an id property (`--id-property`, several codes comma
separated; `Xray_4D.ActivityIds` is used when the elements have it), per-activity overrides of the config, then attributes (location /
trade / zone), then suggestions (never accepted automatically). `--assignments` is the mapping tool's LinkML export (its
`assignments` are used); the `Xray_4D.*` properties already in the IFC are read by the config's model sources. `--prior` keeps the
accepted links of an earlier `links.json` and passes the rest through. The output is a LinkML `LinkDataset`. `--report` writes the
link report (coverage by trade and WBS, unlinked activities and elements, ties, checks). The coverage (share of elements linked, by
count) is printed on stderr; below `--min-coverage` the files are still written and the exit code is 4.

### plan

```
xray-4d plan model.ifc schedule.xer links.json --config map.4d.json [--view planned|actual|variance] [--baseline b.xer]
             [--window all|lookahead:6w|range:2027-05-01..2027-07-01] [--length 120s | --pace 1w=2s] [--write-ifc out.ifc] -o build.4d.json
```

The style comes from the config; the flags override it. `--length` (`120s`, `2m`) fits the film to a length, `--pace` fixes the speed
(`1w=2s`: one schedule week per two seconds; `3d=1s`); not both. `lookahead:6w` starts at the data date. The plan is an
`xray-4d-plan/1` document (`FourDPlan` in `web/src/schedule/types.ts`).

### render

```
xray-4d render model.ifc build.4d.json [--script film.xrayanim] [--size 1920x1080] [--fps 30] [--format mp4|webm|png] [--hud on|off] -o build.mp4
```

Needs Playwright (package `playwright` with a Chromium; set `PLAYWRIGHT_MODULE` to its path if it is not found). How it works: the
model and plan are packed into a temporary page with the same code as `xray-pack` (the viewer template, the model as glb and sidecar,
the plan in `__xrayBoot.plans`; the template is rebuilt when `web/src` is newer, about 3 s), Chromium opens it (software GL), the
page builds the film score (one `schedule4d` cue over the plan's length, plus the cues of `--script` when the script runtime compiles
it; `window.__xray4dFilm`) and the frame-by-frame exporter of the Script tab (`window.__xrayRecord.run`) writes the file, so the
speed of the machine does not change the video. `--fps` is any whole rate 1 to 120. `png` writes a zip of frames. The last line on
stdout is a JSON summary (file, frames, size, bytes, milliseconds). Without a GPU the software renderer is slow: measured on the FZK-Haus sample: 2 s at 320x180 / 12 fps in 12 s
in all (page assembly and start-up included), 10 s at 640x360 / 24 fps in 54 s (about 0.2 s per frame); larger sizes cost more; the weekly CI example below uses a short lookahead film for that reason.

### pack

```
xray-4d pack model.ifc build.4d.json [--script film.xrayanim] [--loop] [--title T] -o build.html
```

A self-contained kiosk page: `xray-pack` with `--plans build.4d.json --autoplay plan:build --kiosk`. `xray-pack` has the new options
`--plans a.4d.json,b.4d.json` (plans are registered by file name without `.4d.json`) and `--autoplay plan:NAME`; with `plan:` the first
`--scripts` file adds its cues to the plan's film.

### all

```
xray-4d all model.ifc schedule.xer --config map.4d.json -o out/ [--no-render] [--min-coverage 0.9] [--write-ifc] [--script F]
            [--view V] [--window W] [--length T] [--size S] [--fps N]
```

Writes `out/links.json`, `link-report.html`, `build.4d.json`, `build.mp4` and `build.html` (and `model.4d.ifc` with `--write-ifc`), and
stops at the first failing step with that step's exit code.

### Weekly CI example

```
# every Monday: export the schedule from P6 as schedule.xer, then
node tools/xray-4d.mjs all model.ifc schedule.xer --config map.4d.json -o out/ \
     --min-coverage 0.95 --view actual --window lookahead:6w --length 60s --size 1280x720 --write-ifc
# publish out/build.mp4, out/build.html, out/link-report.html and out/model.4d.ifc; exit 4 fails the job when the model and schedule drifted apart
```

## IFC 4D write-back

`link --write-ifc` and `plan --write-ifc` write a copy of the model with the linked schedule, through the append-only save
(`web/src/ifcsave`): the original bytes are untouched and one `XRAY-BEGIN ... XRAY-END` block is inserted before the final `ENDSEC;`.
The 4D lines are the last section of the block (between `XRAY-4D-BEGIN` and `XRAY-4D-END`); a second write replaces only that section
and keeps the other Xray sets (classification, `Xray_Review`, `Xray_4D`), so re-saving gives the same bytes. Entities (IFC4 and IFC4X3):

| Entity | Content |
| --- | --- |
| `IfcWorkSchedule` | one, named `Xray 4D`; Description = project short name, Identification = schedule hash prefix, CreationDate = data date, StartTime / FinishTime = first start / last finish, PredefinedType PLANNED (planned and variance views) or ACTUAL |
| `IfcTask` | one per linked activity and role: Identification = task code, Name, IsMilestone, PredefinedType CONSTRUCTION (role build) or DEMOLITION (role remove), TaskTime |
| `IfcTaskTime` | ScheduleStart / ScheduleFinish = the plan's view dates (`plan`) or the planned dates (`link`), ActualStart / ActualFinish when present, IsCritical (with a plan); IfcDateTime texts `2027-03-14T08:00:00` |
| `IfcRelAssignsToControl` | the work schedule controls its tasks |
| `IfcRelAssignsToProduct` | role build: the element is the task's output (RelatingProduct = element, RelatedObjects = its tasks), one per element |
| `IfcRelAssignsToProcess` | role remove: the elements are the inputs of the demolition task (RelatingProcess = task, RelatedObjects = elements) |
| `IfcRelSequence` (+ `IfcLagTime`) | a predecessor relation between two written tasks: FS, SS, FF, SF and the lag (`IFCDURATION('PT16H')`, work time) |

Activities with no linked element in the file get no task. **IFC2X3 decision:** it has no `IfcTaskTime` (it uses
`IfcScheduleTimeControl` with `IfcRelAssignsTasks`), so the 2X3 form is not written: the command prints a warning, writes the other
outputs and skips the IFC copy. Use IFC4 or IFC4X3.

Read-back: `link` reads the model's own IfcTask assignments (`web/src/ifcsave/nativeTasks.ts`, `readNativeTasks`) and passes them to
the linker as `native` links (confidence 1, the most trusted tier). Both forms count: `IfcRelAssignsToProduct` (build) and
`IfcRelAssignsToProcess` on a task that is not a DEMOLITION / DISMANTLE / REMOVAL / DISPOSAL task (build, for tools that export it that
way); on those removal task types it is a remove assignment (returned in `remove`, not used by the linker's `native` option yet). The
task code is the Identification, else the Name. A file written by `link --write-ifc` links natively again. The viewer's own import has
the same function to call on the retained source blob; wiring it into the 4D tab is the viewer's piece.

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
- `web/tools/xray-4d.mjs`: the command table and `inspect`; `web/tools/xray-4d/commands.mjs`: `link`, `plan`, `render`, `pack`, `all`.
  `web/src/ifcsave/workSchedule.ts`, `writeWorkSchedule.ts`, `nativeTasks.ts`: the IFC write-back and read-back; `web/src/anim/fourd/film.ts` and
  `web/src/plugins/boot.ts`: the film score and the packed page's plan autoplay. It loads the TypeScript reader by bundling `web/tools/xray-4d/entry.ts`
  with vite (ssr, one ES module) into `web/tools/xray-4d/schedule.bundle.mjs` on first use. The bundle is rebuilt when
  `web/src/schedule` is newer and is not committed (listed in `.gitignore`). No dependencies are added.

Tests: `web/tests/xray-4d-cli.test.ts` (link, plan, write-ifc with web-ifc read-back, native re-link, pack, and a render that is skipped without Playwright and the single-file template), `web/tests/schedule-xer.test.ts`, `web/tests/schedule-calendar.test.ts` and `web/tests/schedule-cli.test.ts` (the CLI run
on the fixtures in `web/tests/fixtures/xer/`: `building.xer`, one realistic project; `two-projects.xer`; `windows-1252-names.xer`,
non-ASCII names in Windows-1252 with a broken calendar).
