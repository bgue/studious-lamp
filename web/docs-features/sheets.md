# Sheets: PDF drawing sheets

A PDF drawing opens as a **sheet set**, one sheet per page, next to the 3D model. You view it, sketch on it with the same drawing toolbar, raise issues from it, and export a copy of the PDF in which your sketches are real PDF annotations on a layer of their own. The annotations a PDF already has come in too.

Where: the sidebar tab **Issues**, segment **Sheets** (`Issues · Sketches · Sheets`). The segment is a separate one and not a group in Sketches because a sheet has pages and a PDF file, and a sketch on a sheet has no 3D view to restore; sheet sketches are listed with their page there, not in the Sketches grid. Scripting: `window.__xraySheets`. Code: `src/sheets/` (`model.ts`, `annot.ts`, `appearance.ts`, `layout.ts` pure; `pdfRead.ts`, `pdfWrite.ts`, `pdfSession.ts`, `pdfRuntime*.ts` PDF; `store.ts`, `controller.ts`, `viewer.ts`, `ui.ts`), `src/plugins/sheets.ts`. Stage 1 only: registering a sheet to the model (geo-PDF, two points), showing it in 3D and attaching drawings through sheets come later. `Sheet.placement` is there for that and unused.

## Opening a PDF

`Open PDF` in the Sheets segment, the action `Sheets: open a PDF`, or drop a `.pdf` on the page. The model stays loaded. A PDF that carries markup data of ours (a report from the Markup tool, [markup.md](markup.md)) still restores that markup; any other PDF is a sheet set. Opening the same bytes twice finds the first one. A password-protected PDF is refused with a message.

The libraries are **lazy**: `pdfjs-dist` (render, read annotations) and `pdf-lib` (write) load by dynamic `import()` the first time a PDF is opened or exported, and the pdf.js worker with them. Nothing PDF-related is in the main chunk, and showing the Sheets segment loads nothing. In the single-file build both libraries and the worker are embedded as gzip + base64 and unpacked on first use, like the IFC worker; no request leaves the file. The thumbnails of the last session are saved with the record, so listing sheets needs no library either.

## Data model

```
SheetDoc { id, name, bytesKey, pageCount, sha256, model? }
Sheet    { id, docId, page, name, widthPt, heightPt, rotation, box?, placement?: undefined }
```

Ids come from the SHA-256 of the bytes (`doc-<16 hex>`, `doc-<16 hex>-p<page>`), so the same PDF has the same ids in every session, in a sketch JSON and in a BCF file. `widthPt` and `heightPt` are the displayed page after `rotation`; `box` is the visible box in user space (the page's origin need not be 0, 0). A **sheet sketch** is a markup set with `frame: { kind: 'sheet', sheet: <sheet id> }`. Its camera and view are neutral placeholders that nothing reads (`SHEET_CAMERA`). Its shapes are **PDF user-space points** (x right, y up, before the page's `/Rotate`), so they stay put under pan and zoom. Text and callout offsets are fractions of the page height. Sketches carry the model they were made on like all sketches (scope, [markup.md](markup.md)); so do the docs, and the docs of another model are hidden with a count.

## Where it is stored

In memory during the session and in **IndexedDB** (database `xray-sheets`): one record per file for the bytes (key = SHA-256) and one JSON record for the docs, sheets, thumbnails and sheet sketches (never any bytes). After a reload the docs, sheets and sketches are back. Without IndexedDB (a private window) the store works in memory and says so. 3D sketches are not saved between visits; sheet sketches are, because their PDF is. PDF bytes are **never** in localStorage, URL parameters, share links, saved views or presets (`tests/sheets-store.test.ts` checks the code and the record).

## The sheet view

Opening a sheet puts a 2D view over the 3D canvas area, between the top bar and the status bar. The 3D view stays loaded under it. **Back to model** (top left) closes it; so does a model change. The bar also has the page arrows, `Fit`, the list of sketches on the sheet, and `Draw`. `+` and `−` zoom.

