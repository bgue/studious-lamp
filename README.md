# BIM X-ray viewer: reference implementation

A small WebGL viewer that implements the X-ray mode from the report "BIM X-Ray Vision: Technical
Implementation Report". Select an MEP run (a duct or pipe) and the structure that hides it ghosts, in
proportion to how much it blocks the view and how close it is. Everything else stays opaque.

- Focus: the selected run, drawn opaque and in front. Context: concrete structure on nearby storeys.
- Host (intersects a focus element) and Near (inside a buffer radius) are the occluders; only they change alpha.
- Per camera move, rays from the focus surface to the camera give each occluder an occlusion fraction, which sets its target alpha;
  alpha eases to the target every frame.
- One merged geometry, one per-element state texture, three mesh passes plus an edge pass. `SPEC.md` has the full design.

## Prerequisites

- Node 22 and npm (the project was built with Node 22.22).
- `cd web && npm install` (three 0.187, three-mesh-bvh 0.9, lil-gui 0.21, web-ifc 0.0.78 for opening IFC files in the browser, vite 8, vitest 5, typescript 5.9).
- To regenerate models: Python 3.13 with `ifcopenshell` 0.9 and `numpy`.
- For the benchmark: the preinstalled Playwright Chromium (found in `/opt/node-tools/node_modules/playwright`,
  or set `PLAYWRIGHT_MODULE`).

## Convert IFC to glb

The converted models are checked in under `web/public/models`. To regenerate them from the repository root:

```sh
python3 tools/ifc2glb.py models/Building-Structural.ifc models/Building-Architecture.ifc models/Building-Hvac.ifc -o web/public/models/building
python3 tools/ifc2glb.py models/Infra-Plumbing.ifc -o web/public/models/plumbing
python3 tools/synth_model.py -n 5000 -o web/public/models/synth5k     # synthetic 5,000-element benchmark model
```

Each run writes `<name>.glb` (one node per element) and `<name>.json` (the `xray-model/1` sidecar: classes, storeys,
bounds, colours, relations). Any glb without a sidecar also loads; classes are then guessed from node names.

## Run

```sh
cd web
npm run dev          # http://127.0.0.1:5173/?model=building   (building | fzk-haus | plumbing | synth5k | procedural)
npm run build        # typecheck + production bundle in web/dist
npm run preview
```

An unknown or unloadable `?model=` falls back to the in-memory procedural model and shows a red message at the top.
`/demo.html` is the standalone renderer demo without the algorithms.

## Test

```sh
cd web
npm run typecheck
npm test             # vitest: algorithms, worked example, geometry, renderer geometry, tiers, app state, IFC import (build, plan, parity with the converter)
```

`tests/worked-example.test.ts` reproduces the report's numbers on synthetic boxes (S1 Host weight 1.0, B1 0.741, W1 0.02,
C1 Far, S1 occlusion about 0.75 and target alpha about 0.24). `tests/app-state.test.ts` drives `XrayController`
(selection, update sequence, smoothing, pins, hides, far mode, tiers) with the box mock in `tests/boxProvider.ts`.

## Benchmark

```sh
cd web
node bench/bench.mjs            # synth5k and building, writes bench/RESULTS.md, bench/app-<model>.png
node bench/bench.mjs building   # one model
node bench/bench.mjs --scope=near   # Algorithm 2 with the report's Host + Near candidates (default: all)
```

It starts vite on 127.0.0.1:5188, opens the app in headless Chromium (swiftshader, 1920x1080), selects the first IfcDuctSegment,
orbits the camera through 36 positions and records Algorithm 1 and 2 times, rays per update and frame times.
`bench/smoke-render.mjs` is the smaller renderer-only screenshot check. Swiftshader is CPU rasterisation: its frame times are not
GPU numbers.

## Single-file viewer and zip

