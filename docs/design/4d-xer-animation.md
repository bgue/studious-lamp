# 4D from a P6 schedule: XER → model links → animation

Status: design, not built. Builds on the score player, the HUD, frame-by-frame export, the animation script language, the
criteria query language, the classifier, explode, x-ray focus and xray-pack.

## 1. Goal

From a Primavera P6 export (`.xer`) and an IFC model, produce a 4D construction animation that a planner can trust and a
client can watch: elements appear as their activities run, the work in progress is always visible (even inside the
building), the date and progress are on screen, and the camera goes where the work is. Everything runs from the command
line (`xray-4d`) so it fits a scheduling workflow (export from P6, run, get an MP4 and a kiosk page), and every step
leaves an editable artefact (a link table, a 4D plan, a script) so a person can correct what the machine guessed.

```
schedule.xer ─┐                     ┌─> links.json  (activity ↔ elements, with confidence and reasons)  ← review / edit
              ├─ xray-4d link ──────┤
model.ifc ────┘                     └─> link-report.html (coverage, unmatched both ways)
links.json + schedule.xer ─ xray-4d plan ──> build.4d.json (per-element state intervals, time map, shots)
build.4d.json ─ xray-4d script ──> build.xrayanim  (readable, editable; plays in the Script tab)
build.xrayanim ─ xray-4d render ──> build.mp4      (headless, frame by frame, HUD composited)
                 xray-4d pack   ──> build.html     (self-contained kiosk page, autoplay + loop)
```

## 2. Reading the XER

An XER file is tab-separated text in blocks: `ERMHDR` header line, then per table `%T <table>`, `%F <fields...>`,
`%R <values...>` rows, ending with `%E`. Encoding is usually Windows-1252 (fall back to UTF-8 when the header says so or
the bytes are valid UTF-8). One file can hold several projects; the CLI picks one with `--project <short name>` or the
only one.

Tables and fields used (names as P6 writes them; verified against real files during build):

| Table | Fields | Use |
| --- | --- | --- |
| `PROJECT` | `proj_id`, `proj_short_name`, `last_recalc_date` | the data date (actual vs planned split) |
| `CALENDAR` | `clndr_id`, `clndr_name`, `clndr_data` | working days and hours, exceptions (holidays) |
| `PROJWBS` | `wbs_id`, `parent_wbs_id`, `wbs_short_name`, `wbs_name`, `seq_num` | WBS tree (often location or system) |
| `TASK` | `task_id`, `task_code`, `task_name`, `wbs_id`, `clndr_id`, `task_type`, `status_code`, `target_start_date`, `target_end_date`, `early_start_date`, `early_end_date`, `late_start_date`, `late_end_date`, `act_start_date`, `act_end_date`, `restart_date`, `reend_date`, `total_float_hr_cnt`, `driving_path_flag`, `phys_complete_pct`, `complete_pct_type` | the activities |
| `TASKPRED` | `task_id`, `pred_task_id`, `pred_type` (`PR_FS`, `PR_SS`, `PR_FF`, `PR_SF`), `lag_hr_cnt` | logic (for the critical path view and checks) |
| `ACTVTYPE`, `ACTVCODE`, `TASKACTV` | code types (e.g. Area, Level, Trade, Phase), values, assignments | the best linking keys |
| `UDFTYPE`, `UDFVALUE` | `udf_type_label`, `fk_id`, `udf_text` / `udf_number` | user fields, sometimes the model link itself |
| `TASKRSRC`, `RSRC` | resources, quantities | optional: trade colours, crew labels |

Baselines: P6 exports the current schedule; a baseline comes as a second XER (`--baseline baseline.xer`), matched by
`task_code`, for the planned-vs-actual view.

Activity types: `TT_Task` and `TT_Rsrc` animate; `TT_Mile` / `TT_FinMile` become HUD milestones (caption, chapter mark);
`TT_LOE` and `TT_WBS` (level of effort, WBS summary) never drive geometry.

Status and dates: per activity, the dates that count are actual start/finish where they exist, else remaining (`restart`/
`reend`) for in-progress work, else early dates. `phys_complete_pct` gives the progress of active work at the data date.

