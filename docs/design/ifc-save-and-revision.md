# Design: Save IFC, Save cleaned IFC, Revision confirmation walkthrough

Status: design, ready to build. Scope: `web/` (three.js + TypeScript + Vite viewer, web-ifc 0.0.78).
All paths are relative to `web/`. Builders: read section 0, your ticket in section 7, and the sections it names.

Contents: 0 Findings · 1 Save IFC · 2 Cleaned IFC · 3 Revision walkthrough · 4 Persistence · 5 Module plan · 6 Tests · 7 Tickets · 8 Open questions

---

## 0. Findings that shape the design (verified in the repo)

| # | Fact | Consequence |
|---|---|---|
| F1 | The IFC bytes are **transferred** to the import worker and dropped; web-ifc is disposed before the merge (`model/ifcWorker.ts`, `releaseApi`). Nothing of the source survives a load. | Save needs a retained source: keep the user's `File`/`Blob` handle (disk-backed, costs no memory). |
| F2 | `ElementRecord` keeps `expressId` and `file` (source file name) for IFC loads (`model/ifcBuild.ts`, `elementRecord`). A federation is **one** viewer model; duplicates across files are dropped, GlobalId clashes get a `~n` suffix. | The writer addresses elements by `(file, expressId)`, never by the (possibly suffixed) GlobalId. One output file per source. |
| F3 | A classification result is `ClassifyResult` (`classify/types.ts`): discipline, sub-discipline, MasterFormat division, per-part confidence, `source` (`rules`/`cache`/`model`/`manual`/`confirmed`/`corrected`), `model`, `needsReview`, `unsure`, `confirmedBy/At`, `commitId`. Keyed by GlobalId in `ResultStore`. | These are the fields that go into the IFC. |
| F4 | Persistence today: signature cache in localStorage by `modelName|schemaHash|modelId`; manual overrides in localStorage by `modelName|schemaHash`; the review log (commits) in IndexedDB `xray-classification-review` by `modelFingerprint` = hash(sorted GlobalIds + schemaHash). Computed results are **not** stored. | Any GUID change in v2 gives a new fingerprint: v1's commits do not load on v2. The carry-over (3.4) must copy them explicitly. |
| F5 | `compareModels` (`markup/model.ts`) says `revised` only when the **name** is equal and the GUID hash differs. `fileLoader.uniqueName` renames a second file of the same name to `name (2)`, and revision files usually have a different name anyway. | `compareModels` alone misses most revisions. It is reused as the first test; a GUID-overlap test is added beside it (3.1). `compareModels` is not changed. |
| F6 | Element properties are read-only in the app. The only writes are the classifier's `<schema.psetName>.<Property>` entries (`service.writeToModel`). Props are capped at 24 per element in mode `common`. | "Property edits" = the classification pset only. The property diff sees the loaded props only (stated limit, 3.2). |
| F7 | `USER_MODELS` (`app.ts`) keeps every opened `LoadedModel` for the session. | In the session where v1 and v2 are both opened, v1's geometry is in memory for the ghost overlay. After a reload only a stored subset exists (4). |
| F8 | Measured: `IfcAPI.SaveModel` round-trips all 10 IFC files in the repo with every data line identical (IFC2X3 and IFC4); it rewrites the header comment and whitespace (FZK-Haus 2,526,544 → 2,482,629 bytes). | web-ifc's writer does not lose data on these files. It is still not used for saving (1.2), but it is the oracle in tests. |
| F9 | Measured: appending `IFCCLASSIFICATION`, `IFCCLASSIFICATIONREFERENCE`, `IFCRELASSOCIATESCLASSIFICATION`, `IFCPROPERTYSET`, `IFCRELDEFINESBYPROPERTIES` lines as text before the last `ENDSEC;` gives a file that web-ifc and IfcOpenShell 0.9.0 open, with entity count = original + added and **no new** `ifcopenshell.validate` errors (FZK-Haus IFC4, `ports-ifc2x3.ifc`). The originals already carry validation errors (5 and 1), so tests compare error sets, not "zero errors". | The text-append writer is feasible and checkable offline. `python3` + `ifcopenshell` 0.9.0.post1 are installed here. |
| F10 | `Pset_` is a prefix reserved for buildingSMART property sets; validators flag custom sets that use it. | Our sets are named `Xray_Review` and `Xray_Cleanup`, not `Pset_Xray…`. |

---

## 1. Save IFC (full file, original untouched, additions appended)

### 1.1 What is written

The saved file is the **original bytes, unchanged**, plus one block of new lines inserted directly before the final `ENDSEC;` of the DATA section. No original line is edited, removed or renumbered. Header untouched.

```
…original DATA lines…
/* XRAY-BEGIN xray-ifc-additions/1 base=79107 lines=412 tool=xray-viewer/<version> */
#79108=IFCCLASSIFICATION(…);
…
/* XRAY-END bytes=28113 */
ENDSEC;
END-ISO-10303-21;
```

Block content, in this fixed order (deterministic output):

1. Classification systems and references (1.4).
2. `IfcRelAssociatesClassification`, one per reference, all elements of that reference in `RelatedObjects`.
3. Pooled `IfcPropertySingleValue` lines (one per distinct name + type + value).
4. `IfcPropertySet` + `IfcRelDefinesByProperties`: the classification output set (`schema.psetName`, 1.5), `Xray_Review` (1.6), `Xray_Cleanup` marks (2.2). Elements whose property tuples are identical share one set and one relation (a rule-classified signature group collapses to one set).

No timestamp of the save itself is written (so the same state gives the same bytes). Dates in the file come from the results.

### 1.2 Decision: text-level STEP append, not `SaveModel`

| | web-ifc `WriteLine` + `SaveModel` | Text append (chosen) |
|---|---|---|
| Fidelity | Data lines kept (F8); header comment and whitespace rewritten | Original bytes identical up to the insert point |
| Memory at 100 MB+ | File must be opened again in WASM (the importer frees it on purpose), plus one `Uint8Array` of the whole output: about 3× file size on a 32-bit heap (reasoned, not measured) | `new Blob([file.slice(0, cut), blockText, file.slice(cut)])`: zero-copy, peak memory = the block |
| Schemas | Needs typed line objects per schema; 8 entity types × 3 schema families through web-ifc constructors | 8 small text templates per family, fully under our tests |
| Builds | Needs the WASM at save time | Pure TS; runs in node tests without WASM |

web-ifc calls used at **save time: none**. web-ifc is used (a) at import time to capture three numbers per file (1.3), (b) in tests to re-open the output (6).

### 1.3 Source retention and what import must capture

```ts
// src/ifcsave/source.ts
export interface IfcSource {
  /** Same string as ElementRecord.file. fileLoader makes names unique inside one federation (suffix " (2)"). */
  fileName: string;
  /** The user's File, or a Blob of the unzipped / embedded bytes. Never serialised, never in params/links/views/presets. */
  blob: Blob;
  schema: string;                 // FILE_SCHEMA as web-ifc reports it
  maxExpressId: number;           // api.GetMaxExpressID(model)
  ownerHistoryId: number | null;  // OwnerHistory ref of the IfcProject line
  /** Existing IfcClassification lines: reused when name (and edition, when both give one) match. */
  classifications: Array<{ id: number; name: string; edition: string | null }>;
}
export const sourcesOf: WeakMap<LoadedModel, IfcSource[]>;   // set by fileLoader after importIfc
```

- `ifcRaw.extractModel` adds `saveInfo: { maxExpressId, ownerHistoryId, classifications }` to `RawModel`; `ExtractSummary` and `ImportResult.raws[]` pass it through (plain numbers, no cost).
- `fileLoader` keeps `plan.ifc[i]` (the `File`) as `blob`. For `.ifczip` and the embedded IFC of a packed page it makes `new Blob([bytes])` **before** the buffer is transferred.
- A model loaded from glb + sidecar has no source. Save IFC then shows "Attach the source IFC…": the user picks the file, `stepScan` (below) reads it in the worker and the attach is accepted only when ≥ 99 % of the records' `(expressId → GlobalId)` pairs are found in the file.
- If the `File` cannot be read later (moved or changed on disk: `NotReadableError`), say so and ask to pick it again; verify with the same 99 % check.

