# QA wave 7: integration pass (2026-11-07)

Integration check of the four features committed together in `d0af081` (saved views, field AR, viewer fixes, point
clouds). Headless Chromium 1243 (Playwright, swiftshader) against `bench/vite.smoke.config.mjs` on port 5655, one dev
server at a time on an idle 4-core machine (load about 1 before the runs). Console errors and page errors were collected
at every step. The cross-feature checks are in a new script, `bench/smoke-qa-wave7.mjs` (4 parts, screenshots
`bench/qa7-*.png`).

Result: **7 integration bugs fixed** (ICP slowness, deleted packed views coming back, the thumbnail under the help
popover, stray BCF markup after a view restore, BCF planes left over a restored section box, the preset not marked
after a view restore, and saved views fighting a field AR session), plus 1 timing race in `smoke-open-file`'s assertion.
Every smoke passes; open issues are listed at the end.

## Checks

| # | Area | Check | Result |
| --- | --- | --- | --- |
| 1 | ICP timing | `smoke-pointcloud-align`, ICP after the 3-point solve, idle machine | **fixed** (fix 1): 12.8 s before, **5.5 s** after (wave 6 without normals: 6.5 s). Rough starts 22.6 / 19.3 / 19.4 s before, 5.9 / 5.8 / 5.9 s after. The whole smoke: 156 s before, 95 s after |
| 1 | ICP accuracy | the same runs (the fix only changes scheduling; the result is deterministic) | unchanged: phone scan after 3-point 0.014 deg / **0.12 mm**; rough starts 0.26 / 1.35 / 0.20 mm; within the section box 0.46 mm; median deviation 9.5 mm |
| 2 | Packed views | delete a view baked in by `xray-pack --views`, reopen the page | **fixed** (fix 2); unit tests in `tests/views-model.test.ts`, browser check in `smoke-views` ("pack: a deleted packed view does not come back", from `file://`) |
| 3 | Hover thumbnail | the thumbnail of a row under the help popover of the row's name button (1400 and 900 px wide) | **fixed** (fix 3): before, the popover (z-index 100000) covered the thumbnail (900) at the same spot (`x 249..609` over `306..486`); after, the thumbnail sits right of the popover (`qa7-peek-help.png`); check added to `smoke-views` |
| 4a | Views x BCF | save a view while a BCF viewpoint (plane, hide, selection, callout, pin) is applied; restore another view | **fixed** (fix 4): before, the pin and the callout of the old viewpoint stayed drawn; after, no pin, callout, plane, hide or tint is left (`qa7-bcf-restore-plain.png`). The view saved under BCF restores its plane and hide; a later `Clear viewpoint` does not undo them |
| 4a | Views x section box (gizmo) | box from the gizmo button (real click), save; apply a BCF viewpoint over it; restore the box view | **fixed** (fix 4): before, the BCF plane (1) stayed in place of the box's 6 planes, with its pin and callout; after, 6 planes, no BCF markup. Restoring "plain" turns the box and the gizmo button off |
| 4b | Views x explode | restore a view mid-explode with callouts drawn; save exploded with callouts, restore plain and back | pass: collapsed, no element left displaced (max offset 0), callouts gone with the viewpoint, exploded again on restore (`qa7-exploded-callouts.png`) |
| 4c | Views x presets | save with preset `behind-only` active, apply `plain`, restore the view | **fixed** (fix 5): before, no preset was marked (`active() = null`); after, `behind-only` is active again. A view without a preset whose settings differ clears the mark within 1 s |
| 4d | Field AR, then views, BCF, sections | iwer Quest 3 with the stub hit test of `smoke-xr-field`: register with 3 taps, look ghosted, cut on; Shift+PageDown and Save view during the session; exit; then views, BCF, section box and plane | **fixed** (fix 6): before, a view restored during the session replaced the field cut box with the view's plane and overwrote the look (and Save view would store the session's look). After: refused with a status message; Ctrl+Shift+S logs no error. After exit: styles, section, clip planes, near/far as before; views, BCF viewpoints, box and plane work; no console errors |
| 4e | Reserved rects, 1600x900, Views tab open, BCF drawer open | measure labels and BCF pins placed under the gizmo, status bar, tool strip and drawer | pass: every label and pin head is clear (pins under the gizmo move above it with a leader; `qa7-reserved-desktop-views-bcf.png`). Two labels moved to the same free spot overlap each other (open issue) |
| 4e | Reserved rects, 390x844 phone, sidebar closed | the same, plus the dock rail | pass (`qa7-reserved-phone-closed.png`) |
| 4e | Reserved rects, 390x844 phone, Views drawer open | the same | **open issue**: the drawer leaves a 62 px strip of canvas; a 58 px label does not fit with its 4 px gaps, so `place()` gives null and the label stays at its anchor: one sits behind the collapsed gizmo button (the button stays on top and clickable), others behind the drawer or the dock rail (`qa7-reserved-phone-views-open.png`) |
| 4f | Point cloud x gizmo box | building + phone scan at truth + 2.5 cm, room elements selected, gizmo box button (real click), `align within: section box`, Refine | pass: 1.27 mm, 20 000 points in the box, 6.5 s; drift grid for the box; box off by the gizmo: Refine says the box is needed (`qa7-pc-gizmo-box.png`) |
| 4g | Console | every step of every check above | no console errors or page errors |
| 5 | Smokes | the 12 listed smokes, the 17 other `smoke-*.mjs`, `help-smoke`, `smoke-qa-wave7` | pass (`smoke-open-file` after a fix to its assertion, fix 8), see "Smoke scripts" |
| 5 | Unit tests | `npm run typecheck`, `npx vitest run` | pass: 89 files, 1153 passed, 2 skipped (was 1150; 3 new) |
| 6 | Single file | `npm run build`, `npm run bundle`, `node bench/single-file.mjs` | pass: **5.72 MB** (5,994,943 bytes; wave 5: 5.48 MB); building from `file://`: no requests, no console output |
| 6 | Single file: USDZ | the drawer's Download USDZ button from `file://` (iwer injected, so the WebXR tool shows) | pass: `fzk-haus-xray.usdz`, 2.09 MB, 82 elements in 8 materials, 108 ms. The single-file config inlines dynamic imports (`inlineDynamicImports: true`), so `USDZExporter` is in the one chunk (not lazy, but present); the normal build keeps it as a lazy chunk (`dist/assets/USDZExporter-*.js`). No "cannot load" message was needed; a failed export already shows "USDZ export failed: ..." in the drawer (`src/plugins/xr.ts:274`) |
| 6 | Single file: saved views | save (section plane), reload from `file://`, restore, Views tab | pass: the view and its thumbnail survive the reload; camera and plane come back |

