# Markup (internal coordination)

Draw on a saved view, comment, and hand the result to colleagues as a PDF or a JSON file. No BCF topic is needed: a markup set is one saved view (camera, section planes or box, hidden, ghosted, coloured and selected elements, active preset and top-bar mode, render style) plus its markups. A set converts to a BCF topic when an RFI needs one.

Where: the `Markup` tool in the action panel (a drawer), key `K` (rebindable, action `markup.toggle`), the `Markup` folder in the parameter panel, the command palette (`markup.new`, `markup.open`, `markup.pdf`, `markup.json`). Scripting: `window.__xrayMarkup`.

## Workflow

1. Frame the view, open the drawer (`K`), press `New set from view`. The set gets a thumbnail; sets are listed as cards, and a click on a card brings its view back (`Restore view` does the same). Several sets per session. Sets live in the session: export them to keep them.
2. Pick a tool and draw on the view. The orbit does not move while a drawing tool is active (mouse, touch and pen all draw; the right and middle mouse buttons still orbit and pan). The `Select` tool selects and moves markups and leaves the orbit alone elsewhere.
3. Edit in the list: text, status (`Open` / `Resolved`; click the chip), assignee, due date, comment thread. Author names come from the remembered BCF author (`xray.bcf.author`); the box at the bottom of the drawer sets it.
4. `Export PDF` / `Export JSON` (this set), `PDF of all sets`, `Convert to BCF topic`.
5. `Update view` captures the set's view again from the current camera and state (and the thumbnail). Anchored markups (callouts, text, pointers, measurements) keep their 3D anchors. Shapes follow the list beside the button: `on the model` (default) re-projects every shape point through its depth plane into the new camera (`rebaseShape`), so the shape stays on the same model area and keeps its place on screen from the new camera (its plane is re-fitted perpendicular to the new view at the mean depth; a shape with a point behind the new camera stays where it was on screen and is counted); `on the screen` keeps the fractions. It is one undo step (`Ctrl+Z` restores the old view, camera, thumbnail and shape points).

### Tools

| Group | Tool | How |
| --- | --- | --- |
| Select | Select | click selects, drag moves a shape or a text box |
| Cloud | Cloud | drag a rectangle; scalloped arcs, about 11 to 23 px each |
| Cloud | Cloud draw | draw a closed outline (simplified, then scalloped) |
| Annotate | Callout | click an element: text box with a leader to the clicked point; follows the element (exploded view, revised model) |
| Annotate | Text | click the model: a plain text box at that 3D point (on empty space: at the orbit-target distance) |
| Annotate | Pointer | click an element: an arrow pointing at it, text optional |
| Highlight | Marker | draw with a wide translucent stroke (multiply blend, yellow by default) |
| Highlight | Highlight box | drag a translucent box |
| Shapes | Rectangle, Ellipse, Line, Arrow | drag |
| Shapes | Polyline, Polygon | click each corner; double click, `Enter` or the `Finish` button ends it; a click on the first corner closes a polygon |
| Shapes | Pen | draw a freehand line |

