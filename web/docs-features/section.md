# Section: box, plane and clip planes

A section box fitted to the selection or the model with six draggable face handles, and a section plane. Both feed `renderer.setClipPlanes`, which BCF clipping also uses. Lives in the `Section` folder of the panel, in the `Section` tool of the action panel (it adds numeric min / max fields), and on keys `c`, `Shift+c`, `Alt+c`. With no planes the frame is pixel identical to the viewer without the feature (checked by `bench/smoke-section.mjs`).

| Control | Meaning |
| --- | --- |
| `box` | The box clips (key `c`; the first time it fits itself to the selection). |
| `Fit box to selection` | Fits the box to the selection (else the focus, else the model) plus the margin, and enables it (`Shift+c`). |
| `Fit box to model` | The same for the whole model. |
| `margin (m)` | Metres added around the fitted bounds, default 0.5. Changing it refits. |
| `plane` | The section plane clips (`Alt+c`). It works together with the box. |
| `axis` | `x`, `y`, `z` (viewer axes, `y` is vertical) or `camera` (square to the view, follows the camera every frame). |
| `offset (m)` | Metres from the fitted centre (the box centre, or the model centre without a box) along the axis. |
| `flip` | Keep the other side. The kept side is the positive side of the axis (camera: away from the viewer). |
| `caps` | Paint the back faces a cut reveals flat in the cap colour with a light hatch. |
| `cap colour` | The cap colour. |
| `show handles` | Draw the box outline (faint, dashed) and the six face handles on the shared SVG overlay. |
| `Clear section` | Switch box and plane off, forget the box and remove every clip plane (also planes set by a BCF viewpoint). |

The box handles are round dots at the face centres, coloured by axis. Dragging one moves that face along its axis: the pointer ray is projected on the axis line (closest point of two lines), the grab offset is kept, and a face stops 5 cm from the opposite one. The drawer shows the min and max in numeric fields that follow the handles and can be typed into.

## Renderer API

```ts
renderer.setClipPlanes(planes | null, opts?: { cap?: boolean; capColor?: [r, g, b] })
renderer.getClipPlanes(): Array<{ normal: [x, y, z]; point: [x, y, z] }> | null
renderer.clipVersion   // incremented by every setClipPlanes call
```

Planes are in viewer coordinates; each normal points to the KEPT half-space (the BCF plan code flips the BCF direction). Up to 8 planes (a box needs 6, a plane 1, one is spare; the brief said 6, 8 is a superset). `cap` defaults to true when `opts` is omitted, which is what makes an applied BCF viewpoint clip and cap. `getClipPlanes` returns the unit-normalised planes. `setModel` removes them (they belong to the old model).

Every pass tests them per fragment (`clipCut` in `viewModeGlsl.ts`): opaque, ghost, OIT, focus, context and focus edges, edge glow, the peel mask, and the imaging thickness, slab and edge passes, so an element is split exactly, and edges of the cut part are not drawn. Caps use the back-face method of behind-only: in the opaque and focus passes a back face that is visible while planes are active is painted in the cap colour, but only while the camera is on the removed side of at least one plane (from the kept side no cut face is ever visible, so a visible back face is then an open or flipped mesh and keeps its normal shading). Limits are the same as there (an open mesh shows its back faces in the cap colour; a ghosted element has no caps because the ghost pass culls back faces). Behind-only and peelback keep working with planes on (they are independent per-fragment tests, and the peel mask is rebuilt when the planes change). Picking skips a hit that a plane removes (`renderer.pick`).

## Who owns the planes

The section plugin sends planes only when its own settings changed (or every frame while the plane axis is `camera`). If something else calls `setClipPlanes` (a BCF viewpoint), the plugin notices through `clipVersion`, stops sending, and takes the planes back only when you change a section setting. `Clear section` removes whatever is active.

## BCF

Applying a viewpoint with clipping planes calls `setClipPlanes(plan.clip)`: clipped and capped. Creating a topic captures `getClipPlanes()` into the viewpoint (the box counts as six planes). Round trip: `createTopic` with a box and a plane, `clear()`, `applyViewpoint` restores the same seven planes within 1e-3 (checked in `bench/smoke-section.mjs` and, for the maths, `tests/section-maths.test.ts`).

## Scripting and params

- `window.__xraySection = { config, set(partial), fitToSelection(), fitToModel(), clear(), planes() }`. `set` takes any subset of the settings and returns the names it could not use.
- Params section `section` (`{ box: { enabled, fit, margin, min, max }, plane: { enabled, axis, offset, flip }, caps, capColor, showHandles }`, shared in the URL). `min` and `max` are extras: the explicit box after a fit or a drag (null until the first fit). A preset that only sets `box.enabled`, `fit` or `margin` gets a fit when it is applied.
- Actions: `section.toggleBox` (`c`), `section.fitSelection` (`Shift+c`), `section.togglePlane` (`Alt+c`), `section.clear`.

## Developer notes

- Pure maths: `src/section/maths.ts` (planes, box, handles, closest point of a ray to an axis line, face move, section plane) and `config.ts`. Tests: `tests/section-maths.test.ts`.
- Smoke test: `SMOKE_PORT=5361 node bench/smoke-section.mjs` writes `bench/section-*.png` and prints the checks.

## Limits

- Caps are back faces, not true cap polygons: with the camera outside the kept region, a thin single-sided element (a window pane seen from behind) is painted in the cap colour too, and a ghosted (x-ray) element is cut without a cap.
- The box is axis-aligned in the viewer frame.
- The handles are drawn on the SVG overlay without depth testing: a handle behind the model is still visible.
- Picking and the BVH ignore explode offsets (as before), so a pick near a cut of an exploded element may differ.
