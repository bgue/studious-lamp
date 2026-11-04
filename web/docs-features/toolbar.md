# Action panel (toolbar)

A vertical icon strip at the left edge of the canvas (44 px, inside the stage, so it moves with the left sidebar) with one button per tool, and a drawer beside it for tools that have a panel. Key `t` shows or hides the strip (remembered in localStorage `xray.toolbar`).

## Buttons and drawers

- Tools are sorted by their `order` (then id): Open model (10), X-ray (30), View modes (40), Measure (70), Clearance (80), Penetrations (90), Cleanup (110); other plugins add theirs (BCF, ...). Hover or focus a button for its label and description.
- A button is highlighted when its tool is active (`isActive`): x-ray on, a view mode on, measure open, clearance colouring on.
- A tool with a panel opens a 320 px drawer over the canvas (the penetration schedule asks for 460 px); drag the right edge to resize. Only one drawer is open at a time; click the button again, the close button or press Escape to close it. A tool without a panel (Open model, X-ray) acts on click.
- Escape is handled in the capture phase on the document only while a drawer is open, and not at all while the command palette or the cheat sheet is open. A tool with a pending state (measure with a first point) gets Escape first.

| Tool | Drawer |
| --- | --- |
| Open model | no drawer: runs the Open model button of the parameter panel |
| X-ray | no drawer: toggles x-ray (same as key `X`), highlighted when on |
| View modes | Behind-only and peelback toggles, front treatment, offset, front alpha, radius, slope, feather (the full set is in the View modes folder) |
| Cleanup | rule enables, the floating threshold, Preview, Hide and Restore, a status line |
| Measure | see measure.md |
| Clearance | see measure.md |
| Penetrations | see penetrations.md |

The Cleanup drawer starts from the rules of the last cleanup report (or the defaults): there is no getter for the live rules, so after reloading a page whose stored rules differ, press Preview once to see the effect.

## Commands and scripting

- `toolbar.toggle` (key `t`): show or hide the strip. `tool.<id>` (no default key): open that tool; they appear in the command palette (Ctrl+K) for the visible tools.
- `window.__xrayToolbar = { open(id), close(), toggle(), tools() }`. `open` returns false for an unknown or hidden id; `tools()` lists the visible ids in order.
- Packaged viewers (`tools/xray-pack`): `window.__xrayBoot.tools` is an ordered list of tool ids to show (anything else is hidden and gets no `tool.<id>` action); `openTool` opens one at start.
- Plugins add tools with `registerTool` (src/tools/registry.ts). `drawerWidth` is an optional field.

## Shared overlay

`src/ui/overlay.ts` provides `getOverlay(app)`: an SVG layer above the canvas inside the stage (pointer events off). `layer(name)` returns a `<g>`; `onUpdate(cb)` runs when the camera, canvas size or data (`invalidate()`) changed; `project(point)` gives CSS pixel coordinates with `visible` (inside the frustum) and `front` (in front of the camera). Penetration markers, measurements and the clearance legend use it.
