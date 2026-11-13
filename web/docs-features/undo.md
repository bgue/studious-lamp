# Undo and redo: view, selection and settings

One session-only stack for three kinds of change. `Ctrl+Z` (or `Cmd+Z`) undoes, `Ctrl+Shift+Z` and `Ctrl+Y` redo, and the
Undo and Redo buttons under the view cube do the same. A button is disabled when there is nothing to undo or redo; its tooltip
and label name the step: "Undo zoom", "Undo selection", "Undo edgeAlpha". The stack is not saved, not in the params, a share
link, a saved view or a preset, and is cleared when a model is installed.

| Kind | Recorded | Undo |
| --- | --- | --- |
| Camera view | When the camera has been still for 400 ms (longer on slow frames, up to 1 s). A whole wheel gesture, an orbit drag with its damping, a cube click, Home, fit or frame, a view preset recall or a saved view is one entry. Named `zoom`, `pan`, `orbit`, `projection` or `view`. Drift under 0.3 % of the distance is not an entry. | Eases the camera back (240 ms), or snaps when "smooth moves" is off. Switches the orthographic approximation back if the entry changed it. |
| Selection | Every change of the selection set, a box select included. | Selects the previous set (an empty set clears). |
| Setting | Every change of a control of the parameter panel, before to after, named for the control. A slider drag is one entry (changes of one control less than 600 ms apart merge, and a drag that ends where it started leaves no entry). Several controls changing together (a preset) are one entry, "N settings". | Sets each control back through its own change handler, so the picture follows. |

It watches state, it does not hook the controls, so a key, a button, a preset or a script is seen like a drag.

## What it ignores

- What its own undo and redo apply (the `UndoStack` is "applying" while they run, and the watchers are re-baselined).
- Everything during the first 1.5 s after a model is installed (a model load, a `#p=` share link, a boot preset, camera or
  selection): the plugin runs last, so what the boot config changed is the starting state. The stack is cleared then too.
- Read-only status lines, buttons and the model picker.
- Not recorded: settings that live outside the parameter panel (for example some toolbar-only toggles) and markup, which has
  its own history (`src/markup/history.ts`).

## Keys

| Action | Keys |
| --- | --- |
| Undo (`undo.undo`) | `Ctrl+z`, `Meta+z` |
| Redo (`undo.redo`) | `Ctrl+Shift+z`, `Meta+Shift+z`, `Ctrl+y` |

The keys are not taken: in an input, textarea, select or contenteditable (the keymap does not run there, so the browser undoes
the typing); while a sketch is being edited (the drawing toolbar is up or a drawing tool is chosen, `window.__xrayMarkup.editing`: the markup history owns the keys); while
the keyboard focus is inside the classification review walk panel (`.xrw`; it has its own `U` and ignores Ctrl). Another
dialog open (palette, cheat sheet) also blocks them, like every key.

## Limits and the "hard to unzoom" fix

The stack holds 100 entries; the oldest go first. A new change clears the redo list.

Zooming out was hard in the orthographic approximation (the 2 degree field of view): the zoom range and the far plane stayed
in perspective units while the camera moves back about 24 times, so Home (and the wheel) stopped at a third of the model and
the model vanished behind the far plane when zooming out. `XrayRenderer.frameAll` and the projection toggle now scale the
distance limits and the far plane with the camera distance. In perspective the range is unchanged: 0.02 to 20 model radii from
the target, 5 % per wheel notch. Home (gizmo, `Home` key) frames the whole model, is one undo entry and `Ctrl+Z` brings back
the view you left.

## Scripting

`window.__xrayUndo = { undo(), redo(), canUndo, canRedo, undoLabel, redoLabel, list(), clear() }`; `list()` returns
`{ undo: [{ kind, label }], redo: [...] }`, oldest first, the next redo last.

## Files and tests

- `src/undo/stack.ts` (the stack: coalescing, cap, redo, self-applied changes), `src/undo/viewPose.ts` (poses, the move name,
  easing), `src/plugins/undo.ts` (watchers, apply, keys, API), the buttons in `src/plugins/gizmo.ts`.
- Tests: `tests/undo-stack.test.ts`. Smoke test: `SMOKE_PORT=5701 node bench/smoke-pointer-undo.mjs`.
