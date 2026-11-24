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
| Walk mode on / off, see [Walk mode](#walk-mode-and-navigation-style) | `Shift+w`; `Esc` leaves |
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
| `Esc`, `Shift+w`, the chip, the gizmo button | Leave Walk mode (Esc comes before "clear selection"; an open cheat sheet or palette closes first) |

Speeds scale with the model size (the `move speed` and `orbit speed` settings). The orbit target is kept a fixed distance in front of
the eye, so leaving Walk mode leaves a sane orbit. There is no gravity and no collision, and a high aerial view is a fine place to
start. A walk is one camera step in the undo stack ([undo.md](undo.md)), like a held key. While a fly-through, a script or a 4D film
plays, Walk mode is left and `Shift+w` does nothing. A held `w` followed by `Shift` is a sprint; `Shift` then `w` toggles the mode.

**Navigation style** (`navigation style` in the `Keyboard` folder, stored with the other keyboard settings in `localStorage`
`xray.keynav`, not in the params or a share link): `BIM` (default) or `Game`. In `Game` the keys `w a s d q e` fly the camera and its
target at all times (the old behaviour), the middle button zooms, and the wheel zooms to the target, as before.

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
