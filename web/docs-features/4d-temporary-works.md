# Temporary works in the 4D film

The 4D film can build **scaffold, falsework and formwork** around the permanent work: they go up before the work they serve, stand while it is built, and come down after it. They are generated from **rules** in the 4D configuration, drawn as their own layer, and are **not elements of the IFC model** (nothing is added to the IFC, nothing is exported to it). Part of the 4D tab: [4d-schedule.md](4d-schedule.md); the plan and the player: [4d-playback.md](4d-playback.md); the camera: [4d-director.md](4d-director.md).

## The rules

`config.temporaryWorks` in the `.4d.json` (additive; files without it work as before):

```json
"temporaryWorks": {
  "version": 1,
  "rules": [
    { "id": "scaffold", "kind": "scaffold", "name": "Scaffold",
      "for": "class = 'IfcWallStandardCase' and name like 'Wand-Ext%'",
      "erect": { "daysBefore": 1, "duration": 2 },
      "strike": { "activity": "A1450" },
      "size": { "offset": 0.3, "width": 0.8, "lift": 2.0, "bay": 2.5, "above": 1.0 } },
    { "id": "props", "kind": "falsework", "for": "class = 'IfcSlab' and name = 'Slab-033'",
      "erect": { "activity": "A1230" }, "strike": { "activity": "A1260" }, "size": { "spacing": 1.2 } },
    { "id": "form", "kind": "formwork", "for": "class = 'IfcBeam'",
      "erect": { "daysBefore": 1, "duration": 1 }, "strike": { "daysAfter": 3 } }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `version` | 1. A file with another version, or none, gives no temporary works and a problem in the import. |
| `id` | Short id (letters, digits, `-`, `_`; unique). Default `tw1`, `tw2` ... by position. It is in the group ids (`TW-scaffold-1`). |
| `kind` | `scaffold`, `falsework` or `formwork`. |
| `name` | Label in the group names and captions; default the kind. |
| `for` | A criteria query (the viewer's query language, [sets-query.md](sets-query.md)) for the permanent elements the rule serves. Elements that have no work of their own in the plan (existing parts) are not served. |
| `erect` | `{ activity }`: put up **during** that activity (its start to its finish). Or `{ daysBefore, duration }`: the erection ends `daysBefore` calendar days before the served work starts and takes `duration` days. Defaults: 1 day before; scaffold 2 days, falsework 3, formwork 1. |
| `strike` | `{ activity }`: taken down **during** that activity. Or `{ after, daysAfter, duration }`: starts `daysAfter` days after the end of activity `after`, or of the served work when `after` is not given, and takes `duration` days (default 1). Default `daysAfter`: scaffold 1, falsework 14 (curing), formwork 3. A strike never starts before the erection is done. |
| `size` | Metres. Scaffold: `offset` 0.3 (inner standards from the face), `width` 0.8, `lift` 2.0, `bay` 2.5, `above` 1.0 (guard above the top of the served elements). Falsework: `spacing` 1.2. Formwork: `thickness` 0.05. |

The Film step has a **Temporary works** section (below Style): one editable row per rule (kind, name, query, erect, strike, sizes), `Add rule`, `Remove`, and `Show in the film`, the layer's own toggle. Changes are part of the configuration and go into `Export .4d.json`. `window.__xray4dSchedule.tempWorks({ visible? })` returns `{ visible, groups, state, pick }`.

## Groups and timelines

`buildPlan` (`src/schedule/plan.ts`, `src/schedule/tempworks.ts`) runs each rule's query on the model and groups the served elements by **storey and the activity that builds them**: one scaffold group per floor ("Scaffold on Erdgeschoss"), one falsework group under a slab, one formwork group per concrete activity. Each group has its own timeline in `plan.temporaryWorks.groups[]`: `erect {from,to}`, in use, `strike {from,to}` (plan time, ms), the served GlobalIds, the activity and the resolved size. The times are also events for the film's pace. `xray-4d plan` reads the rules from `--config` with no flag; `--no-temporary-works` leaves them out (`xray-4d all` takes it too). `xray-4d render` and `pack` show them, because the plan carries everything the viewer needs.

## Geometry

Generated in the viewer from the plan (`generatePieces`) as simple boxes in the IFC frame, three instanced meshes (one per kind), a few thousand pieces cost three draw calls:

- **Scaffold**: along the outer face of each served wall (the side away from the building centre), per storey group. Standards (two rows, one per bay end, as tall as the lifts plus `above`), and per bay and lift two ledgers, a board and a guard rail. Lifts count from the lowest served element up: `ceil(height / lift)`. Bays: `ceil(length / bay)`. A piece is named "Temporary works: Scaffold, wall run W3, lift 2".
- **Falsework**: props on a grid under each served slab or beam (inset 0.2 m, `spacing`), from the soffit down to the slab or ground below, none inside walls, with head beams on top.
- **Formwork**: panels (at most 2.4 m long, `thickness`) on both faces of walls, on four faces of columns, under the soffit and round the edges of slabs and beams.

Colours: scaffold yellow-orange, falsework blue, formwork plywood brown, all semi-transparent. The pieces follow the explode offset of the storey they serve ("each floor apart"). They are never raycast by picking, so they cannot block a pick of a permanent element; `tempWorks().pick(x, y)` names the piece under a point.

## In the film

Per group, progress runs 0 to 1 over the erection and back to 0 over the striking. Pieces appear in their **build order** with the plan's fade (`style.fadeIn`; 0 is piece by piece at once): scaffold standards first, then lifts bottom-up; falsework props, then the deck beams; formwork panel by panel. Striking is the reverse (top lifts first). The layer exists only while the film plays and is gone after it. The **director** treats them as context: it never frames them and they do not count as work. A scaffold erected near a caption adds "Scaffold up on Erdgeschoss" to that caption (one line, only when it fits), or gets its own caption when none is within 4 s.

## The sample

FZK-Haus 4D (`tools/make_fzk_xer.py` writes the rules): scaffold on the four external walls of each floor, up two days before the external masonry (A1200 ground floor, A1250 gable walls) and struck during A1450 (Strike scaffold, after the facade A1440); falsework under the first-floor slab (A1240) put up during A1230 and struck during A1260; formwork on the ground slab (edge forms, A1150), the downstand beam and the first-floor slab, struck 3 to 7 days after the pour; a rule for footings and columns that matches nothing in this house. The XER is unchanged.

## Limits

- Geometry is made from axis-aligned element bounding boxes: a wall that runs diagonally gets a box-shaped scaffold; curved and sloped elements are approximated.
- A scaffold run is one per wall; corners are not merged and two floors' scaffolds overlap on their shared lift.
- Falsework and formwork do not check clashes with other temporary works; props avoid only walls.
- The pieces are not in the IFC, the link report or the schedule; they have no activities of their own (tie them to existing ones with `activity`).
- Calendar days, not working days, offset the times; the film's time map already gives non-working days little screen time.
- No temporary works are drawn outside the film.
