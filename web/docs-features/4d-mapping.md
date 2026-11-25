# 4D mapping

The **4D tab** of the right sidebar gives each element of the model a **location**, a **trade** and a **zone**. A P6 schedule can then be linked to the model by those three attributes, in the schedule sections of the same tab ([4d-schedule.md](4d-schedule.md); design: [4d-xer-animation.md](../../docs/design/4d-xer-animation.md), sections 3 and 10)). The values are saved into the IFC file (property set `Xray_4D`), kept in the browser per model, and exchanged as a LinkML dataset with SQL or MCP tools.

The mapping sections are **step 1 Map** of the tab's three steps (Map, Link, Film; see [4d-schedule.md](4d-schedule.md)). The status line there reads "Manual assignments: N accepted, N proposed. Kept in this browser for this model." and counts these assignments only, not schedule links. Open it with the tab `4D` (order 50, 420 px wide; a bottom sheet on a phone), with the command `4D mapping: open the 4D tab`, or with `window.__xray4dMap.open()`.

## The data

One record per element, attribute and value is an **assignment** (`Assignment` in [schema/linkml/xray_4d.yaml](../../schema/linkml/xray_4d.yaml), `src/schedule/types.ts`): `element` (GlobalId), `attribute` (`location`, `trade` or `zone`), `value`, `source`, `confidence`, `reasons`, `status`.

- `status`: `proposed` (a suggestion), `accepted` (current), `rejected`, `superseded` (replaced by a newer accepted record). Only accepted records count, are written into the IFC and drive the 4D plan.
- For each element and attribute at most one accepted record is current. A newer accepted record supersedes the older one; the older stays in the list as history.
- Everything you do by hand has `source: manual`, `status: accepted`. Suggestions have `source: suggested` (containment, class table) or `classifier` (the discipline or MasterFormat result helped decide).
- `reviewed_by` is never written by the tool. It is personal data: it stays out of share links, saved views, packed pages, the export (unless asked for) and the IFC.

## Sections of the tab

**Values.** The lists of known locations, trades and zones, one attribute at a time (the buttons at the top). Edit a name in its box (a rename changes every assignment that uses it), pick a colour for each value, delete an unused value, add a new one, or `Seed from model`: storey names become locations, system groups whose name contains "zone" (IfcZone) become zones, and the classifier's disciplines become trades. The default trades are CONC, STEEL, MASONRY, FACADE, ROOF, MEP-MECH, MEP-ELEC, MEP-PLUMB, FINISHES and SITE. A value that an import brought in is listed too.

**Assign.** Type or pick a value, then give it to: the **selection**, a **criteria query** (the query language of the search bar; the count shows live and the matching elements are tinted orange while you type), every element of a **storey**, or a **selection set**. `Every storey` sets the location of every element from its storey in one click. `Clear` takes the accepted value of the chosen attribute away from the selected elements.

**Suggest.** `Suggest` replaces the open proposals by new ones:

| Attribute | Evidence | Confidence |
| --- | --- | --- |
| location | the storey that contains the element | 0.90 |
| zone | the zone group the element belongs to | 0.90 (0.70 for several zones) |
| trade | the IFC class (table below; a `Class:material` row such as `IfcBeam:steel` wins over the bare class) | 0.70, 0.85 with a material rule |
| trade | the classifier's discipline (ARC, STR, MEC, PLB, FPR, ELE, TEL, CIV, PIP, INS) | 0.9 x its confidence |
| trade | the classifier's MasterFormat division | 0.85 x its confidence |

Agreeing evidence adds 0.05 per extra source (at most 0.99); disagreeing evidence is named in the reasons ("Not MEP-MECH: ..."). Elements that already have an accepted value, and spaces, openings and proxies (no trade), get no proposal. The review list shows each proposal with its confidence and reasons, highest first; click a row to see the element, `Accept` or `Reject` it, or `Accept all above` a confidence. The class table (`Class to trade table`) is editable and kept per model.

**Coverage.** Elements with, without and proposed for each attribute, `Select without` (selects the elements that have no accepted value) and `Colour` by location, trade or zone. The colouring is temporary: it is removed when you leave the tab and comes back when you return. Elements without a value are grey.

