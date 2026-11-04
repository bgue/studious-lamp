# QA wave 5: integration pass (2026-11-04)

Integration check of the four features that landed together in `1010366` (status bar, edge glow scope, cleanup units,
criteria sets, BCF pins and callouts, view cube and section tool). Headless Chromium (Playwright, swiftshader) against
`bench/vite.smoke.config.mjs` dev servers; console errors, warnings and page errors were collected at every step
(Chromium's `GPU stall due to ReadPixels` notes, caused by the scripts' own canvas reads, were ignored). Screenshots:
`bench/qa5-*.png` (10 files, palette-quantised, 0.6 MB).

Result: **8 integration bugs fixed** (plus 2 stale smoke assertions and 2 requested gizmo behaviours); every smoke
script passes.

## Checks

| # | Area | Check | Result |
| --- | --- | --- | --- |
| 1 | BCF pins | `smoke-section` "cleared section matches the start" (stray pin `1` after the BCF round trip) | **fixed** (pins follow the drawer, fix 1), then pass (mean 0.012) |
| 2 | Layout 1400x860, 1024x700, 390x844 | Rects of status bar, gizmo, clearance legend, point cloud legend, tool drawer, dock, strip, hover card, BCF pins, measure labels; no horizontal scroll | **fixed** (fixes 2-5), then no overlap that hides a control at any size (`qa5-layout-1400-drawer.png`, `qa5-layout-1024-drawer.png`, `qa5-layout-phone.png`); with a drawer open on a phone the drawer covers the legends, as it covers the view |
| 2 | Phone | Tree and dock panels open over the gizmo (not under it); the gizmo opens inside the screen | pass (`qa5-phone-gizmo-open.png`) |
| 3 | Smokes | All 26 `smoke-*.mjs`, `help-smoke.mjs`, `single-file.mjs` (after `npm run bundle`), distinct ports | pass after fixes; see "Smoke scripts" |
| 4 | Keys | `v` toggles the gizmo; `__keymap.conflicts()` is empty; `smoke-keys` | pass |
| 4 | Presets | `section-focus` applied: the strip lights Box within one refresh (400 ms) | pass |
| 4 | BCF viewpoint planes | Planes from a viewpoint show in the strip | **fixed** (fix 6): Clear turns amber with "Clear the 7 clip planes of the BCF viewpoint", X/Y/Z/Box not lit (`qa5-gizmo-bcf-planes.png`) |
| 4 | BCF vs section | Clear viewpoint after the section tool took over; section plane that was on before a viewpoint | **fixed** (fix 7), then pass |
| 4 | Reset to defaults | Gizmo hidden, `__xrayParams.reset()` shows it again | pass |
| 4 | XR / imaging | `smoke-xr`, `smoke-imaging` with the gizmo present | pass |
| 5 | Criteria sets | Right-click Class in the properties -> "Save as criteria set..." -> editor with `class = 'IfcWallStandardCase'` -> Save; in localStorage; persists after reload; Export JSON; Import on `building` re-evaluates (0 members there, 13 on fzk-haus) | pass (`qa5-criteria-saved.png`, `qa5-criteria-building.png`) |
| 5 | Params | collect -> apply -> collect identical (apart from `exportedAt`), no bad keys | pass |
| 6 | Edge glow | synth5k, OIT on, glow on, scope focus -> near -> all -> focus with the status bar: no console output; frame time (swiftshader, loaded machine) 996 / 1048 / 1383 ms, so `all` costs about 1.4x `focus` | pass (`qa5-glow-all-synth5k.png`) |
| 7 | Single file | `npm run bundle` (5.48 MB); building, plumbing, fzk-haus from `file://`: no banner element, no requests, no console output; status bar details button lists the model credits and "This file" at 1280 and 390 px | pass (`qa5-single-file-credits.png`) |
| 8 | Gizmo ring | Drag from the ring towards its centre: tilt rises in 15 degree steps then holds (0..15) instead of racing | **changed** (fix 8b) |
| 8 | Gizmo roll | Roll the front view, then a mouse orbit: camera up eases back to +Y, picture upright | **changed** (fix 8a) (`qa5-orbit-unrolled.png`) |
| - | Unit tests | `npm run typecheck`, `npm test` | pass, see the end |

