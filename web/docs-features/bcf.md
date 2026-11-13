# BCF issues (BIM Collaboration Format)

Open, review, create and export BCF topics. Reads BCF 2.0, 2.1 and 3.0; writes 2.1 (default) and 3.0. A topic can carry viewpoints (camera, selected elements, hidden elements, colours, clip planes) and a snapshot, and the viewer applies them to the model. Topics are pinned to a 3D point, and viewpoints carry annotations (callouts, notes, arrows, linked measurements, rectangles and freehand lines); see "Pins and annotations".

For internal coordination without a topic (clouds, highlights, shapes, a PDF with a comment table, a JSON file that restores the marked-up view) see [markup.md](markup.md); a markup set converts to a BCF topic (`Convert to BCF topic`).

Where: the `BCF` tool in the action panel (a drawer), the `BCF` folder in the parameter panel, and the command palette. Scripting: `window.__xrayBcf`.

## Workflow

1. `Open BCF` (drawer, panel or palette), or drop a `.bcf` / `.bcfzip` anywhere on the page. Opening replaces the loaded topics; if you have unsaved topics of your own the file is merged in instead (same topic Guid: the file wins).
2. The drawer lists topics with status and priority chips. Filter by status, search title, description, assignee, labels and comments. Select a topic to see its snapshot, description, comments and viewpoints.
3. `Apply` on a viewpoint moves the camera, selects its elements, hides and colours elements and sets clip planes. The status line says what was applied and what was skipped (unknown GlobalIds are counted, not silently dropped).
4. `Clear viewpoint` undoes what BCF changed: the elements it hid (and only those: elements you hid yourself stay hidden), its colours and its clip planes (unless the section tool took the planes over since; a section box or plane that was on before the viewpoint comes back). Camera and selection stay where they are.
5. `New topic` (or `Create topic from view`) asks for title, description, type, status, priority, labels, assignee and author, then stores a topic with a snapshot and a viewpoint of the current view. The author is remembered (localStorage `xray.bcf.author`) and is also the author of comments.
6. `Add comment` on any topic, optionally attaching the current view as a new viewpoint.
7. `Place pin`, `Add callout`, `Add note`, `Add arrow`, `Add rectangle`, `Draw freehand`, `Link measurement` (the `Markup` section of a selected topic) pin the topic and annotate its viewpoint; see below.
8. `Export 2.1` / `Export 3.0` download a `.bcfzip` of every topic in the list (loaded and created).

Panel entries (`BCF` folder): `Open BCF`, `Create topic from view`, `Export BCF 2.1`, `Export BCF 3.0`, `Clear viewpoint`, read-only `BCF status`. Palette actions, without default keys: `bcf.open`, `bcf.create`, `bcf.export` (uses the default export version), `bcf.clear`. The params document has a `bcf` section with the default author and the default export version.

## Pins and annotations

A topic is pinned to one 3D point, and each viewpoint can carry annotations. The drawer's `Markup` section of the selected topic holds the controls; `Show pins` in the drawer bar turns the pins on and off.