**Import / Export.** `Export JSON` writes a LinkML `LinkDataset` with `model`, `model_elements` (class, name, storey and the current location, trade and zone) and `assignments` (all statuses). A mapping-only export has no `schedule` (it is optional in the schema; files from earlier versions carry a marked placeholder, which reads as none). The schedule workflow's `Export links` writes the same dataset with `schedule`, `activities` and `links`; `Import JSON` here reads only the assignments of any such file. `Import JSON` merges a dataset: records with a new id are added, and for the same element and attribute the **newer accepted record wins** (compared by `reviewed_at`, else `created_at`; the older becomes superseded). Importing the same file again changes nothing. Rows that do not fit the schema are skipped and counted; a file that names another model is merged with a warning. This is how assignments go to and come from a SQL or MCP environment (keys are GlobalIds, so a re-exported IFC keeps them).

## Saving into the IFC

`Save IFC` has the box `Include 4D location, trade and zone` (on when the model has accepted assignments or accepted schedule links). The accepted values are written as the property set **`Xray_4D`** with the `IfcLabel` properties `Location`, `Trade` and `Zone` on each mapped element, and the `IfcText` property `ActivityIds` (the task codes of the accepted schedule links, see [4d-schedule.md](4d-schedule.md)), in the same block as `Xray_Review` and `Xray_Cleanup` (see [ifc-save.md](ifc-save.md)): append-only, one block before the final `ENDSEC;`, replaced on every save, the same bytes when nothing changed. Saving with the box off removes the set. Elements with the same three values share one property set and one relation. Proposed, rejected and superseded records are never written.

**Reading back.** When a file is opened, the importer keeps the `Xray_4D.*` properties of every element (in the default property mode too, ahead of the 24-property limit), and the tool turns them into accepted assignments with `source: property`. A saved model therefore reopens mapped. When the browser already holds an accepted value for the same element and attribute (your later edits), the stored one stays.

## Persistence

The assignments, the value lists and the class table are kept in IndexedDB (database `xray-4d-map`, one record per model, keyed by the model identity of `src/markup/scope.ts` like the sketches and issues). They come back when the same model is opened again. Without IndexedDB (a private window) nothing is kept and the tab says so. Nothing goes into the page address, share links, saved views, presets or packed pages.

## Script API

`window.__xray4dMap`:

| Call | Does |
| --- | --- |
| `values()` | `{ location, trade, zone }`: the value names |
| `assign(attr, value, target)` | accepted assignment; `target` is `{ selection: true }`, `{ query }`, `{ storey: name or id }`, `{ set: name }`, `{ ids }` or `{ globalIds }`; returns `{ assigned, unchanged, matched }` |
| `clear(attr, target)` | removes the accepted value (the record becomes rejected) |
| `suggest(attrs?)`, `proposals()` | rebuild and list the proposals |
| `accept(ids)`, `reject(ids)`, `acceptAbove(limit, attr?)` | decide proposals by record id |
| `coverage()` | counts per attribute and value |
| `colourBy(attr or null)`, `selectUnassigned(attr)` | colouring and selection |
| `exportJson()`, `importJson(text)` | the LinkML dataset |
| `saveMap()`, `assignments()` | what Save IFC writes; all records |
| `ready()`, `flush()`, `reset()`, `open()` | restore finished, write now, forget this model, open the tab |

## Files

`src/map4d/` (pure: `assignments.ts`, `values.ts`, `suggest.ts`, `targets.ts`, `linkio.ts`, `ifcio.ts`, `store.ts`; app: `controller.ts`, `panel.ts`), `src/plugins/map4d.ts`, the Xray_4D writer in `src/ifcsave/additions.ts`, tests `tests/map4d-*.test.ts` and `tests/ifcsave-4d.test.ts`, smoke `bench/smoke-4d-map.mjs`.

## Limits

- Zones come from IFC groups whose class is an IfcZone (the model reader lists them with the systems), recognised by "zone" in the name. A zone named otherwise is added by hand.
- The Python converter (`tools/ifc2glb.py`) does not mirror the `Xray_4D` read, so a glb sidecar carries no saved 4D values; open the IFC itself.
- A federation GlobalId suffix `~n` is cut off in the export; the IFC write uses the model's own id.