Also `Link a measurement...` (list of the measure tool's measurements): a measurement markup with its own dimension line and length. Colours: red (default for clouds and shapes), yellow (default for highlights), blue, green, black; each tool remembers its colour. Line weight 1 to 4, `Fill` for closed shapes. A selected markup takes colour, weight and fill changes.

Phone layout: the drawer covers the view, so choosing a drawing tool on a narrow screen (under 760 px) closes the drawer and shows a floating bar (tool name, `Undo`, `Redo`, `Finish` for polylines, `Done`, `Tools`) in the free part of the view; the tool stays on until `Done` (or `Escape`), and the keys keep working. Touch and pen draw with pointer events; two-finger pinch is not used by the drawing tools.

Keys while the drawer is open or a drawing tool is on: `Ctrl+Z` undo, `Ctrl+Shift+Z` (or `Ctrl+Y`) redo, `Delete` removes the selection, `Escape` cancels a drawing, then returns to `Select`, then deselects, then (as always) closes the drawer. In a text field the keys edit text. Undo covers add, delete, move, edit and comments of the active set (100 steps).

## View behaviour when the camera moves

Markups stay drawn on their depth plane in 3D, exactly like BCF rectangles: a shape is stored as fractions of the set camera's view plus the depth (metres along the view direction) of the plane under its middle, so from another camera it stays on the model area it marks (callouts and pointers are 3D anchors that follow their element). When the camera drifts from the set's view (more than 4 degrees, 5 percent of the distance, or 8 percent zoom) the markups fade and a `Return to markup view` button shows at the top of the view. Why not fade-only: a shape that stays on its model area keeps its meaning while you look from the side or fly through the model; a fade-only rule would make the markup disappear exactly when someone wants to check what it marks. The button covers the case where the skewed view is not what you want.

## Export

### PDF

Landscape A4 or Letter (`Markup page size`), Helvetica (WinAnsi; accents kept, symbols such as arrows get an ASCII spelling, anything else `?`), JPEG pictures (DCT, quality 0.9). Per set:

1. Page 1: header (project or model name, date, set title, author, counts), the model view at the set's camera **without** markups, and the `How to get back to this view` block (3 steps, plus a clickable link when the page is served over http or https and the share link is at most 1800 characters).
2. Page 2: the same view with the markups burned in and numbered (the same layout code as the screen: `drawOps`).
3. Pages 3 and up: the comment table (number, type, text, status, author, assignee and due date, comments), repeating its header; long rows continue on the next page.

Picture resolution (`Picture quality` in the drawer, `Markup PDF resolution (dpi)` in the panel, params `markup.pdfResolution`): `screen`, `150`, `200` (default) or `300` dpi. The picture is rendered off screen by the viewer's own renderer, so the X-ray look (ghosts, edges, passes) is the screen's: for the export the drawing buffer is enlarged with `setPixelRatio` and `resize()` (every pass follows the buffer size), two frames are rendered, the pixels are copied into a 2D canvas in the same task, and the buffer goes back, so the canvas does not flicker. The width follows the page: the picture is fitted into the page box (770 x 400 pt on A4) and gets `width in inches x dpi` pixels (about 2000 px for a wide window at 200 dpi, 3000 px at 300 dpi). The picture keeps the aspect of the window, which is the aspect of the set camera, so the shapes are exact. The size is clamped to the graphics card (`maxTextureSize`, `MAX_RENDERBUFFER_SIZE`, at most 8192 px a side and 36 million pixels); when it is lowered the status line and `info.note` of `exportPdf` say so. Markups are burned in with sizes multiplied by the picture to screen factor, so they look as on screen. `exportPdf()` returns `info` (`resolution`, `pictureWidth`, `pictureHeight`, `note`, `ms`).

Every page has a footer with the set title and `Page n of N`. The PDF attaches the JSON (PDF EmbeddedFiles name tree plus `/AF`), stored uncompressed so it extracts byte for byte. Export restores each set's view to render it and then puts your view back. The writer is `src/markup/pdf.ts` (about 300 lines, no dependency); the page layout is `src/markup/report.ts`.

### JSON, `xray-markup-set/1`

```json
{ "schema": "xray-markup-set/1", "generator": "...", "exportedAt": "2026-03-01T09:30:00.000Z",
  "instructions": "To get back to this marked-up view: open the same model in the X-ray viewer, then drop this file ...",
  "model": { "name": "fzk-haus", "elementCount": 107, "guidCount": 107, "guidHash": "<16 hex digits>" },
  "link": "https://.../?model=fzk-haus#view=...",
  "sets": [ { "id": "s...", "title": "Level 1 routing", "author": "...", "created": "...", "updated": "...",
    "view": { "...": "a saved view (xray-views/1 shape): camera, selection, hides, clip, exploded, preset, params" },
    "camera": { "position": [x, y, z], "direction": [..], "up": [..], "fov": 45, "aspect": 1.6 },
    "nextNumber": 4,
    "markups": [
      { "id": "m...", "number": 1, "kind": "cloud", "colour": "red", "weight": 2, "fill": false, "text": "Clash", "status": "open",
        "shape": { "points": [[0.2, 0.2], [0.5, 0.4]], "depth": 12.3 }, "author": "...", "created": "...",
        "assignee": "Ben", "due": "2026-12-24", "comments": [ { "id": "c...", "author": "...", "date": "...", "text": "..." } ] },
      { "id": "m...", "number": 2, "kind": "callout", "text": "Move pipe", "offset": [0.1, -0.09],
        "anchor": { "kind": "element", "point": [1, 2, 3], "elementGuid": "<IfcGuid>", "local": [0.1, 0, 0] }, "...": "..." } ] } ] }
```

- `camera` and every `anchor` are in the IFC frame (metres, Z up) like the BCF side file; shape points are fractions of the view of `camera` (x right, y down) at `depth` metres. `view.camera` is the viewer-frame camera that `Restore view` uses. The saved view leaves out `classify`, `bcf`, keys and the other sections views never store, so a file holds no endpoint or secret (checked by the smoke).
- Model identity: `guidHash` is a 64-bit hash (two FNV-1a runs) of the sorted GlobalId list. On import the viewer compares it with the loaded model: `same`, `revised` (same file name, other elements), `different`, `unknown` (file without identity).
- Kinds: `cloud` (2 points: box; 3 or more: closed outline), `rect`, `ellipse`, `highlightBox` (2 opposite corners, or 4 corners as a quad after `Update view` from a rotated camera), `line`, `arrow` (2 points), `polyline`, `polygon`, `highlight`, `pen`, and the anchored `text`, `callout`, `pointer`, `measure`.
- Versioning: `xray-markup-set/1` is read; a newer major version is refused with a message. Unknown fields are dropped, ids and numbers are filled in, a markup that cannot be read is skipped and listed (`bad`), never silently.

## Getting back to the marked-up view

Open the same model, then drop the PDF or the JSON on the page (a lone `.pdf` or `.json` dropped on the viewer is a markup file; models are `.ifc` / `.glb`), or `Open file` in the drawer. The view comes back (camera, section, hides, colours, selection, preset) and the first set is active with all its markups. The status line and `window.__xrayMarkup.importJson()` report: sets and markups opened; `unknownGuids` (GlobalIds of anchors, linked measurements or the view that the model lacks: the markups stay at their stored 3D points, view parts for missing elements are skipped and counted); `match` and a warning for a revised or different model. A set with an id already in the session is replaced, others are added with a unique title. A PDF not made by this tool, or one re-saved by another tool into object streams, says it carries no markup data; use the JSON.

## Convert to BCF topic

`Convert to BCF topic` (set) or the same button in a markup's detail restores the view, then creates a BCF topic (title = set title, status Open when any markup is open) with a snapshot and viewpoint, callouts, text boxes and pointers as BCF `callout`, `note`, `arrow` annotations (element anchors keep their element), rectangles and highlight boxes as BCF rectangles, every other shape as a BCF freehand line (clouds and polygons closed, ellipses sampled, arrows with a head), measurements as a callout with the length, and the comments as topic comments ("3. text"). Both workflows then share data: export from the BCF tool as usual. Needs the BCF tool.

## Scripting

```js
const m = window.__xrayMarkup;
const set = m.create('Level 1 routing');                       // from the current view
m.add({ kind: 'cloud', points: [[400, 200], [560, 320]] });     // canvas CSS pixels (drag corners); 'fractions' stores view fractions
m.add({ kind: 'callout', at: [480, 260], text: 'Move pipe' });   // click position on the model
m.add({ kind: 'polygon', points: [[...], ...], colour: 'blue', fill: true });
m.comment(id, 'text'); m.update(id, { status: 'resolved', assignee: 'Ben', due: '2026-12-24' }); m.undo(); m.redo();
const pdf = await m.exportPdf({ ids: [set.id], page: 'A4', download: true });   // { name, bytes }
const json = m.exportJson({ ids: [set.id] });                    // { name, bytes }
await m.importJson(text);  await m.importFile(fileOrBlob);        // ImportReport { ok, sets, markups, unknownGuids, match, warnings, skipped }
m.restore(set.id, { animate: false });  await m.toBcf(set.id, markupId?);
m.updateView(set.id, { keep: 'model' | 'screen' });                // { shapes, moved, kept }; undoable with m.undo()
m.pdfResolution = 300;  (await m.exportPdf({ resolution: 150 })).info;  // { resolution, pictureWidth, pictureHeight, note, ms }
m.list(); m.get(id); m.hitTest(x, y); m.away; m.page = 'Letter';
```

The saved views plugin gained `capture()`, `restoreView(view)` and `shareUrlFor(view)` (a view object that is not in the Views list); `window.__xrayBcf` is used for the conversion.

## Files and tests

- `src/markup/model.ts` (types, JSON document, identity, sanitising), `geometry.ts` (scallops, ellipse, simplify, hit distances), `layout.ts` (draw operations; reuses `layoutAnnotation`, `shapePointWorld`, `shapeFraction`), `history.ts` (undo stack), `pdf.ts`, `report.ts`, `controller.ts`, `view.ts` (overlay layer, pointer and key input), `ui.ts` (drawer, drop), plugin `src/plugins/markup.ts`. `annotate.ts` gained a `style` override and a `blend` operation (multiply) for the highlighter.
- Tests: `tests/markup-pdf.test.ts` (structure, xref offsets, stream lengths, escaping, embedded file round trip, Flate), `markup-report.test.ts`, `markup-model.test.ts` (schema round trip, mismatch, identity), `markup-geometry.test.ts` (scallops), `markup-history.test.ts`.
- Smoke: `SMOKE_PORT=5710 node bench/smoke-markup.mjs` draws every tool on fzk-haus, comments, undo and redo, exports PDF and JSON, validates the PDF with pypdf / pdfinfo / pdftoppm (when installed), reloads and drops the PDF, opens the JSON, tries another model, converts to BCF, phone layout with touch and pen. Screenshots `bench/markup-*.png`. The software renderer of headless Chromium runs at 2 to 3 frames per second, so the run takes 15 to 30 minutes.

## Limitations

- Pictures have the aspect of the window (that of the set camera); a very tall window gives a narrow picture on a landscape page. Very large pictures are lowered to the graphics card limits (said in the status line); there is no tiled render.
- A Markup set does not store a thumbnail in the JSON; the PDF pictures are the thumbnails of the report.
- Sets are session data (no browser storage): export to keep them.
- Scallop size is fixed by weight; a shape cannot be resized by handles (delete and redraw, or undo).
- The PDF reader finds the embedded JSON in files written by this tool; a PDF re-saved by an editor that rewrites objects into object streams loses it from this reader (the JSON file still works).
- Orthogonal views use the viewer's approximation (see saved-views.md).