Parser: `src/schedule/xer.ts`, pure, streaming per line, a typed result (`Schedule` with `projects`, `wbs`, `tasks`,
`relations`, `codes`, `udfs`, `calendars`), with a warnings list (unknown tables are kept as raw rows, never fatal).
Tests with synthetic XERs plus any real files the user can share (open question 1).

## 3. Linking activities to elements

This is the hard part and where 4D projects usually stall. The linker tries several sources, best first, and keeps the
reason for every link so a person can check it.

### 3.1 Link sources, in order of trust

1. **Native IFC 4D.** IFC4 `IfcTask` with `IfcRelAssignsToProcess` (elements to tasks) and `IfcTaskTime`. When the model
   already has them, match `IfcTask.Identification` or `Name` to `task_code`. Confidence 1.
2. **An element property that holds the activity id.** Many teams put the P6 code in a property (`Pset_4D.ActivityId`,
   `Identity Data.Comments`, a Revit shared parameter). `--id-property "Pset_4D.ActivityId"`; several codes per element
   (comma separated) are allowed. Confidence 1.
3. **Mapping rules (the normal case).** A small file maps schedule attributes to element queries in the criteria
   language the viewer already has (`src/query`):

   ```yaml
   # map.yaml
   match:                       # which schedule attributes describe the work, by activity code type or WBS level
     level: code:Level          # activity code type "Level"
     area:  code:Area
     trade: code:Trade
   levels:                      # schedule value -> model storey (exact, or regex, or a list)
     L00: "Ground Floor"
     L01: "Level 1"
     /^L(\d\d)$/: "Level $1"
   areas:                       # schedule value -> a zone: an IfcZone, a selection set, or a box in model coordinates
     A: { zone: "Zone A" }
     B: { box: [0, 0, -1, 40, 30, 60] }
   trades:                      # schedule value -> element query (the criteria language)
     CONC: class in (IfcSlab, IfcColumn, IfcBeam, IfcWall) and material ~ "concrete"
     STEEL: class in (IfcBeam, IfcColumn, IfcMember, IfcPlate) and material ~ "steel"
     MEP-DUCT: class in (IfcDuctSegment, IfcDuctFitting, IfcAirTerminal)
     FACADE: class in (IfcCurtainWall, IfcWindow, IfcPlate) and storey != "Roof"
   activities:                  # exceptions by task code: an explicit query or explicit GlobalIds
     A1040: where name ~ "core" and class = IfcWall
     A2210: elements "2O2Fr$t4X7Zf8NOew3FLOH", "1hOSvn6df7F8_7GcBWlRGQ"
   ```

   An activity's elements = level ∩ area ∩ trade (each optional). The classifier's discipline / MasterFormat results
   (`Xray_Review` and the classify service) are queryable too, so `trade: discipline = "Structure"` works on models
   with poor class use.
4. **Suggested links (assisted).** For activities left over, the linker proposes queries from the activity name and WBS
   path: tokens are matched against storey names, zone names, IFC classes and their common words (slab, pour, column,
   duct, riser, curtain wall, MEP first fix ...), system names, and classification. Each suggestion carries a confidence
   and its evidence ("Level 3 from WBS 'L3', IfcSlab from 'slab pour', zone B from 'Zone B'"). Suggestions below the
   threshold are never used silently; they go to review.
5. **Manual.** In the viewer: select elements, pick an activity, link. Same review walk as the revision walk (a card per
   activity with its elements highlighted, Accept / Change / Skip), reusing that UI pattern.

### 3.2 Rules for a clean result

- **Each element ends with one constructing activity** (plus optional temporary or demolition activities). When rules
  give an element to two constructing activities, the more specific rule wins (activity exception > trade+level+area >
  trade+level > trade); a tie is reported, not guessed.
- **Splitting.** One activity often covers many elements over days ("L3 slab pours 1–4"). Inside an activity the elements
  are ordered so they appear progressively, not all at once: `split: sweep x|y|z|-x...` (along an axis, the default for
  slabs and facades), `split: by storey` (bottom up), `split: by name` (pour 1, pour 2 ...), or `split: none`.
