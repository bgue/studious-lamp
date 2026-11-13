# Markup: sketches and the drawing engine

The drawing layer of the viewer. A **sketch** (formerly a markup set) is one saved view (camera, section planes or box, hidden, ghosted, coloured and selected elements, active preset and top-bar mode, render style) plus its drawings and an optional one-line note. A sketch can be drawn on, exported as a PDF report or a JSON file, and raised as an **issue** (a BCF topic) whose viewpoint links to the sketch by id. The same drawing engine draws the viewpoints of issues. The restructure (Issues tab, linking, migration of old sets) is in [issues.md](issues.md); this page describes the engine: tools, attachments, the 2D view, the PDF and the JSON.

Sketches have **no status and no comment thread** any more: those belong to an issue ([bcf.md](bcf.md)). Old sets that carry them keep the data (read-only on the sketch) until they are raised as issues, see [issues.md](issues.md), "Migration of old markup sets".

Where: the `Issues` tab of the left sidebar, segment `Sketches`, key `K` (rebindable, action `markup.toggle`); the drawing toolbar floats over the view while a sketch is edited; the `Markup` folder in the parameter panel; the command palette (`markup.new`, `markup.open`, `markup.pdf`, `markup.json`, and `tool.markup` as the alias of the old drawer action). The Markup drawer of the tool strip is gone. Scripting: `window.__xrayMarkup` (sketches and drawings), `window.__xrayIssues` (panel, links).

## Workflow

1. Frame the view, press `K`, `New sketch`. The sketch gets a thumbnail; sketches are listed as cards, and a click on a card opens its detail and brings its view back (`Restore view` does the same). Several sketches per session. Sketches live in the session: export them to keep them.
2. `New sketch` and `Edit drawing` show the **drawing toolbar** ([issues.md](issues.md), "The drawing toolbar"): pick a tool and draw on the view. The orbit does not move while a drawing tool is active (mouse, touch and pen all draw; the right and middle mouse buttons still orbit and pan). The `Select` tool selects and moves drawings and leaves the orbit alone elsewhere. `Done` hides the toolbar.
3. Edit in the panel: the title, the one-line note, and per drawing the text and the attachment chip. Author names come from the remembered BCF author (`xray.bcf.author`); the box at the bottom of the panel sets it.
4. `Export PDF` / `Export JSON` (this sketch), `Raise as issue`.
5. `Update view` captures the sketch's view again from the current camera and state (and the thumbnail). Anchored markups (callouts, text, pointers, measurements) keep their 3D anchors. Shapes follow the list beside the button: `on the model` (default) re-projects every shape point through its depth plane into the new camera (`rebaseShape`), so the shape stays on the same model area and keeps its place on screen from the new camera (its plane is re-fitted perpendicular to the new view at the mean depth; a shape with a point behind the new camera stays where it was on screen and is counted); `on the screen` keeps the fractions. It is one undo step (`Ctrl+Z` restores the old view, camera, thumbnail and shape points). If the sketch belongs to an issue, the issue's viewpoint is captured again from the same view.

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

Phone layout: the Issues panel is a bottom sheet that steps aside while a sketch is edited, and the drawing toolbar (tools, colours, weights, `Fill`, `Undo`, `Redo`, `Finish` for polylines, `Done`) wraps to fit 390 px; the keys keep working. Touch and pen draw with pointer events; two-finger pinch is not used by the drawing tools.

Keys while a sketch is edited (the toolbar is up or a drawing tool is on): `Ctrl+Z` undo, `Ctrl+Shift+Z` (or `Ctrl+Y`) redo, `Delete` removes the selection, `Escape` cancels a drawing, then returns to `Select`, then deselects. In a text field the keys edit text. The global undo stack skips while a sketch is edited (see [undo.md](undo.md)). Undo covers add, delete, move and edit of the active sketch (100 steps).

## Attachments: what a shape is bound to in 3D

