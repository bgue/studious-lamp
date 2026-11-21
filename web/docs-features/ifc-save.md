# Save IFC

`Save IFC` writes a copy of the IFC file you opened, with the classification, the review state and the cleanup marks added. Open it with the button `Save IFC` in the `Open model` folder, or with the command `Save IFC...` (`ifc.save`) in the command palette.

The copy is the **original file, byte for byte**, plus one block of new lines inserted before the final `ENDSEC;` of the DATA section. No line of the original is changed, removed or renumbered, and the header is untouched. The file is not parsed again and web-ifc is not used at save time, so a 1 GB model costs only the block (a few megabytes) in memory: the output is slices of your file plus the block. Nothing leaves your computer.

## What is written

| Data | Where |
| --- | --- |
| Classification systems and references | `IfcClassification` (reused when the file already has one of the same name and edition) and `IfcClassificationReference`, one per code; `IfcRelAssociatesClassification` links each element to its most specific reference (sub-discipline, else discipline; section, else MasterFormat division) |
| The classification properties | the property set named by the schema (`psetName`, default `XR_Classification`): discipline, sub-discipline, MasterFormat division, title and section, confidence, source, model, needs review. The same values the viewer shows as `<psetName>.<Property>` |
| Review state | `Xray_Review`: `Status` (unreviewed, manual, confirmed, corrected), `Unsure`, `NeedsReview`, `Confidence` and the three part confidences, `BuildingElementProbability`, `ProposedBy`, `Rationale` (rules only), `ReviewedAt`, `CommitId`, `SchemaHash`; after a revision walk also `RevisionStatus` and `RevisionBaseline` |
| Cleanup marks | `Xray_Cleanup`: `FlaggedForRemoval` = true, `Rules`, `Reason`. Nothing is removed from the file |
| 4D mapping | `Xray_4D`: the `IfcLabel` properties `Location`, `Trade` and `Zone` of the accepted 4D assignments, with the box `Include 4D location, trade and zone` ([4d-mapping.md](4d-mapping.md)) |

The set names are `Xray_Review`, `Xray_Cleanup` and `Xray_4D`, not `Pset_...`: that prefix belongs to buildingSMART. If the schema's own `psetName` starts with `Pset_`, the dialog warns you; it is written as given.

Supported schemas: IFC2X3, IFC4 and IFC4X3. For any other schema (IFC2X2, unknown) the dialog names the schema and the button stays disabled.

## The dialog

- The list of files with their size, schema and the number of elements that carry data.
- `Write`: all classified elements, or only the reviewed ones (confirmed, corrected or set by hand).
- `Include reviewer names and comments`: **off every time you open the dialog**. It is not remembered, not a setting and not in the params document. Off: no reviewer name and no review comment is written. On: `Xray_Review.ReviewedBy` and `Xray_Review.Comment` are added. API keys, access tokens and pictures have no way into the file in either case.
- `Mark cleanup matches`: on when cleanup has hidden something. Elements you hid by hand are not marked, only the ones cleanup hid and you did not un-hide.
- A progress bar and `Cancel save`. Cancel stops the worker and writes nothing.

Writing: where the browser offers `showSaveFilePicker` you pick the destination (the file streams to disk); with several files `showDirectoryPicker` asks for a folder. Otherwise each file is downloaded, 300 ms apart.

## Several files (federation)

A model opened from several IFC files is saved as **one output per source file**, named `<stem>.xray.ifc`. Each element goes to the file it came from. A name that already ends `.xray.ifc` keeps it. If two files had the same name, the second was opened as `name (2).ifc`. When the federation dropped duplicate elements (same GlobalId and same geometry in two files), they exist only in the first file that has them; their twins in a later file get no data. The dialog says how many.

## Saving again

The block is marked by two comments, `XRAY-BEGIN ... base=N` and `XRAY-END bytes=N`. Saving a file that already holds a block **replaces** that block, never adds to it; new ids start after `base`. With an unchanged state, saving the saved file gives the same bytes. A file that went through another tool (which drops comments) loses the markers; the property sets named `Xray_Review`, `Xray_Cleanup` or `Xray_4D` and the relations named `Xray ...` are then found by name, taken out and written again, so nothing is written twice. This costs one pass over the file at save time.

## When the source is not available

- A model opened from a `.glb` with a sidecar, a sample or a link has no IFC file. The dialog offers `Attach the source IFC...`. The file is accepted when at least 99 % of the model's elements are found in it with the same express id and GlobalId.
- If the file was moved, renamed or changed on disk, the browser cannot read it and the dialog says so; attach it again.
- The file is kept as a handle only (the `File` you opened, or a `Blob` of the unzipped `.ifczip`). It is never written into params, share links, saved views, presets or packed pages.

## Scripting

`window.__xrayIfcSave = { open(), close(), busy(), sources(), plan(req?), save(req?), attach(files), lastOutputs(), openClean(), cleanCandidates(req?), cleanPlan(req?), saveCleaned(req?) }`

`save({ includeReviewers?, includeCleanupMarks?, scope?: 'all' | 'reviewed', target?: 'download' | 'none' })` returns `{ files: [{ name, source, bytes, lines, elements, replaced }], mode: 'worker' | 'main', target, ms }`. `target: 'none'` keeps the output in memory for `lastOutputs()` and writes nothing.

