# 10. Measure and clearance

## The problem

"Is there room for the insulation between that duct and the beam?" "How far is this pipe from the wall?" You can guess
from the picture, but a guess is no use at a coordination meeting. And when a whole run of pipes passes near structure,
you do not want to measure one gap at a time. You want to see every place where something is too close.

## The idea

There are two tools, and they answer different questions.

**Measure** answers one question at a time. You click two things and get a distance. A distance can be between two
points you click on a surface, or the shortest gap between two whole elements.

**Clearance** answers the question for everything at once. You pick a focus (the duct), and the viewer colours every
nearby structural element by how close it is to that focus. Red is touching or overlapping. Amber is tighter than your limit.
A blue ramp shows the rest. It is like a heat camera that looks at distances.

## 10.1 Point-to-point and element-to-element

### Try it

1. Open **Sample Projects** and choose **Building (Simple-Scene)**.
2. Open the **Measure** tool (the ruler icon in the tool strip). Its drawer opens. While it is open, clicks on the 3D
   view measure.
3. Keep `mode` on `point to point`. Click one point on a wall surface, then another point on the floor. A dashed line
   follows the cursor with the live length. After the second click the dimension stays, with its label.
4. Check that `snap to vertices` is on (it is by default; in the drawer it reads **Snap to vertices (12 px)**). Move toward a corner: a yellow ring appears when the cursor is within 12 px of a corner,
   and the click lands on the corner exactly.
5. Switch `mode` to `element to element`. The duct sits inside the chimney, so first hide the chimney and the walls with the eye icons of their class rows in the **Model** tree. Click the duct, then show the walls again (`Alt+H`) and click a wall. The label shows the shortest distance between the two
   surfaces, and the two closest points are marked. If the elements touch or cross, it shows 0.
6. Look at the drawer. Each measurement is listed with a delete button. **Clear** removes them all. **Export CSV**
   saves them.
7. Press `Escape`. If a first point is pending, it is cancelled. A second `Escape` closes the drawer. The dimensions stay
   on the model after the drawer closes. Measuring just stops.

### How it works

For point-to-point, the viewer shoots a ray from the camera through the pixel you clicked and takes the first surface it
hits. Hidden elements are skipped. Ghosted ones are not, so you can measure a ghosted wall. Because the point is on a
surface and not in the air, the distance is always between real things.

For element-to-element the viewer searches both meshes for the closest pair of points. That is the true minimum
distance, not the distance between centres or boxes.

A label that would land under the gizmo, the status bar, a drawer or a legend slides to the nearest free place and is
joined to its dimension by a dashed leader line.

### Choices and settings

- `units`: metres with 3 decimals, or whole millimetres.
- `snap to vertices`: on or off.
- **Export CSV**: one row per measurement, with the distance in m and in mm, the differences in x, y and z, both end points
  in IFC world coordinates, and the GlobalIds of the elements.

### Limits and gotchas

- Dragging to orbit never makes a point. A measuring click does not change the selection.
- The ray hits the first visible surface. If you want to measure to something behind a wall, hide the wall or use element-to-element.
- A distance is straight-line. It does not follow a pipe route or a walking path.
- The dimensions stay on the model when you close the drawer. Use **Clear** (or `Clear measurements` in the Measure folder
  of the **Parameters** tab) to remove them.
- The same settings live in the **Parameters** tab: `mode`, `units`, `snap to vertices`. They are part of the parameters
  document (chapter 19.1).

## 10.2 Clearance colouring

### Try it

1. In the **Building** model, select the duct. Click it, or find it with the search bar (7.2).
2. Open the **Clearance** tool in the strip and tick **Show clearance of the context to the focus**. Colouring starts. (The command palette also has `clearance.toggle`.)
3. The context elements, meaning walls, slabs, beams and columns, take colours. Red is a clash. Amber is closer than `tight`.
   Everything else within range is fine and runs from teal (near) to blue (far). Anything beyond `max range` keeps its normal colour. A legend sits at
   the bottom right of the view.
4. The drawer shows counts per band and the time it took.
5. Select another element. The colours are recomputed for it.
6. Raise `tight (m)` from 0.05 to 0.2. More elements turn amber.
7. Untick the switch. The original colours return.

### What each band means

| Band | Colour |
| --- | --- |
| clash: distance 0 or overlapping | red |
| tight: below `tight (m)`, default 0.05 | amber |
| ok: up to `max range (m)`, default 0.5 | blue ramp, teal near and blue far |
| beyond max range | unchanged |

The **focus** is the selected element and the run connected to it (chapter 1). The **context** is the structure around
it. Clearance measures from focus to context only. It does not tell you the distance between two walls.

### How it works

Only context elements whose bounding boxes are within `max range` of the focus get the expensive surface-to-surface
distance. They are tried nearest first and the search stops as soon as the boxes cannot beat the best distance found.
That keeps it fast on large models. The colours are put back when you switch off, when the focus changes (then they are
recomputed), and when the model changes.

### Raise issues from results

The drawer has an **Issues** block. **Raise issues from results** makes one issue for every context element that clashes or
is tighter than `tight (m)`. The title reads like `Clearance 120 mm < 300 mm: Pipe-4 / Beam-9`. Each issue holds both
GlobalIds, a view with the camera on the pair, and a drawing tied to the pair. The colouring must be on and a focus
selected. Chapter 15.3 explains what happens when you raise again: only new pairs are added, and pairs that a later run
no longer finds are marked, so you can close them.

The issues carry the labels `clash` or `clearance`. The button is **Raise issues from results**.

### Limits and gotchas

- It colours by element, not by region. A big slab that a duct passes through shows red along its whole extent.
- Elements that host or contain the focus (the slab a duct goes through) always show as clash. For those, use
  chapter 11.
- The colouring writes to the same colour layer as the cleanup preview and the x-ray debug colours. Switch one off before
  you switch another on.
- Clearance is a distance between surfaces. It does not know whether a gap is meant to hold insulation, a hanger or
  a person.

## See also

- 11 Penetrations: where MEP crosses structure, and the opening.
- 15.3 Issues from checks.
- 1.1 Focus, context and the x-ray.