```sh
cd web
npm run bundle                 # typecheck, vite build (vite.single.config.ts), inline everything -> web/dist-single/xray-viewer.html
npm run bundle -- --all        # also embed synth5k (adds about 7 MB, base64 makes it about 9.5 MB)
npm run bundle -- --no-ifc     # without the IFC reader (no web-ifc, no worker, no wasm) -> web/dist-single/xray-viewer-no-ifc.html
cd .. && bash tools/make_zip.sh   # -> /home/user/xray-ref-dist/xray-ref.zip (also available as `npm run zip` in web/)
```

`xray-viewer.html` is one file with the app JS, CSS, the sample models and `xray.config.json` inlined; it needs no server and no
network. The models are injected as `window.__xrayEmbeddedModels` (name -> base64 glb + sidecar object) and the config as
`window.__xrayEmbeddedConfig`; `app.ts` loads embedded models without fetching and the class styles plugin uses the embedded config
instead of fetching `/xray.config.json`. Embedded by default (about 2.4 MB of models, the whole file is 3.84 MB with the IFC reader and
2.61 MB with `--no-ifc`, see "Opening your own files"): `building` (the default when opened from
`file://`), `fzk-haus` and `plumbing`. `synth5k` is not embedded unless `--all` is given; choosing it in the picker without `--all`
shows the red "Could not load model" message and falls back to the procedural model (a console error about the unsupported `file`
fetch scheme is expected then). Selection sets and class style edits are keyed by model name in `localStorage`, so the default sets seed
as usual. `bash tools/make_zip.sh` zips the repo (without `web/node_modules`, `web/dist`, `web/dist-single`, `models-probe`, `.git`,
`__pycache__` and PNGs over 2 MB), puts `xray-viewer.html` at the zip root and always includes `web/public/models/*.glb|json`
(synth5k too). It rebuilds the single file first if it is missing or older than the sources.

File:// caveat: some browsers block `<script type="module" src="...">` from `file://` (module loading is subject to CORS and
each file is its own origin), which is why the normal `web/dist` build cannot be opened by double-click. This bundle uses an inline module script with no imports, which works from
`file://` in Chromium (checked here with `node web/bench/single-file.mjs`: zero console errors, zero network requests, screenshot
`web/bench/single-file.png`) and is expected to work in Firefox, but Firefox and Safari were not available to test here. The page cannot `fetch` anything from `file://`, which is why models and config are embedded. `localStorage`
on `file://` is per browser profile and origin rules differ between browsers, so persistence of sets and style edits may not survive
reloads in some of them.

## Opening your own files

Open IFC and glb files from disk, in the browser, without the Python converter and without a server.

