# Measure and clearance

## Measure

Open the `Measure` tool (ruler icon). Clicks on the canvas measure while the drawer is open; closing it stops measuring but the dimensions stay on the model.

- `point to point`: click two points on surfaces. The point is the first visible surface under the cursor (a ray against the merged-geometry BVH; hidden elements are skipped). With `snap to vertices` the point jumps to the nearest vertex of the hit triangle when it is within 12 px; a yellow ring shows the snap. A dashed rubber band with a live length follows the cursor after the first click.
- `element to element`: click two elements. Shows the minimum surface distance and its two closest points (per-element BVH `closestPointToGeometry`). Elements whose meshes cross or touch show 0.
- Each measurement is a dimension line with a label (`units` m with 3 decimals, or whole mm; a label that would fall under the gizmo, the status bar, an open drawer or a legend moves to the nearest free spot with a dashed leader line to the middle of the dimension), listed in the drawer with a delete button, plus `Clear` and `Export CSV` (id, kind, distance in m and mm, dx, dy, dz, both end points in IFC world coordinates, element GlobalIds).
- Escape cancels the pending first point (drawer stays open); a second Escape closes the drawer. Dragging to orbit never creates a point, and measuring clicks do not change the selection.
- Folder `Measure`: `mode`, `units`, `snap to vertices`, `Clear measurements`. Params section `measure` (units, snap, mode). `window.__xrayMeasure = { list, pending, units, click(point, element), pickAt(x, y), clear() }`; BCF linked measurements read `units` (`src/measure/current.ts`), so their callouts and burned snapshots use the same unit.

## Clearance

Colours the context elements (the context classes: slabs, walls, beams, columns, ...) by their minimum surface distance to the current focus (the selected element and its connected run):

| Band | Colour |
| --- | --- |
| clash: distance 0 or overlapping | red |
| tight: below `tight (m)` (default 0.05) | amber |
| ok: up to `max range (m)` (default 0.5) | blue ramp, teal near to blue far |
| beyond the max range | unchanged |

Only context elements whose bounds are within the max range of a focus element get mesh distance queries, nearest bounds first, stopping as soon as the bounds cannot beat the best distance. A legend sits at the bottom right of the canvas and the drawer shows counts per band and the compute time. The original colours are put back when clearance is switched off, when the focus changes (the colouring is then recomputed) and on model change.

- Folder `Clearance`: `enabled`, `tight (m)`, `max range (m)` and a status line. Params section `clearance` (the two thresholds). Command `clearance.toggle`.
- `window.__xrayClearance = { enabled, counts, status, settings, setEnabled(on), recompute() }`.
- Limits: it colours by element, not by region; the elements that host or contain the focus (a slab a duct passes through) always show as clash. It writes `renderer.state.color`, so it shares those colours with the cleanup preview and the debug bucket colours: switch one off before the other.