A shape is stored as fractions of the set camera's view plus the depth of a plane facing that camera. That plane is only right from the authored view: after an orbit the plane is seen obliquely and geometry at other depths slides out from under the outline. So every shape is either **attached** to something semantic in 3D, or **view-locked**. The fractions stay in every case (they are the view-locked form, and what the 2D view and the PDF burn-in use). The attachment model is shared with the BCF annotations and lives in `src/bcf/attach.ts` (types, reading, chip words, the view-lock rule), `src/bcf/surface.ts` (projection and inference, pure) and `src/markup/attachScene.ts` (rays of the live camera or of the set camera, the BVH).

| `attach.kind` | What it is |
| --- | --- |
| `elements` | A list of GlobalIds. The user's outline is projected onto them (when it projects cleanly) and they get the selection tint while the markup is selected. |
| `surface` | The outline's points were projected onto model surfaces. Each point is `{ e, p, l, n?, g? }`: the element (index into `guids`), the IFC point, its offset from the element's bounds centre (the `anchorPoint` element-frame mechanism: it follows the element in an exploded view or a revised model), and optionally the surface normal and lift. `fp` (bounds of the targets) lets a revised model project the points again onto reshaped elements, see "Reshaped elements". The IFC point is the fallback when the element has no frame. |
| `measurement` | A measurement link (`BcfMeasureLink`, the one a callout uses). |
| `penetration` | The pair of GlobalIds `{ mep, host }` of a penetration of the penetrations tool (its row ids change with every analysis, the pair is stable). |
| `region` | A 3D box (`min`, `max`, IFC frame, axis aligned) fitted to the depth range of the geometry inside the outline. Drawn as a revision-cloud-style box (scalloped edges) in 3D, correct from any angle. |
| `point` | A point in empty space (text boxes). |
| `lines` | World lines in the IFC frame: a foreign BCF viewpoint's `<Lines>`. |
| `none` | View-locked. |

Callouts, text, pointers and measurements keep their `anchor`; `attachmentOf` maps it one to one (element anchor to `elements`, point to `point`, measurement to `measurement`).

### Projection when a shape is finished

`addShape` casts a ray from the live camera through each point of the drawn path (rectangle corners, the ellipse polygon, the cloud outline, line ends, freehand points), densified so no segment is longer than 14 px and thinned to at most 320 rays. `BcfController.castRay` is the same test as a normal pick in the current view mode: hidden and isolated elements are skipped and click-through ghosts are passed first. Hits are cleaned (`cleanHits`):

- a miss, or a run of fewer than 3 hits between two depth jumps (a spike across a silhouette: the depth differs by more than 20 percent and 0.25 m and the two hits are not coplanar), is moved onto the surface plane of the nearest good hit along the stroke. The point stays on its own ray, so the authored view looks the same;
- when more than 30 percent of the points needed that, the stroke does not project cleanly and surface mode is not used;
- each point is lifted off the surface along its normal by 0.2 percent of its distance (5 mm to 5 cm) so the outline does not z-fight with the surface.

The projected outline is drawn on the shared SVG overlay from the 3D points through the live camera each frame (there is no depth test against the geometry). A cloud keeps its scalloped look: the scallops are computed in screen space from the projected path each frame.

### Inference order

1. A measurement (a dimension line within 12 px of the middle of the shape) or a penetration (a marker within 16 px) under the shape: `measurement` or `penetration` (the outline is kept as surface data when it projects cleanly).
2. At least 70 percent of the projected points on at most 5 elements: `surface`.
3. Else for closed shapes (cloud, rectangle, ellipse, polygon, highlight box): a grid of at most 140 rays inside the outline; at least 4 elements with 3 percent of the hits each and 0.15 m of depth spread (10th to 90th percentile): `region`, the box of all hit points padded by 2 cm and 2 percent. Lines (line, arrow, pen, polyline, marker) that project cleanly: `surface`.
4. Else `none`.

Thresholds are in `SURFACE` (surface.ts) and `VIEWLOCK` (attach.ts).

### The attachment chip