- Panel: the folder **Open model** at the top of the lil-gui panel has the button **Open IFC or glb file** (a file dialog, multiple
  files allowed), the button **Cancel load** (enabled only while loading) and the read-only text **Load status** ("Reading
  Building-Structural.ifc, 0.2 MB", "Meshing 120 of 480", "Building model", "Loaded 26 elements in 0.8 s", or the error).
- Drag and drop: drop files anywhere on the page. A "Drop IFC or glb files to open" overlay shows while files are dragged over it.
- Accepted: `.ifc`, `.ifczip` (a zip with an `.ifc` inside), `.glb`, and `.json` (the `xray-model/1` sidecar of a glb).
  - One or more IFC files: **federated** into one model. Element ids run on from file to file, storeys with the same name and an
    elevation within 1 cm are merged, an element with the same GlobalId, class and bounds as an earlier one is skipped (the
    Structural, Architecture and Hvac files of the Simple-Scene set each carry the same project), and the same GlobalId with different geometry is
    renamed `<GlobalId>~<n>`. This is the converter's rule (`tools/ifc2glb.py`).
  - One `.glb`: loaded with `parseModel`. The sidecar is the `.json` with the same base name, else any selected `.json` whose
    `schema` is `xray-model/1`; with none, classes are guessed from node names as for any glb without a sidecar.
  - IFC mixed with glb, several glb files, a `.json` alone, unsupported types (`.txt`, `.gltf`, ...), empty files and corrupt IFC
    give a one-line message in Load status and in the red banner, and the model on screen stays as it was. The new model replaces
    it only when it is ready. Cancel stops a load in the worker at once (the worker is terminated); the build and loader steps that
    follow run on the main thread and are not interruptible, a cancel pressed during them takes effect when they finish.
  - Over 100 MB in total the loader warns and carries on.
- The model is named `file:<first file name>` (` +N more` when federated, ` (2)` when the name is taken) and is added to the
  **Model** picker for the session. It is not stored: reload the page and it is gone. Selection sets and class style edits are keyed
  by that name in `localStorage` like for any model.

How it works, in the order the code runs it:

1. `src/plugins/fileLoader.ts` plans the selection (`planOpen`, tested in `tests/ifc-import-plan.test.ts`), reads the files and unzips
   `.ifczip` (`unzipIfc`, deflate through `DecompressionStream`).
2. `src/model/ifcImport.ts` `importIfc` starts a module Web Worker (`ifcWorker.ts`, `new Worker(new URL('./ifcWorker.ts', import.meta.url), { type: 'module' })`),
   transfers each file's buffer to it and receives progress messages and a `RawModel` whose typed arrays come back as transferables.
   The worker runs `extractIfc` in `ifcRaw.ts`: web-ifc opens the file, products are meshed in chunks of 48, and storeys, containment,
   voids, fills, ports, systems and materials are read from the line data. If the worker cannot start (no `Worker`, a bundling problem), the same
   code runs on the main thread with an event-loop yield between chunks; the plain single-file bundle has no such second copy and reports the
   problem instead. The worker is started as soon as the Open button is pressed or a drag enters the page, so web-ifc is initialised while the file dialog is open.
3. `build` (pure TypeScript, `tests/ifc-import-build.test.ts`) turns `RawModel[]` into the converter's output: skipped classes, marker proxies,
   Z-up to Y-up, origin shift, storey fallback, hosts, ports, systems, federation. It writes glb bytes and the `xray-model/1`
   sidecar in memory and calls `parseModel(glb, sidecar)`. There is one loader path: what you open is exactly what a converted model would be.

What it does the way the converter does it: skips the geometry of `IfcOpeningElement`, `IfcSpace`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey`,
`IfcAnnotation`, `IfcSpatialZone`, `IfcExternalSpatialElement`, `IfcGrid`, `IfcVirtualElement` and the `origin` / `geo-reference` proxy cubes of the
Simple-Scene files; rotates Z-up to Y-up in the vertex data and shifts the overall bounds centre to the origin (`originShift`); smooths
normals with a 30 degree crease; gives each element a storey by containment (walking aggregates up) and, only when the file has storeys, the
nearest storey at or below its lowest point; derives `hosts` from voids and fills; resolves ports to element pairs (IFC4 `IfcRelNests` +
`IfcDistributionPort` + `IfcRelConnectsPorts`, IFC2x3 `IfcRelConnectsPortToElement`); reads systems from `IfcRelAssignsToGroup`; takes the
material name from `IfcRelAssociatesMaterial` (own, else the type's).

Checked against the converter, `tests/ifc-import-parity.test.ts` (web-ifc runs in node there): `Building-Structural` + `Architecture` + `Hvac` against
`building.json`, `AC20-FZK-Haus` against `fzk-haus.json` (17 voids, 16 fills, 16 hosts) and `Infra-Plumbing` against `plumbing.json` give the same class
counts, the same elements (matched by file and express id), element bounds within 1 cm (the largest difference found is 0.01 mm, the origin shift is identical),
the same storeys and storey of every element, the same material names and the same relation counts. Generated IFC4 and IFC2X3 fixtures
(`tests/fixtures/ifc`, made by `tests/fixtures/make_ifc_fixtures.py`) cover what the samples have none of: ports, a system, a material, the storey
fallback and an unstyled element, and again agree with the converter. When the buildingSMART clone of the session is present, the IFC2X3 and IFC4X3 versions of the
Simple-Scene files (`Infra-Bridge`, `Infra-Rail`, `Infra-Road`, `Infra-Plumbing`, the three Building files) give the converter's class counts, systems and storeys as well.
Differences that are kept and explained:

- **Colour.** The reader uses the colour web-ifc reports (the IFC surface colour, with transparency). The converter uses ifcopenshell's diffuse colour, which for
  some exporters differs (the FZK-Haus from ARCHICAD is brighter here: its `IfcSurfaceStyleRendering` carries `DiffuseColour` as a ratio such as 0.81, which ifcopenshell multiplies into the surface colour and web-ifc ignores), and for an element with no style
  ifcopenshell supplies its own default (door brown, slab grey), where the reader falls back to the converter's own class table (`CLASS_COLORS`: concrete grey, duct
  blue, pipe green, cable carrier orange, else 0.7 grey). An element has no style when web-ifc reports opaque white and no `IfcStyledItem` is reachable from its representation, or when the file has no `IfcStyledItem` at all.
- **Triangles.** Meshes are web-ifc's, not ifcopenshell's: curved shapes are tessellated differently (bounds still agree within 1 cm on the samples).
- **Storey of an element inside an `IfcSpace`.** The reader climbs from the space to its storey; the converter's loop does not return one in that case and falls back by elevation.

Measured here (headless Chromium with swiftshader on a 4-core VM, `node web/bench/smoke-open-file.mjs`; the numbers are the time from choosing the file to "Loaded ...", with a cold worker unless noted; the dev-server column is the range over several runs, other jobs ran on the VM in some of them):

| File | Size | Elements | Dev server | `file://` single file |
| --- | --- | --- | --- | --- |
| Building-Structural.ifc | 0.2 MB | 14 | 1.3 to 2.5 s | 2.7 s |
| same, worker started by the Open button, file chosen 1.5 s later | | 14 | 0.2 s | 0.2 s |
| Building-Structural + Architecture + Hvac (federated) | 0.4 MB | 26 | 1.0 to 1.6 s | not run |
| AC20-FZK-Haus.ifc | 2.5 MB | 82 | 1.8 to 2.0 s | 1.8 s |
| Infra-Bridge.ifc (IFC4) | 1.7 MB | 47 | 1.4 to 1.7 s | 0.9 s |
| synthetic, 2,000 boxes | 0.8 MB | 2,000 | 2.0 s | 2.1 s |
| synthetic, 20,000 boxes (240,000 triangles) | 8.2 MB | 20,000 | 11.8 s | 11.9 s |

About 2 s of the cold numbers is starting the worker and compiling the 1.5 MB wasm (the first line is that and little else), which the Open
button's early start hides. The rest is web-ifc (about 0.2 ms per element for plain extrusions at 20,000 elements, rising towards 0.45 ms at 100,000), then the
build and `parseModel` on the main thread (about 0.25 ms per element for the glb and loader, with the page frozen for that time: 4 to 5 s at 20,000 elements).
In node without a browser, a synthetic 100,000-element, 42 MB, 1.2 million triangle file took 45.6 s to extract, 4.2 s to build and 27.9 s in `parseModel`, with the
process at 2.4 GB resident, so files in the tens of megabytes are practical and a few hundred megabytes are not. The synthetic files come from a small generator that is not in the repository (`IfcWall`, `IfcSlab` and `IfcBeam` extrusions on a grid).

Single-file size: **3.84 MB (4,025,117 bytes) with the IFC reader, 2.61 MB (2,737,889 bytes) with `--no-ifc`** (the single file before the reader was 2.71 MB). The reader adds
1.23 MB: the worker script (web-ifc's JavaScript, 3.36 MB) and `web-ifc.wasm` (1.52 MB) are embedded gzip-compressed and base64-encoded (0.48 MB and 0.73 MB), inflated with
`DecompressionStream` when the first file is opened (the worker through a Blob URL, the wasm handed to the worker, which gives it to web-ifc through a Blob URL as well). Opened
from `file://` the bundle makes no network requests (`node web/bench/smoke-open-file.mjs --single`: none). In the `--no-ifc` bundle the button still opens glb files, and an IFC file
gives "This build does not include the IFC reader". The normal build (`npm run build`) keeps the worker and the wasm as separate files under `dist/assets`.

Licence: web-ifc 0.0.78 is MPL-2.0 (file-level copyleft). It is used unmodified; this repository adds nothing to its files. The single-file viewer embeds it (the
worker script is web-ifc's JavaScript plus the code of `ifcRaw.ts`; the wasm is `web-ifc.wasm`) and says so in an HTML comment with the source location
(https://github.com/ThatOpen/engine_web-ifc). The text of the MPL is in `web/node_modules/web-ifc/LICENSE.md`. `ifcopenshell` (LGPL) stays a build-time tool of the converter and is not part of the viewer.

Checks: `cd web && npm test` runs `tests/ifc-import-build.test.ts` (the pure `build` stage on synthetic RawModels), `tests/ifc-import-plan.test.ts` (selection rules and
status text) and `tests/ifc-import-parity.test.ts` (web-ifc against the converter, a few seconds). `node bench/smoke-open-file.mjs` drives the real page in headless Chromium with
`page.setInputFiles`: the panel layout, a single IFC, three federated IFC, the FZK-Haus, glb with sidecar, glb alone, corrupt, empty, truncated, unsupported, mixed and 101 MB inputs
(the model on screen must survive each), `.ifczip`, drag and drop with the overlay, cancelling mid-load, and no console errors. Options: `--single` (the bundle from `file://`, no
non-file requests allowed), `--single --no-ifc`, `--dist` (production build through `vite preview`), `--no-worker` (main-thread fallback), `--stress file.ifc`.
Screenshots: `web/bench/open-file-fzk.png`, `open-file-federated.png`, `open-file-dropzone.png`.

Known limits:

- Only what web-ifc can mesh is shown. Elements it cannot turn into triangles (some `IfcAdvancedBrep` and B-spline surfaces, unusual boolean or
  swept constructions, alignment-based geometry in IFC4X3) are silently missing from the model; `[ifc-import]` in the browser console and `RawModel.stats` count products without geometry. Openings that web-ifc cannot subtract leave the host solid.
- IFC4X3 is read (the Simple-Scene IFC4X3 files give the converter's classes and counts, `IfcRoadPart`, `IfcCourse`, `IfcRail` and so on) but alignments, linear placement
  and referents are only as complete as web-ifc 0.0.78; coverage beyond the sample files is untested. IFC2X3 and IFC4 are the well-trodden paths.
- Size: everything is in memory several times over (file, wasm heap, typed arrays, glb, merged geometry, BVH), roughly 25 times the file size at 40 MB. The browser's
  wasm limit (4 GB at most) and the tab's memory decide; see the numbers above. No streaming, no level of detail.
- Properties other than class, name, GlobalId, storey and material name are not read, so class styles that match on other properties cannot be used.
- web-ifc 0.0.78 quirk handled in `ifcRaw.ts`: the browser wasm's `StreamMeshes` takes three arguments although the JavaScript wrapper passes four; the reader calls the wasm function directly when the wrapper's call is refused.
- The page is not usable while the build and `parseModel` steps run (see above); the reading itself does not block it.
- Firefox and Safari were not available here; the bundle needs `Worker` from a Blob URL on `file://` and `DecompressionStream`, which Chromium has.

## Class styles

Per-class base appearance, settable at build time and editable at runtime. Example: "Steel should be at most 80% opaque" is `"Steel": { "alphaMax": 0.8 }`.

Config file `web/public/xray.config.json` (schema `xray-config/1`):

```json
{
  "schema": "xray-config/1",
  "classStyles": {
    "Steel":     { "alphaMax": 0.8 },
    "IfcColumn": { "floor": 0.5 },
    "IfcGrid":   { "hidden": true }
  },
  "materialAliases": {
    "Steel": ["IfcMember", "IfcBeam:steel", "IfcColumn:steel", "IfcPlate"]
  }
}
```

Style fields (all optional, alpha values 0..1):

| Field | Effect |
| --- | --- |
| `alphaMax` | Caps the element's opacity in every bucket (Far, non-context, and with X-ray off): `alpha = min(alpha, alphaMax)`. Focus elements are exempt, unless the style is keyed by the element's own ifcClass. |
| `alphaMin` | Replaces `sightlines.alphaMin` for this class: the deepest ghosting an occluder of this class reaches (target = alphaMax + (alphaMin - alphaMax) * importance). |
| `floor` | Opacity floor for Algorithm 7. Replaces `overrides.categoryFloors[ifcClass]` for the class (which stays the fallback). |
| `color` | `[r, g, b]` in 0..1, replaces the element base colour. |
| `hidden` | Hides the class. |

Keys are an ifcClass (`IfcColumn`) or a material-class alias (`Steel`). An alias lists what it covers in `materialAliases`: a bare class name (`IfcMember`) matches every element of that class, `Class:text` (`IfcBeam:steel`) additionally needs the element's material name to contain `text` (case-insensitive). Aliases are resolved once per model into a per-element style index (`src/styles.ts`). When several entries apply to an element they merge field by field: aliases first (in key order), then the entry keyed by the element's ifcClass, so element-level entries win over alias entries.

Precedence across sources, lowest first: `xray.config.json`, then the `styles` / `materialAliases` fields of the model sidecar, then runtime edits.

- Build time: `python3 tools/ifc2glb.py ... -o web/public/models/building --config web/public/xray.config.json` copies `classStyles` and `materialAliases` into `model.json` as `styles` and `materialAliases` (`tools/synth_model.py` takes the same flag). The loader passes them through on `SceneModel.styles` / `SceneModel.materialAliases`.
- Runtime: the "Class styles" panel folder has one sub-folder per class present in the model (and per alias that matches at least one element), titled with the element count, with alpha max, alpha min, floor, hidden and colour controls. Edits call `controller.setClassStyles(styles, aliases)` then `app.reclassify()`, and are stored per model in `localStorage` under `xray.classStyles.<modelName>`. Buttons: "Reset to config" (drops the runtime edits), "Export JSON" (downloads the effective styles as `xray.config.json`), "Import JSON" (loads a config file as the runtime edit layer).
- Code: `src/styles.ts` (resolution), `src/controller.ts` (`settings.classStyles`, `setClassStyles`, cap/colour/hidden in the apply path, alphaMin in the targets), `src/algo/overrides.ts` (`styleFloor`), `src/plugins/classStyles.ts` (config load, panel), `tests/class-styles.test.ts`.

## Controls

| Input | Action |
| --- | --- |
| Left drag, wheel, right drag | Orbit, zoom, pan |
| Click | Select the element under the cursor (ghosts below 0.3 alpha are click-through) |
| Shift+click | Add to the selection |
| Click empty space, Escape | Clear the selection |
| X | Toggle X-ray |
| F | Frame all |

The lil-gui panel (top right): the "Open model" folder (see "Opening your own files"), model picker, X-ray and Tiers mode, buffer parameters and storey band (Algorithm 1), samples,
alphaMin/Max, gamma, occluder scope (`all` or `near`), far weight and smoothing rate (Algorithm 2), edge alpha, ghost desaturation, focus-in-front, far mode (opaque or hidden),
debug colour by bucket, user pin floor and the IfcColumn category floor (Algorithm 7), and the buttons Pin selected, Hide selected,
Clear pins/hides and Frame all. Tiers mode uses `[focusClasses]`, `[IfcBeam, IfcColumn]`, `[IfcSlab, IfcWall, IfcWallStandardCase, IfcFooting]`.
The overlay at the bottom left shows element and bucket counts, the last Algorithm 1 and 2 times with ray count, the rolling frame
time, and for the hovered (else the first selected) element its id, class, bucket, proximity weight, occlusion, target alpha and
current alpha. `window.__xray = { app, renderer, classification, stats }` and `window.__xrayReady` are exposed for scripts.

## Code map: report algorithms to code

| Report algorithm | File | Function |
| --- | --- | --- |
| 1. Static classification (Focus, Host, Near, Far, proximity weight) | `web/src/algo/classify.ts` | `classify`, `classifyFromFocus`, `connectedRun`, `bufferRadius` |
| 3. Coarse-to-fine candidate filtering (AABB, then mesh) | `web/src/algo/classify.ts`, `web/src/render/geometry.ts` | `boxDistance` in `classifyFromFocus`; `BvhGeometryProvider.intersects`, `surfaceDistance` |
| 2. Sightlines: sample, ray cast, occlusion, importance, target alpha | `web/src/algo/sightlines.ts` | `collectSamples`, `castSamples`, `sightlines` |
| 2. (L10-11) floors and smoothing, render-state write | `web/src/algo/sightlines.ts` | `smoothAlpha`, `applyRenderState` |
| 7. Opacity floors from pins (user, category, project) | `web/src/algo/overrides.ts` | `computeFloors` (viewpoint rules are a hook, `extraFloor`) |
| 8/9. Category tiers and tiered sightlines | `web/src/algo/tiers.ts` | `classifyTiers`, `sightlinesTiered` |
| Geometry queries (ray all-hits, distance, samples) | `web/src/render/geometry.ts` | `BvhGeometryProvider` |
| Update sequence and per-frame easing | `web/src/controller.ts` | `XrayController.reclassify`, `updateSightlines`, `tick` |
| UI, input, debounce, overlay | `web/src/app.ts` | `ViewerApp` |
| Ghost, focus and edge passes | `web/src/render/renderer.ts`, `shaders.ts` | `XrayRenderer` |

### Deviations from the report

1. **Selection always joins Focus, whatever its class.** Algorithm 1 line 1 of the report keeps only selected elements whose class is in
   `focusClasses`, so selecting furniture, a footing or a slab gave an empty Focus and nothing happened. Here every selected element is
   Focus (explicit selection is intent). The ConnectedRun expansion (ports and systems) still applies only to selected elements whose
   class is in `focusClasses`. Context excludes the whole Focus set, so selecting a slab makes the other slabs and walls Context, and a wall
   that intersects it is Host. The tiered variant puts a selected element of any class into the top tier.
2. **Far elements that block a sightline ghost.** The report's Algorithm 2 only casts rays against Host + Near, so an exterior wall 3 m from
   the duct that sits between the camera and the duct never ghosts. With `sightlines.occluderScope = 'all'` (the default) every Context
   element is a ray candidate. Host and Near use the report's formula, `target = alphaMax + (alphaMin - alphaMax) * occlusion^gamma * proximityWeight`.
   Far elements have no proximity weight; they get `farWeight` (default 0.7) and a ceiling of 1 instead of `alphaMax`:
   `target = 1 + (alphaMin - 1) * (occlusion^gamma * farWeight)`. A Far element that blocks nothing stays fully opaque, one that blocks the
   whole focus settles at `1 + (alphaMin - 1) * farWeight` (0.40 with the defaults). Pins and floors apply to Far elements too, far mode
   `hidden` still hides them, and the tiered variant uses each Far element's own tier context and `tierAlphaMin`. Setting
   `occluderScope = 'near'` restores the report's behaviour exactly (Far is never ghosted). Both settings are in the Sightlines (Alg 2) folder
   of the panel. Cost: the ray candidate set grows from Host + Near to all Context; the BVH provider already casts one ray against the merged
   triangles and filters hits by element, so its cost is unchanged, only the candidate set lookup and the per-element bookkeeping grow.
3. **Stacked occluders are weighted by depth order.** The report credits every occluder on a ray with 1 hit, so three slabs that block the
   same rays all land on the same alpha (about 0.24 with the defaults) and composite into a veil with no layer separation. The ray caster
   returns the hits of a ray ordered from the sample point towards the camera, so the last hit is the one nearest the camera. Order
   `k = 0` is the occluder nearest the camera, `k = 1` the next one behind it, and so on; the hit credit added to the occluder's accumulator is
   set by `sightlines.layerWeighting`:

   | `layerWeighting` | credit of the k-th occluder | notes |
   | --- | --- | --- |
   | `front` (default) | `layerFalloff^k` | `layerFalloff` 0.5 gives 1, 0.5, 0.25: the front layer carries most of the transparency, deeper layers stay more solid |
   | `budget` | 1 if `k < layerBudget`, else 0 | `layerBudget` (integer, default 2): only the first N layers per ray ghost, deeper ones stay opaque (peel just enough) |
   | `uniform` | 1 | the report's behaviour |

   `occlusion = sum of credits / totalSamples` as before, so it stays in [0, 1]; the rest of Algorithm 2 (gamma, proximity weight, `farWeight`,
   ceilings, floors, smoothing) is untouched. Under `occluderScope = 'all'` Far elements take layer slots like any other occluder; under
   `'near'` they are not candidates and take none; elements flagged hidden are not candidates either. A single occluder per ray always has
   k = 0 and credit 1, so the worked example (S1 at occlusion 0.75, target alpha 0.24) is the same in every mode. The tiered variant
   (Algorithm 9) uses the same credit, counting only the occluders that can hide the sample (rank above the sample's own) when it
   assigns k. Note that with tiers the default `front` halves the credit of a lower tier that sits behind a higher one from the camera's
   side. The three settings are in the Sightlines (Alg 2) folder of the panel. The test fixture is `web/tests/fixtures/stacked-scene.ts`,
   covered by `web/tests/stacked-layers.test.ts`. With the fixture (three 250 mm slabs, 300 mm apart, camera above) `front` gives
   occlusions 1.0 / 0.5 / 0.25 and target alphas 0.15 / 0.36 / 0.50 from the top slab down; `budget` 2 leaves the bottom slab at `alphaMax`.

## Known limitations

- Per-object blending with one merged geometry: the ghost pass draws all ghosted elements in one draw call with no per-object
  depth sort, so overlapping ghosts can blend in the wrong order (visible as slight tonal differences at crossings). A per-object
  sort would need one draw per element or order-independent transparency.
- "Focus in front" draws the focus with depth test off; it is never occluded, including by opaque far elements.
- Picking uses the CPU BVH and treats non-focus elements with alpha below 0.3 as click-through, so a heavily ghosted slab cannot be selected by clicking it (clear the selection first or use `selectIds`).
- Swiftshader numbers are CPU rasterisation. The frame times in `web/bench/RESULTS.md` are not GPU numbers (a 1920x1080 frame of the
  5,000-element model takes hundreds of milliseconds there); the Algorithm 1 and 2 timings are CPU JavaScript and are meaningful, but
  they share the machine with the software rasteriser.
- The demo models `building` and `plumbing` have no `IfcRelVoidsElement` relations, so `relations.hosts` is empty and Host detection
  uses the geometric fallback (AABB overlap, then mesh intersection or containment). `synth5k` has hosts relations (synthetic openings).
- Viewpoint opacity rules of Algorithm 7 (floor plate underfoot, exterior wall) are not implemented; the exterior-wall case is covered
  by `occluderScope = 'all'` (see Deviations). Smoothing is per frame, not per
  unit time, so convergence speed depends on frame rate.
- With X-ray off the viewer shows everything opaque, and user hides are not applied.
- The in-memory distance cache assumes a static model; call `clearCaches()` if geometry changes.

## Model sources

- `models/Building-*.ifc` and `models/Infra-*.ifc`: buildingSMART Sample-Test-Files, IFC 4.0.2.1 Simple-Scene, repository commit
  `80d976a9`, retrieved 2026-10-30.
- `models/AC20-FZK-Haus.ifc`: KIT FZK-Haus from the IfcOpenShell repository (see `models/NOTE.md`); converted to `fzk-haus.glb` but not
  offered in the model picker.
- `synth5k`: generated by `tools/synth_model.py`, no external source.
