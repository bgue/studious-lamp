# Pointer modes: Arrow (select) and Hand (move)

What the left mouse button does in the viewport. A two-button toggle under the view cube on the gizmo sets it, with the keys
`R` and `G`. The toolbar and the keys are in [gizmo.md](gizmo.md) and [keyboard.md](keyboard.md).

| | Hand (move), the default | Arrow (select) |
| --- | --- | --- |
| Left drag | Orbit | Draw a selection box |
| Click, no drag | Select | Select |
| Shift | Shift-click adds, Shift-drag pans | Shift-click or Shift-box adds |
| Ctrl or Cmd | Ctrl-click or Cmd-click toggles | Ctrl-click, Cmd-click or a Ctrl or Cmd box toggles |
| Right drag | Pan | Pan |
| Middle drag | Pan | Pan |
| Shift + middle drag | Orbit about the point under the cursor | Orbit about the point under the cursor |
| Wheel | Zoom toward the cursor | Zoom toward the cursor |
| Double click (left) | On an element: select it and fly to it. On empty space: nothing. `Alt` held: enter Walk mode and drop in on that spot | The same |
| Double click (middle) | Frame everything (Home) | Frame everything (Home) |
| Touch | One finger orbits, two fingers zoom and pan | One finger draws the box, two fingers zoom and orbit (pan: switch to Hand) |
| Cursor | `grab`, `grabbing` while a drag runs | the default arrow |

The camera is never out of reach in Arrow mode: the right and middle buttons and the wheel work, and so does the keyboard.

## Navigation style: BIM (default) and Game

The table above is the **BIM** style, the one of Revit, Navisworks and Solibri. The **Game** style (`navigation style` in the
`Keyboard` folder, see [keyboard.md](keyboard.md)) is the older mapping: the middle button zooms, the wheel zooms toward the
target, `w a s d q e` fly the camera at all times, and there is no pivot pick and no double click action. The style is a
per-viewer convenience in `localStorage` `xray.keynav`, not in the params.

- **Wheel zoom to the cursor.** OrbitControls `zoomToCursor`: the camera moves along the ray through the cursor, so the point
  under the cursor stays under it. The orbit target is kept in front of the camera. A pinch on a touch screen zooms about its
  own centre as before (the flag is dropped on a touch pointer and set again on the wheel).
- **Orbit pivots on what you grab.** At the start of an orbit drag (left button in Hand mode, Shift + middle) the app picks the
  point under the cursor with the same pick as a click (hidden elements and ghosts too faint to click are skipped). On a hit the
  orbit target moves along the current view ray to the depth of the hit (`retargetAtDepth` in `src/input/walk.ts`; clamped to the
  zoom limits), so the view does not jump. On a miss the target stays. It is one pick per drag start; touch is not changed.
- **Double click.** Left on an element: select it and fly to it with the fly-to framing (Cinematic > Camera fly-to), recorded in
  the view history. Not while a tool owns the pointer (measure) or with Shift, Ctrl or Cmd. Middle: the browser sends no `dblclick`
  for that button, so two quick middle clicks without a drag frame everything, like `Home`.