The selected markup shows a chip in the panel (inside its detail) and on the canvas next to the shape: `Attached to: 2 pipes · change` or `View-locked · change` (`#markup-attach-chip`, `[data-attach-chip]`). `change` opens a menu: `Elements (current selection)`, `Surface`, `Region`, `Measurement (pick)`, `Penetration (pick)`, `View-locked`. Surface and Region project the stored shape again from the set camera; Measurement and Penetration wait for a click on the dimension line or marker in the view (Escape cancels). A change is one history step: Undo brings the old attachment back. Anchored markups show the chip without `change`. A markup whose elements are missing from the loaded model is flagged `Detached` in the panel and drawn view-locked (never silently moved).

### 3D display rules

- **Attached:** always drawn in 3D at the target, never faded. While selected, the target elements get the selection tint of the viewer. A target that is hidden or isolated away: the shape is drawn dimmed with a `target hidden` hint, it does not float.
- **View-locked:** the rule compares the live camera with the set camera (`viewLockState`). View direction within 10 degrees and the eye within 20 percent of the scene scale: full strength. Fades smoothly (smoothstep) to nothing at 25 degrees or 50 percent of the scale, whichever is further along. Beyond that only a small pin at the centroid of the shape on its old depth plane is left; the pin fades in as the outline fades out. The scale is the larger of the model diagonal and the distance of the authored eye from the model centre, so an orbit of 10 degrees about the model is a shift of about 17 percent and the two criteria agree. Clicking the pin selects the markup and flies to the authored view (`restore`); its tooltip names the markup (`Cloud 3`).
- **Setting `Markup view-locked in 3D`** (Markup folder, `window.__xrayMarkup.viewLocked3d`, params section `markup.viewLocked3d`): `near view + pin` (default), `pin only` (a pin at all times) or `hidden`.
- **2D view, PDF, snapshot burn-in:** unchanged for view-locked markups: they render exactly as before from their set camera. Attached ones render from their 3D data projected through the camera of the page, which is the set camera.

### Older documents

A document from before attachments has no `attach` on its shapes. When it is opened, each such shape is projected from its set camera with the same inference: clean gives an attachment, else `{ kind: 'none' }` with the original fractions untouched. A document made on a different model is not migrated until its sets are moved to the loaded model (they are hidden under `Other models`; see "Which model an item belongs to"). The schema string stays `xray-markup-set/1`: `attach` is an optional field that older viewers ignore, and every shape written now carries one. Update view with `Shapes stay: on the screen` makes shapes view-locked (their fractions stay and the target would be elsewhere); `on the model` keeps attachments and re-bases the fractions as before. Moving an attached shape projects it again at its new place.

## Which model an item belongs to

