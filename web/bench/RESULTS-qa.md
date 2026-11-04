# Final QA pass (2026-11-04)

End-to-end check of the viewer in headless Chromium (Playwright, swiftshader), against a dev server started from
`bench/vite.smoke.config.mjs` on port 5511, plus the packer, the single-file build and a phone-width viewport. On every
step the scripts collected console errors and warnings and page errors. The only messages filtered out were Chromium's
`GPU stall due to ReadPixels` performance notes, which the QA script's own canvas readback causes. Screenshots are
`bench/qa-*.png` (15 files, palette-quantised).

Result: **3 bugs fixed, plus 1 doc example and 1 stale smoke assertion fixed**, everything else passed. The table lists each check and its outcome.

## Checks

| Area | Check | Result |
| --- | --- | --- |
| Models | building, fzk-haus, plumbing, synth5k, debris-demo: load, picture not blank, select via tree row, select via canvas click, `x` toggles x-ray, no console output | pass |
| Models | Model picker switches building -> plumbing | pass |
| Presets | All 12 built-ins on fzk-haus and synth5k (keys `1`-`9` for the first nine, `apply()` for the rest): applied fully (nothing skipped), marked active, picture not blank, no console output | pass |
| Presets | User preset save / export / remove / import / apply; preset share link (`#preset=`) in a new page | pass |
| View modes | `b`, `Shift+b`, `p` (peel takes the GPU JFA path) | pass (`qa-peel-fzk.png`) |
| Imaging | `m` cycles radiograph -> mri -> standard; float32 thickness target, auto exposure measured | pass (`qa-preset-synth5k-radiograph.png`) |
| Section | `c`, `Shift+c` (fits the selection), `Alt+c` (plane); 6 clip planes | pass (`qa-section-fzk.png`, `qa-preset-fzk-haus-section-focus.png`) |
| Cleanup | debris-demo: analyse (28 floating matches), preview, hide, restore, through both the API and the drawer buttons | pass (`qa-cleanup-debris.png`) |
| Hover | Hover card appears over an element, with properties | pass (`qa-hover-fzk.png`) |
| Keys | `?`, `F1`, Escape, `Ctrl+K` (typing and Enter run a command), arrows, `w`, `=`, `Home`, `f`, `Numpad7`, `Alt+s`, `Ctrl+i`, `Ctrl+a`, `h` / `Alt+h`, `[`, `]`, `t`, digits `1` and `3`, `/` | pass |
| Toolbar | Each of the 13 visible tools opens its drawer (or acts) with no errors and no `[help] no help text` warnings (`xr` is hidden: no WebXR in headless) | pass |
| Penetrations | synth5k: Analyse in the drawer (897 rows, 500 listed as documented), Export CSV (898 lines = header + 897), a row click selects | pass (`qa-penetrations-synth5k.png`) |
| Measure | Point to point by two canvas clicks | pass (`qa-measure-synth5k.png`) |
| Clearance | Enabled on a synth5k duct run: clash 435 / beyond 2771 | pass |
| BCF | 2.1 and 3.0 fixtures (zipped from `tests/fixtures/bcf`) loaded through the drawer's file input; viewpoints applied (unknown GUIDs counted) and cleared; a new topic exported as 2.1 and as 3.0 and re-imported with snapshot and viewpoint; the drawer's Export downloads a `.bcfzip` | pass (`qa-bcf-fzk.png`) |
| Point cloud | `building-scan.las` and `.ply` through the drawer's input (worker parse); deviation 99.4 % within 2 cm | pass (`qa-pointcloud-building.png`) |
| Large IFC | `AC20-FZK-Haus.ifc` (82 elements, 2.6 s) and an 8,000-element `make_big_ifc.py` file (6.7 s), both opened with `setInputFiles`; picture not blank; click selects | pass (`qa-large-ifc.png`) |
| Bad input | Unknown `?model=` falls back to the procedural model and shows the red message; a corrupt `.ifc` or `.glb` gives a one-line message, the model stays, no page errors | pass |
| Params | collect -> Reset to defaults -> apply round trip; Import JSON through the Export / import file chooser; share URL in a new page restores peel and radiograph | **fixed** (reset), then pass |
| Packer | glb with `--params` (no `schema`) `--preset peelback --tools ... --open-tool measure --select`; IFC with `--preset radiograph --kiosk --title --camera --tools --open-tool bcf`; 3 federated IFC with `--ifc-reader` (then opening another IFC inside the packed page). Each output opened from `file://`: requested mode, tools, drawer, selection, camera and kiosk all present, no network requests, no console output | **fixed** (false boot warnings), then pass (`qa-pack-ifc.png`) |
| Single file | `npm run bundle` (5.35 MB), then `bench/single-file.mjs` for building, fzk-haus, plumbing and debris-demo: no console output, no non-file requests | pass |
| Phone 390x844 | No horizontal page scroll (also with the tree, the dock or any drawer open), panels start collapsed, every drawer fits between the rails, cheat sheet and palette fit, tap selects | **fixed** (tool strip under the tree rail), then pass (`qa-phone-building.png`, `qa-phone-drawer-penetrations.png`) |
| Existing smokes | `smoke-pack`, `smoke-tools`, `help-smoke` (391/384/363 rows with help on building/fzk-haus/synth5k, 0 missing), `smoke-presets`, `smoke-keys` after the fixes | pass (`smoke-presets` after fixing its stale assertion, item 5 below) |
| Unit tests | `npm run typecheck`, `npm test` | pass, 902 passed + 1 skipped (was 899 + 1) |