- **Drop in here.** `Alt` + double click on the model enters Walk mode and stands on that spot (a surface that faces up, else the floor
  below the hit point) at the eye height; in Walk mode a plain double click does the same, with the same view direction. See
  [keyboard.md](keyboard.md#walk-mode-and-navigation-style). The handler is in `src/plugins/walk.ts` (capture phase, so the fly-to above does not also run).

## Walk mode

Walk mode (`Shift+w`, or the walk button on the gizmo) changes the left button: a drag **looks around from the eye** (yaw and pitch
about the camera position, pitch within 85 degrees), in Hand and in Arrow mode (no selection box while it is on), and one finger
does the same on touch. There is no pointer lock, so it works in an iframe and on a phone. The wheel walks forward and back, a click
still selects, the cursor is an eye, and a chip "Walk · Esc to exit" shows. Details and keys: [keyboard.md](keyboard.md).

## The selection box

The CAD convention. Drag from **left to right** and the box is a *window*: it picks the elements that lie **fully inside** it
(solid blue outline). Drag from **right to left** and it is a *crossing* box: it picks every element it **touches** (dashed
green outline). `Esc` cancels the box while the button is down, and the same `Esc` does not clear the selection. A box without
Shift replaces the selection (an empty box clears it), with Shift it adds, with Ctrl or Cmd it toggles each element it picked.

The pick is made on the screen from the world bounding boxes of the elements (`src/input/boxSelect.ts`, pure, tested in
`tests/box-select.test.ts`): a window needs all 8 corners of the box inside the rectangle; a crossing takes the convex hull of
the projected box (clipped at the near plane), so a rectangle lying inside a big wall still picks the wall. 5000 elements take
about a millisecond; nothing is drawn or raycast. Elements that are hidden (your hides, isolated away, a class hidden by the
class styles) or ghosts too faint to click (alpha under 0.3 and not in focus) are not picked, the same rules as a click. It
uses bounding boxes, so a crossing box can pick an L-shaped element whose empty corner it touches, and it does not look at
occlusion: a box picks the elements behind the ones in front.

The result goes through `app.selectWith(ids, how)` (`'replace' | 'add' | 'toggle'`, over `selectIds`), so the model tree,
the Properties tab and the status bar update as for a click.

## Settings and persistence

The mode is a per-viewer convenience, like the sidebar width. It lives in `localStorage` `xray.pointerMode` (`hand` or
`arrow`), in a try/catch, and is **not** in the params document, the share link, a saved view, a preset or a packed page: no
params section carries it (`tests/pointer-mode.test.ts` checks this, `bench/smoke-pointer-undo.mjs` checks the real params
and share link). "Reset to defaults" does not touch it.

## Keys

| Action | Key |
| --- | --- |
| Arrow mode (`pointer.select`) | `r` |
| Hand mode (`pointer.hand`) | `g` |
| Walk mode (`nav.walk`) | `Shift+w` |

The obvious `V` and `H` are taken (`v` shows or hides the gizmo, `h` hides the selection), so the keys are `R` (rectangle) and
`G` (grab). Both are rebindable and are in the cheat sheet and the command palette under *Modes*.

## Scripting

`window.__xrayPointer = { mode, setMode('arrow' | 'hand'), pick(rect, 'window' | 'crossing'), boxSelect(rect, mode, how?), drawing() }`
with `rect = { x0, y0, x1, y1 }` in canvas CSS pixels. `pick` returns the ids without selecting. The overlay is
`#xray-boxselect` with `data-box="window" | "crossing"`; the canvas carries `data-pointer-mode`.

## Files and tests

- `src/input/boxSelect.ts` (geometry), `src/input/pointerMode.ts` (state, storage, orbit-control settings per style, selection
  modifiers), `src/plugins/pointerMode.ts` (DOM, overlay, actions, zoom to the cursor, pivot pick, double click), the toggle in
  `src/plugins/gizmo.ts`; `src/input/walk.ts` (pure walk and pivot maths), `src/plugins/walk.ts` (chip, look drag, Esc).
- Tests: `tests/box-select.test.ts`, `tests/pointer-mode.test.ts`. Smoke test: `SMOKE_PORT=5701 node bench/smoke-pointer-undo.mjs`
  writes `bench/pointer-modes-desktop.png`, `pointer-box-select.png`, `pointer-modes-phone.png`.

## Limits

- Section planes and view-mode cuts do not hide an element from a box (a click does look at them): the bounding box is used.
- On touch, Arrow mode has two-finger zoom and orbit but no two-finger pan; switch to Hand to pan.
- While the measure tool, the markup tool or a BCF pin placement takes the pointer, those tools win on the first button as
  before; a box is not drawn over a markup drawing tool.
