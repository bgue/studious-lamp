# Gizmo: navigation cube, section strip and plane handles

An on-screen tool in the bottom-right corner of the stage (30 px above the bottom edge, clear of the status bar and of the
right dock): a navigation cube with roll, turn, home and projection buttons, and a compact section strip. Key `v` (action
`gizmo.toggle`) or the panel checkbox `Gizmo / show` hides it; the `-` button collapses it to a small cube button. On a
screen 700 px wide or less it starts collapsed and sits 36 px from the right edge (clear of the dock rail). When an open
tool drawer leaves too little room beside it, the gizmo drops the section strip, then shows only the cube button, then
hides (without changing the saved state); the cube button then opens it over the drawer until `-` or the drawer closes.
Legends (clearance, point cloud deviation) sit left of the gizmo, or above it when there is no room. The state is
kept in `localStorage` `xray.gizmo` and in the params section `gizmo` (`{ visible, collapsed }`, not in the share URL). "Reset
to defaults" restores the factory state, not the stored one: shown, expanded on a desktop and collapsed on a phone (the
section's `factory()` value, `src/ui/params.ts`), also when the gizmo was hidden in an earlier visit. The gizmo box is a
reserved rect of the shared overlay: BCF pins, callouts, measure labels and penetration markers that would fall under it
move beside it with a leader line (see toolbar.md, "Shared overlay").

## Navigation cube

Drawn as SVG from the camera orientation (orthographic projection of a unit cube, painter's order, back faces dropped).
Axes match the viewer: Y up, the IFC front (looking north) is the camera on +Z, right is +X; the same directions as the
keyboard views (`viewDirection` in `src/input/navigation.ts`). Faces are labelled Top, Bottom, Front, Back, Left, Right.
The model sidecar carries no true north, so there are no N/E/S/W labels.

Each visible face is split in 9 cells: the centre (face view), 4 edge strips (edge view: the camera halfway between the 2
faces) and 4 corner squares (corner view: the 3 faces). The region under the pointer is highlighted; the face the camera
looks from is tinted.

| Input | Action |
| --- | --- |
| Click a face, edge or corner | Look from there, framing the selection (else the model) like `Alt+digit`. Top has the back (-Z) at the top of the screen, as on a plan; Bottom has the front at the top. |
| Drag the cube | Orbit about the target (turntable, Y up). |
| Curved arrows at the top corners | Roll the picture 90 degrees counter-clockwise / clockwise about the view axis. |
| Arrows at the bottom corners | Turn the camera 90 degrees left / right about the vertical through the target. |
| Home | Frame the whole model from the default corner (`app.frameAll` pose), eased. `Home` key jumps there. |
| Projection | `view.projection` (`Num 5`, `Alt+5`): the 2 degree pseudo-orthographic camera of the keyboard plugin. There is no true orthographic camera in the renderer. |
| Face cells, keyboard | Each face centre is focusable; Enter or Space looks from it. |

Moves ease over the navigation move time (400 ms, `smooth moves` of the Keyboard folder; off = jump) and record the view
history (`Alt+Left` goes back). The orientation is interpolated as a quaternion, so a move into a top view never swings
through the pole, and a roll is possible: OrbitControls keeps world Y as its orbit axis, so a rolled side view is kept by
setting `camera.up`. At the end of an unrolled move `camera.up` is set back to +Y (a top or bottom view is then tipped by
1e-4 rad so the turntable's azimuth gives the screen up). A drag on the cube, any face click and Home return to world up.
Roll and turn start from the current view snapped to the nearest cube region and quarter-turn when within 1 degree, so
repeated clicks do not drift. A pointer down or wheel on the canvas cancels a running move.

Roll and turn are also palette actions without default keys: `gizmo.rollCw`, `gizmo.rollCcw`, `gizmo.turnLeft`,
`gizmo.turnRight`.

## Section strip

| Button | Action |
| --- | --- |
| X, Y, Z | Section plane square to the viewer axis (Y is vertical: a plan cut) through the centre of the selection, else the model. Click the lit button again to remove the plane. `Alt+c` toggles the plane. |
| Box | Off: fit the section box to the selection (else the model) and turn it on (`Shift+c`). On: turn it off (`c` toggles). |
| Flip | Keep the other side of the plane. |
| Caps | Hatched caps on cut closed solids. |
| Clear | Remove box, plane and any foreign (BCF) clip planes. While the planes of a BCF viewpoint are in force it is amber and says how many planes it removes, and X, Y, Z, Box and Flip are not lit (the section settings are not what the view shows). |

Pressed buttons carry `aria-pressed`; tooltips (native `title`, rebuilt from the current key bindings) name the keys, and
every button has an `aria-label` and a `data-help-key` with an Intent / Impact / Use / Ref entry (`Gizmo/...` in
`src/ui/helpText.ts`).

## Plane handles in the viewport

While the section plane is on (axis x, y, z or custom; not `camera`) and `show handles` is on, the shared SVG overlay shows:

- a faint outline of the plane around the handle point (as wide as the box, else the model);
- an arrow along the plane axis: drag to push or pull the plane. The pointer move is projected on the screen direction
  of the axis (`axisDragMetres`), so the plane follows the pointer; a live readout shows the offset in metres. When the
  axis points at the viewer, dragging up pushes along it;
- 2 rings about the in-plane axes: drag to tilt the plane about the handle point, in 15 degree steps (Shift: free).
  The angle is the screen direction of the pointer from the ring's projected centre, matched on the projected ring (an
  ellipse when oblique; `ellipseAngle`), so the speed does not race near the centre; inside 40 % of the ring's screen
  radius the tilt holds. A ring seen nearly edge on is dragged along its tangent.
  A tilted plane is stored as axis `custom` with `plane.normal`; one that lands on a world axis turns back into x, y or z.

The section box keeps its 6 face handles (`plugins/section.ts`), now with a readout of the face coordinate and the box size.
Handles take the pointer (pointer capture on the SVG element), so a drag never reaches the canvas: no orbit, no pick.

## Section API additions

`window.__xraySection` gained `centre()` (the point offsets are measured from), `planeAxis()` (unit axis before the flip) and
`onChange(cb)`. The plane config gained axis `custom` and the optional `normal` (validated, normalised, in params and the
share URL).

## Scripting

`window.__xrayGizmo = { state, setVisible(v), setCollapsed(v), lookFrom([sx, sy, sz]), roll(±1), turn(±1), home(), isMoving(), handles }`;
`handles.positions()` gives the stage coordinates of the plane handles.

## Files and tests

- `src/gizmo/maths.ts` (pure): regions, direction and up per region, roll, turn, unrolled test, cube cells, label axes,
  axis drags, ring angles, snapping, plane tilt. Tests: `tests/gizmo-maths.test.ts`.
- `src/gizmo/camera.ts` (eased slerp moves), `src/gizmo/cubeView.ts` (SVG cube), `src/gizmo/planeHandles.ts`,
  `src/plugins/gizmo.ts` (DOM, actions, params, panel folder).
- Smoke test: `SMOKE_PORT=5624 node bench/smoke-gizmo.mjs` (fzk-haus, synth5k and a 390x844 phone) writes `bench/gizmo-*.png`.

## Limits

- Orthographic is the keyboard plugin's 2 degree approximation.
- A rolled side view keeps `camera.up` rolled until the next mouse orbit: as soon as a left-button drag on the canvas
  starts, the roll eases back to world up (160 ms, or at once with smooth moves off), so the drag is the usual turntable.
- The handles are drawn without depth testing, like the box handles.