- **Context.** Elements no activity builds are either existing (`--existing` query: shown from the start as solid
  context) or unplanned (shown ghosted from the start and listed in the report).
- **Output.** `links.json`: `{ schema: "xray-4d-links/1", model: identity, schedule: { project, dataDate, file hash },
  links: [{ task_code, role: build|temp|remove, globalIds[], source: native|property|rule|suggested|manual, rule?,
  confidence, reasons[] }], unlinked: { elements[], activities[] } }`. Stable under re-export (keys are GlobalId and
  task_code), so a new XER update re-uses the links and only new activities need work.
- **Report.** `link-report.html`: coverage by WBS and by trade (elements linked, activities linked), activities with
  no elements, elements with no activity (grouped by class and storey, each group with the query that selects it so
  it can go straight into `map.yaml`), ties, low-confidence suggestions.
- **Write-back (optional).** `--write-ifc` adds `IfcTask`, `IfcTaskTime` and `IfcRelAssignsToProcess` to a copy of the
  IFC through the existing append-only save (`src/ifcsave`), so the links travel with the model to other 4D tools.

## 4. The 4D plan: what each element is doing at each moment

`xray-4d plan` turns the schedule plus links into `build.4d.json`, a compact table the player evaluates per frame.

### 4.1 Element states

| State | When | Default look |
| --- | --- | --- |
| `existing` | linked as existing | solid, neutral, slightly desaturated |
| `future` | before its activity starts | hidden; or a faint ghost in "planned" views (`--show-future ghost`) |
| `active` | its activity is running and its split slot has come | appears with a short fade or a rising cut, tinted in its trade colour, with edge glow |
| `complete` | after its slot ends | solid in its material colour, glow off |
| `temporary` | between temp build and removal (formwork, scaffold, props) | hatched or translucent orange, then fades out |
| `removed` | after a demolition activity | fades out red, then hidden |
| `behind` | (actual view) planned complete by the data date but not done | red tint |
| `ahead` | finished earlier than planned | green flash on completion |

Per element the plan stores intervals: `[{ from, to, state, task }]` in schedule time, plus its split slot. For 50 k
elements this is a few MB of JSON; packed and per-frame lookup is O(changes), not O(elements).

### 4.2 Views

- **Planned** (early dates or baseline), **actual-to-date + forecast** (actuals until the data date, remaining dates
  after it, a visible data-date marker), **variance** (planned and actual side by side over time: elements tinted by
  early/late at the moment they complete).
- **Critical path overlay:** activities with total float ≤ `--critical-float` (default 0) or `driving_path_flag` get a
  red edge glow while active and a "critical" tag in labels.

### 4.3 Time mapping (schedule days → video seconds)

A two-year job in a two-minute film needs more than a linear scale:

1. **Working time only:** time is measured on the project's main calendar, so weekends and holidays with no work take no
   screen time.
2. **Density warp:** screen time per working day grows with the number of elements changing state that day (a
   smoothed, monotonic warp: busy weeks get room, quiet months pass quickly), bounded to 0.3×–3× the average speed so
   the clock never jumps.
3. **Dwell:** each milestone and each phase change gets a minimum hold (default 1.5 s) with its caption.
4. **Target length:** `--length 120s` (or `--speed 1week=2s`), the warp is scaled to fit.

The HUD clock shows the schedule date (and week number), not seconds; the progress bar's chapters are the milestones.

## 5. The animation: using visibility, highlight and explode intelligently

The generator is a small "director" that reads the plan and decides, per stretch of time, what to show and from where.
These rules are what makes it more than "elements pop in by date".

### 5.1 Keep the work visible

- **X-ray focus on active work.** The viewer's core feature does the hard part: the elements in `active` state are the
  focus set, so the sightline x-ray ghosts whatever stands between the camera and them. MEP first fix inside closed
  walls, a core rising inside a finished frame: the work stays visible without hiding the building.
