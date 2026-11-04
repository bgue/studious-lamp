# BCF issues (BIM Collaboration Format)

Open, review, create and export BCF topics. Reads BCF 2.0, 2.1 and 3.0; writes 2.1 (default) and 3.0. A topic can carry viewpoints (camera, selected elements, hidden elements, colours, clip planes) and a snapshot, and the viewer applies them to the model. Topics are pinned to a 3D point, and viewpoints carry annotations (callouts, notes, arrows, linked measurements); see "Pins and annotations".

Where: the `BCF` tool in the action panel (a drawer), the `BCF` folder in the parameter panel, and the command palette. Scripting: `window.__xrayBcf`.

## Workflow

1. `Open BCF` (drawer, panel or palette), or drop a `.bcf` / `.bcfzip` anywhere on the page. Opening replaces the loaded topics; if you have unsaved topics of your own the file is merged in instead (same topic Guid: the file wins).
2. The drawer lists topics with status and priority chips. Filter by status, search title, description, assignee, labels and comments. Select a topic to see its snapshot, description, comments and viewpoints.
3. `Apply` on a viewpoint moves the camera, selects its elements, hides and colours elements and sets clip planes. The status line says what was applied and what was skipped (unknown GlobalIds are counted, not silently dropped).
4. `Clear viewpoint` undoes what BCF changed: the elements it hid (and only those: elements you hid yourself stay hidden), its colours and its clip planes. Camera and selection stay where they are.
5. `New topic` (or `Create topic from view`) asks for title, description, type, status, priority, labels, assignee and author, then stores a topic with a snapshot and a viewpoint of the current view. The author is remembered (localStorage `xray.bcf.author`) and is also the author of comments.
6. `Add comment` on any topic, optionally attaching the current view as a new viewpoint.
7. `Place pin`, `Add callout`, `Add note`, `Add arrow`, `Link measurement` (the `Markup` section of a selected topic) pin the topic and annotate its viewpoint; see below.
8. `Export 2.1` / `Export 3.0` download a `.bcfzip` of every topic in the list (loaded and created).

Panel entries (`BCF` folder): `Open BCF`, `Create topic from view`, `Export BCF 2.1`, `Export BCF 3.0`, `Clear viewpoint`, read-only `BCF status`. Palette actions, without default keys: `bcf.open`, `bcf.create`, `bcf.export` (uses the default export version), `bcf.clear`. The params document has a `bcf` section with the default author and the default export version.

## Pins and annotations

A topic is pinned to one 3D point, and each viewpoint can carry annotations. The drawer's `Markup` section of the selected topic holds the controls; `Show pins` in the drawer bar turns the pins on and off.

- **Pin.** A numbered marker (the position of the topic in the list) drawn on the shared overlay. Behind geometry it fades and gets a dashed rim (a ray against the merged-geometry BVH from the camera; hidden and ghosted elements, alpha below 0.5, do not hide it); off screen it becomes a marker at the view edge pointing towards it. Click a pin to select its topic and apply its first viewpoint. Pins show for the topics that pass the drawer filter (and the selected one); the selected topic's pin is blue. New topics are pinned to the centre of the bounds of their elements (the selection, or `globalIds`), else to the surface in the middle of the view; tick `Click the model to place the pin` in the dialog, or click `Place pin`, and the next click on the model sets it. `createTopics` items with a `location` are pinned there.
- **Annotations.** `Add callout` (a leader line from an element to a text box), `Add note` (a text box at a free 3D point) and `Add arrow` (an arrow pointing at an element, the text is optional) apply the topic's viewpoint and take the next click on the model as the anchor; type the text first in the box above the buttons. `Link measurement` lists the measurements of the measure tool; a click copies the measurement (both end points, distance, label, element GlobalIds) into a callout, so it survives without the measure tool and draws its own dimension line. Annotations draw while their viewpoint is applied and follow the camera. Drag a text box to move it, edit the text in the list (double click a box to jump there), `Delete` removes it; a click on a list row highlights it and applies its viewpoint. Escape cancels a placement (a second Escape closes the drawer).
- **Picking** uses the measure tool's ray test (first surface, hidden elements skipped) and passes ghosted elements first, so the click lands on what is drawn solid; placing clicks never change the selection.

### Where the markup is stored

BCF 2.1 and 3.0 have no field for a pin or annotations. The viewer writes a side file `<topic folder>/xray-markup.json` (src/bcf/sidecar.ts) and leaves the BCF XML as the schemas define it:

```json
{ "format": "xray-bcf-markup", "version": 1, "frame": "ifc", "units": "m", "topic": "<guid>",
  "pin": { "position": [x, y, z], "elementGuid": "<IfcGuid>" },
  "viewpoints": { "<viewpoint guid>": {
    "annotations": [{ "guid": "...", "type": "callout", "text": "...", "offset": [0.1, -0.09],
                      "anchor": { "kind": "element", "point": [x, y, z], "elementGuid": "<IfcGuid>" } }],
    "snapshotView": { "position": [...], "direction": [...], "up": [...], "fov": 42, "aspect": 1.78 },
    "baseSnapshot": "xray-<viewpoint guid>-base.png" } } }
```

- Points are IFC project coordinates, the same mapping as the viewpoint cameras (below). Text box offsets are fractions of the view height, so they scale with the snapshot. A measurement anchor holds `measurement: { kind, a, b, distance, label, elementGuids }`.
- Why a side file: the topic folder may hold other files (BCF 3.0 documentation, "Topic folder structure"), and readers open only the files that markup.bcf names, so other tools ignore it. A `Label` such as `pin:x,y,z` was not used: tools show labels to people and 3.0 lists them in `extensions.xml`. The official XSD validation (tests and smoke) still passes, and IfcOpenShell's `bcf-client` reads the exports (bench/smoke-bcf-markup.mjs with `BCF_CLIENT_PYTHON`).
- What other tools see: the snapshot named in markup.bcf of a viewpoint with annotations has them and the pin burned in (a pin alone leaves the snapshot untouched, so pinned topics cost no second image) (the same layout code as the overlay, src/bcf/annotate.ts, projected with the camera that took the snapshot), and the annotated elements are in the viewpoint `Selection`, so they highlight. The clean snapshot is stored beside it as `baseSnapshot`; on import the viewer keeps the clean one, so a re-export burns the markup once.
- A side file the viewer cannot read only adds a warning; invalid annotations are dropped one by one with a warning. Import restores pins and annotations exactly (unit test and smoke test).

## Coordinates

BCF uses IFC project coordinates (metres, Z up). The viewer uses metres, Y up, shifted by the sidecar `originShift` (IFC frame). The converter maps an IFC point `p` to the viewer as `v = (p.x - s.x, p.z - s.z, -(p.y - s.y))`; directions only rotate, `(x, y, z) -> (x, z, -y)`. BCF cameras, selections and clip planes go through exactly this mapping (src/bcf/model.ts), in both directions; the unit tests check round trips and the mapping against a real fzk-haus element.

## What a viewpoint does

| BCF part | Applied as |
| --- | --- |
| PerspectiveCamera | Camera position, orbit target and vertical field of view. The orbit target is the camera position plus the view direction times the distance to the middle of the chord through the model bounds (the centre depth when the view misses the model). If the viewer window is narrower than the viewpoint's `AspectRatio`, the field of view is widened as the BCF 3.0 guidance describes. |
| OrthogonalCamera | Approximated by a perspective camera placed so its vertical extent at the model depth equals `ViewToWorldScale`. The status line says so. |
| Selection | `app.selectIds` by GlobalId. No selection in the viewpoint clears the selection. |
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
bcf.linkMeasurement(topicGuid, measurementId, text?);    // a callout from a measure tool measurement
bcf.updateAnnotation(guid, { text, offset }); bcf.removeAnnotation(guid); bcf.annotations(topicGuid);
bcf.startPlacement('pin' | 'callout' | 'note' | 'arrow', topicGuid, text?); bcf.cancelPlacement(); bcf.pinsVisible = false;
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
- `bench/smoke-bcf-markup.mjs` (SMOKE_PORT=5623): topic with a clicked pin, callout on an element, linked measurement, note, text box drag, Escape, export 2.1 and 3.0 (XSD), reload, import, exact compare, pin click; writes `bench/bcf-markup-live.png`, `bench/bcf-markup-snapshot.png` (the exported snapshot) and `bench/bcf-markup-reimport.png`.

## Limitations

- Orthographic cameras are approximated; viewpoint roll, lines, bitmaps and colour alpha are ignored.
- Elements are matched by GlobalId only (no IfcProject / file matching); a topic made for another model applies its camera but selects nothing, and says how many ids were unknown.
- No editing of existing topic fields besides status and added comments; no zip64; BimSnippet files, documents and header files are carried through unchanged but not shown.
- Selection and exception lists over 1000 components work but the BCF guide recommends keeping them short.
- Markup: other tools see the burned snapshot and the selection only; they drop the side file when they rewrite the archive. Annotations anchor to a fixed point (an exploded or moved element leaves its anchor behind). No rectangle or freehand shapes. The occlusion fade in a burned snapshot uses the current hides, not those at capture time. Annotated elements join the viewpoint selection, so in this viewer they draw as focus when the viewpoint is applied after an import.