`stepScan(blob)` (streaming, 4 MB chunks, worker): a STEP statement tokenizer that honours strings (`''`) and comments. Returns `{ schema, maxExpressId, dataEnd (byte offset of the final ENDSEC), block?: {begin, end, base}, ownerHistoryId, classifications, guidOf(expressId) for a requested id set, ourNamedRoots: number[] }`. Used for: attach, the fallback when the tail markers do not verify, and ticket T5. Budget: ≥ 80 MB/s.

### 1.4 Express ids, idempotency, GlobalIds

- **Allocation:** `next = base + 1`, sequential, in emit order. `base` = `IfcSource.maxExpressId` for a file without our block; for a file that already has our block, `base` = the `base=` value of its `XRAY-BEGIN` marker (web-ifc's max then includes our old lines).
- **Insert point:** read the last 64 KB of the blob, find `END-ISO-10303-21;` and the `ENDSEC;` before it. If an `XRAY-END bytes=N` marker precedes it, the old block starts N bytes before that marker; check that `XRAY-BEGIN` is there. If the check fails (file edited by hand, CRLF changed) run `stepScan` to find the markers.
- **Idempotent re-save:** output = `orig[0 .. blockBegin)` + new block + `orig[blockEnd ..)`. Our previous block is replaced, never added to. With unchanged state, `save(save(x))` is byte-identical to `save(x)` (test).
- **Markers lost** (the file went through another tool, which drops comments and may renumber): `stepScan.ourNamedRoots` finds `IfcPropertySet` named `Xray_Review`/`Xray_Cleanup`/`<schema.psetName>` and relations named `Xray …`. Until T5 lands: refuse with "This file already holds Xray data written by another route; save from the original file". After T5: delete those lines and their exclusive dependents through the patch writer (2.4), then append.
- **GlobalIds of our rooted lines** (`IfcPropertySet`, `IfcRel*`) are deterministic: 128-bit hash of `"xray|" + kind + "|" + key`, where key is the reference code or the sorted member GlobalIds, in IFC base-64 (22 chars, first char `0`–`3`). Same state, same GUIDs.
- **Strings:** `'` → `''`, `\` → `\\`, code points < 0x20 → `\X\HH`, > 0x7E → `\X2\HHHH\X0\` (UTF-16; astral via `\X4\HHHHHHHH\X0\`). `IfcLabel`/`IfcIdentifier` are cut to 255 characters; `IfcText` is not cut.

### 1.5 Classification entities

The schema drives the systems. `ClassificationSchema` gets one optional, additive field (it must not enter `schemaHash`):

```ts
interface SchemaSystemMeta { name: string; source?: string; edition?: string; editionDate?: string /* YYYY-MM-DD */; location?: string }
interface ClassificationSchema { /* … */ systems?: { discipline?: SchemaSystemMeta; masterformat?: SchemaSystemMeta } }
```

Defaults when absent: discipline system `{ name: schema.codeList ?? schema.title, source: 'project', edition: schemaEditionOf(schema) }`; division system `{ name: 'MasterFormat', source: 'CSI', edition: schema.masterformat.edition ?? 'unspecified' }`. A schema whose code lists are Uniclass, OmniClass or a company list names them here; nothing else changes.

An element is associated with its **most specific** reference per system: the sub-discipline reference when there is one, else the discipline reference; the section when the result has one, else the division.

| Line | IFC2X3 | IFC4 and IFC4X3 |
|---|---|---|
| `IFCCLASSIFICATION` | `(Source, Edition, $, Name)`; Source and Edition are mandatory, default text as above | `(Source, Edition, EditionDate, Name, $, Location, $)` |
| Discipline reference | `IFCCLASSIFICATIONREFERENCE($, code, label, #classification)` | `(…, $, code, label, #classification, $, $)` |
| Sub-discipline reference | `($, 'DISC.SUB', label, #classification)` (2X3 has no reference hierarchy; the dotted code keeps it unique) | `($, subCode, label, #disciplineReference, $, $)` (parent is the discipline reference) |
| Division / section | `($, '23' or '23 31 13', title, #classification)` | same with the 6-attribute form; a section's parent is its division reference |
| `IFCRELASSOCIATESCLASSIFICATION` | `(guid, #ownerHistory, 'Xray classification', $, (#el,…), #reference)` | same, OwnerHistory `$` |

An existing `IfcClassification` of the original with the same name (case-insensitive) and the same edition (or none on either side) is **referenced**, not duplicated. Existing classification relations of the original are never touched.

Schema families: `IFC2X3*` → `2x3`; `IFC4X3*` → `4x3`; other `IFC4*` → `4`. Anything else (IFC2X2, unknown): Save IFC is disabled with the schema named. `4` and `4x3` share all eight templates in this design; the family is still carried so a difference found later has one switch.

**OwnerHistory:** family `2x3`: every rooted line references `IfcSource.ownerHistoryId` (the project's own history; no new person, organisation or application is invented). If it is null (invalid 2X3 file) the block adds a minimal chain `IfcPerson($,'Unknown',…)`, `IfcOrganization($,'Unknown',…)`, `IfcPersonAndOrganization`, `IfcApplication(#org,'<version>','Xray viewer','xray')`, `IfcOwnerHistory(#pao,#app,$,.ADDED.,$,$,$,0)`. Families `4`/`4x3`: `$`. Reviewer names never go into OwnerHistory.

### 1.6 Property sets

**A. `<schema.psetName>`**: exactly the properties `service.writeToModel` shows in the app, with `propertyNames(schema)` as names: discipline, subDiscipline, masterformatDivision, masterformatTitle, masterformatSection (`IfcLabel`), confidence (`IfcNormalisedRatioMeasure`), source, model (`IfcLabel`), needsReview (`IfcBoolean`). Empty values are left out. This is the app's only "property edit" (F6). If the name starts with `Pset_` the dialog shows a one-line warning (F10) and writes it as given.

**B. `Xray_Review`** (review state and provenance):

| Property | IFC type | Source |
|---|---|---|
| `Status` | `IfcLabel` | `unreviewed` \| `manual` \| `confirmed` \| `corrected` |
| `Unsure` | `IfcBoolean` | `result.unsure === true` |
| `NeedsReview` | `IfcBoolean` | `result.needsReview` |
| `Confidence` | `IfcNormalisedRatioMeasure` | `overallConfidence(result)` |
| `DisciplineConfidence`, `SubDisciplineConfidence`, `DivisionConfidence` | `IfcNormalisedRatioMeasure` | per part, absent part omitted |
| `BuildingElementProbability` | `IfcNormalisedRatioMeasure` | `result.buildingElement` |
| `ProposedBy` | `IfcLabel` | `rules`, or the model id (`result.model`), or `manual`: where the proposal came from before any review |
| `Rationale` | `IfcText` | rules only |
| `ReviewedAt` | `IfcDateTime` (`4`, `4x3`); `IfcLabel` with the ISO text (`2x3`, which has no such simple type) | `result.confirmedAt` |
| `CommitId` | `IfcIdentifier` | `result.commitId` |
| `SchemaHash` | `IfcIdentifier` | `schemaHash(schema)` |
| `RevisionStatus` | `IfcLabel` | `new` \| `changed` \| `rematched` \| `unchanged`, only after a revision walk (3) |
| `RevisionBaseline` | `IfcLabel` | baseline model name, only with `RevisionStatus` |
| `ReviewedBy` | `IfcLabel` | `result.confirmedBy`. **Opt-in only** |
| `Comment` | `IfcText` | the review change's comment. **Opt-in only** |

Leak rule: `ReviewedBy` and `Comment` are written only when the dialog's "Include reviewer names and comments" box is ticked (default off, not remembered across sessions, not a setting, not in params). API keys, tokens and pictures have no path into the plan (the plan type below has no such field). A leak test saves with the box off and asserts the reviewer string is absent from the bytes.

### 1.7 Data shapes

```ts
// src/ifcsave/plan.ts  (pure)
export type SchemaFamily = '2x3' | '4' | '4x3';
export interface SaveOptions { includeNames: boolean; includeCleanupMarks: boolean; scope: 'all' | 'reviewed' }
export interface ElementSave {
  expressId: number; globalId: string;
  result?: ClassifyResult; comment?: string;
  revision?: { status: 'new' | 'changed' | 'rematched' | 'unchanged'; baseline: string };
  cleanup?: { rules: string[]; reasons: string[] };
}
export interface FileSavePlan { fileName: string; family: SchemaFamily; base: number; ownerHistoryId: number | null;
  existingClassifications: IfcSource['classifications']; elements: ElementSave[] }
export function planSave(model: SceneModel, results: ReadonlyMap<string, ClassifyResult>, schema: ClassificationSchema,
  sources: readonly IfcSource[], o: SaveOptions, extra?: { comments?; revision?; cleanup? }): FileSavePlan[];   // one per source

// src/ifcsave/additions.ts  (pure)
export function emitAdditions(plan: FileSavePlan, schema: ClassificationSchema, o: SaveOptions): { text: string; lines: number; lastId: number };

// src/ifcsave/splice.ts  (pure over Blob)
export async function locateInsert(blob: Blob): Promise<{ cut: number; oldBlock?: { begin: number; end: number; base: number } }>;
export function splice(blob: Blob, at: { cut: number; oldBlock? }, blockText: string): Blob;

// src/ifcsave/readBack.ts  (pure, text level; also the import of a saved state)
export function readAdditions(blockText: string): { byExpressId: Map<number, { codes; review: Record<string, unknown> }> };
```

### 1.8 Worker, progress, large files, federation

- `src/ifcsave/saveWorker.ts` (module worker, same pattern as `model/ifcWorker.ts`): `{ type:'save', plans, schema, options, blobs }` → progress `{ phase: 'locate' | 'emit' | 'splice', file, done, total }` → `{ type:'saved', files: Array<{ fileName, parts: BlobPart[] , lines }> }`. Blobs cross the boundary by reference. Main-thread fallback when the worker cannot start (same as the importer).
- Emit cost is linear in elements: budget 50 k elements < 1 s, block size about 150–300 bytes per distinct pset. The original is never read beyond its last 64 KB.
- Writing: `showSaveFilePicker` + `createWritable().write(blob)` where available (streams from disk, shows bytes written); else `downloadBlob`. The output blob is slices of the source file plus the block, so a 1 GB model costs megabytes of memory.
- **Federation: one file per source**, named `<stem>.xray.ifc`. Elements go to the file named by `record.file`. Report "n duplicate elements exist only in <first file>" when `BuildReport.duplicatesSkipped > 0` (their twin in the later file gets no data; documented limit). More than one file: `showDirectoryPicker` when available, else one download per file with a 300 ms gap.
- UI: one button "Save IFC…" (placed by ticket T2, see 5.3). Dialog: file list with sizes and schema, scope (all classified / only reviewed), the two tick boxes (names + comments, cleanup marks), progress bar, cancel (terminates the worker).

---

## 2. Saving a cleaned IFC

Three actions, increasing risk. Only the first is in the default flow.

| Action | What it does | Default |
|---|---|---|
| **Save IFC** with "Mark cleanup matches" | Nothing is removed. Each cleanup-hidden element gets `Xray_Cleanup` | On when cleanup has hidden anything |
| **Save cleaned copy…** | Physically removes the elements cleanup hid, repairs relationships, sweeps orphans. File `<stem>.cleaned.ifc` | Separate button, confirm dialog with counts |
| **Save simplified copy…** | As cleaned copy, and replaces body geometry of simplified elements | Separate, experimental flag, off |

### 2.1 Which elements

The ids in `CleanupHides.owned` (hidden by cleanup, not un-hidden by the user). Elements the user hid by hand are included only with the box "Also remove elements I hid by hand". Read through `window.__xrayCleanup` / the controller's `userHides`; `plugins/cleanup.ts` is not edited by these tickets (the cleanup agent owns it) except for one button hook in T5.

### 2.2 `Xray_Cleanup` (mark)

| Property | Type | Meaning |
|---|---|---|
| `FlaggedForRemoval` | `IfcBoolean` | `.T.`: cleanup proposes removal; the element is still in this file |
| `Rules` | `IfcLabel` | matched rule names joined with `;` (`tiny;floating`) |
| `Reason` | `IfcText` | the reasons of the cleanup report |
| `KeptBecause` | `IfcLabel` | only in a cleaned copy, on an element that could not be removed safely (2.3) |

### 2.3 What removing an element means

Removing element E deletes E's line. Every line that references E must then be repaired. Rules, applied by relationship class (names valid in 2X3, 4 and 4X3 unless noted):

| Referrer of E | Action |
|---|---|
| `IfcRelContainedInSpatialStructure`, `IfcRelReferencedInSpatialStructure` (E in `RelatedElements`) | Remove E from the set. Empty set → delete the relation |
| `IfcRelAggregates`, `IfcRelNests`, E as a **part** | Remove from `RelatedObjects`; empty → delete relation |
| `IfcRelAggregates`, `IfcRelNests`, E as the **whole** | Remove E only if every part is also removed (parts that are ports: see below). Otherwise **do not remove E**: mark it, `KeptBecause='has parts'` |
| `IfcRelVoidsElement` (E is host) | Delete the relation and the opening element, and the opening's `IfcRelFillsElement`. If a filler (door, window) of such an opening is **not** being removed: do not remove E, `KeptBecause='hosts a door or window'` (option "Remove hosts anyway" lifts this; the filler then stands in no wall) |
| `IfcRelFillsElement` (E is filler) | Delete the relation. The opening stays (a hole in the host). Counted in the report |
| `IfcRelProjectsElement` | As voids: the feature goes with E |
| `IfcRelConnectsPathElements`, `IfcRelConnectsElements`, `IfcRelInterferesElements`, `IfcRelCoversBldgElements` (as covering), `IfcRelSpaceBoundary` | Delete the relation (for list-valued ends: trim, delete when empty) |
| Ports: `IfcRelConnectsPortToElement` (2X3), `IfcRelNests` with ports (4+) | Delete the relation and E's ports; delete every `IfcRelConnectsPorts` of those ports. The neighbour's port stays, unconnected |
| `IfcRelDefinesByProperties` | Trim; empty → delete relation; the set goes in the orphan sweep |
| `IfcRelDefinesByType` | Trim; empty → delete relation. The type object **stays** |
| `IfcRelAssociatesMaterial` / `…Classification` / `…Document` | Trim; empty → delete relation |
| `IfcRelAssignsToGroup` and other `IfcRelAssigns*` | Trim; empty → delete relation. The group or system stays |
| Any other `IfcRel*` | E inside a list with other members → trim; else delete the relation |
| `IfcStyledItem`, `IfcPresentationLayerAssignment` (weak referrers of representation items) | Do not keep their target alive. Target deleted → styled item deleted; layer list trimmed, deleted when empty |
| **Any non-relationship line** referencing E | Do not remove E; `KeptBecause='referenced by #id CLASS'` |

**Orphans** (representation, placement, property definitions): strong reference counting. After the deletions above, every line whose strong reference count fell to zero **because of a deletion in this run** is deleted, repeatedly (work list). This removes E's `IfcProductDefinitionShape`, shape representations, items, profiles, points, and psets/quantity sets used by no one else. It keeps, automatically: an `IfcLocalPlacement` that another element's placement is relative to, representation maps shared with a type, shared materials and styles. Lines that had zero references in the original are never touched. Type objects, groups, spatial elements, units, contexts, the project: never deleted.

**Risk statement (goes into the confirm dialog, short form):**
- Safe: free-standing debris, strays, duplicates, proxies with no relationships: the bulk of what cleanup finds.
- Guarded by default (kept and marked instead): assemblies with remaining parts, hosts of remaining doors/windows, anything referenced by a non-relationship line.
- Accepted loss: connectivity of neighbours (ports, path connections) is cut; an opening can remain without a filler.
- Not handled: structural analysis relations, cost/schedule assignments beyond trimming, `IfcRelSequence`. A file with `IfcStructuralAnalysisModel` gets a warning line.
- A cleaned copy is a **derived** file: its name says so, and the block comment records `removed=n kept=m`.

### 2.4 Patch writer (text level, T5)

```ts
// src/ifcsave/stepIndex.ts  (pure; whole file in memory in the worker)
export interface StepIndex { count: number; id: Uint32Array; offset: Float64Array; length: Uint32Array; type: Uint16Array; typeNames: string[];
  fwdStart: Uint32Array; fwd: Uint32Array;   // forward references, CSR
  invStart: Uint32Array; inv: Uint32Array;   // referrers, CSR
  rowOf(expressId: number): number }
export function indexStep(bytes: Uint8Array, onProgress?): StepIndex;
// src/ifcsave/removal.ts  (pure)
export interface RemovalPlan { delete: Set<number>; rewrite: Map<number, string>; kept: Array<{ expressId: number; because: string }>; stats }
export function planRemoval(ix: StepIndex, bytes: Uint8Array, remove: readonly number[], o: { removeHostsAnyway: boolean }): RemovalPlan;
// src/ifcsave/patch.ts
export function writePatched(bytes: Uint8Array, ix: StepIndex, plan: RemovalPlan, blockText: string): BlobPart[];   // 4 MB chunks, original order
```

```
planRemoval:
  seeds = remove ∩ IfcElement lines
  repeat until no change:
    for E in seeds not yet decided: for R in inv(E): apply table 2.3 → delete R | rewrite R | add cascade seeds (openings, ports) | veto E
  vetoed E: undo its relation edits, record kept
  strong[i] = number of strong referrers of i (weak referrer classes excluded)
  work = all deleted lines; for d in work: for t in fwd(d): if --strong[t] == 0 and t is sweepable: delete t, push t
```

Argument-level parsing is done only for the lines being rewritten (`stepText.parseArgs`, `stepText.formatArgs`). Memory: file bytes + about 0.8× file size of index + the output. Limit: sources above 1 GB are refused for cleaned copies with a plain message (plain Save IFC has no limit). Budget: index ≥ 40 MB/s; 100 MB file end to end < 10 s in the worker.

### 2.5 Simplified geometry write-back (experimental, T5b)

Input from the cleanup agent's simplification (interface this design asks of them; nothing else is assumed):

```ts
export interface SimplifiedMesh { globalId: string; positions: Float32Array /* viewer frame, metres */; indices: Uint32Array; closed: boolean }
```

Per element: delete the original **Body** `IfcShapeRepresentation` from the product definition shape (orphans swept as in 2.3) and add one new representation in the **same** representation context:

| Family | Representation |
|---|---|
| `4`, `4x3` | `IfcShapeRepresentation(#ctx,'Body','Tessellation',(#fs))`, `IfcTriangulatedFaceSet(#IfcCartesianPointList3D, $, closed, CoordIndex, $)` |
| `2x3` | closed mesh: `'Brep'` with `IfcFacetedBrep(IfcClosedShell(IfcFace(IfcFaceOuterBound(IfcPolyLoop,.T.))…))`; open mesh: `'SurfaceModel'` with `IfcShellBasedSurfaceModel(IfcOpenShell)`. About 5 lines per triangle: warn above 200 k triangles per file |

Must be preserved: GlobalId, class, all attributes, psets, type, material, containment, voids and fills, the element's **ObjectPlacement** (so coordinates are converted viewer → IFC world (`viewerToIfc`, `bcf/model.ts`) → the element's local frame by inverting its placement chain, read at text level → file length unit), non-body representations (Axis, FootPrint), the first body item's surface style (a new `IfcStyledItem` on the new item pointing at the same style), layer assignment.

Lost, stated in the dialog: parametric geometry (extrusions, profiles), per-item styles beyond the dominant one, mapped (type-shared) geometry for that occurrence; a `…StandardCase` element no longer meets its class's geometry convention. Elements with `IfcLinearPlacement`/`IfcGridPlacement`, or whose written bounds differ from the viewer bounds by > 1 mm in the self-check (re-open the output with web-ifc in the worker, files ≤ 200 MB), keep their original representation and are listed. Recommendation: build this last and keep it behind `?experimental=simplifiedIfc` until the user has tried cleaned copies (open question Q5).

---

## 3. Revision confirmation walkthrough

Scenario: v1 loaded, classified, reviewed. v2 arrives. Vocabulary: **base** = v1, **head** = v2.

### 3.1 Detecting a revision

A **snapshot** of a model (4.1) is stored whenever it has something worth carrying: after a classify run ends, after a review commit, and when another model replaces it while it has results. On every `onModel`:

```
now = loadedIdentity(app)
for snap in snapshots, newest first, snap.key != identityKey(now):
  if compareModels(snap.identity, now).match == 'revised'  → candidate (reason: same name)
  else if jaccard(snap.guidSketch, sketch(now)) >= 0.30     → candidate (reason: shares n % of its elements)
  else if sameStem(snap.name, now.name) and classHistogramSimilarity >= 0.9 → weak candidate (GUIDs regenerated)
```

`guidSketch`: the 256 smallest 32-bit hashes of the GlobalIds (bottom-k minhash); `sameStem` strips ` (n)`, `rev X`, `_vN`, dates and the extension. A candidate shows a banner: "This looks like a revision of **<name>** (saved <date>, <n> reviewed). **Review changes** · Not a revision". Manual entry points: "Compare with…" (pick any stored snapshot) and "Compare with an IFC file…" (the file is extracted in the import worker without being displayed and snapshotted; it has no decisions, so only the diff and the report apply). Nothing is carried over before the user clicks **Review changes**.

### 3.2 Diff

**Geometry signature** (`revision/geomSig.ts`, pure; one pass over an element's triangles):

```ts
/** 11 floats per element. All are surface integrals, so they do not depend on how the surface is triangulated. */
export interface GeomSig { area: number; volume: number /* |signed sum|, 0 when open */; centroid: Vec3 /* area-weighted */;
  moments: Vec3 /* eigenvalues of the area-weighted covariance, descending: rotation and translation free */;
  extent: Vec3 /* AABB size */ }
```

Per-triangle covariance is exact (`A/12 · (Σ vᵢvᵢᵀ + (Σvᵢ)(Σvᵢ)ᵀ)` about the origin, shifted to the centroid at the end; computed in Float64 relative to the element's bounds centre). Centroids are converted to the IFC world frame (`viewerToIfc` with the model's `originShift`) before two models are compared, because base and head may have different origin shifts.

Budget: ≤ 50 ns per triangle. Signatures are computed on the main thread in 8 ms slices over `MergedGeometry` (`geometry` position/index + `ranges`), lazily, when a snapshot is first needed: the arrays (hundreds of MB) cannot be copied to a worker. 10 M triangles ≈ 0.5 s spread over about 60 frames. Test: 1 M triangles < 400 ms in node.

**Pair comparison** (tolerances in `RevisionOptions`, defaults shown):

```
shapeSame = rel(area) <= 0.005 and max rel(moments) <= 0.01            // rel(x) = |a-b| / max(|a|,|b|,1e-9)
if !shapeSame                          → flag geometry
else if |Δcentroid| > 0.001 m          → flag placement, move = |Δcentroid|
     or  max|Δextent| > max(0.002 m, 0.1 %) → flag placement, rotated = true
```

**Attribute and property diff** (per matched pair):

| Flag | Compared |
|---|---|
| `class` | `ifcClass` |
| `type` | `Attr.ObjectType` (type name) and `Attr.PredefinedType` |
| `attributes` | `name`, `Attr.Tag`, `Attr.Description` |
| `storey` | storey name, or elevation differing by > 1 cm |
| `material` | `material` |
| `properties` | every other key of `props`: added, removed, changed (numbers: rel > 1e-4). Keys under `schema.psetName.` and `Xray_` are ignored |
| `systems` | sorted system names |

Limit (F6): only the loaded properties are compared (mode `common`: attributes, `Pset_*Common`, base quantities, 24 per element). The card says "compared: loaded properties" (open question Q4).

**Matching:**

```
1. by GlobalId (strip the federation suffix "~n"): pair → compare → unchanged | changed{flags}
2. leftovers: D = base only, N = head only.  If |GUID pairs| < 5 % of min(|base|,|head|):
     estimate a global offset = the most frequent rounded centroid delta among (class, name, shape-bucket) keys that are unique on both sides; subtract it
3. candidates for d in D: N elements in the 27 grid cells (1 m cells, on centroid) around d, plus N elements with the same Tag (non-empty), plus same (name, shape-bucket)
4. score(d, n) = 0.30·g + 0.25·p + 0.20·m + 0.15·c + 0.10·s
     g = 1 − clamp(max(rel(area), max rel(moments)) / 0.05)
     p = 1 − clamp(|Δcentroid| / max(0.5 m, 0.5·diag(d)))
     m = 1 if Tag equal and non-empty, or name equal; 0.7 if nameStem equal (classify/state.ts); else 0
     c = 1 same class; 0.5 same after dropping "StandardCase"/"ElementedCase"; else 0
     s = 1 same storey name or elevation within 1 cm; else 0
5. sort all candidate pairs by score descending; take greedily one-to-one while score >= 0.80 and (score − next best score of either side) >= 0.05
   → rematched{score, flags from the pair comparison}.   score >= 0.95 is "high" (eligible for bulk accept)
6. the rest of D → deleted; the rest of N → new
```

```ts
// src/revision/types.ts
export type Category = 'new' | 'deleted' | 'changed' | 'rematched' | 'unchanged';
export type ChangeFlag = 'geometry' | 'placement' | 'class' | 'type' | 'attributes' | 'storey' | 'material' | 'properties' | 'systems';
export interface DiffEntry {
  key: string;                    // head GlobalId; "del:" + base GlobalId for deleted
  category: Category; base?: string; head?: string;      // GlobalIds
  flags: ChangeFlag[]; move?: number /* m */; rotated?: boolean; score?: number;
  props?: Array<{ key: string; before?: PropValue; after?: PropValue }>;
  /** signatureOf(buildInput) differs between base and head: the change can alter the classification. */
  classifyAffected: boolean;
}
export interface RevisionDiff { base: ModelIdentity; head: ModelIdentity; options: RevisionOptions;
  counts: Record<Category, number>; flagCounts: Record<ChangeFlag, number>; entries: DiffEntry[] /* unchanged entries are counted, not listed */ }
export function diffModels(base: ModelSnapshot, head: ModelSnapshot, o?: Partial<RevisionOptions>): RevisionDiff;   // pure
```

`diffModels` runs in `revision/diffWorker.ts` (input: two snapshots, columnar typed arrays, transferred). Budget: 50 k × 50 k elements < 1 s; 500 k < 8 s; the fully re-GUIDed case must stay within 3× of that (the grid bounds the candidates).

### 3.3 Categories

`unchanged` · `changed` (one or more flags, each shown separately) · `rematched` (GUID changed, matched by signature; may also carry flags) · `new` · `deleted`.

### 3.4 What carries over (on "Review changes", before the walk opens)

| Element | Result (computed / manual) | Committed decision (review log) | Walk |
|---|---|---|---|
| unchanged | copied to head as is (source kept), no classifier call | carried: see below | not visited |
| changed, `classifyAffected` false, geometry not used by the classifier | copied as is | **not** carried; the base decision is the suggestion | visited: re-confirm |
| changed, `classifyAffected` true (or geometry/placement flag while `imageSettings()`/`geometrySettings()` is on) | classifier re-run with the current settings (the signature cache makes most of these free); the base result is kept as `suggestion` | not carried; base decision shown beside the new proposal | visited |
| rematched | as changed/unchanged by its flags, **after** the match is accepted | carried under the head GlobalId after the match is accepted | visited (confirm the match) |
| new | classified with the current settings (`svc.classify(ids)`) | none | visited |
| deleted | none | stays in the base log, which is never edited | visited: acknowledge |

**Carrying commits** (F4): for each base commit that still has an effective change on a carried element, append to the head log a commit with the **same author and time**, `note: 'Carried over from <base name>'`, only the carried changes, GlobalIds rewritten for accepted rematches, and

```ts
interface ReviewCommit { /* … */ carriedFrom?: { fingerprint: string; commitId: string } }   // additive; parseReviewLog accepts it
```

Commit id = `<baseCommitId>~<headFingerprint[0..6]>`, so running the carry-over twice adds nothing (`mergeCommits` dedupes by id). Requires the same `schemaHash`; with a different schema the banner says decisions cannot be carried and offers the diff and report only.

**Issues and sketches** attach by GUID and already follow a revised model (`markup/scope.ts`, `bcf/reproject.ts`). The walk adds, through one adapter (5.3):
- accepted **rematch**: retarget attachments from the base GUID to the head GUID;
- **deleted** element with attachments: the item shows "2 issues, 1 sketch attached" and three choices: **Keep, flagged** (default: stays detached with the note "element deleted in <head name>"), **Re-attach to…** (pick an element), **Resolve issues** (status resolved, comment "element removed in revision"). Nothing is deleted.

### 3.5 Walk order, items, filters

`revision/walkOrder.ts` (pure) builds `RevisionItem[]` from the diff, reusing `WalkElement`, `WalkItem`, `SkipList` and `sweepOrder` of `classify/reviewWalk.ts`:

```ts
export interface RevisionItem extends WalkItem { category: Category; flags: ChangeFlag[]; entries: DiffEntry[] }
export const REVISION_ORDERS = ['category', 'storey', 'class'] as const;   // primary grouping; the other two are the tie-breakers
export interface RevisionFilters { category?: Category; flag?: ChangeFlag; storey?: string; ifcClass?: string;
  undecided?: boolean; unsure?: boolean; onlySkipped?: boolean; hasAttachments?: boolean; minMove?: number }
```

- Default order `category`: deleted → rematched → changed → new; inside a category by storey elevation, then class, then `sweepOrder`.
- Grouping into one item ("confirm once for all N"): same category, same flag set, same class, same storey, same base classification codes, and for placement moves the same move vector within 1 mm (a shifted grid line becomes one item). `A` toggles all/one as in the review walk.
- Unchanged elements are not items; a filter chip shows their count and can isolate them.

### 3.6 Panel, card, overlay

New panel `plugins/revisionWalk.ts`, same visual language and DOM classes as the review walk (`.xrw…`; `classifyReview.ts` exports its style installer, no other change there). It is mounted through `PanelHost` (5.3): the right-hand sidebar when that exists, else the floating panel position the review walk uses.

Card, top to bottom: progress (`37 of 410 · 12 skipped`), item title and category badge, flag chips, **what changed** table (rows: flag · before · after; placement row "moved 8 mm north-east", geometry row "area −12 %, volume −9 %", properties as key rows, at most 8 then "n more"), classification block (base decision with reviewer status, new proposal with confidence when re-run), attachments line, decision buttons (outside the scroll area, as in the review walk).

Overlay (`revision/ghost.ts`): the head element is drawn normally and framed; the base shape is a translucent tinted ghost mesh in an overlay group (red: base / deleted, green: new, amber: changed head outline). Base geometry comes from `USER_MODELS` in the same session (F7), else from the stored ghost meshes (4.3), else the base **bounds box** as wireframe. `G` cycles ghost: both → head only → base only.

Decisions and keys (same keys as the review walk where the meaning is the same):

| Key | Action | new | deleted | changed | rematched |
|---|---|---|---|---|---|
| `Enter` / `Y` | Accept | is new; confirm the proposed classification | acknowledge deletion (attachment choice as selected) | accept the change with the **default** classification: base codes when `classifyAffected` is false or the new proposal equals them, else the new proposal | match is right; carry decisions, retarget attachments |
| `2` | Accept with the other classification | – | – | the non-default one of {base codes, new proposal} | – |
| `E` | Edit classification, then accept | yes | – | yes | yes |
| `R` | Reject (dispute) | "should not be here" | "should not be gone" | "change is wrong" | not the same element → splits into deleted + new |
| `N` / `→` | Skip (`Shift+N`: skip the other elements of the item) | all | | | |
| `?` | Unsure flag on the decision | all | | | |
| `←` back · `[` `]` element in item · `A` all/one · `U` undo · `G` ghost · `B` bulk · `Esc` close | | | | | |

Accept on a classified element creates a normal pending review change through `svc.review.propose(...)` (`confirm`, or `correct` after `E`/`2`), so the existing commit, undo, revert and log export all apply. A **Reject** records a dispute (report row, `Unsure`-style filter) and offers "Raise issue" (creates an issue at the element; for a deleted element at the base centroid). The classification is not committed for a rejected element.

**Bulk** (`B` opens the list; each rule shows its count and highlights the elements before it is applied; applied as one undo step):

```ts
export interface BulkRule { id: string; label: string; category?: Category; flagsWithin?: ChangeFlag[] /* all flags of the entry are in this set */;
  maxMove?: number; minScore?: number; classifyAffected?: boolean; noAttachments?: boolean; needsReview?: boolean; storey?: string; ifcClass?: string }
export function selectBulk(entries: readonly DiffEntry[], rule: BulkRule, ctx): DiffEntry[];   // pure
```

Shipped rules: "Accept placement-only moves up to [10] mm" · "Accept property-only changes that do not affect the classification" · "Accept rematches with score ≥ 0.95" · "Acknowledge deletions with nothing attached" · "Accept new elements classified by a rule and not needing review" · "Everything in the current filter". The millimetre and score fields are editable.

Phone layout (≤ 640 px wide or coarse pointer): the panel is a bottom sheet, 45 % of the height, drag handle to 85 %; decision buttons in a fixed two-row grid (Accept, Reject / Skip, Unsure, More); the what-changed table collapses to flag chips that expand on tap; swipe left = skip, swipe right = back; bulk and filters under "More". No key is required.

### 3.7 Outputs

1. **Revision report**: `revision-<base>-to-<head>.csv` and a summary `…-summary.md` (`revision/report.ts`, pure). CSV columns: `Category, Flags, BaseGlobalId, HeadGlobalId, IfcClass, Name, Storey, MoveMm, Rotated, MatchScore, PropertyChanges, ClassifyAffected, BaseDiscipline, BaseSubDiscipline, BaseDivision, HeadDiscipline, HeadSubDiscipline, HeadDivision, Verdict, Unsure, Classification (kept|new|edited|none), AttachmentAction, Note, DecidedAt, DecidedBy`. Summary: identities, thresholds, counts per category and flag, per storey table, accepted/rejected/skipped/undecided, bulk rules applied, carried commits. `DecidedBy` is in this file as it is in the existing review CSV (an explicit user export); it is in no setting, link, view or preset.
2. **Updated decision log**: the head's review log (carried commits + the walk's commits), exported by the existing "Export review log".
3. **Save IFC** on the head writes the confirmed state; with a finished or open revision session it adds `RevisionStatus` and `RevisionBaseline` (1.6). Deleted elements are not in the head file, so they appear in the report only.

---

## 4. State model and persistence

IndexedDB database **`xray-revisions`**, version 1 (pattern of `sheets/store.ts`: a backend interface, a memory backend for node and private windows, the UI says "kept for this session only" when IndexedDB is missing).

| Store | Key | Value |
|---|---|---|
| `snapshots` | `identityKey(identity)` (`name|count|guidHash`) | `SnapshotRecord` (4.1); index `name` |
| `sessions` | `<baseKey>><headKey>` | `RevisionSession` (4.2); index `headKey` |
| `ghosts` | session key | one Blob: base meshes of changed, rematched and deleted elements (4.3) |

Nothing here reaches localStorage, URL params, share links, saved views, presets or packed pages; `tests/revision-store.test.ts` adds these stores to the leak assertions.

### 4.1 Snapshot

```ts
export interface ModelSnapshot {
  schema: 'xray-model-snapshot/1';
  identity: ModelIdentity; savedAt: string; classificationSchemaHash: string; reviewFingerprint: string;
  originShift: [number, number, number]; guidSketch: Uint32Array; classHistogram: Record<string, number>;
  // columnar, index = element order
  globalId: string[]; ifcClass: string[]; name: string[]; tag: string[]; typeName: string[]; material: string[];
  storey: Array<{ name: string; elevation: number } | null>; systems: string[][];
  classifySignature: string[];              // signatureOf(buildInput(model, id))
  props: Array<Record<string, PropValue> | null>;
  bounds: Float32Array;                     // 6 per element, IFC world frame
  sig: Float32Array;                        // 11 per element (GeomSig), centroid in the IFC world frame
  results: Array<ClassifyResult | null>;    // probabilities trimmed to the top 3
}
interface SnapshotRecord { key: string; name: string; savedAt: string; counts: { elements: number; results: number; committed: number };
  guidSketch: Uint32Array; classHistogram: Record<string, number>; body: Blob /* gzip JSON + the two Float32Arrays */ }
```

Detection reads only the small record fields; `body` is read when a diff starts. Retention: the 3 newest snapshots per name stem, 300 MB in total, oldest evicted first; a snapshot referenced by an open session is not evicted. Size guide: 50 k elements ≈ 6–10 MB compressed.

### 4.2 Session

```ts
export interface RevisionDecision { key: string; verdict: 'accepted' | 'rejected'; unsure?: true; classification: 'kept' | 'new' | 'edited' | 'none';
  attachments?: 'keep' | 'reattach' | 'resolve'; reattachTo?: string; note?: string; at: string; by: string; bulk?: string; commitId?: string }
export interface RevisionSession {
  schema: 'xray-revision/1'; key: string; base: ModelIdentity; head: ModelIdentity; baseName: string;
  createdAt: string; updatedAt: string; status: 'open' | 'finished';
  options: RevisionOptions; diff: RevisionDiff; carried: { commits: string[]; results: number } | null;
  decisions: Record<string, RevisionDecision>; skipped: string[];
  cursor: { order: RevisionOrder; filters: RevisionFilters; itemKey: string | null; elementIndex: number };
}
```

Saved 500 ms after every decision, skip or cursor move, and on `visibilitychange`/`pagehide`. Unlike the review walk, **skips are stored** (a revision walk spans days).

**Reload mid-walk:** the page starts empty; the user opens the head file again. `onModel` finds the open session by `headKey` and shows "Resume revision review (123 of 410 decided)". Resume does not recompute the diff (it is in the session), restores the cursor, re-proposes as pending every accepted decision that has no `commitId` yet (the review walk's pending set is session-only), and re-runs the classifier only for new and `classifyAffected` elements that have no result (the signature cache answers most). If the head file opened is not the session's head (identity differs) the session is not offered. A session whose base snapshot was evicted still resumes (it needs only its own diff); ghosts fall back to boxes.

### 4.3 Ghost meshes

When a session is created in the same browser session as the base (F7), the base meshes of changed (geometry or placement), rematched and deleted elements are written to `ghosts`: positions quantised to 0.1 mm Int32 relative to the element bounds, Uint32 indices, in the IFC world frame; cap 64 MB (largest elements dropped first, they fall back to boxes).

---

## 5. Module and file plan

### 5.1 New pure modules (node-testable, no DOM, no three.js, no WASM)

| File | Content |
|---|---|
| `src/ifcsave/stepText.ts` | STEP string encode/decode, statement tokenizer, `parseArgs`/`formatArgs`, line builders |
| `src/ifcsave/stepScan.ts` | streaming scan over a Blob (1.3) |
| `src/ifcsave/ifcGuid.ts` | deterministic 128-bit hash → 22-char IFC GUID |
| `src/ifcsave/families.ts` | schema family, the eight templates per family, value typing (1.5, 1.6) |
| `src/ifcsave/plan.ts`, `additions.ts`, `splice.ts`, `readBack.ts` | 1.7 |
| `src/ifcsave/stepIndex.ts`, `removal.ts`, `patch.ts`, `meshRep.ts` | 2.4, 2.5 |
| `src/revision/geomSig.ts` | signature of a triangle range; sliced runner over arrays |
| `src/revision/snapshot.ts` | `snapshotOf(model, sigs, results, …)`, encode/decode, `guidSketch`, `revisionCandidate` |
| `src/revision/diff.ts`, `match.ts` | 3.2 |
| `src/revision/carry.ts` | carry plan: results to copy, ids to re-classify, commits to append (3.4) |
| `src/revision/walkOrder.ts`, `bulk.ts`, `report.ts` | 3.5–3.7 |
| `src/revision/session.ts`, `store.ts` | 4 (backend interface, memory + IndexedDB) |

### 5.2 Workers

`src/ifcsave/saveWorker.ts` (save, cleaned copy), `src/revision/diffWorker.ts`. Both created through a small runtime file beside `model/ifcRuntime.ts` so the single-file build can inline or disable them the same way; both have a main-thread fallback.

### 5.3 UI and wiring

| File | Change |
|---|---|
| `src/ui/panelHost.ts` (new) | `interface PanelHost { mount(id: string, title: string, el: HTMLElement): void; show(id: string): void; hide(id: string): void }` and `floatingPanelHost(app)` (the review walk's position). The sidebar agent's host replaces it in **one** place; no ticket depends on sidebar internals |
| `src/plugins/ifcSave.ts` (new) | plugin `ifcSave`: "Save IFC…" action (`registerAction`, top-bar File menu entry, button in the Classify drawer's export row), dialog, progress; `window.__xrayIfcSave = { plan(), save(opts), sources() }` for smoke tests |
| `src/plugins/revision.ts` (new) | plugin `revision`: snapshot triggers, detection banner, session lifecycle, `window.__xrayRevision = { candidates(), start(baseKey), state(), decide(key, verdict), bulk(ruleId), report() }` |
| `src/plugins/revisionWalk.ts` (new) | the panel (3.6) |
| `src/revision/ghost.ts` (new) | overlay meshes (three.js) |
| `src/revision/attachHost.ts` (new) | `interface AttachmentHost { countFor(guid): { issues: number; sketches: number }; retarget(map: ReadonlyMap<string,string>): number; flagDeleted(guids, note): void; resolveIssues(guids, comment): number }` over the markup, BCF and issues stores |
| `src/plugins/index.ts` | add `ifcSavePlugin`, `revisionPlugin` after `classifyPlugin` |
| `src/plugins/fileLoader.ts`, `src/model/ifcRaw.ts`, `ifcShared.ts`, `ifcWorker.ts`, `ifcImport.ts` | `saveInfo` pass-through, `sourcesOf`, unique file names in a federation (1.3) |
| `src/classify/reviewLog.ts` | `carriedFrom` on `ReviewCommit` (parse + keep) |
| `src/classify/types.ts`, `schema.ts` | optional `systems` (not in `schemaHash`) |
| `src/classify/reviewService.ts` | `appendCarried(commits)`; `src/classify/service.ts`: `adoptResults(results)` (merge without a run) |
| `src/plugins/classifyReview.ts` | export the style installer only |
| `src/plugins/cleanup.ts` | T5 only: one "Save cleaned copy…" button calling `__xrayIfcSave`. Coordinate with the cleanup agent; no other edit |
| `docs-features/ifc-save.md`, `docs-features/revision.md`, a section in `docs-features/classify.md` | user docs (docs-links test must pass) |

---

## 6. Tests

Fixtures (all generated, deterministic, checked in with their generator):

| Fixture | Made by | Content |
|---|---|---|
| `tests/fixtures/ifc/fzk-v2.ifc` + `fzk-v2.truth.json` | `tests/fixtures/make_revision_fixture.py` (ifcopenshell, seed 1) from `models/AC20-FZK-Haus.ifc` | moves 3 elements by 5 mm and 2 by 250 mm, rotates 1, deletes 4 (one a window with its opening), adds 3 (copies with new GUIDs at new places), re-GUIDs 6 unchanged elements, changes the class of 1, the type name of 2, a `Pset_WallCommon` value of 3, lengthens 1 wall. The truth file lists every expected category and flag set |
| `tests/fixtures/ifc/fzk-v2-reguid.ifc` | same script, `--reguid-all` | every GUID regenerated, model shifted by (1000, 0, 0) m: exercises the global-offset step |
| `tests/fixtures/ifc/mini-ifc4x3.ifc` | `make_ifc_fixtures.py` (extended) | 5 elements, schema `IFC4X3_ADD2` |
| `tests/fixtures/ifc/ports-ifc2x3.ifc`, `ports-ifc4.ifc` | exist | 2X3 / 4 with ports, for removal rules |
| `tests/fixtures/ifc/voids-ifc4.ifc` | `make_ifc_fixtures.py` (extended) | wall + 2 openings + door + window + an aggregate with 2 parts, for removal vetoes |

Unit and integration tests (vitest, node):

| File | Asserts |
|---|---|
| `ifcsave-steptext.test.ts` | string escapes round-trip (quotes, backslash, umlauts, CJK, astral); tokenizer skips `;` inside strings and comments; `parseArgs`/`formatArgs` round-trip on 200 real lines |
| `ifcsave-additions.test.ts` | per family: exact text of each template; pooling (identical tuples share one set); deterministic ids and GUIDs; reuse of an existing `IfcClassification`; 2X3 uses `ownerHistoryId`, 4 uses `$`; names absent with `includeNames:false` (leak assertion) |
| `ifcsave-roundtrip.test.ts` | for FZK-Haus (IFC4), `ports-ifc2x3.ifc`, `mini-ifc4x3.ifc`, `Process-Plant.ifc`: save with synthetic results on every element, then (a) `saved.slice(0, cut)` equals the original bytes; (b) web-ifc re-open: `GetAllLines().size() == original + lines`; (c) every original GlobalId maps to the same express id; (d) `IFCRELASSOCIATESCLASSIFICATION` read with `GetLine(…, true)` gives the expected code per element; `Xray_Review` values read back; (e) save again with the same state → identical bytes; with changed state → entity count = original + new lines (no doubling); (f) `readAdditions` equals the plan |
| `ifcsave-validate.test.ts` | runs `python3 -c` with `ifcopenshell.validate` on original and saved; the saved error set ⊆ the original's. Skipped with a notice when python or ifcopenshell is missing (same pattern as `ifc-import-parity.test.ts`) |
| `ifcsave-scan.test.ts` | `stepScan` max id and `dataEnd` equal web-ifc's `GetMaxExpressID` and the true offset on all fixtures; finds an old block; chunk-boundary cases |
| `ifcsave-removal.test.ts` | each row of table 2.3 on the small fixtures: output opens in web-ifc; removed GlobalIds absent; all others present with unchanged lines; no dangling reference (`every #n referenced exists`); vetoes produce `Xray_Cleanup.KeptBecause`; validate error set ⊆ original; entity count = original − deleted + added |
| `revision-geomsig.test.ts` | a box triangulated 3 ways gives equal signatures within 1e-5; translation changes only the centroid; rotation changes only centroid/extent; 1 % scale flags geometry; perf budget |
| `revision-diff.test.ts` | `fzk-v2` against the truth file: every category and flag set exact; 5 mm moves report 5 ± 0.5 mm; the 6 re-GUIDed elements are `rematched` with score ≥ 0.95; `fzk-v2-reguid`: ≥ 95 % rematched, none wrong; synthetic 50 k × 50 k under the time budget |
| `revision-carry.test.ts` | unchanged keep results and commits (author, time, `carriedFrom`); running twice adds no commit; changed elements get no commit and a suggestion; `classifyAffected` drives the re-run list; different schema hash → no carry |
| `revision-walk.test.ts` | order and grouping pinned for `fzk-v2`; filters; bulk rule "placement ≤ 10 mm" selects exactly the 3 small moves; decisions → pending review changes |
| `revision-store.test.ts` | snapshot encode/decode; eviction; session resume state; memory backend; leak assertions (no store content in params, views, presets, share link, pack) |
| `revision-report.test.ts` | CSV header and rows for `fzk-v2`; summary counts |

Smoke outline (`bench/smoke-ifc-save-revision.mjs`, Playwright, same style as `bench/smoke-bcf.mjs`):
1. Open `AC20-FZK-Haus.ifc`; classify all with rules only; open the review walk, confirm 3 items, commit.
2. `__xrayIfcSave.save({ includeNames:false })` → capture the download; re-open it in the page as a new model: element count equal, `props` show `<psetName>.Discipline`; bytes contain no reviewer name. Screenshot `bench/ifc-save-dialog.png`.
3. Open `fzk-v2.ifc`; expect the revision banner; click "Review changes"; expect counts equal to the truth file; unchanged committed elements show as committed.
4. Walk: accept a move (ghost visible: screenshot `bench/revision-walk-changed.png`), reject a deletion, apply bulk "moves ≤ 10 mm", skip one, flag one unsure.
5. Reload the page, open `fzk-v2.ifc` again → "Resume" → the cursor and decisions are back.
6. Export the report; check the row count; Save IFC on v2 → `RevisionStatus` present.
7. Phone viewport 390 × 844: the bottom sheet and buttons are on screen (screenshot `bench/revision-walk-phone.png`).
8. Cleaned copy (after T5): load `Building-Architecture.ifc`, run cleanup hide, "Save cleaned copy", re-open, hidden elements are gone, the rest equal.

---

## 7. Tickets

Order: **T1 and T3 in parallel** → **T2 and T4 in parallel** → **T5**. T1 and T3 are pure cores with no shared files.

### T1: IFC save core (pure) — no dependency
- Scope: sections 1.1–1.7 without UI and without the worker.
- Files: `src/ifcsave/{stepText,stepScan,ifcGuid,families,plan,additions,splice,readBack}.ts`; `src/classify/types.ts` + `schema.ts` (`systems`, parsed, not hashed); `tests/fixtures/make_ifc_fixtures.py` (`mini-ifc4x3.ifc`); tests `ifcsave-steptext`, `-additions`, `-roundtrip`, `-validate`, `-scan`.
- In tests, `IfcSource` values (`maxExpressId`, `ownerHistoryId`, `classifications`) come from `stepScan`; T2 supplies them from the importer.
- Acceptance: all five test files pass; `npm run typecheck`; existing tests unchanged (`classify-settings` schema hash snapshot still equal).

### T2: Save IFC in the app — needs T1
- Scope: 1.3 (retention, `saveInfo`, attach flow), 1.8 (worker, progress, federation, pickers), dialog, opt-in box, cleanup **marks** (2.2, read from `__xrayCleanup`/`userHides`), docs.
- Files: `src/ifcsave/{source,saveWorker,runtime}.ts`, `src/plugins/ifcSave.ts`, `src/plugins/index.ts`, `src/plugins/fileLoader.ts`, `src/model/{ifcRaw,ifcShared,ifcWorker,ifcImport}.ts`, `docs-features/ifc-save.md`, `bench/smoke-ifc-save-revision.mjs` (steps 1–2), tests `ifcsave-app.test.ts` (plan from a real `importIfc` of two federated files → two outputs, each element in its own file; importer `saveInfo` equals `stepScan`), leak test additions.
- Acceptance: tests pass; smoke steps 1–2 pass; `bench-large-ifc` import time within 2 % of before; saving a 100 MB+ file (the bench's synthetic large IFC) completes with the page's JS heap growing by less than 50 MB (record the numbers in `bench/RESULTS-ifc-save.md`).

### T3: Revision core (pure) — no dependency
- Scope: 3.1 (candidate test), 3.2, 3.3, the carry plan of 3.4, 3.5, bulk and report of 3.6–3.7, section 4 stores and session.
- Files: `src/revision/{types,geomSig,snapshot,diff,match,carry,walkOrder,bulk,report,session,store,diffWorker}.ts`; `src/classify/reviewLog.ts` (`carriedFrom`); `tests/fixtures/make_revision_fixture.py` + the two fixtures and truth file; the six `revision-*.test.ts` files.
- Acceptance: tests pass, including the timing budgets; `classify-review` tests unchanged.

### T4: Revision walkthrough UI — needs T3 (T2 only for smoke step 6)
- Scope: detection banner and manual entry points, carry-over execution (`adoptResults`, `appendCarried`, classify of new/affected), the panel, card, ghost overlay, keys, bulk UI, phone layout, attachment adapter, session autosave and resume, report export, `RevisionStatus` hand-off to the save plan (`extra.revision`).
- Files: `src/ui/panelHost.ts`, `src/plugins/{revision,revisionWalk}.ts`, `src/revision/{ghost,attachHost}.ts`, `src/plugins/index.ts`, `src/classify/{service,reviewService}.ts` (the two small methods), `src/plugins/classifyReview.ts` (export styles), `docs-features/revision.md`, smoke steps 3–7.
- Sidebar: mount only through `PanelHost`. If the sidebar has landed, add its adapter in `panelHost.ts`; if not, ship with `floatingPanelHost`.
- Acceptance: smoke steps 3–7 pass; keyboard-only and touch-only runs both finish the `fzk-v2` walk; `help-text`/`keymap` tests updated for the new keys; no new entry in params/presets (`params-roundtrip` unchanged).

### T5: Cleaned copy (and simplified copy, flagged) — needs T1, T2
- Scope: 2.3, 2.4, "Save cleaned copy…" with the confirm dialog and report; the markers-lost path of 1.4. **T5b** (separate commit, behind `?experimental=simplifiedIfc`): 2.5, only once the cleanup agent's `SimplifiedMesh` output exists.
- Files: `src/ifcsave/{stepIndex,removal,patch,meshRep}.ts`, `src/ifcsave/saveWorker.ts` (new message type), `src/plugins/ifcSave.ts`, one button in `src/plugins/cleanup.ts` (agree with the cleanup agent first), `make_ifc_fixtures.py` (`voids-ifc4.ifc`), `ifcsave-removal.test.ts`, smoke step 8.
- Acceptance: removal tests pass on 2X3 and 4; a cleaned FZK-Haus with 20 random non-host elements removed re-opens in web-ifc and in ifcopenshell with error set ⊆ original; 100 MB synthetic end to end < 10 s.

Dependencies on other agents: **right-hand sidebar** (T4 mounts through `PanelHost`, T2's button also sits in the top-bar File menu so it does not wait for the sidebar); **cleanup simplification + glb save** (T2 reads cleanup state through the existing global; T5 adds one button to their file; T5b consumes `SimplifiedMesh`).

---

## 8. Open questions for the user

| # | Question | Recommended default |
|---|---|---|
| Q1 | Property set names. You suggested `Pset_XrayReview`; the `Pset_` prefix is reserved for buildingSMART and validators flag it. | `Xray_Review` and `Xray_Cleanup` |
| Q2 | May reviewer names and review comments be written into a saved IFC? | Only when the box in the save dialog is ticked; off by default, asked every time |
| Q3 | Should decisions on unchanged elements carry over with no click at all when a revision is detected? | One click ("Review changes") first: detection by name or GUID overlap can be wrong, and the carry-over writes commits |
| Q4 | Is a diff of the loaded properties (attributes, common psets, base quantities) enough, or do you need every property compared? The full diff means reading both files' complete property sets (slower load of both). | Loaded properties now; a "deep property diff" option later if needed |
| Q5 | Cleaned copy: are the guarded cases right (keep and mark assemblies with remaining parts and walls that still host a door or window)? And is geometry write-back (simplified copy) wanted at all, given it replaces parametric geometry with triangles? | Guards on; simplified copy stays experimental until you have used cleaned copies |
| Q6 | Which classification system names should the shipped schema declare (the `systems` block)? | Discipline list: the schema's own code-list name and edition; divisions: "MasterFormat", source "CSI", the schema's edition |
| Q7 | Rejected changes ("this deletion is wrong"): should a reject always raise an issue, or only record a report row? | Report row always; "Raise issue" as a button, not automatic |