Every markup set belongs to the model it was made on: `set.model` is a model identity (`name`, `elementCount`, `guidCount`, `guidHash`, see `ModelIdentity` in `src/markup/model.ts`; the same shape as the document's `model`). The rules are pure and tested (`src/markup/scope.ts`, `tests/markup-scope.test.ts`) and shared with the BCF topics ([bcf.md](bcf.md)). On every model change (the `onModel` hook of the plugins, which runs for the Sample Projects menu, the file loader and drops alike) each set is compared with the loaded model by `compareModels`:

| Result | What the viewer does |
| --- | --- |
| `same` | Listed with the current sets and drawn. |
| `revised` (same name, other elements: a new revision) | Listed and drawn, tagged `revised model`. Attachments are checked against the new elements (see "Reshaped elements"): targets that moved or changed are followed, targets that no longer fit are detached (view-locked) and flagged `Detached ... The model is a revision: this may already be designed`. |
| `unknown` (a file that names no model) | Listed and drawn, tagged `model unknown`. |
| `different` | Hidden: not active, nothing of it on the overlay or the model (no outline, pin, tint, highlight), not in the sets grid, not exported by default. |

- **Panel.** The Sketches list shows the sketches of the loaded model only. A collapsed `Other models (n)` group (`details[data-other-models]`) below it lists the others, grouped per model (`Made on fzk-haus (82 elements). Hidden on this model.`). Per set: `Open` (shows it on purpose, until the model changes; it stays marked as another model and its targets are not here), `Move to this model` and `Delete set` (two clicks).
- **Move to this model** sets `set.model` to the loaded model and runs the attachment migration again: shapes without an `attach` (older files) are inferred on this model, targets this model lacks show detached (view-locked, nothing is deleted); the status line says how many. Undo does not cover it (it is a change of ownership, not of the set's contents).
- **Persistence.** Sets are session data (no browser storage, see Limitations), so there is nothing to restore into another model's view. The JSON and PDF carry `model` on each set (`null` when unknown) next to the document's `model`; a file from before this field gives its sets the document's model, and a file with neither is `unknown`. If sets are ever stored in the browser they must be keyed by that identity and must not be restored into a different model.
- **Import.** `Open file` / drop / `importJson` compares each set's model with the loaded one. Sets of another model are kept under `Other models`, their view is not restored, and the report and the status line warn (`ImportReport.match` is the worst result, `warnings` say where the sets went). The same warning is shown as a message on screen as for a revised model. Older shapes are migrated only for the sets that are shown (the others when they are moved).
- **Federated loads.** Several IFC files opened together are federated into one model of the viewer (one name `file:<first> +N more`, one element list, `GlobalId` clashes renamed with `~N`). An item belongs to that federation as a whole, with the identity of the whole; there is no per-file ownership. Opening the same files again gives the same identity (`same`), opening one file of them alone is `different` (another name).
- **Scripting.** `list()` returns the sets of the loaded model, each with `scope` (`same`, `revised`, `unknown`, `different`) and `model` (name); `list({ all: true })` also the hidden ones. `otherModels()` groups the hidden sets per model; `openOther(id)`, `moveToModel(id)` (returns `{ migrated, attached, detached }`) and `deleteSet(id)` do what the panel buttons do.

## Reshaped elements: following a revision

A `surface` outline stores each point with the element it landed on and its offset from that element's bounds centre (`l`). That follows an element that a revised model **moves**; an element that is **reshaped** (a longer wall, a re-routed pipe) has a new centre and the outline would float off the surface. So a surface outline also stores, additively (all optional, older files without them still read and draw as before):

- `pts[].n`: the unit surface normal at the point (IFC frame, facing the authoring camera) and `pts[].g`: how far it was lifted off the surface (m);
- `fp`: the bounds of each target element (`guids` order, IFC frame, `[minx, miny, minz, maxx, maxy, maxz]`) at attach time.

When a set or an annotation is drawn on a model whose identity is `revised`, or whose element bounds differ from `fp` (also on `same`: a re-export with the same GlobalIds), the outline is projected again (`src/bcf/reproject.ts`, pure; the per-element BVHs of the model back it, `src/markup/reprojectScene.ts`):

1. **Expected place** (needs `fp`). Per axis: a side of the bounds that did not move keeps the point where it was (a wall lengthened at one end keeps the outline where it was drawn); both sides moved by the same amount move the point with them (a moved element); anything else stretches the point with the bounds. Without `fp` the old rigid follow (current bounds centre plus `l`) is tried first, then the stored IFC point `p`.
2. **Landing.** A ray is cast from a tolerance above the point along the stored normal (the authoring camera direction for data without `n`) onto the triangles of that element only; a miss falls back to the nearest point of its triangles. The point lands when it ends within the tolerance of where it was expected: 3 percent of the element diagonal, between 5 cm and 30 cm, plus the lift. It is placed on the surface again at its lift.
3. **Detached.** When more than 30 percent of the points cannot land, or an element is gone, or it moved further than max(3 m, 1.5 x its old diagonal) (it counts as replaced, so a markup does not chase it across the building), the outline is detached: drawn view-locked (the near-view rule, then the pin) and flagged in the chip and the panel, never floating. Up to 30 percent of the points that cannot land stay where they were expected.

The result is cached per model load and per outline (`SurfaceResolver`): nothing is cast again per frame, the cache is dropped when another model loads or an item is moved to the model. The stored data is not changed (go back to the original revision and the outline is as it was); PDF pages and BCF snapshot burn-ins use the same re-projection. Thresholds are in `REPROJECT` (reproject.ts).

## View behaviour when the camera moves

View-locked shapes stay drawn on their depth plane in the 2D view and the PDF (see above for 3D). When the camera drifts from the set's view (more than 4 degrees, 5 percent of the distance, or 8 percent zoom) a `Return to markup view` button shows at the top of the view, and anchored markups draw faded. Attached shapes do not fade: they are in 3D.

A sketch with at least one tied drawing (an attachment of kind `surface`, `elements`, `measurement`, `penetration`, `region` or `point`) can leave the authored camera: `3D · Plan · Section` shows it from above or in a vertical cut, and the attached drawings follow. See [issues.md](issues.md), "Plan and Section views".

## Export

### PDF

Landscape A4 or Letter (`Markup page size`), Helvetica (WinAnsi; accents kept, symbols such as arrows get an ASCII spelling, anything else `?`), JPEG pictures (DCT, quality 0.9). Per set:

1. Page 1: header (project or model name, date, set title, author, counts), the model view at the set's camera **without** markups, and the `How to get back to this view` block (3 steps, plus a clickable link when the page is served over http or https and the share link is at most 1800 characters).
2. Page 2: the same view with the markups burned in and numbered (the same layout code as the screen: `drawOps`).
3. Pages 3 and up: the comment table (number, type, text, status, author, assignee and due date, comments), repeating its header; long rows continue on the next page.

Picture resolution (`Picture quality` in the sketch detail, `Markup PDF resolution (dpi)` in the panel, params `markup.pdfResolution`): `screen`, `150`, `200` (default) or `300` dpi. The picture is rendered off screen by the viewer's own renderer, so the X-ray look (ghosts, edges, passes) is the screen's: for the export the drawing buffer is enlarged with `setPixelRatio` and `resize()` (every pass follows the buffer size), two frames are rendered, the pixels are copied into a 2D canvas in the same task, and the buffer goes back, so the canvas does not flicker. The width follows the page: the picture is fitted into the page box (770 x 400 pt on A4) and gets `width in inches x dpi` pixels (about 2000 px for a wide window at 200 dpi, 3000 px at 300 dpi). The picture keeps the aspect of the window, which is the aspect of the set camera, so the shapes are exact. The size is clamped to the graphics card (`maxTextureSize`, `MAX_RENDERBUFFER_SIZE`, at most 8192 px a side and 36 million pixels); when it is lowered the status line and `info.note` of `exportPdf` say so. Markups are burned in with sizes multiplied by the picture to screen factor, so they look as on screen. `exportPdf()` returns `info` (`resolution`, `pictureWidth`, `pictureHeight`, `note`, `ms`).

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
    "model": { "name": "fzk-haus", "elementCount": 107, "guidCount": 107, "guidHash": "<16 hex digits>" },
    "markups": [
      { "id": "m...", "number": 1, "kind": "cloud", "colour": "red", "weight": 2, "fill": false, "text": "Clash", "status": "open",
        "shape": { "points": [[0.2, 0.2], [0.5, 0.4]], "depth": 12.3 }, "author": "...", "created": "...",
        "assignee": "Ben", "due": "2026-12-24", "comments": [ { "id": "c...", "author": "...", "date": "...", "text": "..." } ] },
      { "id": "m...", "number": 2, "kind": "callout", "text": "Move pipe", "offset": [0.1, -0.09],
        "anchor": { "kind": "element", "point": [1, 2, 3], "elementGuid": "<IfcGuid>", "local": [0.1, 0, 0] }, "...": "..." } ] } ] }