## Fixes

1. **Stray BCF pins over the model.** Pins were drawn whenever a topic had one, also with the BCF drawer closed and no
   viewpoint applied, so a pin `1` stayed over the model after any BCF round trip. Now pins show while the BCF drawer is
   open (filtered as before, `Show pins` toggles them), and with it closed only the pin of the topic whose viewpoint is
   applied; `Clear viewpoint` removes it. `src/bcf/controller.ts:695` (`setDrawerOpen`), `:709` (`pinnedTopics`),
   `src/bcf/ui.ts:352` and `:716`; docs `docs-features/bcf.md`, help text `Show pins`. Commit `9101c3e`, `af607df`.
2. **Legends under the gizmo and the status bar.** The clearance and point cloud legends sat in the bottom-right corner,
   under the new gizmo (z-index 12 over the SVG overlay), the clearance legend's last 10 px under the status bar, and both
   legends on top of each other. The overlay now tracks the chrome over the canvas edges and the gizmo box every frame
   (`src/ui/overlay.ts:154` `refreshChrome`), and `legendSpot` (`src/ui/overlay.ts:80`) places a legend left of the
   gizmo, or above it when there is no room, in one stacked column (`src/measure/clearanceTool.ts:173`,
   `src/pointcloud/controller.ts:631`). Unit tests in `tests/toolbar-overlay.test.ts`. Commit `7484a53`.
3. **Status bar (and its red messages) hidden under an open tool drawer.** The drawer ran to the bottom of the stage over
   the left part of the status bar; on a phone it covered all of it. The drawer now ends above the status bar
   (`src/ui/toolbarView.ts:25`). Commit `7484a53`.
4. **BCF pins and edge markers under the chrome.** Off-screen pins became edge markers 16 px from the canvas edge, i.e.
   under the status bar or the tool strip/drawer. A pin under the chrome or off screen is now an edge marker inside the
   free view (`src/bcf/annotate.ts:248`, insets from `src/bcf/pins.ts:173`). Unit test in `tests/bcf-markup.test.ts`.
   Commit `7484a53`.
5. **Gizmo under the tool drawer.** At 1024 px a drawer covered the section strip and half the cube; on a phone the cube
   button sat on the drawer. `fitLayout` (`src/plugins/gizmo.ts:487`) drops the strip, then shows only the cube button
   (which opens the gizmo over the drawer until `-` or the drawer closes), then hides, without touching the saved state.
   Commit `7b49f00`.
6. **BCF clip planes invisible in the section strip.** With viewpoint planes in force the strip showed the section
   settings (for example X lit while BCF planes cut the model). New `SectionApi.foreignPlanes()`
   (`src/plugins/section.ts:170`); the strip marks Clear amber with the plane count and lights nothing else
   (`src/plugins/gizmo.ts:390`). Commits `9101c3e`, `7b49f00`.
7. **Clear viewpoint wiped the section tool's planes.** After a viewpoint, turning on a section plane and then
   `Clear viewpoint` set the renderer planes to null; the section plugin then saw foreign planes and stopped pushing, so
   X stayed lit with nothing cut. BCF now clears only its own planes (renderer `clipVersion`,
   `src/bcf/controller.ts:405`), and the section plugin takes the planes back when foreign planes go away
   (`src/plugins/section.ts:194`), so a section that was on before a viewpoint returns after `Clear viewpoint`.
   Commit `9101c3e`.