## Fixes

1. **ICP 2 to 4 times slower than before the normals step.** In the browser the normal estimate took 11.5 s of a
   15 s run, against 0.7 s in Node for the same points. `estimateNormalsAsync` yielded after every 12 ms of work, and
   each yield let the page draw a frame (150 to 300 ms with swiftshader). So about 95 % of the time went to frames.
   ICP itself already used an adaptive slice. The normal estimate now does the same: after a long gap it takes a longer
   slice (half the gap, at most 250 ms), so on a fast machine slices stay at 12 ms. `src/pointcloud/normals.ts:262`.
   Profile (`refine()` from a start near the truth, browser): normals 11.5 s to 1.7 s, the whole run 15.0 s to 5.0 s.
   Neighbour count, dense copy and grid are unchanged, so the normals and the accuracy figures in
   `RESULTS-pointcloud-w7.md` are unchanged.
2. **Packed views came back after deletion.** On every open of a packed page the boot views were merged into the
   stored list by id, so a deleted view was "new" again. The ids and `updated` stamps offered are now kept per model in
   `localStorage` `xray.viewsPacked.<model>`. A packed view already offered with the same or an older stamp is
   skipped, and a page packed again with a newer version of a view offers it again. `src/views/model.ts:558`
   (`PACKED_SEEN_PREFIX`, `loadPackedSeen`, `savePackedSeen`, `mergePackedViews` at `:592`),
   `src/plugins/views.ts:690`. Tests: `tests/views-model.test.ts:259` (3 cases), `bench/smoke-views.mjs:423`.
3. **Hover thumbnail under the help popover.** Both opened right of the sidebar at the row; the popover is on top of
   everything. The thumbnail now moves right of the popover (else below, above or left) when they overlap. A
   MutationObserver on `#xray-help` places it again when the popover appears after its delay.
   `src/views/panel.ts:540`, `:548` (`placePeek`), `:569` (`watchHelp`). Check: `bench/smoke-views.mjs:289`.
4. **Stray BCF markup and planes after restoring a view.** Restoring a view did not end the applied BCF viewpoint, so
   its pin and callouts stayed drawn. Its colour tint and hide provenance stayed too, and over a restored section box
   its plane kept the box's planes out. A restore now calls `clearViewpoint()` first when a viewpoint is applied.
   `src/plugins/views.ts:290`. The BCF window API gained `applied` and `clearViewpoint(quiet?)`:
   `src/plugins/bcf.ts:127`.
5. **Restoring a view did not mark its preset.** The view stores the preset id, but the presets plugin only marked a
   preset on `apply`. New `window.__xrayPresets.markActive(id)` sets the mark and re-baselines the "still active" hash.
   The views restore calls it for a view with a preset. `src/plugins/presets.ts:51`, `:243`; `src/plugins/views.ts:296`.
6. **Saved views during an XR session.** Field AR sets its own look, cut box and camera and puts them back on exit. A
   view restored during the session replaced the cut and the look; a view saved then would store the session's look.
   During a session, save and update are refused with a message, restore and step say "leave the AR or VR session
   first", and Play stops. `src/plugins/views.ts:186` (`inXr`), `:257`, `:268`, `:282`, `:337`, `:400`, `:419`.
   The Ctrl+Shift+S action and the panel's Update now catch the error and show it instead of throwing.