- **Pin.** A numbered marker drawn on the shared overlay. The number belongs to the topic: a new topic gets the next free number (one more than the highest in use) and keeps it, also when topics before it are removed or the list is filtered or sorted; it is stored in the side file (`pinNumber`). Topics from other tools (no side file) get the next free numbers in list order when the file is opened; when a merged file brings a number that is already in use, the incoming topic gets the next free one. Behind geometry it fades and gets a dashed rim (a ray against the merged-geometry BVH from the camera; hidden and ghosted elements, alpha below 0.5, do not hide it); off screen, or under the status bar or an open tool drawer, it becomes a marker at the edge of the free view pointing towards it. A pin whose point lies under the gizmo or a legend is drawn beside it with a dashed leader line to the point (or as an edge marker when there is no free spot within 160 px); edge markers keep out of the gizmo and the legends too (reserved rects of the overlay, `src/ui/reserved.ts`). Click a pin to select its topic and apply its first viewpoint. Pins show while the BCF drawer is open, for the topics that pass the drawer filter (and the selected one); the selected topic's pin is blue. With the drawer closed only the pin of the topic whose viewpoint is applied shows, and `Clear viewpoint` removes it too, so pins never linger over the model outside a review. New topics are pinned to the centre of the bounds of their elements (the selection, or `globalIds`), else to the surface in the middle of the view; tick `Click the model to place the pin` in the dialog, or click `Place pin`, and the next click on the model sets it. `createTopics` items with a `location` are pinned there.
- **Annotations.** `Add callout` (a leader line from an element to a text box), `Add note` (a text box at a free 3D point) and `Add arrow` (an arrow pointing at an element, the text is optional) apply the topic's viewpoint and take the next click on the model as the anchor; type the text first in the box above the buttons. An element anchor (callout, arrow, a pin on an element) also stores its offset from the bounds centre of the element (`local`), so it follows the element: in the exploded view (the cinematic explode offsets, `renderer.elementOffset`) and in a revised model where the element moved. A text box that would fall under the gizmo, the status bar, an open drawer or a legend moves to the nearest free spot (a note then gets a dashed leader line).
- **Rectangles and freehand lines.** `Add rectangle` and `Draw freehand` apply the topic's viewpoint; then drag on the view (the orbit does not move while you draw; Escape cancels). The shape is stored in the view of the viewpoint camera (the snapshot camera): its points are fractions of the view width and height, on a plane through the surface under the middle of the shape (`depth`, metres along the view direction). With the viewpoint camera the shape sits exactly where it was drawn; from another camera it is drawn on that plane in 3D, so it stays on the model area it marks. The text typed first becomes a label above the top-left corner. Shapes are burned into the snapshot like callouts (pixel for pixel when the snapshot camera is known). A viewpoint with only an orthogonal camera and no snapshot camera cannot take shapes. `Link measurement` lists the measurements of the measure tool; a click copies the measurement (both end points, distance, label, element GlobalIds) into a callout, so it survives without the measure tool and draws its own dimension line. The length shows in the unit of the measure tool (`m` or `mm`, its `units` setting) on screen and in the burned snapshot, and follows that setting when it changes; the stored `distance` is metres. An element-to-element measurement moves its end points with the exploded elements. Annotations draw while their viewpoint is applied and follow the camera. Drag a text box to move it, edit the text in the list (double click a box to jump there), `Delete` removes it; a click on a list row highlights it and applies its viewpoint. Escape cancels a placement (a second Escape closes the drawer).
- **Picking** uses the measure tool's ray test (first surface, hidden elements skipped) and passes ghosted elements first, so the click lands on what is drawn solid; placing clicks never change the selection.

### Attachments and 3D lines

Rectangles and freehand lines carry an `attach` like a markup shape (`src/bcf/attach.ts`, see [markup.md](markup.md), "Attachments"): `surface`, `region`, `measurement`, `penetration`, `elements`, `lines`, or `none` (view-locked). `addShape` projects the drawn path from the live camera onto the model with the same inference as the Markup tool; an annotation from an older file has no `attach` and is projected from its viewpoint camera when the viewpoint is applied (clean gives an attachment, else it stays view-locked with its fractions). Attached shapes draw in 3D; view-locked ones follow the same fade and pin rule (the pin returns to the viewpoint) and the `Markup view-locked in 3D` setting.

Export mapping (`viewpointWithMarkup`, write.ts):

- the target GlobalIds of attached shapes join the viewpoint `Components/Selection`, merged with what is there (other tools highlight them; the viewer does not select them again on apply, see `markupSelection`);
- `surface` shapes (and the outline of `elements`, `measurement`, `penetration`) are written as `<Lines>`: the projected path as 3D segments in IFC coordinates; `region` shapes as the 12 edges of the box. The viewpoint's own lines stay; lines of an earlier export of ours are replaced, not doubled (matched by rounded endpoints);
- the snapshot PNG keeps the burn-in as before;
- the side file carries the full `attach` per annotation (surface points with their local frame, region, links), so a round trip through this viewer is lossless.

Import of a foreign viewpoint with `<Lines>` and no annotations of ours: when the viewpoint is applied it shows one `lines` annotation, the segments drawn as 3D world lines in the IFC frame. Its lines are in the viewpoint already and are not written twice.

