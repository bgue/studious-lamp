# Keyboard navigation

Everything the keyboard does goes through one action registry (`src/input/actions.ts`). The keymap plugin
(`src/plugins/keymap.ts`) owns the key listeners. The cheat sheet, the command palette and the shortcut editor read the
same registry, so a plugin that registers an action gets a key, a cheat sheet row and a palette entry for free.

## Files

| File | Role |
| --- | --- |
| `src/input/actions.ts` | Registry: `registerAction` (replaces by id), `getActions`, `runAction`, `onActionsChanged`. Optional fields added for the keymap: `repeat`, `modifiers`, `description`; `hold(app, dt, mods)`. |
| `src/input/keymap.ts` | Engine: chord parsing, matching, dispatch, hold actions, conflicts, overrides, export and import. No DOM at import. |
| `src/input/navigation.ts` | Camera maths and the navigation and view actions, view history, storeys, Tab cycling. |
| `src/input/commands.ts` | Selection and visibility actions, tree filter focus (`Alt+f`), `preset.1` to `preset.9` placeholders. |
| `src/plugins/keymap.ts` | Wires listeners, the `Keyboard` panel folder, the params section `keymap`. |
| `src/ui/cheatsheet.ts`, `palette.ts`, `keymapView.ts` | Cheat sheet, command palette, shortcut editor, toast and stylesheet. |

## Chord syntax

`Ctrl+`, `Alt+`, `Shift+`, `Meta+` then a `KeyboardEvent.key` (`x`, `?`, `Escape`, `ArrowLeft`, `PageUp`) or
`code:` plus a `KeyboardEvent.code` (`code:Numpad7`, `code:Digit1`). Rules:

- Ctrl, Alt and Meta must match exactly. Shift must match exactly, except for a chord that is one printable symbol
  (`?`, `+`, `[`, `=`), where the layout decides Shift.
- Letters are case-insensitive: `h` is the key without Shift, `Shift+h` the key with it.
- `Alt+<letter>` also matches by physical key, because Alt produces other characters on some layouts.
- Keys are ignored while a text field (input, textarea, select, contenteditable) has focus. Escape blurs the field.
  Checkboxes, radios and buttons do not count as text fields.
