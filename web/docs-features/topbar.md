# Top bar

A thin strip (32 px) along the top of the canvas (`#xray-topbar`, inside `#stage`, so it spans the stage between the model tree and the parameter dock). On the left a segmented control with four visualisation modes; to the right a host element, `#xray-topbar-search`, that takes the rest of the width. The search bar ([search.md](search.md), `src/plugins/awesomeBar.ts`) mounts into it; the top bar itself leaves it empty. Code: `src/ui/topBar.ts` (pure model and DOM), `src/plugins/topBar.ts`. Tests: `tests/topbar.test.ts`. Smoke: `SMOKE_PORT=5661 node bench/smoke-topbar.mjs` (screenshots `bench/topbar-*.png`).

## The four modes

A mode is a thin wrapper: a click applies a built-in preset through `window.__xrayPresets.apply`, so modes, presets, saved views, the share link and `xray-pack --preset` stay one thing.

| Mode | Key | Preset | What it sets |
| --- | --- | --- | --- |
| Ghost | `Shift+1` | `coordination` | The classic sightline x-ray, the factory look and the baseline: x-ray on, sightlines, far mode and display at their defaults, view modes, imaging, section and clearance off, bloom, edge glow and auto orbit off. |
| Radiograph | `Shift+2` | `radiograph` | `imaging.style radiograph`, `palette classic`, bloom and edge glow off: the model as a medical x-ray picture, the selection as bright bone. See [imaging.md](imaging.md). |
| Glow | `Shift+3` | `focus-glow` (new) | `cinematic.edgeGlow` on with `glowScope focus`, plus the selective `bloom`: the selection gets a soft halo and a bright outline; the context stays ghosted. |
| Cutaway | `Shift+4` | `peel-only` | `viewModes.peel` enabled with `outside solid`, `sightlines.alphaMax 1`, bloom and edge glow off, frames the selection: a window shaped like the selection is cut through whatever blocks it and everything else stays solid. |

Why `peel-only` for Cutaway. Tried on `fzk-haus`, window 22, from outside: the peel window with solid surroundings shows the selection inside the room with a clean edge, and the model stays readable. Peelback (the same window with ghosted surroundings) leaves the roof timbers as a grid of lines over the window. Behind-only plus peel throws away everything in front of the selection and leaves a floating wedge. A section box fitted to a small selection (`section-focus`) clips the model down to the window and hides the context altogether. A larger selection (a room, a storey) also works with `section-focus`; that preset stays on key `9`.

## The highlight follows what is applied

The active mode is the one whose preset the presets engine reports as active (`window.__xrayPresets.active()`), polled four times a second:

- Click a mode, press `Shift+1` to `Shift+4`, pick the preset in the drawer, press key `1` or `7`, or restore a saved view taken under a mode preset (the views plugin calls `markActive`): the bar highlights the matching mode (`aria-pressed="true"`).
- The engine compares a hash of the collected parameters once a second (see presets.md, "The active mark"); when any setting differs the mark and the highlight clear. The bar does not show "modified".
- Another preset (`hide-blockers`, `mri-scan`, a user preset) highlights nothing.
- At start, when nothing was changed after the first model (no `#p=` link, no boot preset or params), the bar marks `coordination` (via `markActive`), so Ghost is lit for the factory look. The hash for this check ignores `classStyles` and `materialAliases`, which load from `xray.config.json` after the model.
- Clicking the active mode again returns to the normal shaded view: it applies `plain` (x-ray off; view modes, imaging, section and clearance reset). Nothing is highlighted afterwards.

## Visibility

- Parameter `topBar.visible` (params section `topBar`, default on; not in the share link, not stored in saved views, ignored by the presets hash). Panel folder `Top bar`, control `Show top bar`; key `Shift+t`; `window.__xrayTopBar.setVisible(v)`. The choice is remembered in localStorage `xray.topbar`.
- Hidden in a kiosk page (`xray-pack --kiosk`), with `--no-topbar` (boot `topBar: false`), and while a WebXR session runs. `window.__xrayTopBar.shown()` tells whether it is on screen.

## Layout

- The bar registers its rect with the shared overlay (`ov.reserve('topbar', ...)`), and the overlay counts `#xray-topbar` as a top inset, so measure labels, penetration markers, BCF pins, callouts and legends stay below it.
- The tool strip and its drawer start below the bar (CSS variable `--tb-h`, set on `body` together with the class `tb-on`; `0px` when hidden). The status bar, the gizmo and the dock are unchanged. On a phone (max-width 700 px) the model tree and the dock are overlays; they start below the bar too.
- Phone (390 x 844): the modes become 30 px icon-only buttons; the label stays as the accessible name (`aria-label="Radiograph (Shift+2)"`); the search host shrinks (minimum 60 px) but stays.

## Scripting

`window.__xrayTopBar = { modes(), active(), apply(id), setVisible(v), visible(), shown(), host }`. `apply('radiograph')` does what a click does, including "again returns to normal". Actions: `topbar.mode.ghost`, `topbar.mode.radiograph`, `topbar.mode.glow`, `topbar.mode.cutaway` (group Modes) and `topbar.toggle` (group Panels).

## Plugin order

`topBarPlugin` is the first plugin: it creates the bar and the search host before the other plugins install (the search plugin mounts into the host), and its first `onModel` records the factory settings hash before any other plugin changes the state.

## Limits

- The highlight is as precise as the presets engine's mark: a setting that changes by itself (a running animation that writes into a section) clears it.
- A user preset that duplicates a mode preset does not light the mode (the match is by preset id). A `public/xray.presets.json` entry that replaces a built-in id (for instance `radiograph`) changes what the mode does, because the mode applies whatever that id is.
- Hidden during XR is checked by polling `window.__xrayXr.manager.active`; a session started by another path that does not set it keeps the bar.
