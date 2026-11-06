# Wave 7 fixes: BCF markup, overlay, gizmo reset, IFC errors, presets (2026-11-05)

Ten known issues from `RESULTS-qa.md` and `RESULTS-qa-wave5.md` (and the limits listed in `docs-features/bcf.md`). Each
fix has a unit test where the logic is pure and a browser check in `bench/smoke-fixes-w7.mjs` (SMOKE_PORT=5714,
screenshots `bench/fixes-w7-bcf.png`, `bench/fixes-w7-snapshot.png`).

| # | Issue | Fix | Where | Tests |
| --- | --- | --- | --- | --- |
| 1 | Reset to defaults does not bring back a gizmo hidden before the page loaded | A params section can give its factory value (`ParamSection.factory()`); `snapshotSections` uses it before the value collected after the first model. The gizmo's is `{ visible: true, collapsed: <phone> }` | `src/ui/params.ts:38`, `:671`; `src/plugins/gizmo.ts:67`, `:626` | `tests/params-roundtrip.test.ts` "factory value of a plugin section"; smoke 1 (desktop expanded, 390 px phone collapsed) |
| 2 | Pins, measure labels, BCF callouts under the gizmo | Reserved-rect registry on the overlay: `ov.reserved` (edge chrome strips, gizmo box, legends drawn on the overlay, `ov.reserve(key, rect)`) and `ov.place()` (nearest free spot, `freeSpot`). Measure labels and BCF/note boxes move out with a dashed leader; penetration markers under a rect move beside it with a leader; a BCF pin whose point is covered is drawn beside the rect with a leader (or as an edge marker when nothing is free within 160 px); edge markers avoid the rects | `src/ui/reserved.ts:64`; `src/ui/overlay.ts:173`, `:190`, `:197`; `src/plugins/measure.ts:294`; `src/plugins/penetrations.ts:264`; `src/bcf/annotate.ts:272`, `:411` | `tests/bcf-markup-fixes.test.ts` "reserved rects"; smoke 2 (label under the gizmo moves out, leader drawn) |
| 3 | Annotated elements draw solid after an import | "Solid" meant this: the elements that annotations point at are added to the viewpoint `Selection` (so other tools highlight them), so applying selected them, which makes them Focus: alpha 1, `FLAG_FOCUS`, never an occluder. A callout on a wall turned the wall opaque over the window the topic is about. The side file now records `markupSelection` (entries added only for annotations; derived from the annotations for older files). Applying selects the rest; the markup-only elements get the shader's selection tint (same 0.35 mix to yellow) as a temporary colour, keep ghosting, and lose it on Clear viewpoint | `src/bcf/sidecar.ts:88`; `src/bcf/controller.ts:342`, `:383`, `:958` | `tests/bcf-markup-fixes.test.ts` "side file fields"; smoke 3 (after an import: window selected, wall not, wall tinted then restored) |
| 4 | Callouts do not follow exploded or moved elements | Element anchors and pins store `local` (offset from the element's bounds centre, IFC frame); drawing places them at the current centre plus `local` plus the element's displacement (`renderer.elementOffset(id)`, new getter beside `setElementOffset`; `offsetsVersion` makes the overlay redraw while the explode animates). Element-to-element linked measurements move their end points too. Displaced anchors skip the BVH occlusion fade | `src/bcf/annotate.ts:229`; `src/bcf/controller.ts:845`, `:858`; `src/render/renderer.ts:1841`, `:1857`; `src/ui/overlay.ts:215` | `tests/bcf-markup-fixes.test.ts` "element-local anchors"; smoke 4 |
| 5 | No rectangle or freehand shapes | Annotation types `rect` and `freehand` with `shape: { points (fractions of the viewpoint camera view), depth }`. `Add rectangle` / `Draw freehand` buttons, mouse drag on the canvas (orbit blocked, Escape cancels, live preview). Drawn through the viewpoint camera to 3D and back with the live camera; burned into the snapshot pixel for pixel; stored in the side file | `src/bcf/annotate.ts:86`, `:301`; `src/bcf/controller.ts:972`; `src/bcf/pins.ts:167`; `src/bcf/sidecar.ts:190`; help texts `BCF drawer/Add rectangle`, `BCF drawer/Draw freehand` | `tests/bcf-markup-fixes.test.ts` "rectangle and freehand"; smoke 5 (rectangle by mouse drag, burned snapshot, shapes back after import) |
| 6 | Pin numbers are the list position | `BcfTopic.pinNumber`: next free number (max + 1) on creation, side file `pinNumber`; topics without one (other tools) and duplicates from a merge get the next free numbers in list order | `src/bcf/controller.ts:725`, `:735` | `tests/bcf-markup-fixes.test.ts`; smoke 6 (1, 2 before export; 1, 2 after import; new topic 3) |
| 7 | Linked measurements always in metres | The measure tool exposes `units`; links store no default text (older links whose text is the stored label count as empty), and the label is formatted in the current unit live and in the burned snapshot; the drawer lists use it too. There is no global length unit (the cleanup unit is the cleanup tool's own), so the measure tool's setting is the one used | `src/measure/current.ts`; `src/bcf/annotate.ts:258`; `src/bcf/controller.ts:869` | `tests/bcf-markup-fixes.test.ts` "measurement units"; smoke 7 (`100 mm`) |
| 8 | Burned snapshot dimming uses current hides | The occlusion test takes a see-through predicate; the burn uses the set captured with the viewpoint (hidden or ghosted at capture, in memory for this session's viewpoints) or, for imported viewpoints, the hidden elements of the viewpoint Visibility (same rules and guard as applying) | `src/bcf/controller.ts:494`, `:1103`, `:1124` | code path exercised by every burn in the smokes (no pixel test) |
| 9 | Corrupt IFC shows web-ifc's internal message | Worker failures that are not our own reader errors get code `reader`; the loader maps them to "This IFC file could not be read: it may be damaged or not an IFC file (<name>)" and logs the raw text to the console (`[open-file] IFC reader detail: ...`). Our own messages (empty, no header, no geometry, out of memory) pass through | `src/model/ifcErrors.ts:29`; `src/model/ifcWorker.ts:163`; `src/model/ifcImport.ts` (error keeps `code`); `src/plugins/fileLoader.ts:352` | `tests/ifc-errors.test.ts`; smoke 9 (damaged file, model stays) |
| 10 | Selection-dependent presets leave the camera on the whole model | Optional preset flag `frame: 'selection'`: after params and actions the camera fits the selection (requestFrame, so the fly-to animates); no selection, no move; `lastResult().framed`. Set for `section-focus`, `behind-only`, `peelback`, `peel-only`. Validated, exported, shared | `src/presets/model.ts`; `src/presets/engine.ts:150`; `src/plugins/presets.ts:106`; `src/presets/builtin.ts`; `public/xray.presets.json`; `docs-features/presets.md` | `tests/presets-engine.test.ts` "frame selection", `tests/presets-store.test.ts`; smoke 10 (distance 26.6 m to 3.9 m, target on the window) |

Docs: `docs-features/bcf.md` (pins, annotations, shapes, side file, Selection row, limits), `gizmo.md` (reset, reserved
rect), `toolbar.md` ("Shared overlay": reserved rects), `measure.md`, `presets.md`, `large-ifc.md`.

## Not fixed / limits

- Notes (free points) and point-to-point measurements do not follow exploded elements (they have no element); the
  burned snapshot draws anchors at the unexploded elements even if it was taken in the exploded view.
- For imported viewpoints the burn-in fade knows the hidden elements, not which were ghosted at capture.
- Shapes seen from a camera far from the viewpoint camera are mapped onto the shape plane and look skewed.
- No pixel-level test of fix 8; the save form of user presets does not offer `frame`.

## Verification

- `npm run typecheck`: pass. `npm test`: 89 files, 1150 passed, 2 skipped (new: `tests/bcf-markup-fixes.test.ts` 14,
  `tests/ifc-errors.test.ts` 3, plus cases in `params-roundtrip`, `presets-engine`, `presets-store`).
- Smokes (headless Chromium, swiftshader, own vite per script): `smoke-fixes-w7` 16/16, `smoke-bcf-markup` 23/23 (XSD
  valid), `smoke-bcf` 30/30, `smoke-section` 11/11, `smoke-tools` 31/31, `smoke-gizmo` 27/27, `smoke-presets` 83 checks,
  ALL OK.
- Under the load of four agents' smokes at once (load average 12 to 18 on 4 cores), `smoke-gizmo` and `smoke-presets`
  timed out on Playwright's default 30 s navigation, and one `smoke-bcf` click timed out. All of them passed when re-run.
  The two smokes now give `goto`/`reload` the same 240 s they already allowed for startup.
- The damaged file in smoke 9 (a valid header with broken entities) gives the reader's own "has no geometry" line, so it
  does not reach web-ifc's internal error. The rewrite of internal errors is covered by the unit test, not by a file that
  reproduces `reading 'arguments'`.