### Where the markup is stored

BCF 2.1 and 3.0 have no field for a pin or annotations. The viewer writes a side file `<topic folder>/xray-markup.json` (src/bcf/sidecar.ts) and leaves the BCF XML as the schemas define it:

```json
{ "format": "xray-bcf-markup", "version": 1, "frame": "ifc", "units": "m", "topic": "<guid>", "pinNumber": 3,
  "pin": { "position": [x, y, z], "elementGuid": "<IfcGuid>", "local": [dx, dy, dz] },
  "viewpoints": { "<viewpoint guid>": {
    "annotations": [{ "guid": "...", "type": "callout", "text": "...", "offset": [0.1, -0.09],
                      "anchor": { "kind": "element", "point": [x, y, z], "elementGuid": "<IfcGuid>", "local": [dx, dy, dz] } },
                    { "guid": "...", "type": "rect", "text": "...", "offset": [0, 0], "anchor": { "kind": "point", "point": [x, y, z] },
                      "shape": { "points": [[0.21, 0.3], [0.48, 0.62]], "depth": 12.4 },
                      "attach": { "kind": "surface", "surface": { "guids": ["<IfcGuid>"], "closed": true, "pts": [{ "e": 0, "p": [x, y, z], "l": [dx, dy, dz] }] } } }],
    "markupSelection": ["<IfcGuid>"],
    "snapshotView": { "position": [...], "direction": [...], "up": [...], "fov": 42, "aspect": 1.78 },
    "baseSnapshot": "xray-<viewpoint guid>-base.png" } } }
```