8. Gizmo behaviours asked for by the gizmo agent:
   a. **Rolled orbit.** A rolled view eases back to world up (160 ms, or at once with smooth moves off) as soon as a
      left-button drag starts on the canvas (`src/plugins/gizmo.ts:545` `startUnroll`, `:565` `unrollFrame`).
   b. **Ring sensitivity.** The tilt angle is the pointer's direction from the ring's projected centre, matched on the
      projected ring (ellipse) sampled at drag start (`ellipseAngle`, `src/gizmo/maths.ts:263`; used in
      `src/gizmo/planeHandles.ts:184` and `:215`), with a hold zone of 40 % of the ring radius in that direction. Unit
      tests in `tests/gizmo-maths.test.ts`. Commits `7b49f00`, `d833148`.

Stale smoke assertions (the new behaviour is correct): `smoke-sidebar` read the property values with the new menu
button glyph (`.props-grid dd` -> `.pv-t`) and the old sets markup (`.set .name`, Apply button -> one-line `.set-row`
with the name as the apply button), commit `c4d1f51`. It also assumed no right dock (older than wave 5) and a fixed
500 ms for the collapse, commit `20d8065`.

## Smoke scripts

All run with their own vite on distinct ports. On the first parallel pass the 4-core box ran at load 7 to 14 and
`smoke-imaging`, `smoke-oit`, `smoke-viewmodes` (900 s limit), `smoke-layers` (page load timeout) and one measure-label
check in `smoke-tools` timed out; each passed when re-run with fewer jobs at once.

| Script | First pass (parallel, partly before the fixes) | Final |
| --- | --- | --- |
| `smoke-section` | FAIL: cleared section vs start (stray pin) | pass (mean 0.012) |
| `smoke-sidebar` | FAIL: stale selectors and dock width | pass (assertions updated) |
| `smoke-gizmo` | pass | pass (after all gizmo changes) |
| `smoke-bcf`, `smoke-bcf-markup` | pass | pass |
| `smoke-keys` | pass | pass (one load flake on `w` held 300 ms, then pass; no conflicts) |
| `smoke-tools` | measure label not drawn within 400 ms (load) | pass |
| `smoke-imaging`, `smoke-oit`, `smoke-viewmodes`, `smoke-layers` | timeout under load | pass |
| `help-smoke` | pass | pass (0 missing texts, 0 `[help]` warnings) |
| `smoke-presets`, `smoke-cleanup`, `smoke-open-file`, `smoke-cinematic2` | pass | pass |
| `smoke-dock`, `smoke-hover`, `smoke-pointcloud`, `smoke-xr` | pass | pass |
| `smoke-cinematic`, `smoke-cinematic-explode`, `smoke-cinematic-ghost`, `smoke-pack`, `smoke-render`, `smoke-scope` | pass | (not affected) |
| `single-file.mjs` (building, plumbing, fzk-haus) | pass | pass: no requests, no console output |

## Known issues (not fixed)

- Reset to defaults restores the gizmo's `{ visible, collapsed }` as they were after the first model, which comes from
  localStorage: a gizmo hidden before the page loaded stays hidden after Reset (same for every plugin section).
- Pins and annotations that point to the bottom-right corner can sit under the gizmo (the gizmo is not an inset: that
  would shrink the whole right edge). The hover card (a transient tooltip, z-index 40) may lie over the dock rail.
- With a tool drawer open on a phone, the legends and most of the view are under the drawer.
- The ring's hold zone keeps the tilt while the pointer crosses the centre; a full turn needs a drag around the ring.
- Measurement labels and BCF callouts are drawn where their points project; they can fall under the gizmo or a drawer.
- Under heavy load (several swiftshader pages at once) some smoke checks with fixed waits time out; they pass when run
  one or two at a time.

## Tests

`npm run typecheck` passes; `npm test`: 76 files, 1010 passed + 1 skipped (was 1003 + 1 before this pass; new tests for `ellipseAngle`, `legendSpot` and pin insets).
