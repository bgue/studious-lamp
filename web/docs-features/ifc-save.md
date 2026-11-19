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

The set names are `Xray_Review` and `Xray_Cleanup`, not `Pset_...`: that prefix belongs to buildingSMART. If the schema's own `psetName` starts with `Pset_`, the dialog warns you; it is written as given.

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

The block is marked by two comments, `XRAY-BEGIN ... base=N` and `XRAY-END bytes=N`. Saving a file that already holds a block **replaces** that block, never adds to it; new ids start after `base`. With an unchanged state, saving the saved file gives the same bytes. Hand-edited or re-exported files whose markers are lost are refused with a message; save from the original.

## When the source is not available

- A model opened from a `.glb` with a sidecar, a sample or a link has no IFC file. The dialog offers `Attach the source IFC...`. The file is accepted when at least 99 % of the model's elements are found in it with the same express id and GlobalId.
- If the file was moved, renamed or changed on disk, the browser cannot read it and the dialog says so; attach it again.
- The file is kept as a handle only (the `File` you opened, or a `Blob` of the unzipped `.ifczip`). It is never written into params, share links, saved views, presets or packed pages.

## Scripting

`window.__xrayIfcSave = { open(), close(), busy(), sources(), plan(req?), save(req?), attach(files), lastOutputs() }`

`save({ includeReviewers?, includeCleanupMarks?, scope?: 'all' | 'reviewed', target?: 'download' | 'none' })` returns `{ files: [{ name, source, bytes, lines, elements, replaced }], mode: 'worker' | 'main', target, ms }`. `target: 'none'` keeps the output in memory for `lastOutputs()` and writes nothing.

## Limits

- The property diff of a revision sees only what the viewer loaded; this feature adds data, it never edits existing data.
- Reading the file back needs a tool that understands IFC; the added lines were checked with web-ifc and IfcOpenShell 0.9 (no new validation errors).
- Large files: the save worker reads only the last 64 KB of the source. In the single-file build the worker is inlined; where no worker can start, the save runs on the main thread (the block is built in about 1 s for 50,000 elements).