## Bugs fixed

1. **"Reset to defaults" left plugin modes on.** `src/plugins/exportParams.ts:86` applied only `defaultParams`, which covers
   the core sections. View modes, imaging, section and the other plugin sections kept their state: after Reset, peelback and
   radiograph were still on, although the button's help says "every slider and switch returns to its starting value". Now
   the plugin snapshots the registered plugin sections after the first model (`src/plugins/exportParams.ts:170`, new
   helper `snapshotSections` in `src/ui/params.ts:650`; `keymap` is left out because shortcuts have their own reset).
   Reset applies that snapshot after the core defaults and switches clearance colouring off. Test:
   `tests/params-roundtrip.test.ts` ("defaults of plugin sections").
2. **False `[xray-boot]` warnings in packed pages.** `applyParams` reports a missing `schema` as an ignored key, and the boot
   plugin applied `{ camera }` with no schema. So every page packed with `--camera` logged "ignored camera: expected position
   and target as three numbers each", although the camera was applied. A `--params` file without `schema` (which
   `xray-pack` accepts) logged "ignored parameter keys: schema". Fix: `withSchema` in `src/plugins/boot.ts:29`, used at
   lines 90 and 95. Test: `tests/pack-inject.test.ts` ("boot params schema").
3. **Tool strip hidden on phones.** At widths up to 700 px the tree and the dock overlay the stage (`index.html`), and the
   collapsed tree rail (28 px, z-index 20) covered most of the 44 px tool strip, so the icons were cut off. On narrow
   screens the strip now starts after the left rail, and the drawer is capped so it ends before the dock rail
   (`src/ui/toolbarView.ts:72`). This is CSS only, so there is no unit test; the phone check above covers it.
4. **Doc example.** The federated Building example in `README.md` and `docs-features/xray-pack.md` used
   `--select class:IfcWindow`, but the three Building IFC files contain no windows, so `xray-pack` warned. The example
   now uses `class:IfcDuctSegment`.
5. **Stale smoke assertion.** `bench/smoke-presets.mjs:217` expected a saved user preset to have no `imaging` section, which
   was written before the imaging plugin existed. With imaging in the build, `save` correctly stores it (`missing: []`), so
   the check failed. The assertion now expects `imaging` to be present and nothing to be missing.

## Known issues left (not changed)

- The committed root `xray-viewer.html` comes from the baseline commit and is older than `web/src` (no presets,
  imaging and so on). `npm run zip` builds the zip from `dist-single/`, so the zip is current; the repo copy is stale.
  Regenerating a 5.6 MB file is the owner's call.
- `section-focus` (and the other selection-dependent presets) on synth5k: the box fits a single 0.6 m duct while the
  camera stays on the whole 5,000-element model, so the picture is almost empty until you press `f`. This is by design
  (presets.md: presets never move the camera; the Limits section names these presets).
- A corrupt IFC reports web-ifc's internal message ("IFC reader failed: Cannot read properties of undefined (reading
  'arguments')"). It is one line and harmless, but not friendly.
- WebXR could not be exercised (no XR device in headless Chromium). The `xr` tool hides itself and `__xrayXr.state()`
  reports "WebXR is not supported on this device"; this is the environment, not a bug.
- With the tree expanded on a phone, the debug overlay (`#xray-overlay`) sits partly off-screen to the right. It is
  clipped (no page scroll) and is only a stats readout.