- Pan: drag (left button on the empty page, or the middle or right button anywhere). Zoom: wheel (about the cursor), `+` / `-` keys, the buttons, or a **two-finger pinch**. `0` fits.
- pdf.js draws the whole page once (up to 2400 px on the long side) and the picture scales with the zoom. When the zoom settles (about a quarter second) it draws the visible part again at the real zoom level, so the page is sharp at any zoom. Annotations are not drawn by pdf.js; the viewer draws them as sketches, so nothing shows twice.
- It works at 360 px: the bar wraps, the toolbar fits, the issues bottom sheet steps aside when a sheet opens.

## Sketching on a sheet

`Draw` (or `Edit drawing` in the Sheets segment) makes a sketch on the sheet when it has none, and shows the **same floating toolbar** as the 3D view, in the sheet view: cloud, cloud draw, rectangle, ellipse, arrow, line, polyline, polygon, pen, text, callout, marker, highlight box, colours, weights, fill, undo and redo, `Done`. The 3D `Pointer` is left out. Text and callout take the text typed in the bar, then a click on the page; the callout points at the click. Select, move and delete work; `Ctrl+Z` and `Ctrl+Shift+Z` undo and redo; `Esc`, `Enter` and double click work as in 3D. Stroke widths, text and badges scale with the sheet size (an A1 sheet gets thicker lines than A4: 1 unit per point up to 800 points across, then in proportion), so the same weight looks right on any sheet.

## Export: annotations on their own layer

`Export marked-up PDF` (per PDF, in the Sheets segment, or `__xraySheets.exportMarkedUp(docId)`) writes a copy of the original with pdf-lib:

- an **Optional Content Group** named `X-ray markups`, listed in `/OCProperties` (`/OCGs`, `/D /Order`, `/D /ON`); every annotation added has `/OC` pointing at it, so the layer toggles in Acrobat and Bluebeam;
- **real annotations**, each with `/C` colour, `/BS` width, `/Contents` (the shape text or the note), `/T` author, `/NM` id, `/M` date and an `/AP` appearance stream (so viewers that do not synthesise one still show it);
- the page content is **not touched**. pdf-lib has no incremental save, so the file is saved whole (without object streams).

| Tool | Annotation |
| --- | --- |
| cloud, cloud draw | `/Polygon`, `/BE <</S /C /I 1>>`, `/IT /PolygonCloud` |
| rectangle | `/Square` |
| ellipse | `/Circle` |
| line | `/Line`, `/LE [/None /None]` |
| arrow | `/Line`, `/LE [/None /ClosedArrow]` |
| polyline | `/PolyLine` |
| polygon | `/Polygon` |
| pen | `/Ink` |
| marker | `/Ink`, wide, `/CA 0.5` |
| highlight box | `/Square`, filled, `/CA 0.4` |
| text | `/FreeText` |
| callout | `/FreeText`, `/IT /FreeTextCallout`, `/CL` (target first) |

`/T` is "X-ray" unless you typed a name in that sketch; it is never a stray reviewer name. `/NM` is `xray-<sketch id>.<markup id>`. A **re-export replaces** the earlier X-ray annotations (every `/NM` starting `xray-`, with their appearance streams) instead of doubling them; deleting the last sketch of a page and exporting again clears it. Our own annotations also carry a few private keys (`/XrayKind`, `/XrayPts` ...) so that opening the file gives back exactly the shape that was drawn; without them (another tool edited the file) the shape is rebuilt from the standard keys, which is the table read backwards. A filled shape is `/IC` with the fill opacity in the appearance only; the label of a shape is in `/Contents`, not drawn in the appearance. Also kept: `Export JSON` of a sketch, like any sketch.

## Import: annotations already in the PDF

When a PDF opens, its annotations are read with pdf.js `getAnnotations()` (our own `/NM xray-` annotations with pdf-lib, because pdf.js does not expose `/NM` and our private keys):

