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

| Action | Keys |
| --- | --- |
| Orbit left / right | `ArrowLeft` / `ArrowRight` |
| Orbit up / down | `ArrowUp` / `ArrowDown` |
| Pan left / right / up / down | `Shift+ArrowLeft/Right/Up/Down` |
| Fly forward / back | `w` / `s` |
| Fly left / right | `a` / `d` |
| Fly down / up | `q` / `e` |
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
| Clear selection (closes overlays first) | `Escape` |
| Select all visible | `Ctrl+a` |
| Invert selection | `Ctrl+i` |
| Select all of the same class | `Alt+s` |
| Toggle x-ray | `x` |
| Hide selected | `h` |
| Unhide all (your hides only; pins stay) | `Alt+h` |
| Hide everything not selected | `Shift+h` |
| Toggle model tree / parameter panel | `[` / `]` |
| Focus the tree filter | `Alt+f` (was `/`, now the search bar) |
| Search bar: elements, commands, presets, views, sets, settings, WHERE queries ([search.md](search.md)) | `/`, `Ctrl+k`, `Meta+k` |
| Cheat sheet | `?`, `F1` |
| Command palette | `Ctrl+Shift+k`, `Meta+Shift+k` (was `Ctrl+k`, now the search bar) |
| Presets 1 to 9 (placeholders until the presets plugin replaces them) | `code:Digit1` to `code:Digit9` |
| Top bar modes: Ghost, Radiograph, Glow, Cutaway ([topbar.md](topbar.md)); pressing the active mode again returns to the normal view | `Shift+code:Digit1` to `Shift+code:Digit4` (`Shift+1` to `Shift+4`) |
| Show or hide the top bar | `Shift+t` |
| Classify: review walk, to confirm classifications ([classify.md](classify.md#review-walk)); while it is open it also takes Enter or Y, 2, E, N, the arrow keys, `[`, `]`, A, U and Esc | `Shift+r` |
| Save view; previous / next saved view ([saved-views.md](saved-views.md)) | `Ctrl+Shift+s`; `Shift+PageUp` / `Shift+PageDown` |

The top bar keys avoid the digits (presets), `Alt+<digit>` (views) and the numpad: `Shift+1` to `Shift+4` match by physical key, so they work on layouts where Shift+digit types another symbol. They are actions `topbar.mode.ghost`, `topbar.mode.radiograph`, `topbar.mode.glow`, `topbar.mode.cutaway` and `topbar.toggle`, rebindable like any other.

Other plugins register their own actions with their own keys (for example `b`, `Shift+b`, `p`, `Alt+=`, `Alt+-`, `i`);
they show up in the cheat sheet under their group.

## Views and coordinates

Viewer space is Y up. The IFC front (looking north) is the camera on +Z. Top looks along -Y. Views use the cinematic
fly-to when the plugin is present (400 ms), else an eased tween, else jump at once (`smooth moves` off).
The orthographic toggle is an approximation: a 2 degree field of view with the camera dollied out so the framing stays.
There is no renderer change, so depth precision and the far plane are adjusted but perspective effects are not exactly zero.

## Settings (panel folder `Keyboard`)

`keyboard navigation` (master switch for the Navigation and Views keys), `orbit speed (deg/s)`, `pan speed`,
`move speed`, `invert vertical`, `smooth moves`, and the buttons `Shortcuts (?)`, `Edit shortcuts`,
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
