# Data formats of the skill's tools

## schedule.json (`xer_read.py`, schema `xray-xer-json/1`)

```json
{
  "schema": "xray-xer-json/1", "file": "fzk-haus.xer", "encoding": "utf-8", "sourceHash": "<sha256>",
  "project": { "id": "4711", "shortName": "FZK-HAUS", "dataDate": "2027-05-19T08:00", "calendarId": "1001" },
  "projects": ["FZK-HAUS"], "calendars": [{ "id": "1001", "name": "Mon-Fri 8h", "hoursPerDay": 8 }],
  "codeTypes": { "Level": ["SITE", "EG", "DG", "ALL"], "Trade": ["CONC-SLAB", "..."] },
  "udfLabels": ["Crew size", "Responsible"],
  "activities": [{
    "code": "A1200", "id": "10009", "name": "External masonry walls, ground floor", "wbsPath": ["FZK", "SHELL", "EG"],
    "type": "task", "status": "complete",
    "dates": { "targetStart": "2027-03-31T08:00", "earlyStart": "...", "actualStart": "2027-04-02T08:00", "actualEnd": "..." },
    "totalFloatHours": 0, "driving": false, "percentComplete": 100,
    "codes": { "Level": "EG", "Trade": "MASON-EXT", "Phase": "SHELL" }, "udfs": { "Crew size": 4, "Responsible": "..." }
  }],
  "relations": [{ "predecessor": "A1160", "successor": "A1200", "type": "FS", "lagHours": 24 }]
}
```

`type` is `task` / `resource` / `milestone` / `finishMilestone` / `loe` / `wbsSummary` / `other`; `status` is
`notStarted` / `active` / `complete`. Dates are local without a zone.

## model.json (`ifc_read.py`, schema `xray-ifc-json/1`)

```json
{
  "schema": "xray-ifc-json/1", "file": "AC20-FZK-Haus.ifc", "fileHash": "<sha256>", "ifcSchema": "IFC4",
  "storeys": [{ "name": "Erdgeschoss", "elevation": 0.0 }], "zones": [],
  "elements": [{
    "globalId": "1bzfVsJqn8De5PukCrqylz", "class": "IfcWallStandardCase", "name": "Wand-Ext-ERDG-2", "type": "...",
    "storey": "Erdgeschoss", "zones": [], "material": "...", "bbox": [x, y, z, x, y, z],
    "props": { "Xray_4D.Trade": "MASON-EXT" },
    "tasks": [{ "task": "A1200", "role": "build" }]
  }],
  "existingTasks": ["A1200"]
}
```

`bbox` is the placement origin (both corners), and is used only to order elements inside an activity. `props` holds the
`Xray_4D` set always, other properties on request (`--props`, `--all-props`). `tasks` lists 4D links already in the file.

## The 4D configuration (`.4d.json`, the viewer's format)

```json
{
  "schema": "xray-4d-config/1",
  "schedule": { "project": "FZK-HAUS", "location": [{ "code": "Level" }], "trade": [{ "code": "Trade" }] },
  "model": { "location": [{ "property": "Xray_4D.Location" }, { "storey": true }], "trade": [{ "property": "Xray_4D.Trade" }] },
  "values": { "location": { "EG": "Erdgeschoss", "DG": "Dachgeschoss", "/^L(\\d+)$/": "Level $1" } },
  "tradeQueries": { "MASON-EXT": "class = 'IfcWallStandardCase' and name like 'Wand-Ext%'" },
  "activities": { "A2210": { "globalIds": ["..."] }, "A1040": { "query": "name like '%core%'" } },
  "split": { "MASON-EXT": "sweep_x", "*": "none" },
  "style": { "view": "planned", "unbuilt": "hidden", "length": 90 }
}
```

Schedule sources: `code`, `udf`, `wbsLevel`, `wbsPattern` (+`group`), `namePattern` (+`group`). Model sources: `property`,
`storey`, `zone`. Value keys may be `/regex/` with `$1` in the replacement.

## links.json

A LinkML `LinkDataset` (`schema/linkml/xray_4d.yaml` in xray-ref): `model`, `schedule`, `activities` (task_code, name,
wbs_path, activity_type, activity_status, start, finish, location, trade, zone, critical), `model_elements`,
`assignments`, `links` (id, activity, role build|remove, elements, source, confidence, reasons, split, status), `ties`,
`unlinked_activities`, `unlinked_elements`.

## Agent proposals (`link.py --proposals`)

```json
[{ "activity": "A1340", "role": "build", "elements": ["2IxUUNUVPB6Ob$eicCfP2N"], "confidence": 0.6,
   "reasons": ["roof tiling covers the roof slabs Dach-1 and Dach-2"] }]
```

## Animation scripts

`.xrayanim` text in the X-ray animation script language. The reference, grammar and guide are in the xray-ref docs:
`web/docs-features/animation-script*.md`. `xrayanim_check.mjs` prints
`{ ok, errors: [{line, col, message, hint, severity}], cues, duration, kinds }` and exits 1 on errors. Pass
`--plan NAME=plan.json` to check scripts that use the 4D statements against a plan.
