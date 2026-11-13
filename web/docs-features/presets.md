# Presets

A preset is a named look of the viewer: a partial parameter document (`xray-params/1`, the same keys as the JSON export) plus an optional list of actions. Applying one never changes the model or the selection, and it moves the camera only when the preset carries a `camera` or the flag `frame: "selection"` (see below). Keys `1` to `9` apply the first nine presets, and the five modes of the top bar ([topbar.md](topbar.md)) apply `solid`, `coordination`, `radiograph`, `focus-glow` and `peel-only`; the action panel has a `Presets` tool (order 5) and the parameter panel has a `Presets` folder.

## The built-in presets

| Key | id | Group | What it sets |
| --- | --- | --- | --- |
| 1 | `coordination` | Review | The Ghost mode of the top bar. The factory x-ray view: x-ray on, sightlines, far mode `opaque` back to their defaults, view modes, imaging, section and clearance off, cinematic bloom, edge glow and auto orbit off. |
| 2 | `hide-blockers` | Review | `sightlines`: `alphaMin 0`, `alphaMax 1`, `gamma 0.3`, `occluderScope all`, `farWeight 1`, `layerWeighting budget`, `layerBudget 6`. What blocks the focus disappears, everything else stays solid. |
| 3 | `behind-only` | Cutaway | `viewModes.behind`: enabled, `frontTreatment 'cut + cap'`; frames the selection. |
| 4 | `peelback` | Cutaway | `viewModes.peel`: enabled, `outside 'x-ray'`; frames the selection. |
| 5 | `peel-only` | Cutaway | `viewModes.peel`: enabled, `outside 'solid'`; `sightlines.alphaMax 1`; `cinematic` `bloom` and `edgeGlow` off; frames the selection. The Cutaway mode of the top bar. |
| 6 | `stacked-floors` | Review | `sightlines`: `layerWeighting front`, `layerFalloff 0.3`; `cinematic.grade`: enabled, `strength 0.85`. |
| 7 | `radiograph` | Imaging | `imaging`: `style radiograph`, `palette classic`; `cinematic` `bloom` and `edgeGlow` off. The Radiograph mode of the top bar. |
| 8 | `mri-scan` | Imaging | `imaging`: `style mri`, `mri.scan true`. |
| 9 | `section-focus` | Cutaway | `section`: `box.enabled`, `box.fit selection`, `caps true`; action `section.fitSelection`; frames the selection. |
| - | `presentation` | Presentation | `cinematic`: `dressing`, `bloom`, `flyTo`, `reveal` on, `sweep` enabled (`mode both`). |
| - | `clearance-review` | Review | `clearance`: enabled with the default bands (`tight 0.05`, `max 0.5`). |
| - | `plain` | Basic | `xray false`; `cinematic` `bloom` and `edgeGlow` off (so leaving the Glow mode gives a plain view). Resets sections and clearance too (unlike `solid`). |
| - | `solid` | Basic | `xray false`; `viewModes` and `imaging` reset; `cinematic` `bloom`, `edgeGlow` and `autoOrbit` off. Does not name `section` or `clearance`, so cuts and clearance stay as they are. The Solid mode of the top bar, and what a click on a lit mode switches to. |
| - | `focus-glow` | Presentation | `cinematic`: `bloom` on, `edgeGlow` on, `glowScope focus`. The selection gets a soft halo and a bright outline; the structure around it stays ghosted. The Glow mode of the top bar. |

`focus-glow` was added for the top bar (nothing else in the set glowed the selection); it has no key, so keys `1` to `9` did not move. The other three modes reuse `coordination`, `radiograph` and `peel-only`. Because Glow adds bloom and edge glow as a look of its own, `radiograph` and `peel-only` now also switch `cinematic.bloom` and `cinematic.edgeGlow` off (as `coordination` did already), so changing from Glow to another mode does not leave the glow on.

All built-ins have `base: "defaults"`, and each names the same set of mode sections (`viewModes`, `imaging`, `section`, `clearance`, empty when unused), so applying one switches the previous one's mode off instead of stacking on it.

## Data model

```json
{ "id": "peelback", "name": "Peelback", "description": "One plain sentence.", "group": "Cutaway",
  "base": "defaults", "params": { "schema": "xray-params/1", "viewModes": { "peel": { "enabled": true } } },
  "actions": ["section.fitSelection"], "frame": "selection" }
```

- `group`: `Review`, `Cutaway`, `Imaging`, `Presentation` or `Basic` for built-ins; user presets are in `My presets`.
- `base: "defaults"`: the sections the preset touches are first reset to the factory values, then the preset is applied. The touched sections are the top-level keys of `params`. An empty object (`"imaging": {}`) is a marker: the section is reset but nothing is set. `base: "current"` applies over the present state. Core sections (`xray`, `sightlines`, `farMode`, `tiersMode`, `tiers`, `display`) reset to `defaultParams`; plugin sections (`viewModes`, `imaging`, `section`, `clearance`, ...) reset to the value they had after the first model loaded; `cinematic` resets only the first-level keys the preset names (a preset that sets `grade` does not turn off your bloom). `camera`, `overrides`, `selectionSets`, `classStyles`, `materialAliases`, `classification` and `rendering` are never reset.
- `actions`: action ids run with `runAction` after the params are applied. An unknown or disabled action is listed as skipped (`action:<id>`).
- `frame` (optional, only value `"selection"`): after the params and the actions, the camera moves so the selection fills the view (along the current view direction, the same fit as a fly-to; the cinematic plugin animates it when fly-to is on). Without a selection nothing moves and nothing is reported as skipped; `lastResult().framed` says whether the camera moved. Without the flag a preset never moves the camera. Why: the selection-dependent presets cut or peel around the selection, and on a big model a small selection (a 0.6 m duct on synth5k) seen from the whole-model view gives a picture that looks empty. `section-focus`, `behind-only`, `peelback` and `peel-only` set it. Exports, imports, user presets and share links keep the flag.
- Unknown sections or keys (the plugin is not in this build, a key was renamed) are skipped and listed; the rest still applies. The drawer then shows "Partly applied. Skipped: ..." on the card, the parameter panel shows it in `Preset status`, and `window.__xrayPresets.lastResult().skipped` has the list. Empty markers of absent sections are not reported.
- `clearance.enabled` is not a params field (the clearance section carries the thresholds only), so presets use it as a key and the presets plugin switches the tool through `window.__xrayClearance.setEnabled`. Saving a preset with the `clearance` section stores the switch too.

