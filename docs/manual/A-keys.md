# Appendix A. Keyboard reference and shortcut editor

Press `?` or `F1` in the viewer for the cheat sheet. It lists the keys that are live right now, so it is always right for your
build and your changes. This appendix is the same list on paper, for the viewer as it ships.

## How keys are written

- `Ctrl+`, `Alt+`, `Shift+` and `Meta+` (Cmd on a Mac) come before the key. `Shift+h` is the key `h` held with Shift.
- Letters do not care about case. `h` is the key without Shift.
- `code:Numpad7` means the physical key, not the character. `code:Digit1` is the top-row `1`.
- Keys do nothing while you type in a text box. `Escape` leaves the box.
- Keys do nothing while the cheat sheet, the command palette or the shortcut editor is open.
- Ctrl, Alt and Meta must match exactly. Shift must match exactly too, except for keys that are one symbol (`?`, `+`, `[`, `=`), where your keyboard layout decides.

## Moving the camera

Hold the keys to keep moving. Hold `Ctrl` to go slow (a quarter speed).

| Action | Keys |
| --- | --- |
| Orbit left, right | `ArrowLeft`, `ArrowRight` |
| Orbit up, down | `ArrowUp`, `ArrowDown` |
| Pan left, right, up, down | `Shift+ArrowLeft`, `Shift+ArrowRight`, `Shift+ArrowUp`, `Shift+ArrowDown` |
| Fly forward, back | `w`, `s` |
| Fly left, right | `a`, `d` |
| Fly down, up | `q`, `e` |
| Zoom in (15 %) | `=`, `+`, `code:NumpadAdd` |
| Zoom out (15 %) | `-`, `code:NumpadSubtract` |
| Storey up, down | `PageUp`, `PageDown` |
| Next, previous selected element | `Tab`, `Shift+Tab` |
| Previous, next camera position (history of 50) | `Alt+ArrowLeft`, `Alt+ArrowRight`, or mouse buttons 4 and 5 |

## Standard angles and framing

These frame the selection, or the whole model when nothing is selected.

| Action | Keys |
| --- | --- |
| Front | `code:Numpad1`, `Alt+code:Digit1` |
| Back | `Ctrl+code:Numpad1`, `Alt+Shift+code:Digit1` |
| Right | `code:Numpad3`, `Alt+code:Digit3` |
| Left | `Ctrl+code:Numpad3`, `Alt+Shift+code:Digit3` |
| Top | `code:Numpad7`, `Alt+code:Digit7` |
| Bottom | `Ctrl+code:Numpad7`, `Alt+Shift+code:Digit7` |
| Isometric | `code:Numpad0`, `Alt+code:Digit0` |
| Perspective or orthographic | `code:Numpad5`, `Alt+code:Digit5` |
| Frame the selection, or everything when nothing is selected | `f` |
| Frame the selection | `.`, `code:NumpadDecimal` |
| Frame everything | `Home` |
| Show or hide the view cube and section strip | `v` |

Roll 90 degrees and turn 90 degrees (the view cube buttons) have actions with no key. Bind them in the editor.

## Selecting and hiding

| Action | Keys |
| --- | --- |
| Clear the selection (closes open overlays first) | `Escape` |
| Select all visible | `Ctrl+a` |
| Invert the selection | `Ctrl+i` |
| Select all of the same class | `Alt+s` |
| Arrow mode: click selects, drag draws a selection box | `r` |
| Hand mode: drag orbits | `g` |
| Hide selected | `h` |
| Show all your hides again (pins stay) | `Alt+h` |
| Hide everything that is not selected | `Shift+h` |
| Undo the last camera move, selection or setting | `Ctrl+z`, `Meta+z` |
| Redo | `Ctrl+Shift+z`, `Meta+Shift+z`, `Ctrl+y` |

## Looks, modes and cuts

| Action | Keys |
| --- | --- |
| Toggle x-ray | `x` |
| Top bar mode Solid, Ghost, Radiograph, Glow, Cutaway | `Shift+0`, `Shift+1`, `Shift+2`, `Shift+3`, `Shift+4` |
| Show or hide the top bar | `Shift+t` |
| Apply preset 1 to 9 | `1` to `9` (top-row digits) |
| Behind-only on or off | `b` |
| Behind-only: next front treatment | `Shift+b` |
| Peelback on or off | `p` |
| Peelback: grow, shrink the window | `Alt+=`, `Alt+-` |
| Imaging: next style (standard, radiograph, MRI) | `m` |
| Section box on or off | `c` |
| Section box: fit to the selection | `Shift+c` |
| Section plane on or off | `Alt+c` |
| Hover card on or off | `i` |

