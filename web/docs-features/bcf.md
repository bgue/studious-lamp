# BCF issues (BIM Collaboration Format)

Open, review, create and export BCF topics. Reads BCF 2.0, 2.1 and 3.0; writes 2.1 (default) and 3.0. A topic can carry viewpoints (camera, selected elements, hidden elements, colours, clip planes) and a snapshot, and the viewer applies them to the model.

Where: the `BCF` tool in the action panel (a drawer), the `BCF` folder in the parameter panel, and the command palette. Scripting: `window.__xrayBcf`.

## Workflow

1. `Open BCF` (drawer, panel or palette), or drop a `.bcf` / `.bcfzip` anywhere on the page. Opening replaces the loaded topics; if you have unsaved topics of your own the file is merged in instead (same topic Guid: the file wins).
2. The drawer lists topics with status and priority chips. Filter by status, search title, description, assignee, labels and comments. Select a topic to see its snapshot, description, comments and viewpoints.
3. `Apply` on a viewpoint moves the camera, selects its elements, hides and colours elements and sets clip planes. The status line says what was applied and what was skipped (unknown GlobalIds are counted, not silently dropped).
4. `Clear viewpoint` undoes what BCF changed: the elements it hid (and only those: elements you hid yourself stay hidden), its colours and its clip planes. Camera and selection stay where they are.
5. `New topic` (or `Create topic from view`) asks for title, description, type, status, priority, labels, assignee and author, then stores a topic with a snapshot and a viewpoint of the current view. The author is remembered (localStorage `xray.bcf.author`) and is also the author of comments.
6. `Add comment` on any topic, optionally attaching the current view as a new viewpoint.
7. `Export 2.1` / `Export 3.0` download a `.bcfzip` of every topic in the list (loaded and created).

Panel entries (`BCF` folder): `Open BCF`, `Create topic from view`, `Export BCF 2.1`, `Export BCF 3.0`, `Clear viewpoint`, read-only `BCF status`. Palette actions, without default keys: `bcf.open`, `bcf.create`, `bcf.export` (uses the default export version), `bcf.clear`. The params document has a `bcf` section with the default author and the default export version.

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
bcf.createTopic({ title, description, type, status, priority, labels, assignedTo, author, snapshot, globalIds, camera });
bcf.createTopics([{ title, description?, globalIds: [...], camera?: { position, target }, labels? }], { snapshot? });
bcf.addComment(topicGuid, 'text', { author, viewpoint });
const bytes = await bcf.exportZip('3.0');        // Uint8Array; bcf.download('3.0') also saves the file
```

`createTopics` builds one topic per item with a viewpoint that selects the listed elements and frames them (camera from their bounds when `camera` is not given; `camera` is in viewer coordinates). It selects and frames each item in turn to take the snapshots and restores your camera and selection afterwards. Snapshots default to on for up to 20 topics; pass `{ snapshot: true | false }` to override.

## Files and tests

- `src/bcf/zip.ts` zip reader and writer (stored and deflate through `CompressionStream`, CRC32, directory entries), `xml.ts` small strict XML reader (used instead of `DOMParser`, so browser and node tests behave identically), `parse.ts`, `write.ts`, `plan.ts` (pure viewpoint planning and capture), `controller.ts`, `ui.ts`; plugin `src/plugins/bcf.ts`.
- Tests `tests/bcf-*.test.ts`, fixtures `tests/fixtures/bcf` (hand written 2.1 and 3.0 archives as folders, the official XSDs under `xsd/`, the BCF documentation under `docs/`). `tests/fixtures/bcf/validate_xsd.py` validates unpacked archives against the XSDs with lxml; `tests/bcf-xsd.test.ts` runs it and skips when python3 or lxml is missing.
- `bench/smoke-bcf.mjs` (SMOKE_PORT=5333) runs the browser workflow and writes `bench/bcf-drawer.png`.

## Limitations

- Orthographic cameras are approximated; viewpoint roll, lines, bitmaps and colour alpha are ignored.
- Elements are matched by GlobalId only (no IfcProject / file matching); a topic made for another model applies its camera but selects nothing, and says how many ids were unknown.
- No editing of existing topic fields besides status and added comments; no zip64; BimSnippet files, documents and header files are carried through unchanged but not shown.
- Selection and exception lists over 1000 components work but the BCF guide recommends keeping them short.