- **Ours** come back as editable sheet sketches (one per sketch they came from, with its title), so export and re-open round-trip.
- **Others** (Square, Circle, Line, PolyLine, Polygon, Ink, FreeText, Highlight, Text notes, StrikeOut) become one **read-only sketch** per page, `Imported annotations`. It is drawn with their colour and geometry; selecting a shape shows its author and contents; the Sheets segment lists them. `Copy to editable sketch` makes an editable copy. A read-only sketch refuses edits (`MarkupSet.readonly`). Fills and appearance streams of foreign annotations are not reproduced (stroke, geometry, colour, text are); FreeText becomes a text box at the same place.
- Links, widgets, form fields, popups and hidden annotations are ignored.

## Raise as issue

`Raise as issue` on a sheet sketch works like for 3D sketches (one sketch, at most one issue; editing the sketch updates the issue). The viewpoint has **no camera**: it holds a PNG snapshot of the sheet region (the shapes with a margin, at least a quarter of the page) with the sketch drawn on it. The topic gets a **DocumentReference** to the PDF: BCF 3.0 `DocumentReferences/DocumentReference` with a `DocumentGuid` and `documents.xml` + `Documents/<guid>` in the zip; BCF 2.1 `DocumentReference` with `isExternal="false"` and `ReferencedDocument` `../Documents/<file name>.pdf` and the file in the zip. The side file `xray-markup.json` has, per viewpoint, `sheet`: `{ sha256, page, name, docName, title, bounds, markups }` (the sheet, the page, the region and the shapes in PDF points). Opening such a bcfzip opens the PDF from the zip when it is not open, makes a sketch of the shapes and links it to the issue; the sheet is found by the SHA-256. If the same PDF is opened later, sketches that waited for it (`Waiting for their PDF`) find their sheet. The snapshot is rendered again from the sketch before every export. See [bcf.md](bcf.md).

## Scripting

`window.__xraySheets`: `openFile(file)`, `docs()`, `sheets(docId?)`, `open(sheetId)`, `close()`, `openSheet`, `view()` (scale, offset, render counts), `zoomAt(x, y, k)`, `fit()`, `toUser(x, y)` and `toStage(ux, uy)`, `sketches(sheetId)`, `newSketch(sheetId)`, `add(setId, { kind, points | at, text })`, `copyToEditable(setId)`, `exportMarkedUp(docId, { download })`, `raise(setId, { topic? })`, `removeDoc(docId)`, `save()`, `status`, `persistent`. The Issues API takes `open('sheets')`.

## Files and tests

`tools/make_sample_pdf.mjs` builds `bench/fixtures/sample-sheet.pdf` (2 pages, walls, a title block, three foreign annotations; deterministic, 4.6 KB). Tests (node): `tests/sheets-annot.test.ts` (the mapping both ways for every tool at every page rotation, appearance, ids), `tests/sheets-pdf.test.ts` (the layer, `/OC`, subtypes, page content untouched, no doubling, round trip, foreign import with pdf.js legacy), `tests/sheets-bcf.test.ts` (the DocumentReference and side file round trip, BCF 2.1 and 3.0), `tests/sheets-store.test.ts` (store, no bytes in the record or anywhere that travels). Smoke: `SMOKE_PORT=5714 node bench/smoke-sheets.mjs` (screenshots `bench/sheets-view.png`, `sheets-phone.png`, `sheets-imported.png`).

## Limitations

- Appearances were checked structurally (pdf-lib, pdf.js, poppler) and not opened in Acrobat or Bluebeam: the layer, `/OC`, the subtypes and keys follow the PDF 1.7 rules, but how those programs show or edit them was not tested.
- Text in `/FreeText` is drawn in Helvetica (WinAnsi); other characters become `?` in the appearance (`/Contents` keeps them). On a rotated page the text box is not rotated with the page. Optional content needs PDF 1.5; an older header is raised to 1.5.
- The full file is rewritten on export (no incremental save). Encrypted PDFs are not supported.
- pdf.js draws without the standard font and wasm data files (no fetch): non-embedded standard fonts use system fonts, and JPX images and some ICC profiles may not draw.
- Imported foreign annotations are drawn simply (no fills, no custom appearance); the original appearance stays in the PDF for other viewers.