Pressing a lit top bar mode again switches to Solid. Solid itself does nothing when pressed again.

## Panels, search and review

| Action | Keys |
| --- | --- |
| Search bar | `/`, `Ctrl+k`, `Meta+k` |
| Cheat sheet | `?`, `F1` |
| Command palette | `Ctrl+Shift+k`, `Meta+Shift+k` |
| Focus the filter of the model tree | `Alt+f` |
| Show or hide the model tree | `[` |
| Show or hide the right sidebar | `]` |
| Show or hide the tool strip | `t` |
| Open the Issues tab on Sketches | `k` |
| Save a view | `Ctrl+Shift+s` |
| Previous, next saved view | `Shift+PageUp`, `Shift+PageDown` |
| Classify: start the review walk | `Shift+r` |
| Revision: start the review walk | `Shift+v` |

> Check: The cheat sheet in keyboard.md says `k` opens "Sketches"; the manual's word list says "drawing" and "issue". Confirm what the key opens in the final Views and Issues UI (chapters 13 to 15).

### Keys inside a review walk

While a walk is open it takes its own keys. They are not rebindable here.

| Key | Classification walk | Revision walk |
| --- | --- | --- |
| `Enter`, `y` | Accept | Accept |
| `2` | Accept with the other classification | Accept with the other classification |
| `e` | Edit the classification, then accept | Edit the classification, then accept |
| `n` | Skip (`Shift+n` skips the rest of the item) | Skip (`Shift+n` skips the rest of the item) |
| `?` | Mark the decision unsure | Mark the decision unsure |
| `ArrowLeft` | Back | Back |
| `[`, `]` | Step to another element of the item | Step to another element of the item |
| `a` | All alike, or this element only | All alike, or this element only |
| `u` | Undo the last decision | Undo the last decision or bulk rule |
| `Escape` | Close | Close |
| `r` | | Reject (dispute) |
| `g` | | Cycle the ghost: both, head only, base only |
| `b` | | Open the bulk rules |

In the revision walk, `ArrowRight` also skips.

> Check: classification walk keys are summarised in keyboard.md ("Enter or Y, 2, E, N, ?, arrows, [, ], A, U and Esc"); the revision column is from `src/revision/keys.ts`. Confirm the two tables once chapters 18 and 20 are written.

## Actions without a key

These are in the command palette (`Ctrl+Shift+k`) and can be given a key. A few examples: `bcf.open`, `bcf.export`,
`cleanup.preview`, `cleanup.hide`, `cleanup.restore`, `penetrations.analyse`, `pointcloud.open`, `pointcloud.deviation`,
`clearance.toggle`, `measure.clear`, `views.play`, `ifc.save`, `ifc.saveCleaned`, `xr.vr`, `xr.ar`, `xr.field`.

## The cheat sheet

`?` or `F1` opens it. Type in the search box to filter. **Edit shortcuts** closes it and opens the shortcut editor.

## The command palette

`Ctrl+Shift+k` lists every action and every button and switch of the settings panel, with the folder shown and the key where
there is one. Type a few letters. The best matches are those that start with your letters, start a word, or have your letters in
a row. What you used lately comes first. Arrow keys choose, `Enter` runs, `Escape` closes.

## The shortcut editor

1. Open it with **Edit shortcuts** in the **Keyboard** folder of the settings panel, or from the cheat sheet.
2. Click a key cell, then press the new keys. `Backspace` removes the key. `Escape` cancels.
3. A cell that shares a chord with another action turns red, and the clash is listed at the top. When two actions share a chord, the first one that is enabled runs.
4. **Add key cell** gives an action one more key. **Reset row** restores one action. **Reset all** restores everything.
5. **Filter box** narrows the list. **Export JSON** saves your keys as an `xray-keymap/1` file. **Import JSON** reads one.

Your changes are kept in this browser. They are also the `keymap` part of an exported parameters file. An empty list for an
action unbinds it.

## Keyboard settings

The **Keyboard** folder has: **keyboard navigation** (a master switch for the camera keys), **orbit speed (deg/s)**, **pan speed**,
**move speed**, **invert vertical**, **smooth moves** (off makes the standard angles jump), and the buttons **Shortcuts (?)**,
**Edit shortcuts**, **Command palette (Ctrl+Shift+K)** and **Reset shortcuts**. Speeds scale with the size of the model.

The standard angles use a 400 ms glide. The orthographic switch is an approximation: a very narrow field of view with the camera
moved back, so perspective effects are close to zero, not exactly zero.