## Saving a cleaned copy

`Save cleaned copy...` in the `Model cleanup` folder (next to `Save cleaned model`, which writes a glb), or the command `Save cleaned copy...` (`ifc.saveCleaned`), writes `<stem>.cleaned.ifc`: your IFC file **without the elements cleanup hid**. It is a derived file: the name says so, the block comment records `removed=n kept=m`, and your original is never changed. Run cleanup and `Hide matches` first; the elements are the ones cleanup hid and you did not un-hide (plus, with the box ticked, the ones you hid by hand).

The dialog first reads and plans the removal (a dry run), then shows a report: how many elements and lines go, the rules behind them (`tiny`, `floating`, ...), how many relationship lists were trimmed or deleted, and the elements that are **kept and marked** with the reason. Nothing is written until you press `Save cleaned copy`.

What removing an element means: its line goes; every relationship that mentions it is repaired (the element leaves the containment list, the aggregate, the property and material associations; a relationship left with nothing is deleted); the geometry, placement and property sets that nothing else uses are swept out. Shared things stay: a placement another element is relative to, a material or style used elsewhere, type objects, groups, spatial elements, units and contexts.

| Case | What happens |
| --- | --- |
| A wall (or slab, ...) with openings | The opening elements, their voids and fills go with it. If a door or window **that stays** stands in one of its openings, the wall is **kept** and marked `KeptBecause = hosts a door or window` (box `Remove walls even if a door or window stays` lifts this; the door or window then stands in no wall) |
| A door or window | Its fill is cut. The opening stays as a hole in the wall |
| An assembly | Removed only when all its parts are removed too. Otherwise kept and marked `has parts` |
| A duct, pipe or fitting with ports | The element, its ports and the connections of its ports go; the neighbour's port stays, unconnected |
| Anything another line refers to that is not a relationship | Kept and marked `referenced by <class>` |
| Project, site, building, storey, space | Never removed |

Kept elements get `Xray_Cleanup` with `FlaggedForRemoval`, `Rules`, `Reason` and `KeptBecause`. Accepted loss: neighbours lose connections (ports, path connections) and an opening can stay without its door or window. Not handled: structural analysis relations, cost and schedule assignments beyond trimming, `IfcRelSequence`; a file with `IfcStructuralAnalysisModel` gets a warning line. An earlier Xray block of the file is dropped and written again.

The box `Also write the classification` adds the classification and review data of the elements that stay (as `Save IFC` does; reviewer names only when that box is ticked). The copy is written in memory in the save worker (the whole file is read once, indexed, and written in 4 MB chunks), so a source above 1 GB is refused for a cleaned copy with a plain message; plain `Save IFC` has no such limit. A model opened from several files gets one cleaned copy per file that has something to remove.

Scripting: `cleanCandidates()` returns `{ cleanup, handHidden }`; `cleanPlan(req?)` returns `{ files: [report], missingSources }` where each report holds `removed`, `cascaded`, `kept: [{ expressId, globalId, because, rules, reasons }]`, `stats` and `warnings`; `saveCleaned({ withClassification?, includeReviewers?, removeHostsAnyway?, includeHandHidden?, ids?, target?: 'download' | 'none' })` returns `{ files: [{ name, source, bytes, sourceBytes, removed, cascaded, kept, linesDeleted, lines }], kept, mode, target, ms }`.

### Simplified geometry (experimental)

With `?experimental=simplifiedIfc` in the page address, the dialog shows `Replace the body of N simplified elements` when the Simplify tools have staged replacement meshes (`__xrayCleanup.simplify.plan().replacements`). The Body representation of each such element is replaced by a triangle mesh: `IfcTriangulatedFaceSet` (IFC4, IFC4X3), a faceted brep for a closed mesh or a shell based surface model for an open one (IFC2X3, about 5 lines per triangle; the dialog warns above 200,000 triangles). The mesh is converted from the viewer frame back to IFC: undo the Y-up swap and the origin shift, divide by the file's length unit (read from the project's unit assignment), then undo the element's own placement chain, so the element keeps its **ObjectPlacement**. GlobalId, class, attributes, property sets, type, material, containment, voids, fills, other representations (axis, footprint), the first body item's surface style and layer assignments stay. The old body and everything only it used are swept out. The new lines go **before** the Xray block, so a later `Save IFC` (which replaces the block) cannot remove them.

Lost: parametric geometry (extrusions, profiles), per-item styles beyond the first, type-shared geometry for that occurrence; a `...StandardCase` element no longer meets its class's geometry convention. An element with a linear or grid placement, no Body, or a shape shared with something else keeps its original body and is listed. After writing, the output (up to 200 MB) is read again with the importer and the bounds of every replaced element are compared with the viewer: more than 1 mm off and that element keeps its original body (the file is written again). `saveCleaned({ withSimplified: true })` returns `geometry: { applied, skipped, selfChecked, selfCheckFailed }`.

## Limits

- The property diff of a revision sees only what the viewer loaded; this feature adds data, it never edits existing data.
- Reading the file back needs a tool that understands IFC; the added lines were checked with web-ifc and IfcOpenShell 0.9 (no new validation errors).
- Large files: the save worker reads only the last 64 KB of the source. In the single-file build the worker is inlined; where no worker can start, the save runs on the main thread (the block is built in about 1 s for 50,000 elements).