## The `xray-presets/1` document

```json
{ "schema": "xray-presets/1", "presets": [ { "id": "...", "name": "...", "description": "...", "group": "...", "base": "...", "params": { }, "actions": [ ] } ] }
```

Used for export, import and the build-time override.

### Build-time override: `public/xray.presets.json`

The file ships the built-ins as data (it must equal `src/presets/builtin.ts`; `tests/presets-builtin.test.ts` checks that). An installation can edit it: **an entry with a built-in id replaces that built-in (it keeps its place, so keys 1 to 9 stay), an entry with a new id is added after the built-ins** (and has no key). Loading order at install: `window.__xrayEmbeddedPresets` (single-file builds and `xray-pack` templates embed the file in every variant), else `fetch('/xray.presets.json')`, else the TS built-ins. While the fetch is running the TS built-ins are in use; a fetch that fails or returns something that is not a presets document is ignored silently.

## User presets

- `Save current as preset` (drawer button, or the folder button, which opens the drawer with the form): name, one-sentence description and the sections to store. Default ticks: `sightlines`, `display`, `farMode`, `viewModes`, `imaging`, `section`, `cinematic` (only those this build has are offered). The preset is stored with `base: "current"`.
- Rename and re-describe (`Edit`), `Duplicate` (also for built-ins, which cannot be edited), `Delete`, `Share` (copies a link).
- `Export` downloads the user presets as an `xray-presets/1` file; `Import` adds presets from such a file (always as user presets; ids and names are made unique, bad entries are reported).
- Stored in `localStorage` key `xray.presets` (user presets only). Storage that throws is tolerated: the presets then last for the session.
- Share link: `...?model=building#preset=<base64url of {schema, preset}>`. On load it is applied once after the first model (before the `#p=` parameters link, if both are present) and removed from the address. A shared preset is applied, not saved; it is shown as "Shared preset". Its actions run too, so open links from people you trust.

## The active mark

The last applied preset is marked `active` on its card and named in `Preset status`. A hash of the collected parameters (without camera, selection sets, playback progress and the `topBar` section, so showing or hiding the top bar keeps the mark; `imaging.mri.position` is ignored so a running MRI scan does not clear it) is compared once a second; when any setting differs, the mark is cleared. Changes in the first second after applying (settling animations, `section.fitSelection`) are taken into the baseline.

## Parameter panel, keys, scripting

- Folder `Presets`: `preset` (dropdown), `Apply preset`, `Save current as preset`, `Export presets`, `Import presets`, `Preset status` (read-only).
- Actions `preset.1` to `preset.9` (label `Preset: <name>`, group `Presets`, keys `1` to `9`; they replace the placeholders of the keymap) and `presets.open` (no key; opens the drawer).
- `window.__xrayPresets`: `list()` (id, name, description, group, key, builtIn, base, active), `markActive(id, note?)` (marks a preset active without applying it; used by saved views and by the top bar for the factory look), `apply(idOrName)` (id, name, or key number; throws for an unknown preset; returns `{ id, name, applied, skipped, actions, partial }`), `save(name, sections?, description?)`, `remove(id)`, `active()`, plus `lastResult()`, `get(id)`, `exportJson(all?)`, `importJson(text)` and `shareUrl(id)`.
- The packager: `xray-pack --preset <name>` sets `window.__xrayBoot.preset`, which the boot plugin applies through `__xrayPresets.apply` before the params document.

## Developer notes

- `src/presets/model.ts` (types, validation, document, override merge, share encoding), `engine.ts` (apply, reset, capture, settings hash), `store.ts` (list, persistence, import/export), `builtin.ts` (data), `panel.ts` (drawer DOM); `src/plugins/presets.ts` wires them to the app. Tests: `tests/presets-*.test.ts`. Smoke: `SMOKE_PORT=5342 node bench/smoke-presets.mjs` (screenshots `bench/preset-*.png`).
- The engine only needs a `ParamsApp`, so it is tested with a fake app; plugin sections are faked with `registerParamSection`.

## Limits

- Presets reset and apply settings; they cannot change the selection or load a model.
- A plugin section that exists in the build is reset to the value it had after the first model loaded, which is the factory value unless a URL parameter or the boot document changed it earlier.
- The active mark is a settings comparison, not a flag: an unrelated plugin whose collected section changes by itself (a running animation that writes into a section) clears it.
- `selection`-dependent presets (`section-focus`, `behind-only`, `peelback`, `peel-only`) show nothing useful without a selection; with one they frame it (`frame: "selection"`). The save form does not offer the flag: add it to an exported file by hand.
