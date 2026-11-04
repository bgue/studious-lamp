# Section: box, plane and clip planes

A section box fitted to the selection or the model with six draggable face handles, and a section plane. Both feed `renderer.setClipPlanes`, which BCF clipping also uses. Lives in the `Section` folder of the panel, in the `Section` tool of the action panel (it adds numeric min / max fields), and on keys `c`, `Shift+c`, `Alt+c`. With no planes the frame is pixel identical to the viewer without the feature (checked by `bench/smoke-section.mjs`).

| Control | Meaning |
| --- | --- |
| `box` | The box clips (key `c`; the first time it fits itself to the selection). |
| `Fit box to selection` | Fits the box to the selection (else the focus, else the model) plus the margin, and enables it (`Shift+c`). |
| `Fit box to model` | The same for the whole model. |
| `margin (m)` | Metres added around the fitted bounds, default 0.5. Changing it refits. |
| `plane` | The section plane clips (`Alt+c`). It works together with the box. |
| `axis` | `x`, `y`, `z` (viewer axes, `y` is vertical), `camera` (square to the view, follows the camera every frame) or `custom` (the tilted axis `plane.normal`, set by the gizmo's rings, see [gizmo.md](gizmo.md)). |
| `offset (m)` | Metres from the fitted centre (the box centre, or the model centre without a box) along the axis. |
| `flip` | Keep the other side. The kept side is the positive side of the axis (camera: away from the viewer). |
| `caps` | Paint the back faces a cut reveals flat in the cap colour with a light hatch. |
| `cap colour` | The cap colour. |
| `show handles` | Draw the box outline (faint, dashed) and the six face handles on the shared SVG overlay. |
| `Clear section` | Switch box and plane off, forget the box and remove every clip plane (also planes set by a BCF viewpoint). |

The box handles are round dots at the face centres, coloured by axis. Dragging one moves that face along its axis: the pointer ray is projected on the axis line (closest point of two lines), the grab offset is kept, and a face stops 5 cm from the opposite one. While a face is dragged, a readout next to it shows the face coordinate and the box size in metres. The section plane has its own arrow and ring handles (gizmo plugin, [gizmo.md](gizmo.md)). The drawer shows the min and max in numeric fields that follow the handles and can be typed into.

## Renderer API

```ts
renderer.setClipPlanes(planes | null, opts?: { cap?: boolean; capColor?: [r, g, b] })
renderer.getClipPlanes(): Array<{ normal: [x, y, z]; point: [x, y, z] }> | null
renderer.clipVersion   // incremented by every setClipPlanes call
```

Planes are in viewer coordinates; each normal points to the KEPT half-space (the BCF plan code flips the BCF direction). Up to 8 planes (a box needs 6, a plane 1, one is spare; the brief said 6, 8 is a superset). `cap` defaults to true when `opts` is omitted, which is what makes an applied BCF viewpoint clip and cap. `getClipPlanes` returns the unit-normalised planes. `setModel` removes them (they belong to the old model).

Every pass tests them per fragment (`clipCut` in `viewModeGlsl.ts`): opaque, ghost, OIT, focus, context and focus edges, edge glow, the peel mask, and the imaging thickness, slab and edge passes, so an element is split exactly, and edges of the cut part are not drawn. Caps use the back-face method of behind-only: in the opaque and focus passes a back face that is visible while planes are active is painted in the cap colour, but only while the camera is on the removed side of at least one plane (from the kept side no cut face is ever visible, so a visible back face is then an open or flipped mesh and keeps its normal shading). A ghosted element has no caps because the ghost pass culls back faces. Caps are painted for closed solids only (next section); the focus, which is drawn in front without a depth test, gets a depth test of its own while caps are on, so only its nearest face decides. Behind-only and peelback keep working with planes on (they are independent per-fragment tests, and the peel mask is rebuilt when the planes change). Picking skips a hit that a plane removes (`renderer.pick`).

## Closed solids

Caps are painted only on elements that are closed solids. At model load every element gets a closed flag (`src/model/closedMesh.ts`, an edge-manifold check: vertices welded by position to 10 micrometres, every undirected edge used by an even number of triangles; unmatched edges that are at most 15 % of the edges and have a vanishing vector area, the cracks and T-junctions of real IFC solids, are tolerated; an element with fewer than 4 triangles is open). The flag is stored as bit 4 (value 16) of the flags channel of the state texture (`stateB.r`, ORed in at upload, never in `RenderState.flags`) and read as `flagClosed(vFlags)` by the opaque pass, the focus pass and the MRI slab pass. Behind-only `cut + cap`, the peel cap, the section cap and the MRI slab cap all use it; an open element (a pane, a sheet, a box with a face missing) simply shows its back faces shaded like any other face (the MRI slab draws them like front faces). The check ran in 14 ms for 5,000 elements (synth5k) and in about 70 to 150 ms for a synthetic 100,000 elements with 1.07 million triangles (`tests/render-closed.test.ts` prints the numbers); all elements of the three bundled test models count as closed.

The selected window of fzk-haus is a good example: its glass is a 2 cm thick closed box, and with the section box fitted to it the panes used to be painted with the cap hatch. That was the focus pass (drawn in front, depth test off) painting every back face of the glass over its front faces, in draw order. With caps on, the focus now has its own depth test (a depth reset just before the focus pass, then `LessEqual`), so only the nearest face of the glass decides and the panes show their shaded glass (`bench/section-box.png`).

## Who owns the planes

The section plugin sends planes only when its own settings changed (or every frame while the plane axis is `camera`). If something else calls `setClipPlanes` (a BCF viewpoint), the plugin notices through `clipVersion`, stops sending, and takes the planes back only when you change a section setting. `Clear section` removes whatever is active.

## BCF

Applying a viewpoint with clipping planes calls `setClipPlanes(plan.clip)`: clipped and capped. Creating a topic captures `getClipPlanes()` into the viewpoint (the box counts as six planes). Round trip: `createTopic` with a box and a plane, `clear()`, `applyViewpoint` restores the same seven planes within 1e-3 (checked in `bench/smoke-section.mjs` and, for the maths, `tests/section-maths.test.ts`).

## Scripting and params

- `window.__xraySection = { config, set(partial), fitToSelection(), fitToModel(), clear(), planes(), centre(), planeAxis(), onChange(cb) }`. `set` takes any subset of the settings and returns the names it could not use. `centre()` is the point the offset is measured from, `planeAxis()` the unit axis before the flip.
- Params section `section` (`{ box: { enabled, fit, margin, min, max }, plane: { enabled, axis, offset, flip, normal? }, caps, capColor, showHandles }`, shared in the URL). `min` and `max` are extras: the explicit box after a fit or a drag (null until the first fit). A preset that only sets `box.enabled`, `fit` or `margin` gets a fit when it is applied.
- Actions: `section.toggleBox` (`c`), `section.fitSelection` (`Shift+c`), `section.togglePlane` (`Alt+c`), `section.clear`.

## Developer notes

- Pure maths: `src/section/maths.ts` (planes, box, handles, closest point of a ray to an axis line, face move, section plane) and `config.ts`. Tests: `tests/section-maths.test.ts`.
- Smoke test: `SMOKE_PORT=5361 node bench/smoke-section.mjs` writes `bench/section-*.png` and prints the checks.

## Limits

- Caps are back faces, not true cap polygons, and only closed solids get them: a thin single-sided element (a window pane modelled as one sheet) shows its back faces shaded, and a ghosted (x-ray) element is cut without a cap. A closed shell that has hundreds of unmatched edges (a badly welded import) counts as open and gets no cap.
- Only while caps are on and the camera looks in from the cut side, the focus pass is drawn with a depth reset and its own depth test; context edge glow (a cinematic option) is then drawn without the depth of the context in the focus area.
- The box is axis-aligned in the viewer frame.
- The handles are drawn on the SVG overlay without depth testing: a handle behind the model is still visible.
- Picking and the BVH ignore explode offsets (as before), so a pick near a cut of an exploded element may differ.
