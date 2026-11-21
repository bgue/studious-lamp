# 4D linking and planning

How a P6 schedule becomes element timelines for the 4D film. Design: `docs/design/4d-xer-animation.md` (sections 3, 4, 8). Code, all
pure TypeScript with no viewer or DOM dependency: `src/schedule/attrs.ts`, `link.ts`, `plan.ts`, `planTime.ts`, `report.ts`,
`model.ts`. Contracts: `src/schedule/types.ts` and `schema/linkml/xray_4d.yaml`.

```
Schedule (xer.ts) + FourDModel (model.ts) + FourDConfig + Assignment[]
     -> linkSchedule()   -> FourDLinks (links.json, LinkML JSON form)
     -> buildReport()    -> LinkReport -> renderReportHtml()   (link-report.html)
Schedule + FourDLinks + FourDModel + FourDStyle
     -> buildPlan()      -> FourDPlan (build.4d.json)
```

## The model view

`FourDModel` is the only thing the linker knows about the model: `identityKey`, `name`, and per element `globalId`, `ifcClass`,
`name`, `storey`, `zone`, `props` (`'Pset.Prop'` -> text), `bbox`, `discipline`, `material`; optional `storeys` with elevations.
`bbox` is in the IFC frame (Z up, metres). Adapters: `fromSceneModel(scene)` for the viewer's `SceneModel`, `fromSidecar(sidecar)`
for the node reader of `xray-pack` (the same element and storey records; it converts the viewer's Y up to Z up). Tests and other tools build
the object by hand.

## Where location, trade and zone come from

`config.schedule.location | trade | zone` are lists of sources, tried in order, the first with a value wins:

| Source | Reads |
| --- | --- |
| `{ "code": "Level" }` | the activity code of that code type (short name) |
| `{ "udf": "Area" }` | the user-defined field with that label |
| `{ "wbsLevel": 1 }` | the WBS short name at that depth (0 = first under the project) |
| `{ "wbsPattern": "STR/(L\\d+)", "group": 1 }` | a regex over the joined WBS path `P/STR/L3` (no group given: group 1 if there is one, else the match) |
| `{ "namePattern": "zone ([A-Z])" }` | a regex over the activity name |

`config.values.location | trade | zone` maps the schedule value to the model's value: an exact key, then the same key ignoring case,
then keys written `/regex/` (flags allowed, `/^blk-(\w+)$/i`) with `$1`..`$9` and `$&` in the target. No hit: the value is used as is.
Elements are read with `config.model.location | trade | zone`: `{ "property": "Xray_4D.Location" }` (any case), `{ "storey": true }`,
`{ "zone": true }`, `{ "discipline": true }`; first hit wins. Accepted `Assignment` rows (the mapping tool, the classifier, agents)
win over the model properties; `proposed`, `rejected` and `superseded` rows are ignored, and of several accepted rows for one element
and attribute the newest (`created_at`, else list order) wins. Values compare trimmed and ignoring case.

## The link tiers

`linkSchedule(schedule, model, config, assignments, opts)` claims elements for activities, best source first:

1. **manual**: accepted `ActivityLink`s in `opts.priorLinks` (an earlier run, a person, an agent) are kept and win.
2. **native**: `opts.native`, a map GlobalId -> task codes from the model's `IfcTask` assignments. Confidence 1.
3. **property**: `opts.idProperty` ('Pset_4D.ActivityId'); the value holds one or more codes separated by comma or semicolon. Confidence 1.
4. **override**: `config.activities[code]`, a criteria `query` and/or `globalIds`. Confidence 1.
5. **attributes**: an activity's elements are the elements whose location, trade and zone equal the activity's; each attribute is
   optional (an activity with none claims nothing). An element with no trade matches a trade through `config.tradeQueries[trade]`
   (a criteria query; the key is tried as the mapped value, then the schedule value). Elements of `config.model.existing` are never built
   by this tier. Confidence 0.6 / 0.8 / 0.9 for one / two / three attributes.
6. **suggested**: for activities that got nothing. Words in the activity name and WBS path are matched against storey names and
   level numbers ('L3', 'Level 03', '3rd floor', 'GF'), zone names and class words (slab, pour, column, wall, duct, pipe, door ...).
   Result: `source: 'suggested'`, `status: 'proposed'`, a confidence (class + storey + zone 0.8 and up, class alone 0.35, reduced when the
   match covers more than half the model), reasons ("IfcDoor from 'door'", "storey 'Level 2' from 'l2'") and a criteria query in `rule`.
   Suggestions are never accepted automatically and never drive the plan; below `opts.minSuggestConfidence` (0.3) they are dropped.

The explicit tiers (manual, native, property, override) of an activity replace its attribute inference: an activity that names its
elements does not also match by attributes. Milestones, level-of-effort and WBS summary activities never get elements.

### Specificity and ties

An element wanted by several building activities goes to the strongest claim: manual > native > property > override > three
attributes > two > one. Equal strength between different activities is a **tie**: the element is linked to none, listed in `ties` (and the
report) and stays in `unlinked_elements`. Link reasons say how many candidates were lost to a more specific activity or to a tie.
A tied activity gets no suggestion.

### Remove role

`config.activities[code].role = "remove"` makes the activity demolish what it matches (by query, globalIds, or its attributes, existing
elements included) and produces an `ln-<code>-remove` link. In the plan the element is `existing`, then `active` (fading out), then `removed`.

### Output

`FourDLinks` in the LinkML JSON form (snake_case). Ids are stable: `ln-<task_code>-build` / `ln-<task_code>-remove`
(a numeric suffix if a passed-through prior link already has the id). `status` is `accepted` for the deterministic tiers and `proposed` for
suggestions. Existing prior links that are not accepted are passed through untouched; a rejected or proposed prior link stops a new suggestion for
that activity. `assignments` are passed through. The `split` of a link comes from `config.activities[code].split`, else `config.split[trade]`,
else `config.split['*']`; with no config rule the field is left out (the plan reads that as `none`). Pass `opts.createdAt` to stamp
`created_at`; without it the output is byte for byte deterministic.

## Plan: views, windows, splits, critical

`buildPlan(schedule, links, model, style, { baseline?, config?, existing?, overlap? })`. Only **accepted** links drive it.

**Views.** `planned`: early dates (target dates where early are missing); a baseline `Schedule` replaces them by task code. `actual`:
actual start/finish where present; work in progress runs from its actual start to its remaining finish (never before the data date);
work not started uses remaining, else early dates. `variance`: the planned timeline against a reference (baseline, else the **target**
dates, since P6's early dates are the forecast, else early) with two extra states at the data date: `behind` (planned finish at or before the
data date, not done: from the planned finish until it is done) and `ahead` (done at the data date, before its planned finish: from its
actual finish until the planned finish). `behind` and `ahead` are written in the variance view only.

**Windows.** `all`: first start to last finish. `lookahead` `{from: 'dataDate' | date, weeks}`: from the data date (or the date; without
a data date, the first start) for N weeks. `range`. Intervals are clipped to the window; an element finished before the window starts is `complete`
from the window start, one in progress at the start is `active` from it, work after the window has no interval. Tasks and milestones are those
touching the window.

**Elements.** Intervals are sorted and do not overlap; `future` is never written (before the first interval an element is future). Linked
elements get `active` for their slot then `complete`; elements of `config.model.existing` (or flagged `existing` in the links, or `opts.existing`)
without a remove link have one `existing` interval; elements no accepted link names are not in the plan (the player ghosts them).

**Split rules** divide the activity's duration (calendar time) among its elements, in order, each element active for one slice;
neighbouring slices overlap by `overlap` of a slice (default 0.25), the first starts with the activity and the last ends with it.

| Rule | Order |
| --- | --- |
| `none` | all elements together |
| `sweep_x`, `sweep_y`, `sweep_z` | by bbox centre along the axis, ascending (`sweep_minus_*` descending); elements without a bbox last |
| `by_storey` | one slice per storey, bottom up (storey elevations; elements of one storey are simultaneous) |
| `by_name` | natural sort of the element name (Pour 2 before Pour 10) |

Ties in a sort are broken by name, then GlobalId.

**Critical.** `PlanTask.critical` is true when the activity is on the driving path or its total float is at or under `style.criticalFloatHours`
(`null`: driving flag only).

## Time map and progress

`timeMap` is `[[planMs, seconds], ...]`: seconds strictly increasing, plan time non-decreasing. Knots at every local midnight.

1. **Working time.** A day weighs its working hours on the project's default calendar (exceptions and weekday table; default Monday to
   Friday 8 h); a non-working day weighs 0.02 h, so weekends and holidays take almost no screen time but the map stays invertible.