7. Docs: `docs-features/saved-views.md` (packed views marker, BCF clear on restore, preset mark, XR sessions).
8. Smoke fix, not a viewer bug: in `smoke-open-file` the 101 MB non-glb fails in about 0 s on an idle machine. Its error
   replaces the "Large input" banner before the polling `waitForFunction` sees it (the glb path did not change in wave 7;
   the wave 5 runs were loaded, so the read took longer). The smoke now records the banner with a MutationObserver.
   `bench/smoke-open-file.mjs:299`.

No help text or settings changed, so `npm run docs` was not needed. `src/ui/helpText.ts` is untouched.

## Smoke scripts

One at a time, port 5655, idle machine. Screenshots that the smokes rewrote in `bench/` were put back to the committed versions; the new screenshots are `bench/qa7-*.png` (13 files, palette-quantised, 0.9 MB).

| Script | Result | Time |
| --- | --- | --- |
| `smoke-pointcloud-align` | 23/23 | 95 s (156 s before fix 1) |
| `smoke-views` | 92/92 (2 new checks) | 299 s |
| `smoke-xr` | 27/27, no console errors or warnings | 230 s |
| `smoke-xr-field` | 37/37, no console errors or warnings | 509 s |
| `smoke-fixes-w7` | 16/16 | 59 s |
| `smoke-bcf` | 30/30 | 84 s |
| `smoke-bcf-markup` | 23/23 | 113 s |
| `smoke-section` | 11/11 | 206 s |
| `smoke-tools` | 31/31 | 73 s |
| `smoke-gizmo` | 27/27 | 221 s |
| `smoke-presets` | 83 checks, ALL OK | 313 s |
| `smoke-pointcloud` | 46/46 | 52 s |
| `smoke-qa-wave7` (new) | 47/47 and 1 INFO line (the phone with the Views drawer open, an open issue). The first run flagged the 5 px dot at the end of a pin's leader under the gizmo, which marks the true point by design; the check now looks at pin heads of 10 px and more | 249 s |
| `smoke-cinematic`, `smoke-cinematic-explode`, `smoke-cinematic-ghost` | pass, no console output | 24 s, 30 s, 34 s |
| `smoke-cinematic2` | pass (only Chromium's "GPU stall due to ReadPixels" warnings from the script's own canvas reads, which the script ignores) | 83 s |
| `smoke-cleanup` | 66/66 | 147 s |
| `smoke-dock`, `smoke-hover`, `smoke-sidebar` | pass, 25/25, all checks, 13/13 | 34 s, 59 s, 29 s |
| `smoke-imaging` | pass, no console errors or warnings | 476 s |
| `smoke-keys` | 29/29, zero console errors | 40 s |
| `smoke-layers`, `smoke-oit`, `smoke-render`, `smoke-scope` | pass | 65 s, 570 s, 2 s, 15 s |
| `smoke-open-file` | first run FAIL "the 100 MB warning was not shown"; pass after a fix to the smoke (below) | 96 s |
| `smoke-pack` | all checks passed | 23 s |
| `smoke-viewmodes` | pass, no console errors or warnings | 1485 s |
| `help-smoke` | 51/51 | 139 s |
| `single-file.mjs` | pass: no requests, no console output | - |

## Open issues

- Phone (390x844) with the Views drawer (or any sidebar tab) open: only 62 px of canvas are left between the drawer and
  the dock rail. Labels that cannot fit stay at their anchor (`src/plugins/measure.ts:294` falls back to the anchor when
  `place()` gives null), so one can sit behind the collapsed gizmo button. The button stays on top and clickable.
  Possible fix: fall back to a spot that ignores the drawer but keeps the gizmo and status bar, or hide labels when no
  spot is free.
- Labels moved out of the chrome do not avoid each other: two measure labels moved out from under the tool strip and
  drawer land on the same free spot (`qa7-reserved-desktop-views-bcf.png`, left edge of the view).
- The status line of the BCF drawer reads "Viewpoint cleared (n hidden elements restored)" after a view restore ended a
  viewpoint, although the view then sets its own hides.
- `markActive` trusts the view: a setting changed less than 1 s before saving (before the presets hash check ran) is
  saved with the old preset id, and the restore marks that preset.
- Saved views during an XR session are refused, not queued: a view chosen during the session is not applied on exit.
- ICP in the browser is still about 3 times the Node time (5 s against 2.2 s), because swiftshader frames are drawn
  between slices. On a GPU machine the gap should be small. The adaptive slice keeps the page responsive (at most
  250 ms per slice).
- The root `xray-viewer.html` (the tracked copy of the single file) was not refreshed. `web/dist-single/xray-viewer.html`
  is the new build.

## Tests

`npm run typecheck` passes. `npx vitest run`: 89 files, 1153 passed, 2 skipped (was 1150 + 2; new: the 3 packed views
cases in `tests/views-model.test.ts`).