```

- `camera` and every `anchor` are in the IFC frame (metres, Z up) like the BCF side file; shape points are fractions of the view of `camera` (x right, y down) at `depth` metres. `view.camera` is the viewer-frame camera that `Restore view` uses. The saved view leaves out `classify`, `bcf`, keys and the other sections views never store, so a file holds no endpoint or secret (checked by the smoke).
- Model identity: `guidHash` is a 64-bit hash (two FNV-1a runs) of the sorted GlobalId list. On import the viewer compares it with the loaded model: `same`, `revised` (same file name, other elements), `different`, `unknown` (file without identity). The document's `model` is the model of the file; each set also carries its own `model` (`null`: unknown), so a file with sets of several models stays correct. See "Which model an item belongs to".
- Kinds: `cloud` (2 points: box; 3 or more: closed outline), `rect`, `ellipse`, `highlightBox` (2 opposite corners, or 4 corners as a quad after `Update view` from a rotated camera), `line`, `arrow` (2 points), `polyline`, `polygon`, `highlight`, `pen`, and the anchored `text`, `callout`, `pointer`, `measure`.
- Versioning: `xray-markup-set/1` is read; a newer major version is refused with a message. Unknown fields are dropped, ids and numbers are filled in, a markup that cannot be read is skipped and listed (`bad`), never silently.

## Getting back to the marked-up view

Open the same model, then drop the PDF or the JSON on the page (a lone `.pdf` or `.json` dropped on the viewer is a markup file; models are `.ifc` / `.glb`), or `Open file` in the Sketches segment. The view comes back (camera, section, hides, colours, selection, preset) and the first set is active with all its markups. The status line and `window.__xrayMarkup.importJson()` report: sets and markups opened; `unknownGuids` (GlobalIds of anchors, linked measurements or the view that the model lacks: the markups stay at their stored 3D points, view parts for missing elements are skipped and counted); `match` and a warning for a revised or different model. Sets made on another model are kept under `Other models` and not restored (see "Which model an item belongs to"). A set with an id already in the session is replaced, others are added with a unique title. A PDF not made by this tool, or one re-saved by another tool into object streams, says it carries no markup data; use the JSON.

## Raise as issue (formerly Convert to BCF topic)

`Raise as issue` ([issues.md](issues.md)) restores the view, then makes an issue whose viewpoint links to the sketch by id. The drawing on the viewpoint is the projection of the sketch described below (not a copy that drifts): it is rebuilt on every edit and before export. The older conversion, kept here for the mapping of kinds, restores the view, then creates a BCF topic (title = set title, status Open when any markup is open) with a snapshot and viewpoint, callouts, text boxes and pointers as BCF `callout`, `note`, `arrow` annotations (element anchors keep their element), rectangles and highlight boxes as BCF rectangles, every other shape as a BCF freehand line (clouds and polygons closed, ellipses sampled, arrows with a head), measurements as a callout with the length, and the comments as topic comments ("3. text"). Both workflows then share data: export from the BCF tool as usual. Needs the BCF tool.

## Scripting

```js
const m = window.__xrayMarkup;
const set = m.create('Level 1 routing');                       // from the current view
m.add({ kind: 'cloud', points: [[400, 200], [560, 320]] });     // canvas CSS pixels (drag corners); 'fractions' stores view fractions
m.add({ kind: 'callout', at: [480, 260], text: 'Move pipe' });   // click position on the model
m.add({ kind: 'polygon', points: [[...], ...], colour: 'blue', fill: true });
m.update(id, { text: 'Move pipe' }); m.setNote(set.id, 'Duct crosses the beam'); m.undo(); m.redo();   // comment() and status, assignee, due no longer change a sketch
await window.__xrayIssues.raise(set.id);                         // Raise as issue: returns the issue guid
const pdf = await m.exportPdf({ ids: [set.id], page: 'A4', download: true });   // { name, bytes }
const json = m.exportJson({ ids: [set.id] });                    // { name, bytes }
await m.importJson(text);  await m.importFile(fileOrBlob);        // ImportReport { ok, sets, markups, unknownGuids, match, warnings, skipped }
m.restore(set.id, { animate: false });  await m.toBcf(set.id, markupId?);
m.updateView(set.id, { keep: 'model' | 'screen' });                // { shapes, moved, kept }; undoable with m.undo()
m.pdfResolution = 300;  (await m.exportPdf({ resolution: 150 })).info;  // { resolution, pictureWidth, pictureHeight, note, ms }
m.list(); m.get(id); m.hitTest(x, y); m.away; m.page = 'Letter';
m.list({ all: true });  m.otherModels();                           // sets of other models (hidden): scope, model name; grouped per model
m.openOther(id); m.moveToModel(id) /* { migrated, attached, detached } */; m.deleteSet(id);
```

The saved views plugin gained `capture()`, `restoreView(view)` and `shareUrlFor(view)` (a view object that is not in the Views list); `window.__xrayBcf` is used for the conversion.

## Files and tests

- `src/markup/model.ts` (types, JSON document, identity, sanitising), `geometry.ts` (scallops, ellipse, simplify, hit distances), `layout.ts` (draw operations; reuses `layoutAnnotation`, `shapePointWorld`, `shapeFraction`), `history.ts` (undo stack), `pdf.ts`, `report.ts`, `controller.ts`, `view.ts` (overlay layer, pointer and key input), `ui.ts` (drawer, drop), plugin `src/plugins/markup.ts`. `annotate.ts` gained a `style` override and a `blend` operation (multiply) for the highlighter.
- Tests: `tests/markup-pdf.test.ts` (structure, xref offsets, stream lengths, escaping, embedded file round trip, Flate), `markup-report.test.ts`, `markup-model.test.ts` (schema round trip, mismatch, identity), `markup-geometry.test.ts` (scallops), `markup-history.test.ts`.
- Model scope and revisions: `tests/markup-scope.test.ts` (the decision per `compareModels` result, the `Other models` grouping, set and topic identity in the files, both controllers on a model change), `tests/markup-reproject.test.ts` (a box lengthened, thickened, moved, removed and moved far away; 30 percent rule; fallback normals; the cache); smoke `SMOKE_PORT=5707 node bench/smoke-markup-scope.mjs` (items on fzk-haus, building shows no old pin or shape and `Other models (1)`, back on fzk-haus they are drawn, Move to this model, Open, a file made on another model, a different IFC from the file loader, Delete, zero console errors).
- Attachments: `tests/markup-attach.test.ts` (inference on a synthetic scene of boxes, local-frame follow, the fade and pin rule, migration, BCF Lines, Components and side file round trip); smoke `SMOKE_PORT=5703 node bench/smoke-markup-attach.mjs` (cloud around an element attached and still on it after a 60 degree orbit, view-locked cloud faded at 15 and a pin at 60 degrees, the pin flies back, Change and Undo, BCF Lines and selection, both pointer modes, phone). Screenshots `bench/markup-attach-authored.png`, `markup-attach-orbited.png`, `markup-viewlocked-pin.png`.
- Smoke: `SMOKE_PORT=5710 node bench/smoke-markup.mjs` draws every tool on fzk-haus, comments, undo and redo, exports PDF and JSON, validates the PDF with pypdf / pdfinfo / pdftoppm (when installed), reloads and drops the PDF, opens the JSON, tries another model, converts to BCF, phone layout with touch and pen. Screenshots `bench/markup-*.png`. The software renderer of headless Chromium runs at 2 to 3 frames per second, so the run takes 15 to 30 minutes.

## Limitations

- Attached outlines are projected on the overlay with no depth test: an outline on a wall is still drawn when another element hides that wall from the new camera. Surface hits use the geometry as it was when the shape was finished; a revised model is followed by projecting the points onto the current triangles of the elements ("Reshaped elements"), which needs the normals and bounds stored since then: older files follow the bounds centre only (and are detached when an element is gone). A region is not re-fitted on a revised model.
- A region is an axis-aligned box in the IFC frame (not an oriented box).
- `Measurement` and `Penetration` pick on the screen; penetration rows exist only after the penetrations tool ran.

- Pictures have the aspect of the window (that of the set camera); a very tall window gives a narrow picture on a landscape page. Very large pictures are lowered to the graphics card limits (said in the status line); there is no tiled render.
- A Markup set does not store a thumbnail in the JSON; the PDF pictures are the thumbnails of the report.
- Sets are session data (no browser storage): export to keep them. Sets of other models are kept for the session only too; delete them or move them to the model.
- Scallop size is fixed by weight; a shape cannot be resized by handles (delete and redraw, or undo).
- The PDF reader finds the embedded JSON in files written by this tool; a PDF re-saved by an editor that rewrites objects into object streams loses it from this reader (the JSON file still works).
- Orthogonal views use the viewer's approximation (see saved-views.md).
