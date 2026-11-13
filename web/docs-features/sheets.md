# Sheets: PDF drawing sheets

A PDF drawing opens as a **sheet set**, one sheet per page, next to the 3D model. You view it, sketch on it with the same drawing toolbar, raise issues from it, and export a copy of the PDF in which your sketches are real PDF annotations on a layer of their own. The annotations a PDF already has come in too.

Where: the sidebar tab **Issues**, segment **Sheets** (`Issues · Sketches · Sheets`). The segment is a separate one and not a group in Sketches because a sheet has pages and a PDF file, and a sketch on a sheet has no 3D view to restore; sheet sketches are listed with their page there, not in the Sketches grid. Scripting: `window.__xraySheets`. Code: `src/sheets/` (`model.ts`, `annot.ts`, `appearance.ts`, `layout.ts` pure; `pdfRead.ts`, `pdfWrite.ts`, `pdfSession.ts`, `pdfRuntime*.ts` PDF; `store.ts`, `controller.ts`, `viewer.ts`, `ui.ts`), `src/plugins/sheets.ts`. A sheet can also be **placed in the model** (see [Placing a sheet](#placing-a-sheet)): then it shows in 3D, the model draws over it, and its sketches attach to the elements under them. An unplaced sheet works as described first, unchanged. Code of the placement: `placement.ts`, `geoPdf.ts`, `mapConversion.ts`, `sectionCut.ts`, `attachSheet.ts` (pure), `placeService.ts`, `placeView.ts`, `overlayDraw.ts`, `scene3d.ts`, `chrome.ts`.

## Opening a PDF

`Open PDF` in the Sheets segment, the action `Sheets: open a PDF`, or drop a `.pdf` on the page. The model stays loaded. A PDF that carries markup data of ours (a report from the Markup tool, [markup.md](markup.md)) still restores that markup; any other PDF is a sheet set. Opening the same bytes twice finds the first one. A password-protected PDF is refused with a message.

The libraries are **lazy**: `pdfjs-dist` (render, read annotations) and `pdf-lib` (write) load by dynamic `import()` the first time a PDF is opened or exported, and the pdf.js worker with them. Nothing PDF-related is in the main chunk, and showing the Sheets segment loads nothing. In the single-file build both libraries and the worker are embedded as gzip + base64 and unpacked on first use, like the IFC worker; no request leaves the file. The thumbnails of the last session are saved with the record, so listing sheets needs no library either.

## Data model

```
SheetDoc { id, name, bytesKey, pageCount, sha256, model? }
Sheet    { id, docId, page, name, widthPt, heightPt, rotation, box?, placement?, geo? }
```

Ids come from the SHA-256 of the bytes (`doc-<16 hex>`, `doc-<16 hex>-p<page>`), so the same PDF has the same ids in every session, in a sketch JSON and in a BCF file. `widthPt` and `heightPt` are the displayed page after `rotation`; `box` is the visible box in user space (the page's origin need not be 0, 0). A **sheet sketch** is a markup set with `frame: { kind: 'sheet', sheet: <sheet id> }`. Its camera and view are neutral placeholders that nothing reads (`SHEET_CAMERA`). Its shapes are **PDF user-space points** (x right, y up, before the page's `/Rotate`), so they stay put under pan and zoom. `placement` and `geo` are described under Placing a sheet. Text and callout offsets are fractions of the page height. Sketches carry the model they were made on like all sketches (scope, [markup.md](markup.md)); so do the docs, and the docs of another model are hidden with a count.

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

## Placing a sheet

A sheet is a plain drawing until it is **placed**: given a place in the model. Placed, it shows in 3D, the model can be drawn over it, and sketches on it attach to model elements. The Sheets segment says it per sheet: `Not placed`, `Placed (manual, 2 points)`, `Placed (manual, ±N mm)` (three or more points), `Placed (manual, scale 1:100)` or `Placed (geo)`. Actions per sheet: `Place in model…` (`Place again…`), `Show in 3D`, `Model overlay`, `Remove placement`.

```
SheetPlacement { kind: 'manual' | 'geo', level: { storeyGuid?, name?, elevation }, plane?: 'plan' | { normal, point },
                 transform: { scale, rotation, tx, ty }, residual?, source, pairs?, drawingScale? }
```

`transform` is a 2D similarity (scale, rotation, translation, never a mirror) from PDF user-space points to the model's plan coordinates (IFC frame, X east, Y north, metres); `scale` is metres of model per PDF point. A plan sheet lies in the horizontal plane at `level.elevation` (metres, IFC Z; the storey's elevation). `plane` can hold a vertical plane for elevations and sections: the data model and `sheetToModel` handle it (the sheet's x along the plane, y up), but **the placement view places plans only**, and sketches attach through plan placements only. `residual` is the root mean square of the point misfits in metres, only with three or more pairs. The placement is saved with the sheet in IndexedDB (`Sheet.placement`) and **never** in a URL, share link, saved view or preset; the tests check the code and the record.

**Place in model…** opens the placement view over the canvas area: the sheet on the left, the plan of the chosen storey on the right (the plan cut as vectors, below). On a phone (up to 700 px) the two sides show one after the other, in steps; the hint line says which. The storey list is the model's storeys (lowest first; a model without storeys has one level at its lowest element).
- Pick point A on the sheet, then the same point in the model, then B on the sheet and in the model. Model picks **snap** to the corners of the cut outlines, then to its edges (12 px). Pan and zoom both sides (wheel, drag, pinch).
- Two pairs give the exact transform. `Add point` takes a third (up to eight); three or more are fitted by least squares and the **misfit** is shown in millimetres.
- `Use drawing scale`: type the scale (the 100 of 1:100), pick one pair, give the rotation in degrees (counter-clockwise, 0 when the drawing and the model share north). A point is 1/72 inch, so 1:100 is 35.28 mm of model per point.
- The result shows at once as the model overlay on the sheet. `Accept`, `Redo` (start the points again), `Cancel`. `Undo point` removes the last pick. Placing again starts from the points of the placement.
- When shapes on the sheet would move off the elements they are attached to, Accept asks first (`Place anyway` / `Keep editing`); nothing changes until you confirm.

### Geo-referenced PDFs

When a PDF opens, `Sheet.geo` is read from the page: **ISO 32000** geospatial (`/VP` array, viewport with `/Measure << /Subtype /GEO /GPTS /LPTS /GCS >>`; `LPTS` is 0..1 of the viewport's `/BBox`, the page when it has none) and, best effort, **OGC LGIDict** (`/CTM` and `/Projection`; UTM on WGS 84 names its EPSG code). `GPTS` is latitude and longitude as ISO says; a producer that writes projected coordinates in a projected `/GCS` (read as easting, northing) is read as projected. Degrees are projected to UTM for the EPSG families we know (WGS 84, ETRS89 and NAD83 UTM zones, Krüger series); any other projection of degrees is not applied.

The model's `IfcMapConversion` and `IfcProjectedCRS` are read from IFC files (Eastings, Northings, OrthogonalHeight, XAxisAbscissa, XAxisOrdinate, Scale, the EPSG code in the CRS name; map unit and project length unit applied, so the numbers are metres; `SceneModel.mapConversion`, sidecar key `mapConversion`). The chain is sheet → CRS → model: a similarity fitted to the corner points (a skewed geo-referencing is refused), then the inverse of the map conversion. **When the PDF's CRS is projected and the same as the model's, the sheet is placed by itself and marked `geo`**, at the storey its name mentions, else the lowest (change it with `Place again…`). Otherwise nothing is guessed: not placed, and the panel shows what was found and why ("The PDF is in EPSG:25832 and the model in EPSG:31467", "lat/long without a projection this viewer can apply", "the model has no IfcMapConversion") next to `Place in model…`. Conversion between two projected CRS is not done.

## Model overlay

`Model overlay` in the sheet view (or in the Sheets segment) draws **the plan cut as thin vector outlines** over the PDF, lined up through the placement, with an opacity slider and, with three or more pairs, a `Misfit ±N mm` readout. The cut is the plane **storey + 1.2 m** (as the Plan view of a sketch, `src/issues/derivedViews.ts`): the triangles of every element that the plane passes through are sliced (`sectionCut.ts`), the segments chained into outlines, straight runs merged. Decision: vectors, not an offscreen render of the 3D view. It costs a few milliseconds per level (cached), is sharp at any zoom with nothing to redraw when the zoom settles, needs no second WebGL pass next to the OIT and section code, and gives the same outlines the placement view snaps to and the attachment tests against. Slabs and anything that the plane does not pass through are not in it (as in a plan).

## In 3D

`Show in 3D` puts the placed sheet in the 3D view as a **textured quad** at its level (3 cm above it, so it does not fight the floor): the page drawn with pdf.js at 2048 px on the long side, drawn again at 4096 px once the camera is within about 1.6 radii of it. A slider in the Sheets segment sets the opacity of all of them. The quad is a mesh with no raycast and no depth write: picks (which use the per-element BVHs), measurements and the classification never see it, and section caps, the x-ray modes and the OIT composite draw as before. It is not clipped by section planes. The sketches of a placed sheet are drawn in 3D, on the quad, with the layout of attached 3D sketches (`src/markup/layout.ts`), when the sheet is shown in 3D or its sketch is the active one, and the model is visible. Plan sheets only.

## Attachment: sketches through a placed sheet

When a shape or text is drawn or moved on a **placed plan sheet**, its points go through the placement to model coordinates and `attachSheet.ts` decides the attachment from what the plan cut shows, in the same kinds as 3D sketches (`src/bcf/attach.ts`), stored on the markup the same way, with GlobalIds for BCF:

| Under the shape | Stored |
| --- | --- |
| a point (text, callout, a tiny shape under 0.3 m) on an element (inside its outline or within 10 cm) | text and callout: the anchor becomes `element` with the GlobalId; a tiny shape: `point` with the GlobalId |
| a closed outline over or around 1 to 12 elements | `elements` (their GlobalIds), with the outline lying on the plan as `surface` data |
| a line along or across up to 5 elements (within 12 cm) | `surface` |
| nothing, or more than 12 elements | `region`: the shape's bounds at the level, up to the next storey (3 m without one), padded 5 cm |

The shape itself stays in PDF points, so the sheet still draws it. **Placing again re-derives the attachments** (asking first, above); `Remove placement` sets them back to none. An unplaced sheet's sketch stays sheet-only: no attachment, nothing in 3D.

**Raise as issue** on such a sketch adds a real 3D viewpoint to the issue: the target GlobalIds as components, a perspective camera framing the targets, next to the sheet snapshot and the DocumentReference (stage 1). The viewpoint follows the sketch before every export. The sketch has the **3D · Plan · Section** switch (in the issue and the sketch row): Plan and Section are derived from the targets as for 3D sketches and are written to the BCF as extra viewpoints; 3D frames the targets (a sheet sketch has no camera of its own) and leaves the sheet view. Opening the bcfzip elsewhere gives a sketch with the same attachments, without the placement.

## Scripting

`window.__xraySheets`: `openFile(file)`, `docs()`, `sheets(docId?)`, `open(sheetId)`, `close()`, `openSheet`, `view()` (scale, offset, render counts), `zoomAt(x, y, k)`, `fit()`, `toUser(x, y)` and `toStage(ux, uy)`, `sketches(sheetId)`, `newSketch(sheetId)`, `add(setId, { kind, points | at, text })`, `copyToEditable(setId)`, `exportMarkedUp(docId, { download })`, `raise(setId, { topic? })`, `removeDoc(docId)`, `save()`, `status`, `persistent`. Placement: `levels()`, `placement(sheetId)`, `setPlacement(sheetId, p, { confirmed })`, `placeByPairs(sheetId, pairs, { level })`, `removePlacement`, `place.open / state / clientOfSheet / clientOfModel` (the placement view; the last two give client pixels to click on), `cut(elevation)`, `cutPolys(elevation)`, `geo(sheetId)`, `show3d(sheetId, on)`, `quad(sheetId)`, `setQuadOpacity(v)`, `scene3d()`, `overlay(sheetId, on)`, `overlayState()`, `attachments(setId)`, `viewpointOf(setId)`. The Issues API takes `open('sheets')`.

## Files and tests

`tools/make_sample_pdf.mjs` builds `bench/fixtures/sample-sheet.pdf` (2 pages, walls, a title block, three foreign annotations; deterministic, 4.6 KB). Tests (node): `tests/sheets-annot.test.ts` (the mapping both ways for every tool at every page rotation, appearance, ids), `tests/sheets-pdf.test.ts` (the layer, `/OC`, subtypes, page content untouched, no doubling, round trip, foreign import with pdf.js legacy), `tests/sheets-bcf.test.ts` (the DocumentReference and side file round trip, BCF 2.1 and 3.0), `tests/sheets-store.test.ts` (store, no bytes in the record or anywhere that travels). Smoke: `SMOKE_PORT=5714 node bench/smoke-sheets.mjs` (screenshots `bench/sheets-view.png`, `sheets-phone.png`, `sheets-imported.png`).

Placement: `tools/make_sample_pdf.mjs` also writes `bench/fixtures/geo-sheet.pdf` (one page, 1:100, an ISO 32000 `/VP` with `/GEO` in EPSG:25832, projected coordinates; sheet point 0, 0 is E 500100, N 5400010). Tests: `tests/sheets-placement.test.ts` (similarity from two pairs, least squares and residual, scale + rotation + one pair, status words, reading a stored placement), `sheets-placement-geo.test.ts` (the /VP read from the fixture with pdf-lib, LGIDict, UTM, IfcMapConversion numbers, the chain PDF → CRS → model, the CRS-mismatch refusal), `ifc-map-conversion.test.ts` (IfcMapConversion and the storey GlobalIds read by web-ifc from an IFC text, also a millimetre model), `sheets-placement-cut.test.ts` (slicing, outlines, snapping), `sheets-placement-attach.test.ts` (elements, region, point and empty cases over known footprints), `sheets-placement-store.test.ts` (saved with the sheet, never in a view, preset or link). Smoke: `SMOKE_PORT=5715 node bench/smoke-sheets-place.mjs` builds a sheet from FZK-Haus's own ground-floor plan cut at 1:100 turned 20 degrees (screenshots `bench/sheets-place.png`, `sheets-overlay.png`, `sheets-3d.png`, `sheets-place-phone.png`). FZK-Haus has no IfcMapConversion: the smoke gives the page's model one to exercise the geo path, a unit test reads a real one from an IFC.

## Limitations

- Placement: the placement view places **plan** sheets; elevation and section sheets have the data model (`plane`) but no way to place them yet, and nothing attaches through them. A geo-PDF in a CRS other than the model's is not converted, and degrees are projected for UTM EPSG codes only (other projections, such as Gauss-Krüger, are placed by hand). Several storeys on one sheet are not handled: one sheet, one level. The cut outlines are of elements that the plane passes through; a sketch over a floor slab alone attaches to nothing (a region). The 3D quad is not clipped by section planes. A placement is relative to the model it was made on (the sheet is hidden with the other models' sheets).

- Appearances were checked structurally (pdf-lib, pdf.js, poppler) and not opened in Acrobat or Bluebeam: the layer, `/OC`, the subtypes and keys follow the PDF 1.7 rules, but how those programs show or edit them was not tested.
- Text in `/FreeText` is drawn in Helvetica (WinAnsi); other characters become `?` in the appearance (`/Contents` keeps them). On a rotated page the text box is not rotated with the page. Optional content needs PDF 1.5; an older header is raised to 1.5.
- The full file is rewritten on export (no incremental save). Encrypted PDFs are not supported.
- pdf.js draws without the standard font and wasm data files (no fetch): non-embedded standard fonts use system fonts, and JPX images and some ICC profiles may not draw.
- Imported foreign annotations are drawn simply (no fills, no custom appearance); the original appearance stays in the PDF for other viewers.