- Points are IFC project coordinates, the same mapping as the viewpoint cameras (below). Text box offsets are fractions of the view height, so they scale with the snapshot. A measurement anchor holds `measurement: { kind, a, b, distance, label, elementGuids }`. `local` (pins and element anchors) is the anchor minus the element's bounds centre, IFC frame. `type` is `callout`, `note`, `arrow`, `rect` or `freehand`; the last two carry `shape` (a rectangle has its 2 opposite corners). `markupSelection` lists the selection entries that are there only because annotations point at them (written whenever the viewpoint has annotations; a side file without it is read as "every annotated element that leaves the selection non-empty"). The additions are optional fields of version 1; older readers ignore them.
- Why a side file: the topic folder may hold other files (BCF 3.0 documentation, "Topic folder structure"), and readers open only the files that markup.bcf names, so other tools ignore it. A `Label` such as `pin:x,y,z` was not used: tools show labels to people and 3.0 lists them in `extensions.xml`. The official XSD validation (tests and smoke) still passes, and IfcOpenShell's `bcf-client` reads the exports (bench/smoke-bcf-markup.mjs with `BCF_CLIENT_PYTHON`).
- What other tools see: the snapshot named in markup.bcf of a viewpoint with annotations has them and the pin burned in (a pin alone leaves the snapshot untouched, so pinned topics cost no second image) (the same layout code as the overlay, src/bcf/annotate.ts, projected with the camera that took the snapshot), and the annotated elements are in the viewpoint `Selection`, so they highlight. The occlusion fade of the burned pin and anchors uses what was hidden or see-through when the snapshot was taken (kept in memory for viewpoints made in the session, else the hidden elements of the viewpoint's Visibility), not the hides of the moment of export. The clean snapshot is stored beside it as `baseSnapshot`; on import the viewer keeps the clean one, so a re-export burns the markup once.
- A side file the viewer cannot read only adds a warning; invalid annotations are dropped one by one with a warning. Import restores pins and annotations exactly (unit test and smoke test).

## Coordinates

BCF uses IFC project coordinates (metres, Z up). The viewer uses metres, Y up, shifted by the sidecar `originShift` (IFC frame). The converter maps an IFC point `p` to the viewer as `v = (p.x - s.x, p.z - s.z, -(p.y - s.y))`; directions only rotate, `(x, y, z) -> (x, z, -y)`. BCF cameras, selections and clip planes go through exactly this mapping (src/bcf/model.ts), in both directions; the unit tests check round trips and the mapping against a real fzk-haus element.

## What a viewpoint does

| BCF part | Applied as |
| --- | --- |
| PerspectiveCamera | Camera position, orbit target and vertical field of view. The orbit target is the camera position plus the view direction times the distance to the middle of the chord through the model bounds (the centre depth when the view misses the model). If the viewer window is narrower than the viewpoint's `AspectRatio`, the field of view is widened as the BCF 3.0 guidance describes. |
| OrthogonalCamera | Approximated by a perspective camera placed so its vertical extent at the model depth equals `ViewToWorldScale`. The status line says so. |
| Selection | `app.selectIds` by GlobalId. No selection in the viewpoint clears the selection. Elements in the selection only because annotations point at them (`markupSelection`) are not selected: as focus they would draw solid over what the viewpoint is about. They get the selection tint (the same yellow mix as a selected element) as a temporary colour, keep the x-ray look (they ghost when they block the view), and lose the tint on `Clear viewpoint`. The status line counts them as `annotated highlighted`. |
| Visibility | Order as the spec: `DefaultVisibility`, then `ViewSetupHints` (spaces, openings), then `Exceptions`. `DefaultVisibility` false hides every element except the exceptions; true hides the exceptions. Applied through `settings.overrides.userHides`. If `DefaultVisibility` is false and none of the listed visible components exists in the model, visibility is skipped (it would blank the view) and the status line says so. |
| Coloring | Temporary colour override of the listed elements, restored on clear. The alpha byte is ignored. |
| ClippingPlanes | `renderer.setClipPlanes` when the renderer provides it (typeof checked), otherwise reported as skipped. A BCF `Direction` points into the clipped (invisible) half-space; the renderer's normal points into the kept half-space, so the normal is the negated direction. |
| Lines, Bitmaps | Not shown; counted in the status line. |

Applying a viewpoint first clears the previous one. Viewpoint roll is ignored (the orbit camera keeps Y up).

## Authoring details

- Snapshot: `renderer.render()` then a canvas read in the same task (no `preserveDrawingBuffer`), downscaled so the longer side is at most 1280 px (the 3.0 guide asks for at most 1500).
- Viewpoint from the view: camera (position, direction, up, field of view, aspect), the selection, the user's hides as visibility exceptions (the shorter list goes into `Exceptions`: few hides give `DefaultVisibility` true, few visible elements give false), and the current clip planes through `getClipPlanes()` when present.
- Elements whose GlobalId is not a valid 22 character IfcGuid (the synthetic demo models) are left out of selections and visibility lists, since the schema would reject them. A federation suffix `~n` is stripped.
- 2.1 limits honoured on write: field of view clamped to 45..60 (the 2.1 schema), no `AspectRatio`. 3.0 gets `AspectRatio`, lower-case guids, `extensions.xml`, and non-empty required strings (`TopicType` defaults to `Issue`, `TopicStatus` to `Open`).

## Scripting

```js
const bcf = window.__xrayBcf;
await bcf.load(fileOrArrayBuffer);               // { merge: true } to add to the current topics
bcf.topics;                                      // BcfTopic[] (live)
bcf.applyViewpoint(topicGuid, viewpointGuid?);   // { ok, applied[], skipped[], unknownGuids, status }
bcf.clearViewpoint();                            // number of hidden elements restored
bcf.createTopic({ title, description, type, status, priority, labels, assignedTo, author, snapshot, globalIds, camera, pin });
bcf.createTopics([{ title, description?, globalIds: [...], camera?: { position, target }, labels? }], { snapshot? });
bcf.addComment(topicGuid, 'text', { author, viewpoint });
bcf.setPin(topicGuid, [x, y, z] | null, elementGuid?);   // viewer coordinates
bcf.addAnnotation(topicGuid, { type: 'callout' | 'note' | 'arrow', text, anchor: { kind: 'element' | 'point', point, elementGuid } }, viewpointGuid?);
bcf.addShape(topicGuid, 'rect' | 'freehand', [[x, y], ...], text?);   // canvas CSS pixels, as a drag draws it
bcf.pinNumber(topicGuid);                                // the stable pin number
bcf.linkMeasurement(topicGuid, measurementId, text?);    // a callout from a measure tool measurement
bcf.updateAnnotation(guid, { text, offset }); bcf.removeAnnotation(guid); bcf.annotations(topicGuid);
bcf.startPlacement('pin' | 'callout' | 'note' | 'arrow' | 'rect' | 'freehand', topicGuid, text?); bcf.cancelPlacement(); bcf.pinsVisible = false;
await bcf.composeSnapshot(topicGuid, viewpointGuid?);   // PNG bytes with the markup burned in, as exported
const bytes = await bcf.exportZip('3.0');        // Uint8Array; bcf.download('3.0') also saves the file
```

`createTopics` builds one topic per item with a viewpoint that selects the listed elements and frames them (camera from their bounds when `camera` is not given; `camera` is in viewer coordinates). It selects and frames each item in turn to take the snapshots and restores your camera and selection afterwards. Snapshots default to on for up to 20 topics; pass `{ snapshot: true | false }` to override.

## Files and tests

- `src/bcf/sidecar.ts` the markup side file, `annotate.ts` pure markup layout (draw operations for the overlay and the snapshot canvas, snapshot camera projection), `pins.ts` the live overlay, placement and dragging; `src/measure/current.ts` read-only list of the measure tool's measurements.
- `src/bcf/zip.ts` zip reader and writer (stored and deflate through `CompressionStream`, CRC32, directory entries), `xml.ts` small strict XML reader (used instead of `DOMParser`, so browser and node tests behave identically), `parse.ts`, `write.ts`, `plan.ts` (pure viewpoint planning and capture), `controller.ts`, `ui.ts`; plugin `src/plugins/bcf.ts`.
- Tests `tests/bcf-*.test.ts`, fixtures `tests/fixtures/bcf` (hand written 2.1 and 3.0 archives as folders, the official XSDs under `xsd/`, the BCF documentation under `docs/`). `tests/fixtures/bcf/validate_xsd.py` validates unpacked archives against the XSDs with lxml; `tests/bcf-xsd.test.ts` runs it and skips when python3 or lxml is missing.
- `bench/smoke-bcf.mjs` (SMOKE_PORT=5333) runs the browser workflow and writes `bench/bcf-drawer.png`.
- `tests/bcf-markup.test.ts`: side file round trip (2.1 and 3.0), burned and clean snapshot files, annotated elements in the selection, tolerant reading, the IFC mapping against a three.js camera projection, the burn-in layout and canvas painting, XSD validation with markup present.
- `tests/bcf-markup-fixes.test.ts`: reserved rects (pins and boxes out of the gizmo), element-local anchors and explode offsets, measurement units, shapes (fractions to 3D and back, direct burn-in), pin number, `local`, shapes and `markupSelection` through the side file. `bench/smoke-fixes-w7.mjs` (SMOKE_PORT=5714) drives them in the browser (rectangle by mouse drag, the import-and-apply selection tint, pin numbers across an import).
- `bench/smoke-bcf-markup.mjs` (SMOKE_PORT=5623): topic with a clicked pin, callout on an element, linked measurement, note, text box drag, Escape, export 2.1 and 3.0 (XSD), reload, import, exact compare, pin click; writes `bench/bcf-markup-live.png`, `bench/bcf-markup-snapshot.png` (the exported snapshot) and `bench/bcf-markup-reimport.png`.

## Limitations

- Orthographic cameras are approximated; viewpoint roll, lines, bitmaps and colour alpha are ignored.
- Elements are matched by GlobalId only (no IfcProject / file matching); a topic made for another model applies its camera but selects nothing, and says how many ids were unknown.
- No editing of existing topic fields besides status and added comments; no zip64; BimSnippet files, documents and header files are carried through unchanged but not shown.
- Selection and exception lists over 1000 components work but the BCF guide recommends keeping them short.
- Markup: other tools see the burned snapshot and the selection only; they drop the side file when they rewrite the archive. Notes (free points) and point-to-point measurements do not follow exploded elements; the burned snapshot draws anchors at the unexploded elements even when the snapshot was taken in the exploded view. For imported viewpoints the burn-in occlusion fade knows the hidden elements of the Visibility but not which elements were ghosted. Shapes drawn from a camera far from the viewpoint camera are mapped onto the shape plane, so they look skewed when seen from the side.