- **Peel when x-ray is not enough.** When the active set is small and deep inside (its screen area under a threshold and
  more than N occluders on its sightlines), switch to peel (cutaway) around it for that stretch.
- **Section box for interior phases.** When all active work for more than a few seconds is on one storey and inside
  the envelope (fit-out), clip to that storey (a section box a little larger than the storey) and fly in; remove the
  box when work leaves it.

### 5.2 Explode when work is spread vertically

- When active elements sit on 3 or more storeys at once (typical: frame going up while fit-out follows below), explode
  storeys vertically (the existing storey explode, gap scaled to storey height) so every floor with work is visible from
  one camera; collapse when work concentrates again. Explode changes are eased over 1–2 s and never happen during a fast
  camera move.
- At phase milestones ("Frame complete", "Envelope closed") an optional short explode-and-orbit beat shows the whole
  state of the building, then collapses.

### 5.3 Highlight with meaning, not decoration

- Trade colours (from `map.yaml` or a default palette by discipline) only while active; completed work returns to
  material colours so the picture does not turn into a rainbow.
- Edge glow marks what is being built *now*; red edge glow marks critical work. The focus halo (bloom) is kept for
  milestones only.
- Labels: at most 3 activity labels at a time, on the largest active groups (activity name, % complete, finish date);
  more go to a HUD list ("Now: 6 activities") in a corner.

### 5.4 Camera director

- The **interest region** per moment is the bounding box of active elements, weighted by how many change state in the
  next few seconds.
- **Shot choice:** wide (whole site) when the region covers most of the model or several distant areas; medium when one
  area; close when one small group. Shots last at least 4 s; a new shot only when the region moves more than its own size
  or the shot type changes.
- **Moves:** the fly-to framing (margin, closest distance) with the constant-speed path from the fly-through work; slow
  orbit during long stretches with little change; no cuts, only moves, unless `--cuts` (then hard cuts with a fade).
- **Comfort rules:** the camera never moves and explodes at the same time; never more than one big move per 3 s; the
  up axis stays up.

### 5.5 HUD

Date and week, % complete (by count or by quantity), a mini S-curve (planned vs actual) in a corner for the actual
view, current activities list, milestone captions, the critical path legend, the data-date marker on the progress bar.
All drawn by the HUD layer, so the video shows the same.

## 6. Output formats: a schedule cue plus a readable script

A big schedule has thousands of activities and tens of thousands of state changes. Writing one cue per element change
would blow past the score limits (5000 cues) and make the script unreadable. So:

- **New cue kind `schedule4d`** (additive to `score.ts`): references the 4D plan (inline or by name) and a time map; the
  player evaluates element states for the current schedule date each frame and applies visibility, alpha (fades), tint
  and glow. The HUD reads the date and progress from it.
- **New cue kinds (additive):** `tint` (elements, colour, fade), `explode` (by storey / radial, factor, over), `collapse`,
  `focus` (set the x-ray focus to elements or to "active"), `sectionBox` (around elements or a storey, or off),
  `clock` (show a schedule date for the HUD). The director emits these as normal cues on top of the `schedule4d` cue.
- **Script language additions** (same style as today), so the generated film is an editable `.xrayanim`:

  ```
  -- generated by xray-4d from schedule.xer (data date 2027-03-14), links.json; edit freely
  schedule "build.4d.json" view actual from "2026-09-01" to "2028-05-30" over 120 seconds
  together
    fly to everything over 3 seconds
    caption "Tower A" "Planned 2026-09-01 to 2028-05-30" for 3 seconds
  end together
  at date "2026-11-02"                       -- waits until the schedule clock reaches this date
    explode storeys by 1.5 over 2 seconds
  at date "2027-01-18"
    section box around storey "Level 3" over 1.5 seconds
    fly to active over 2 seconds
    label active with name, percent for 4 seconds
  at date "2027-02-10"
    section box off over 1 second
    collapse over 2 seconds
  at milestone "Envelope closed"
    caption "Envelope closed" for 2 seconds
  ```

  New statements: `schedule <file> view planned|actual|variance [from <date>] [to <date>] over N`, `at date <date>`,
  `at milestone <name>`, `tint <elements> <colour> [fading over N]`, `explode storeys|radial [by N] [over N]`,
  `collapse [over N]`, `focus <elements>|active`, `section box around <elements>|storey <name> [over N]`,
  `section box off`, and the element words `active`, `completed`, `critical`. The grammar document and its test get the
  new rules.