2. **Pace.** `fixed`: linear in working time. `warp`: per working day, the number of element state changes (plus task starts and finishes for activities
   without elements), smoothed (gaussian, sigma 3 working days), as a multiple of the mean, clamped to 0.3x..3x, renormalised until stable.
   No changes anywhere: same as fixed.
3. **Holds.** Each milestone in the window holds `style.milestoneHold` seconds with plan time flat (two knots with the same plan time). If the
   holds would take more than 40% of `length` they shrink to fit.
4. **Scale.** To `style.length` seconds (holds included), or to `style.daysPerSecond` (window calendar days / daysPerSecond seconds of motion plus
   the holds). When both are set, `daysPerSecond` wins.

`progress`: samples every 7 days from the window start and at its end. `planned` is the mean fraction of the element slots (planned dates) that has
elapsed (by activity when nothing is linked); `actual` is the same with the actual view's slots, only up to the data date and only in the
`actual` and `variance` views.

## Report

`buildReport(schedule, links, model, { config?, minConfidence? })` and `renderReportHtml(report)` (one self-contained page, inline CSS, no
scripts or external assets).

- Coverage: elements by count and by bbox volume (existing elements excluded), building activities linked / unlinked / suggested only, by trade and by first WBS level.
- Elements with no activity, grouped by class and storey, each with a criteria `query` that selects the group (it leaves out `model.existing` elements when the group has some).
- Activities with no elements, ties, links to review (proposed, or confidence under `minConfidence`, default 0.6).
- Checks: open starts and ends, actual dates after the data date, out-of-sequence progress (an FS or SS predecessor not done), negative float,
  finish before start, and **built before support**: an element that starts before the slab of the storey below (matched by plan overlap of the bboxes when both have one),
  grouped by activity pair. Listed, never fixed.