- Keys are ignored while the cheat sheet, the palette or the editor is open (they handle their own keys).
- A focused list widget keeps its own keys, see [Focus rules](#focus-rules).
- `preventDefault` is called only for keys an enabled action took.

## Default bindings

### Navigation (hold keys act every frame; Ctrl held = slow, x0.25)

`w a s d q e` do nothing in the default BIM style: they fly the camera only in Walk mode, or in the Game style. The actions
(`nav.forward`, `nav.back`, `nav.left`, `nav.right`, `nav.down`, `nav.up`) keep their ids and chords, so custom keymaps and the
cheat sheet still work (the cheat sheet labels them "(Walk mode)").

| Action | Keys |
| --- | --- |
| Orbit left / right | `ArrowLeft` / `ArrowRight` |
| Orbit up / down | `ArrowUp` / `ArrowDown` |
| Pan left / right / up / down | `Shift+ArrowLeft/Right/Up/Down` |
| Fly forward / back (Walk mode, or the Game style) | `w` / `s` |
| Fly left / right (Walk mode, or the Game style) | `a` / `d` |
| Fly down / up (Walk mode, or the Game style) | `q` / `e` |
| Walk mode, see [Walk mode](#walk-mode-and-navigation-style) | `Shift+w` enters; `Esc` leaves |
| Zoom in (15 %) | `=`, `+`, `code:NumpadAdd` |
| Zoom out (15 %) | `-`, `code:NumpadSubtract` |
| Storey up / down | `PageUp` / `PageDown` |
| Next / previous selected element | `Tab` / `Shift+Tab` |
| Previous / next view (history, 50 poses) | `Alt+ArrowLeft` / `Alt+ArrowRight`, mouse buttons 4 and 5 |

### Views (frame the selection, else the whole model)

| Action | Keys |
| --- | --- |
| Front | `code:Numpad1`, `Alt+code:Digit1` |
| Back | `Ctrl+code:Numpad1`, `Alt+Shift+code:Digit1` |
| Right | `code:Numpad3`, `Alt+code:Digit3` |
| Left | `Ctrl+code:Numpad3`, `Alt+Shift+code:Digit3` |
| Top | `code:Numpad7`, `Alt+code:Digit7` |
| Bottom | `Ctrl+code:Numpad7`, `Alt+Shift+code:Digit7` |
| Isometric | `code:Numpad0`, `Alt+code:Digit0` |
| Perspective / orthographic | `code:Numpad5`, `Alt+code:Digit5` |
| Frame selection (or all when nothing is selected) | `f` |
| Frame selection | `.`, `code:NumpadDecimal` |
| Frame all | `Home` |
| Roll 90° clockwise / counter-clockwise, turn 90° left / right (view cube buttons) | unbound by default; actions `gizmo.rollCw`, `gizmo.rollCcw`, `gizmo.turnLeft`, `gizmo.turnRight` |

### Selection, visibility, panels, other

| Action | Keys |
| --- | --- |
| Show or hide the view cube and section strip | `v` |
| Clear selection (leaves Walk mode and closes overlays first) | `Escape` |
| Select all visible | `Ctrl+a` |
| Invert selection | `Ctrl+i` |
| Select all of the same class | `Alt+s` |
| Arrow mode (click selects, drag draws a selection box) / Hand mode (drag orbits), see [pointer-modes.md](pointer-modes.md) | `r` / `g` |
| Undo / redo the last camera move, selection or setting, see [undo.md](undo.md) | `Ctrl+z`, `Meta+z` / `Ctrl+Shift+z`, `Meta+Shift+z`, `Ctrl+y` |
| Toggle x-ray | `x` |
| Hide selected | `h` |
| Unhide all (your hides only; pins stay) | `Alt+h` |
| Hide everything not selected | `Shift+h` |
| Toggle model tree / right sidebar ([right-sidebar.md](right-sidebar.md)) | `[` / `]` |
| Focus the tree filter | `Alt+f` (was `/`, now the search bar) |
| Search bar: elements, commands, presets, views, sets, settings, WHERE queries ([search.md](search.md)) | `/`, `Ctrl+k`, `Meta+k` |
| Cheat sheet | `?`, `F1` |
| Command palette | `Ctrl+Shift+k`, `Meta+Shift+k` (was `Ctrl+k`, now the search bar) |
| Presets 1 to 9 (placeholders until the presets plugin replaces them) | `code:Digit1` to `code:Digit9` |
| Top bar modes: Solid, Ghost, Radiograph, Glow, Cutaway ([topbar.md](topbar.md)); pressing a lit mode again switches to Solid | `Shift+code:Digit0` to `Shift+code:Digit4` (`Shift+0` to `Shift+4`) |
| Show or hide the top bar | `Shift+t` |
| Classify: review walk, to confirm classifications ([classify.md](classify.md#review-walk)); while it is open it also takes Enter or Y, 2, E, N (skip; Shift+N the other skip in a type), `?` (flag the next action as unsure, a guess), the arrow keys, `[`, `]`, A, U and Esc; the panel handles these itself | `Shift+r` |
| Revision: review changes between an earlier model and this one, to confirm what differs ([revision.md](revision.md)); while the walk is open it also takes Enter or Y, 2, E, R (reject), N (skip), `?`, the arrow keys, `[`, `]`, A, U, G (ghost), B (bulk rules) and Esc; the panel handles these itself | `Shift+v` |
| Views: open the Views tab on the filter With drawings ([issues.md](issues.md)); the palette also has `issues.open`, `issues.sketches`, `issues.edit`, `issues.done`, and `tool.bcf` / `tool.markup` as aliases of the old drawer actions | `k` |
| Save view; previous / next saved view ([saved-views.md](saved-views.md)) | `Ctrl+Shift+s`; `Shift+PageUp` / `Shift+PageDown` |

The top bar keys avoid the digits (presets), `Alt+<digit>` (views) and the numpad: `Shift+0` to `Shift+4` match by physical key, so they work on layouts where Shift+digit types another symbol. They are actions `topbar.mode.solid`, `topbar.mode.ghost`, `topbar.mode.radiograph`, `topbar.mode.glow`, `topbar.mode.cutaway` and `topbar.toggle`, rebindable like any other.

Other plugins register their own actions with their own keys (for example `b`, `Shift+b`, `p`, `Alt+=`, `Alt+-`, `i`);
they show up in the cheat sheet under their group.

## Walk mode and navigation style

The default style is **BIM**, as in Revit, Navisworks and Solibri: arrows orbit, `Shift`+arrows pan, the mouse pans with the
middle button, the wheel zooms to the cursor ([pointer-modes.md](pointer-modes.md)). The tank keys live in **Walk mode**, which you
enter on purpose.

**Walk mode** (`nav.walk`, `Shift+w`, or the walk button next to the Arrow / Hand toggle on the gizmo, [gizmo.md](gizmo.md)). A chip
"Walk · Esc to exit" shows at the top of the view and the cursor becomes an eye. It is a per-viewer state: it is not in the params,
the share link, a saved view, a preset or a packed page, and a new model leaves it.

| Input in Walk mode | Effect |
| --- | --- |
| `w` / `s`, `ArrowUp` / `ArrowDown` | Walk forward / back along the view direction projected on the horizontal plane (the eye height stays) |
| `a` / `d` | Strafe left / right |
| `ArrowLeft` / `ArrowRight` | Turn the view left / right about the eye (yaw), as in Navisworks |
| `q` / `e` | Lower / raise the eye |
| `Shift` held | 3 times faster (also `Shift+ArrowUp` and the like); `Ctrl` held: 0.25 times |
| Left drag, one finger | Look around from the eye (yaw and pitch, pitch within 85 degrees); no pointer lock, so it works in an iframe and on a phone |
| Wheel | Walk forward / back |
| Click | Still selects |
| `Esc`, the chip, the gizmo button | Leave Walk mode (Esc comes before "clear selection"; an open cheat sheet or palette closes first) |

Speeds scale with the model size (the `move speed` and `orbit speed` settings). The orbit target is kept a fixed distance in front of
the eye, so leaving Walk mode leaves a sane orbit. There is no gravity and no collision, and a high aerial view is a fine place to
start. A walk is one camera step in the undo stack ([undo.md](undo.md)), like a held key. While a fly-through, a script or a 4D film
plays, Walk mode is left and `Shift+w` does nothing. While walking, `Shift+w` is not a toggle: `Shift` with `w` runs forward, whichever key goes down first (`nav.walk` is enabled only outside Walk mode, and the keymap always lists the loose-modifier matches after the exact ones, so the held `w` with `Shift` reaches `nav.forward`).

**Navigation style** (`navigation style` in the `Keyboard` folder, stored with the other keyboard settings in `localStorage`
`xray.keynav`, not in the params or a share link): `BIM` (default) or `Game`. In `Game` the keys `w a s d q e` fly the camera and its
target at all times (the old behaviour), the middle button zooms, and the wheel zooms to the target, as before.

## Focus rules

A list widget is an element with `role="tree"`, `"listbox"` or `"grid"`, or with a `data-keys-own` attribute (the model tree, the
Views list and the Sets list). While focus is inside one, the keymap plugin (`src/plugins/keymap.ts`, predicate in
`src/input/focusOwner.ts`) lets the widget keep its keys:

- Arrow keys, `Home`, `End`, `PageUp`, `PageDown`, `Enter` and `Space`, and `Shift+ArrowUp/ArrowDown`, never reach global actions.
  So `PageUp` in the tree moves the tree cursor instead of changing storey.
- Plain characters stay with the widget when its mode is `all` (default, also `data-keys-own="all"`). `data-keys-own="nav"` (the
  model tree, the Views list, the Sets list) leaves letters to the global keymap; the tree takes only the letters that have no global
  action, see below.
- Chords with `Ctrl`, `Alt` or `Meta`, and every key the widget does not use (`f`, `h`, `x`, `Shift+h`, `[`, `?`, `Shift+ArrowLeft`...),
  still run global actions on the current selection.
- `Escape` in a widget moves focus to the 3D canvas and does nothing else. A second `Escape` (focus is now on the canvas) does what
  it does globally: close overlays, then clear the selection.
- `Tab` is unchanged: it moves browser focus, and means "next selected element" only while focus is on the page or the canvas.
- The canvas has `tabindex="0"`; clicking it focuses it, which changes nothing for the pointer.

### F6 regions

| Action | Keys |
| --- | --- |
| `focus.nextRegion`: 3D canvas, left sidebar, right sidebar, top bar, canvas | `F6` |
| `focus.prevRegion` | `Shift+F6` |

Focus goes to the list widget of the active tab (the model tree, the first row of Sets or Views), the active right sidebar pane, the
lit mode button of the top bar, or the canvas. A collapsed sidebar or a hidden top bar is skipped (open it with `[` or `]` first). The
region shows a focus ring (`data-region-ring`) until focus leaves it or a pointer is used. F6 also works from inside a text
field such as the tree filter (it is the one global key that does; it types nothing). Both actions are in the cheat sheet and rebindable; help texts: `Keyboard/Next region`,
`Keyboard/Previous region` in `src/ui/helpText.ts`.

### Model tree keys

The tree (`src/ui/treeView.ts`, pure logic in `src/ui/treeKeys.ts`) is one Tab stop. Its active row is tracked by key, so it survives
the virtualised window; the scroller has `aria-activedescendant` and the active row `.act` (a ring only while the tree has focus,
separate from the `.sel` selection fill).

| Keys | Effect |
| --- | --- |
| `ArrowUp` / `ArrowDown`, `Home` / `End`, `PageUp` / `PageDown` | Move the active row (a page is the visible rows minus one) |
| `ArrowRight` | Open a closed row; on an open row go to its first child |
| `ArrowLeft` | Close an open row; else go to the parent |
| `*` | Open all siblings of the active row |
| `Enter`, `Space` | Select the active row's elements, replacing the selection (a click on it; a storey or class selects all its elements) |
| `Ctrl+Space` | Toggle the row's elements in the selection |
| `Shift+ArrowUp` / `Shift+ArrowDown` | Move and add the new row's elements to the selection |
| Letters | Type-ahead: jump to the next row whose name starts with the typed text (buffer resets after 500 ms) |

Type-ahead rule: a letter starts type-ahead only if no enabled global action is bound to that key (so `d`, `t`, `Shift+i` work; `f`, `h`,
`x`, `i`, `Alt+f` stay global). Once a buffer is running (the last letter was less than 500 ms ago) every character joins it, so
`Shift+I` then `fcDoor` finds `IfcDoor`. Repeating one letter cycles through the rows with that initial. Use `Shift+<letter>` for a
letter that is bound globally. Alt chords follow the same rule (unbound ones type-ahead).

The visibility (eye) button of a row has no Tab stop: `h`, `Shift+h` and `Alt+h` act on the selection. Selecting an element in 3D
(click, search, Tab) opens its storey and class, scrolls the row into view and makes it the active row, without moving focus.

## Views and coordinates

Viewer space is Y up. The IFC front (looking north) is the camera on +Z. Top looks along -Y. Views use the cinematic
fly-to when the plugin is present (400 ms), else an eased tween, else jump at once (`smooth moves` off).
The orthographic toggle is an approximation: a 2 degree field of view with the camera dollied out so the framing stays.
There is no renderer change, so depth precision and the far plane are adjusted but perspective effects are not exactly zero.

## Settings (panel folder `Keyboard`)

`keyboard navigation` (master switch for the Navigation and Views keys), `orbit speed (deg/s)`, `pan speed`,
`move speed`, `invert vertical`, `smooth moves`, `navigation style` (BIM or Game), and the buttons `Shortcuts (?)`, `Edit shortcuts`,
`Command palette (Ctrl+Shift+K)`, `Reset shortcuts`. Speeds scale with the model size (fly rate is 0.2 model diagonals per
second times `move speed`; pan is 0.5 screen heights per second times `pan speed`). Settings persist per browser in
`localStorage` `xray.keynav`.

## Rebinding

`Edit shortcuts` opens a list of all actions. Click a key cell, press the new keys (Backspace removes the cell, Escape
cancels). Cells that share a chord with another action turn red and the conflict is listed at the top (also logged once
to the console as `[keymap] conflict`). `Export JSON` and `Import JSON` write and read a `xray-keymap/1` document.
Overrides persist in `localStorage` `xray.keymap` as `{ actionId: [chords] }` (an empty list unbinds the action) and are
the `keymap` section of the exported viewer parameters. When two actions share a chord, the first enabled one runs.

## Command palette

`Ctrl+Shift+k` lists every action plus every button and checkbox of the parameter panel (folder path shown, key binding shown
for actions). Fuzzy ranking favours prefixes, word starts and consecutive letters; recently used entries come first
(`localStorage` `xray.palette.recent`). Arrow keys choose, Enter runs, Escape closes.

## Registering an action

```ts
registerAction({ id: 'my.thing', label: 'Do my thing', group: 'Modes', keys: ['Alt+t'], run: (app) => { ... } });
```

Add `hold(app, dt, mods)` for a held key, `repeat: true` to let auto-repeat run a discrete action, `enabled(app)` to
let the key fall through when the action does not apply.