## 7. The CLI: `xray-4d`

Node, next to `xray-pack`, reusing its IFC reader bundle (`tools/pack/convert.mjs`), the pure schedule, link and plan
modules, and headless Chromium (Playwright) for rendering.

```
xray-4d inspect schedule.xer                      # projects, data date, counts, code types and values, WBS tree
xray-4d link   model.ifc schedule.xer --map map.yaml [--id-property P] [--existing Q] -o links.json --report r.html
xray-4d plan   model.ifc schedule.xer links.json [--view actual] [--baseline b.xer] [--length 120s] -o build.4d.json
xray-4d script build.4d.json [--style calm|dynamic] [--cuts] [--labels 3] -o build.xrayanim
xray-4d render model.ifc build.xrayanim --size 1920x1080 --fps 30 [--format mp4|webm|png] -o build.mp4
xray-4d pack   model.ifc build.xrayanim [--loop] -o build.html
xray-4d all    model.ifc schedule.xer --map map.yaml -o out/   # every step, stopping at the first error
```

- `render` opens the single-file viewer headless with the model, loads the plan and script, and calls the frame-by-
  frame exporter; progress on stderr; exit codes like xray-pack (usage 2, input 3, link coverage below `--min-coverage`
  4, render failure 5). A GPU makes it fast; the software renderer works, slowly.
- Every step is deterministic (same inputs, same output), so a weekly schedule update can run in CI and publish a new
  film and kiosk page.

## 8. Checks that make the result trustworthy

- Coverage thresholds (`--min-coverage 0.9` of elements by count and by volume).
- Logic sanity: activities with no predecessor or successor, out-of-sequence progress, actual dates after the data date,
  negative float, start/finish inversions; listed in the report, not fixed.
- Spatial sanity: an element built before the element it sits on (a column on Level 4 before the Level 3 slab it
  stands on, from bounding boxes and storey order) is flagged; often a linking mistake.
- The report and the film carry the schedule file hash, data date and link file hash in the captions/credits, so a
  viewer knows which schedule they are looking at.

## 9. Build plan (fan-out)

| Piece | Content | Depends on | Model |
| --- | --- | --- | --- |
| A | XER parser + calendars + `inspect` + tests (synthetic files) | — | Haiku |
| B | Linker: sources 1–3, specificity, splitting, `links.json`, report | A | Sonnet |
| C | Suggested links (token matching, evidence) + the link review walk in the viewer | B | Sonnet |
| D | Plan builder: states, views, critical path, time warp | A, B | Sonnet |
| E | Score additions (`schedule4d`, `tint`, `explode`, `collapse`, `focus`, `sectionBox`, `clock`) in the player + HUD date/S-curve | contract first | Sonnet |
| F | Director + script generator + language additions + grammar update | D, E | Sonnet |
| G | CLI (`xray-4d` commands, headless render, pack) | B, D, F | Haiku |
| H | Write-back of IfcTask links to IFC (optional) | B | Haiku |

The contract (cue kinds, `build.4d.json` and `links.json` schemas) is written first, like `score.ts` and `hud.ts`, so
A, B and E can start in parallel.

## 10. Open questions

1. A real XER (even a trimmed one) and its model: how do your schedules describe location and trade (activity codes?
   WBS? names?), and does any model carry activity ids?
2. Default story: actual-to-date + forecast, or planned? Show future elements as ghosts or hidden?
3. Film length and style: a calm 2–3 minute client film, or a planner's review at a fixed speed (1 week = 2 s)?
4. Temporary works (formwork, scaffolding, cranes): are they in your models?
5. Write the links back into the IFC (IfcTask) so other 4D tools can use them?