## Example `FourDConfig`

```json
{
  "schema": "xray-4d-config/1",
  "schedule": {
    "project": "TOWER",
    "location": [{ "code": "Level" }, { "wbsLevel": 2 }, { "namePattern": "\\b(L\\d+)\\b" }],
    "trade": [{ "code": "Trade" }, { "udf": "Trade" }],
    "zone": [{ "code": "Area" }, { "wbsPattern": "/Zone ([A-Z])/", "group": 1 }]
  },
  "model": {
    "location": [{ "property": "Xray_4D.Location" }, { "storey": true }],
    "trade": [{ "property": "Xray_4D.Trade" }, { "discipline": true }],
    "zone": [{ "property": "Xray_4D.Zone" }, { "zone": true }],
    "existing": "name LIKE 'Old wall%'"
  },
  "values": {
    "location": { "L00": "Ground Floor", "/^L0?(\\d+)$/": "Level $1" },
    "trade": { "STEEL": "Structure" },
    "zone": { "A": "Zone A", "B": "Zone B" }
  },
  "tradeQueries": {
    "MEP": "class IN ('IfcDuctSegment', 'IfcDuctFitting', 'IfcPipeSegment')",
    "FACADE": "class IN ('IfcCurtainWall', 'IfcWindow') AND storey != 'Roof'"
  },
  "activities": {
    "A500": { "query": "class = 'IfcWindow'", "split": "sweep_x" },
    "A720": { "globalIds": ["2O2Fr$t4X7Zf8NOew3FLOH", "1hOSvn6df7F8_7GcBWlRGQ"] },
    "A600": { "query": "name LIKE 'Old wall%'", "role": "remove" }
  },
  "split": { "CONC": "sweep_x", "MAS": "by_storey", "*": "none" },
  "style": {
    "view": "planned",
    "unbuilt": "hidden",
    "window": { "kind": "lookahead", "from": "dataDate", "weeks": 6 },
    "length": 120,
    "pace": "warp",
    "camera": "director",
    "explode": "auto",
    "xrayFocus": true,
    "sectionBox": "auto",
    "labels": 3,
    "criticalFloatHours": 0,
    "colours": { "CONC": "#8d99ae", "MEP": "#2a9d8f" },
    "captions": true,
    "milestoneHold": 1.5
  }
}
```

Use from code:

```ts
const links = linkSchedule(schedule, fromSceneModel(scene), config, assignments, { idProperty: 'Pset_4D.ActivityId', createdAt: new Date().toISOString() });
const report = buildReport(schedule, links, model, { config });
const plan = buildPlan(schedule, links, model, config.style, { config });
```
