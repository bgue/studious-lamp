# BIM X-ray viewer: reference implementation

A WebGL viewer for building models that implements the X-ray mode of the report "BIM X-Ray Vision: Technical Implementation
Report". Select a duct, a pipe or any element and the structure that hides it ghosts, in proportion to how much it blocks the
view and how close it is. Everything else stays opaque. The selection and the elements connected to it (a duct run, a system)
form the Focus; slabs, walls, beams and columns are the Context; the Context that crosses or sits near the Focus (Host and
Near) and whatever blocks the line of sight to it are the occluders, and only they change alpha.

Around that core the viewer is a small coordination tool. It opens IFC and glb files straight from disk (no server, no
converter), cuts and sections the model in several ways, measures, schedules penetrations, reads and writes BCF issues, overlays
laser scans, finds debris, and can be packed with a model into one HTML file to send to someone. It is built as a core plus
plugins (see "Development"), so every feature below is a separate module with its own document under `web/docs-features/`.

- **Viewing**
  - X-ray ghosting with edges, per-camera-move sightlines, category tiers, pins and class styles; weighted blended
    order-independent transparency for the ghost pass.
  - View modes: behind-only cut and partial peelback ([view-modes.md](web/docs-features/view-modes.md)).
  - Imaging looks: radiograph and MRI slice ([imaging.md](web/docs-features/imaging.md)).
  - Section box and section plane with caps ([section.md](web/docs-features/section.md)).
  - Cinematic effects: fly-to, flythrough, tour, sweep and reveal, exploded storeys, bloom, edge glow, depth grading.
  - Presets: twelve named looks on keys `1` to `9` ([presets.md](web/docs-features/presets.md)).
- **Coordination**
  - Measure (point to point, element to element) and clearance colouring ([measure.md](web/docs-features/measure.md)).
  - Penetration schedule: where MEP passes through hosts and whether there is an opening ([penetrations.md](web/docs-features/penetrations.md)).
  - BCF 2.0, 2.1 and 3.0 issues with viewpoints ([bcf.md](web/docs-features/bcf.md)).
  - Point clouds and as-built deviation ([pointcloud.md](web/docs-features/pointcloud.md)).
  - Model cleanup: find and hide floating, tiny, duplicate or distant debris ([cleanup.md](web/docs-features/cleanup.md)).
  - WebXR, experimental: walk through the model in VR, place it on a table in AR, or lay it at real size over the real building on
    site (field AR) to see the services behind walls ([webxr.md](web/docs-features/webxr.md)).
- **Input and output**
  - Open `.ifc`, `.ifczip` and `.glb` in the browser; large files are handled in a worker ([large-ifc.md](web/docs-features/large-ifc.md)).
  - Selection sets, static or by criteria query ([sets-query.md](web/docs-features/sets-query.md)), class styles, parameter
    export and import, share links.
  - `xray-pack`: model plus viewer in one HTML file ([xray-pack.md](web/docs-features/xray-pack.md)).
  - A single-file viewer, `xray-viewer.html`, that runs from disk.
- **Navigation**
  - Model tree, hover cards with properties ([hover-info.md](web/docs-features/hover-info.md)).
  - Keyboard navigation, cheat sheet, command palette, rebindable keys ([keyboard.md](web/docs-features/keyboard.md)).
  - Action panel (toolbar) with a drawer per tool ([toolbar.md](web/docs-features/toolbar.md)), tooltips on every setting
    ([docs/SETTINGS.md](docs/SETTINGS.md)).

`SPEC.md` is the contract for the model format, the extension points and the rendering design.

## Quick start

**Without installing anything:** open `xray-viewer.html` (at the root of the zip) in Chromium, Edge or Chrome by double-click. It
is one file with the app, the sample models (`building`, `fzk-haus`, `plumbing`, `debris-demo`) and the IFC reader inside; it
makes no network requests. Firefox and Safari were not available for testing here.

**From source** (Node 22 and npm):

```sh
cd web
npm install
npm run dev          # http://127.0.0.1:5173/?model=building
```

`?model=` takes `building`, `fzk-haus`, `plumbing`, `synth5k`, `debris-demo` or `procedural`. An unknown or unloadable value
falls back to the in-memory procedural model and shows a red message at the top. Then: click an element (a duct is a good start),
orbit with the left mouse button, press `X` to switch x-ray on and off, `?` for the key list.

## Opening your own files

Open IFC and glb files from disk without the Python converter and without a server.

- **Open model** (top of the panel, and the first tool of the action panel): **Open IFC or glb file** (multiple files allowed),
  **Cancel load**, and the read-only **Load status**. Or drop files anywhere on the page.
- Accepted: `.ifc`, `.ifczip`, `.glb`, and `.json` (the `xray-model/1` sidecar of a glb). Several IFC files are **federated** into
  one model with the converter's rules (consecutive ids, storeys merged by name and elevation within 1 cm, an element with the same
  GlobalId, class and bounds is skipped, the same GlobalId with different geometry is renamed `<GlobalId>~<n>`). One glb takes the
  `.json` of the same base name as its sidecar; without one, classes are guessed from node names.
- Wrong input (mixed IFC and glb, several glb, a lone `.json`, unsupported types, empty or corrupt files) gives a one-line message
  in Load status and in the red segment of the status bar; the model on screen stays. Over 100 MB in total the loader warns and carries on.
- The model is named `file:<first file name>` (` +N more` when federated) and is added to the Model picker for the session only.
  Selection sets and class styles are kept per name in `localStorage`.

**How an IFC file is read.** A module Web Worker runs web-ifc (`src/model/ifcRaw.ts`): products are meshed in chunks, relations and
properties are read. With the **direct path** (the default) the worker also merges the geometry into the flat arrays the renderer
draws, computes the crease edges and builds and serialises the BVH, then hands everything over as transferables; the main thread
only wraps them (`MergedGeometry.fromArrays`). A 100,000-element file no longer freezes the page. The glb path (`buildModelData`,
`writeGlb`) is unchanged and is what `xray-pack` and the parity tests use. Without a worker the same code runs on the main thread.
Details and measurements: [large-ifc.md](web/docs-features/large-ifc.md), `web/bench/RESULTS-large-ifc.md`.

Options (folder **Open model**, applied to the next IFC file you open, not stored):

| Option | Values | Effect |
| --- | --- | --- |
| `edges` | `auto` (default), `all`, `none` | Edge lines. `auto` skips them above 50,000 elements (largest extra buffer, slow to draw). |
| `properties` | `common` (default), `none` | `none` skips property reading: faster and smaller, hover cards show no property sets. |
| `Model stats` | read-only | Elements, triangles, buffer megabytes and load seconds of the model on screen. |

`Load status` walks through the stages with counts: `Reading X, 89.6 MB`, `Opening X`, `Meshing 4800 of 100000`, `Reading
relations`, `Merging 52000 of 100000 elements`, `Edges 31000 of 100000 elements` (or `Edges skipped (auto: over 50,000
elements)`), `BVH 45% (1.76 M triangles)`, `Transferring geometry`, `Uploading 100000 elements`, then `Loaded 100000 elements in
23.4 s`. The `Large model` tool shows the same numbers with per-stage timings.

The reader follows the converter (`tools/ifc2glb.py`): it skips `IfcOpeningElement`, `IfcSpace`, `IfcSite`, `IfcBuilding`,
`IfcBuildingStorey`, `IfcAnnotation`, `IfcSpatialZone`, `IfcExternalSpatialElement`, `IfcGrid`, `IfcVirtualElement` and the
`origin` / `geo-reference` proxy cubes; rotates Z up to Y up; shifts the bounds centre to the origin (`originShift`); smooths
normals with a 30 degree crease; assigns storeys by containment with a nearest-storey fallback; derives `hosts` from voids and
fills; resolves ports and systems; and records opening bounds (`relations.openings`) and properties (`props`).
`web/tests/ifc-import-parity.test.ts` compares it with the converter's output: same classes, elements, relations, storeys, material
names, element bounds within 1 cm. Documented differences: colours (web-ifc's surface colour against ifcopenshell's diffuse
colour; unstyled elements take the converter's class colours), tessellation of curved shapes, and the storey of an element inside
an `IfcSpace`.

## Packaging viewers with xray-pack

`xray-pack` wraps a model in the viewer and writes one self-contained `.html` file that opens from `file://` or an email
attachment. You choose the starting parameters, preset, selection, visible tools, camera and kiosk mode.

```sh
cd web
npm run pack -- ../models/AC20-FZK-Haus.ifc -o fzk.html
npm run pack -- Building-Structural.ifc Building-Architecture.ifc Building-Hvac.ifc -o building.html --select class:IfcDuctSegment --kiosk
```

Inputs are `.ifc` / `.ifczip` (federated) or one `.glb`. IFC files are converted in node by the same TypeScript reader the
browser uses. Options (`--params`, `--preset`, `--select`, `--tools`, `--open-tool`, `--kiosk`, `--camera`, `--ifc-reader`,
`--samples`, `--views`, `--open-view`, `--force`, ...), the boot sequence, templates, CI use and limits are in
[web/docs-features/xray-pack.md](web/docs-features/xray-pack.md).

## The action panel and its tools

A vertical icon strip at the left edge of the canvas (key `t` shows or hides it) with a drawer per tool. Only one drawer is open
at a time; Escape closes it. Every tool also has a folder in the parameter panel (top right), palette commands (Ctrl+K) and a
`window.__xray*` scripting object. [toolbar.md](web/docs-features/toolbar.md) describes the strip and the shared overlay.

**Status bar.** A one-line, 22 px bar along the bottom of the canvas, between the strip and the parameter dock (it follows both
when they collapse, and the phone layout): model name and element count, x-ray on or off (and tiers), the bucket counts
focus, host, near and far, the hovered or selected element (`#id class "name"`) and the frame time. Its tooltip and the `ⓘ`
button (or a click on the model name) show the full details (Algorithm 1 and 2 timings, rays, the bucket, occlusion and alpha
of the element) and the credits of the built-in models ("About models"; a single-file bundle lists its embedded models and
says that it needs no server). Messages (loading, errors, imports) appear as a red segment with a dismiss button instead of a
banner over the canvas. The bar keeps the id `xray-overlay` (the message text `xray-message`); `src/ui/statusBar.ts`.

**Edge glow** (Cinematic, `Edge glow` folder). A glowing outline whose `glow scope` is `focus` (default: the focus set), `near`
(focus, host and near buckets) or `all` (every visible element). It follows the selection and the classification. Older
parameter documents with `glowNear: true` load as `near`.

- **X-ray** (key `X`). Switches the ghosting of occluders on and off. The settings are the report's: buffer, samples, alpha
  range, gamma, smoothing, occluder scope, layer weighting, far mode, tiers, pins and floors (see "Defaults" in `SPEC.md` and
  "Deviations from the report" below).
- **View modes** ([view-modes.md](web/docs-features/view-modes.md)). Behind-only (`b`) cuts the context in front of the focus
  with a plane square to the view; partial peelback (`p`) cuts a window shaped like the focus silhouette. Both decide per
  fragment, so large slabs are split rather than hidden whole.
- **Imaging** ([imaging.md](web/docs-features/imaging.md)). Radiograph and MRI-slice looks with the focus as the glowing
  "bone"; key `m` cycles `standard`, `radiograph`, `mri`. `auto exposure` (default on) fits the radiograph brightness to the
  thickness of the model, so a tall stack of floors stays readable.
- **Section** ([section.md](web/docs-features/section.md)). A section box fitted to the selection or the model with draggable
  face handles, plus a section plane; keys `c`, `Shift+c`, `Alt+c`. BCF clipping planes use the same renderer call. Caps are
  painted on closed solids only.
- **Gizmo** ([gizmo.md](web/docs-features/gizmo.md)). A navigation cube in the bottom-right corner of the stage: click a face,
  edge or corner to look from there, drag to orbit, roll or turn 90 degrees, home, perspective / orthographic. Next to it a
  section strip: planes X / Y / Z through the selection, a box fitted to the selection, flip, caps, clear. The section plane
  gets an arrow (push / pull with a metre readout) and rings (tilt in 15 degree steps, Shift free) on the model. Key `v`
  hides it; on a phone it collapses to a button.
- **Measure** ([measure.md](web/docs-features/measure.md)). Point to point (with vertex snapping) and element to element
  (minimum surface distance), dimension lines on the model, CSV export.
- **Clearance** ([measure.md](web/docs-features/measure.md)). Colours the context by distance to the focus: clash (red), tight
  (amber), ok (blue ramp).
- **Penetrations** ([penetrations.md](web/docs-features/penetrations.md)). A schedule of where MEP elements pass through slabs,
  walls and beams, with orientation, size and opening status; markers on the model, CSV export, and BCF topics from rows.
- **BCF** ([bcf.md](web/docs-features/bcf.md)). Open or drop `.bcf` / `.bcfzip`, apply viewpoints (camera, selection, hides,
  colours, clip planes), create topics with snapshots, comment, export BCF 2.1 or 3.0. Topics are pinned to a 3D point (numbered
  markers on the model) and viewpoints carry callouts, notes, arrows and linked measurements; they live in a side file
  `xray-markup.json` per topic folder (the BCF XML still validates) and are burned into the exported snapshot.
- **Point cloud** ([pointcloud.md](web/docs-features/pointcloud.md)). Open LAS, E57, PLY, PCD, XYZ or PTS scans, align them (Align by 3 points and Refine (ICP) with oriented point normals, room by room with `align within`, also for phone LiDAR scans), and colour
  the points by deviation from the model (tolerance 2 cm by default). `tools/make_pointcloud.py` makes a sample scan.
- **Cleanup** ([cleanup.md](web/docs-features/cleanup.md)). Rules for floating, tiny, distant, duplicate and degenerate elements
  and class groups; preview, hide and restore without changing the model. Every threshold names its unit; lengths show in mm, cm
  or m (`length unit`) and are stored in metres. The `debris-demo` model has examples of each (below).
- **WebXR** ([webxr.md](web/docs-features/webxr.md)), experimental. Feature detected; the `WebXR` folder and tool appear only on a
  device that supports VR or AR (or AR Quick Look). VR at real scale from the orbit camera with controller rays, trigger to select,
  squeeze for X-ray, snap turn and walking; AR with a hit-test ring, placement, and the scales `1:1` and `tabletop 1:50`.
  **Field AR** for the building site (Android Chrome with ARCore, Quest 3 / 3S): register the model on the real building by 2 or
  more point pairs (model points picked before or in the session, room points by hit test; yaw and shift solved with gravity
  kept, residuals shown), a WebXR anchor that holds it while you walk, saved sites (persistent anchors on Quest, re-tap 2 points
  elsewhere), cm and degree nudges, the looks `x-ray` / `ghosted` / `full`, a cut around you and at the storey ceiling, tap for
  the element card and its clearance, overlay snapshots that become BCF topics, a phone panel. iPhone and iPad have no WebXR in
  any browser: they get a USDZ export for AR Quick Look (placed on a surface, no registration) and a QR link. Developed and tested
  against the iwer emulator, not on a device.
- **Presets** ([presets.md](web/docs-features/presets.md)). Named looks, user presets, share links.
- **Large model** ([large-ifc.md](web/docs-features/large-ifc.md)). Size, buffers and per-stage timings of the model opened from a file.

Hover cards ([hover-info.md](web/docs-features/hover-info.md)) show name, class, storey, material and a few properties after the
pointer rests 350 ms; the default property filter also matches ArchiCAD's `BaseQuantities.*` keys.

### The debris-demo model

`?model=debris-demo` is a 400-element synthetic building (`python3 tools/synth_model.py -n 400 --debris 24 -o
web/public/models/debris-demo`) with 14 floating bolts and 10 offcuts, a cluster of three touching 12 cm boxes, one stray 300 m
away, two duplicate beams and a zero-thickness wall, all named `Debris ...` and listed in the selection set **Debris**. With the
cleanup defaults the floating, tiny, distant, duplicate and degenerate rules match all of them except the cluster (its boxes touch
each other; set the floating `mode` to `small clusters` to include it) and no structure.

## Selection sets

The **Sets** tab of the sidebar keeps named groups of elements per model ([sets-query.md](web/docs-features/sets-query.md)).
A static set lists elements saved from the selection. A criteria set stores a query and finds its members again on every
model load and every apply:

```sql
class IN ('IfcWall', 'IfcWallStandardCase') AND "Pset_WallCommon.IsExternal" = TRUE AND "BaseQuantities.NetVolume" > 2
```

The language is a SQL `WHERE` subset (`= != < <= > >=`, `LIKE`, `IN`, `BETWEEN`, `IS NULL`, `AND OR NOT`, parentheses) over
one row per element: `class`, `name`, `storey`, `storeyElevation`, `material`, `globalId`, `id`, bounds (`xMin` ... `zMax`,
`sizeX/Y/Z`, `volume`) and every property key in double quotes. Missing values are NULL with SQL three-valued logic; strings
compare without case. It is a small parser in `web/src/query/` (no SQLite), about 20 ms for 100,000 elements.
**New criteria set** opens a row builder (field, operator, value, with suggestions from the model) that writes the query,
next to a raw query box, a live match count with inline errors, and **Preview**. Each set is one line: click the name to
select and frame, **+** to add, **⋯** for Update or Re-evaluate, Rename, Edit criteria, Duplicate and Delete; a filter box
finds a set among many. Right-click a row of the properties footer (or its **⋯**) to select all elements with the same
value or the same property, copy the value, or save the equivalent query as a criteria set. Sets are stored by GlobalId
in `localStorage` (`xray.sets.<model>`) and exported as `xray-sets/1` JSON; criteria sets add `kind` and `query` and stay
readable by older versions as static sets.

## Saved views

The **Views** tab of the sidebar keeps named viewpoints per model ([saved-views.md](web/docs-features/saved-views.md)).
**Save view** (`Ctrl+Shift+S`) stores the camera (with roll, field of view and the orthographic flag), the section box and
plane, the selection, hides, pins and isolate, the exploded state, x-ray, view modes, imaging and the other look settings,
plus a small thumbnail. Click a row to restore it (the camera turns there; elements are matched by GlobalId, and missing ones
are reported in the status bar); `Shift+PageUp` / `Shift+PageDown` step through the views and **Play** shows them as a
slideshow with a dwell time. Each row has **⋯** for Update, Rename, Duplicate, Copy link (`#view=`, one view), Save as BCF
topic and Delete; rows reorder by dragging and a grid toggle shows the thumbnails. Views are stored in `localStorage`
(`xray.views.<model>`), exported and imported as `xray-views/1` JSON, and packed with
`xray-pack ... --views views.json --open-view "Name"`.

## Keyboard

The common bindings (all rebindable; full list in [keyboard.md](web/docs-features/keyboard.md)). Keys are ignored while a text
field has focus. **`?` (or `F1`) opens the full cheat sheet; `Ctrl+K` opens the command palette**, which lists every action and
every button of the parameter panel.

| Input | Action |
| --- | --- |
| Left drag, wheel, right drag | Orbit, zoom, pan |
| Click, Shift+click | Select the element under the cursor (ghosts below 0.3 alpha are click-through); add to the selection |
| Escape | Close overlays, then clear the selection |
| `X` | Toggle x-ray |
| `F`, `Home` | Frame the selection (else all); frame all |
| Arrow keys, `W A S D Q E` | Orbit; fly |
| `+` / `-`, `PageUp` / `PageDown` | Zoom; storey up and down |
| `Tab`, `Shift+Tab` | Next and previous selected element |
| `Alt+Left`, `Alt+Right` | View history back and forward |
| Numpad `1` `3` `7` `0` `5` | Front, right, top, isometric, perspective or orthographic (`Ctrl` for the opposite side) |
| `Ctrl+A`, `Ctrl+I`, `Alt+S` | Select all visible, invert, same class |
| `H`, `Shift+H`, `Alt+H` | Hide selected, hide everything not selected, unhide all |
| `[`, `]`, `/` | Model tree, parameter panel, tree filter |
| `B`, `P`, `M`, `C` | Behind-only, peelback, imaging cycle, section box |
| `I`, `T`, `V` | Hover info, action panel, view cube and section strip |
| `1` to `9` | Presets |
| `Ctrl+Shift+S`, `Shift+PageUp` / `Shift+PageDown` | Save view; previous and next saved view |

## Presets

Applying a preset sets parameters only; it never changes the model or the selection. Built-in presets reset the sections they
touch first, so switching between them does not stack. Presets that need a focus (`behind-only`, `peelback`, `section-focus`) show
nothing useful with an empty selection.

| Key | Preset | Group | What it does |
| --- | --- | --- | --- |
| 1 | `coordination` | Review | The factory x-ray view: modes, imaging, section, clearance and cinematic extras off. |
| 2 | `hide-blockers` | Review | Occluders fade to nothing (`alphaMin 0`), everything else stays solid. |
| 3 | `behind-only` | Cutaway | Behind-only with `cut + cap`. |
| 4 | `peelback` | Cutaway | Peelback with x-ray outside the window. |
| 5 | `peel-only` | Cutaway | Peelback, everything outside the window solid. |
| 6 | `stacked-floors` | Review | Front-weighted layers (`layerFalloff 0.3`) and a depth grade. |
| 7 | `radiograph` | Imaging | Radiograph style, classic palette. |
| 8 | `mri-scan` | Imaging | MRI style with the scan sweep running. |
| 9 | `section-focus` | Cutaway | Section box fitted to the selection, with caps. |
| - | `presentation` | Presentation | Dressing, bloom, fly-to, reveal and the sweep on. |
| - | `clearance-review` | Review | Clearance colouring with the default bands. |
| - | `plain` | Basic | X-ray off. |

You can save the current settings as your own preset, export and import them (`xray-presets/1`), and share one as a link.
An installation can replace or add presets with `web/public/xray.presets.json`. See [presets.md](web/docs-features/presets.md).

## Settings and tooltips

Every control of the panel has a tooltip with four lines: Intent, Impact, Use and Ref (the section of the report). Hover for
350 ms, or focus a slider with the keyboard. **Impact** is the plain-language effect you will see when you move the control.
[docs/SETTINGS.md](docs/SETTINGS.md) is the same text as a reference table; it is generated from `web/src/ui/helpText.ts` by
`npm run docs`, so edit the source, not the table.

The whole parameter set can be exported as JSON (`xray-params/1`, folder Export / import), imported again, and a small part
(model, classification, sightlines, display, camera, view modes, imaging, section) is carried in a share link.

### Class styles

Per-class base appearance, set at build time and editable at runtime: "steel at most 80 % opaque" is `"Steel": { "alphaMax": 0.8 }`.
The config file is `web/public/xray.config.json` (`xray-config/1`):

```json
{
  "schema": "xray-config/1",
  "classStyles": { "Steel": { "alphaMax": 0.8 }, "IfcColumn": { "floor": 0.5 }, "IfcGrid": { "hidden": true } },
  "materialAliases": { "Steel": ["IfcMember", "IfcBeam:steel", "IfcColumn:steel", "IfcPlate"] }
}
```

| Field | Effect |
| --- | --- |
| `alphaMax` | Caps the element's opacity in every bucket: `alpha = min(alpha, alphaMax)`. Focus elements are exempt unless the style is keyed by their own ifcClass. |
| `alphaMin` | Replaces `sightlines.alphaMin` for the class: the deepest ghosting an occluder of this class reaches. |
| `floor` | Opacity floor (Algorithm 7) for the class. |
| `color` | `[r, g, b]` in 0..1, replaces the base colour. |
| `hidden` | Hides the class. |

Keys are an ifcClass or a material alias. An alias lists what it covers: `IfcMember` matches every element of the class,
`IfcBeam:steel` also needs the material name to contain `steel`. Precedence, lowest first: `xray.config.json`, the `styles` /
`materialAliases` fields of the model sidecar, runtime edits (stored per model in `localStorage` under
`xray.classStyles.<model>`; buttons Reset to config, Export JSON, Import JSON). `ifc2glb.py` and `synth_model.py` bake the config
into a sidecar with `--config`. Code: `src/styles.ts`, `src/plugins/classStyles.ts`, `tests/class-styles.test.ts`.

## Development

Prerequisites: Node 22 and npm (`cd web && npm install`: three 0.187, three-mesh-bvh 0.9, lil-gui 0.21, web-ifc 0.0.78, vite 8,
vitest 5, typescript 5.9). To regenerate models: Python 3.13 with `ifcopenshell` 0.9 and `numpy`. For the benchmark and the smoke
scripts: the preinstalled Playwright Chromium (`/opt/node-tools/node_modules/playwright`, or set `PLAYWRIGHT_MODULE`).

**Convert** (from the repository root). The converted models are checked in under `web/public/models`; each run writes
`<name>.glb` (one node per element) and `<name>.json` (the `xray-model/1` sidecar, see `SPEC.md`):

```sh
python3 tools/ifc2glb.py models/Building-Structural.ifc models/Building-Architecture.ifc models/Building-Hvac.ifc -o web/public/models/building
python3 tools/ifc2glb.py models/Infra-Plumbing.ifc -o web/public/models/plumbing
python3 tools/synth_model.py -n 5000 -o web/public/models/synth5k                    # synthetic benchmark model
python3 tools/synth_model.py -n 400 --debris 24 -o web/public/models/debris-demo     # cleanup demo
python3 tools/validate_glb.py web/public/models/debris-demo                          # independent glb + sidecar check
python3 tools/make_pointcloud.py                                                     # sample scans in web/public/samples
python3 tools/make_pointcloud.py --phone                                             # phone LiDAR style scan of one room
```

`ifc2glb.py --props none|common|all` controls the hover properties (default `common`).

**Run, test, build** (from `web/`):

```sh
npm run dev          # vite dev server, 127.0.0.1:5173
npm run typecheck    # tsc --noEmit
npm test             # vitest run: algorithms, worked example, geometry, renderer maths, every plugin's pure part, IFC import and parity, docs checks
npm run build        # typecheck + production bundle in web/dist
npm run preview      # serve web/dist on 127.0.0.1:4173
npm run docs         # regenerate docs/SETTINGS.md from src/ui/helpText.ts
```

`/demo.html` is the standalone renderer demo without the algorithms. `tests/worked-example.test.ts` reproduces the report's numbers
on synthetic boxes (S1 Host weight 1.0, B1 0.741, W1 0.02, C1 Far, S1 occlusion about 0.75, target alpha about 0.24).

**Benchmark and smoke scripts** (from `web/`; each starts its own vite server; the smoke scripts read the port from `SMOKE_PORT`, `bench.mjs` from `BENCH_PORT`):

```sh
node bench/bench.mjs                  # synth5k and building: Algorithm 1 and 2 times, frame times; writes bench/RESULTS.md
node bench/bench.mjs building --scope=near
node bench/bench-large-ifc.mjs        # large IFC import (see bench/RESULTS-large-ifc.md)
node bench/smoke-open-file.mjs        # file opening, drag and drop, cancel, federation
SMOKE_PORT=5401 node bench/smoke-cleanup.mjs
```

`bench/bench.mjs` selects the first IfcDuctSegment, orbits the camera through 36 positions and records Algorithm 1 and 2 times, rays
per update and frame times. Swiftshader is CPU rasterisation: its frame times are not GPU numbers, while the Algorithm 1 and 2
timings are CPU JavaScript and meaningful. There is one `bench/smoke-*.mjs` per feature (`ls web/bench`).

**Single file and zip** (from `web/`):

```sh
npm run bundle                 # typecheck, vite build (vite.single.config.ts), inline everything -> web/dist-single/xray-viewer.html
npm run bundle -- --all        # also embed synth5k (about +9.5 MB)
npm run bundle -- --no-ifc     # without the IFC reader -> web/dist-single/xray-viewer-no-ifc.html
npm run template               # templates for xray-pack in web/dist-single (rebuilt automatically when stale)
npm run zip                    # same as: bash tools/make_zip.sh -> /home/user/xray-ref-dist/xray-ref.zip
```

The single file has the app JS and CSS, `xray.config.json`, `xray.presets.json` and the models `building`, `fzk-haus`, `plumbing`
and `debris-demo` inlined (`window.__xrayEmbeddedModels`, `__xrayEmbeddedConfig`, `__xrayEmbeddedPresets`); `synth5k` only with
`--all`. The IFC reader (web-ifc's worker script and wasm, gzip and base64) adds 1.2 MB and is inflated when the first file is
opened. The zip contains the repo without `node_modules`, `dist` and `dist-single`, the single file at its root, and always the
`web/public/models` files. Opened from `file://` the bundle makes no network requests (checked by `node bench/single-file.mjs`);
a plain `web/dist` build cannot be opened by double-click because browsers block module scripts from `file://`.

### Plugin architecture

`src/app.ts` is the core: loader, renderer, `XrayController`, the lil-gui panel and the status bar. Everything else is a plugin
listed in `src/plugins/index.ts` (order matters: hooks run in this order; `help` runs after every panel-building plugin,
`panelDock` last, `boot` at the very end).

- **`AppPlugin` hooks** (all optional): `install(app)` once after the GUI exists and before the first model; `onModel(app)` after every
  model install; `onStatic(app)` after the selection, classification or settings changed (Algorithm 1 has run);
  `onFrame(app, now, dt)` before the frame renders (return true to force a render-state upload); `afterFrame(app, now)`.
- **Action registry** (`src/input/actions.ts`): `registerAction({ id, label, group, keys, run, hold?, repeat?, enabled? })`. The
  keymap, the cheat sheet, the palette and the shortcut editor all read it, so an action gets a key, a cheat sheet row and a palette
  entry for free.
- **Tool registry** (`src/tools/registry.ts`): `registerTool({ id, label, title, icon, order, panel?, toggle?, isActive? })` puts a
  button in the action panel; `panel(container, app)` builds the drawer.
- **Param sections** (`src/ui/params.ts`): `registerParamSection(name, { collect(), apply(value, bad, path), share? })` adds a section to the exported
  `xray-params/1` document; `bad.push(path)` in `apply` reports unusable keys. Presets, `xray-pack --params` and share links use it.

To add a plugin:

1. Create `src/plugins/myThing.ts` exporting `const myThingPlugin: AppPlugin = { name: 'myThing', install(app) { ... } }`; keep the
   logic that needs no DOM in its own module (`src/myThing/`) so it can be tested with vitest.
2. In `install`, add a lil-gui folder (`app.panel.addFolder(...)`) and register a tool (`registerTool`) with a drawer if it needs one.
3. Register actions with `registerAction` and a params section with `registerParamSection` (`share: true` only for small ones).
4. Import the plugin and add it to `PLUGINS` in `src/plugins/index.ts` at the position its hooks need; expose a
   `window.__xrayMyThing` object for scripts and smoke tests.
5. Write `tests/myThing-*.test.ts` for the pure part, a `bench/smoke-myThing.mjs` if it draws, and `web/docs-features/myThing.md`;
   add help text for its controls in `src/ui/helpText.ts` and run `npm run docs`.

## Code map: report algorithms to code

| Report algorithm | File | Function |
| --- | --- | --- |
| 1. Static classification (Focus, Host, Near, Far, proximity weight) | `web/src/algo/classify.ts` | `classify`, `classifyFromFocus`, `connectedRun`, `bufferRadius` |
| 2. Sightlines: sample, ray cast, occlusion, importance, target alpha | `web/src/algo/sightlines.ts` | `collectSamples`, `castSamples`, `sightlines` |
| 2. (L10-11) floors and smoothing, render-state write | `web/src/algo/sightlines.ts` | `smoothAlpha`, `applyRenderState` |
| 3. Coarse-to-fine candidate filtering (AABB, then mesh) | `web/src/algo/classify.ts`, `web/src/render/geometry.ts` | `boxDistance` in `classifyFromFocus`; `BvhGeometryProvider.intersects`, `surfaceDistance` |
| 7. Opacity floors from pins (user, category, project) | `web/src/algo/overrides.ts` | `computeFloors` (viewpoint rules are a hook, `extraFloor`) |
| 8/9. Category tiers and tiered sightlines | `web/src/algo/tiers.ts` | `classifyTiers`, `sightlinesTiered` |
| 10. View mode: behind-only (plane from camera and focus, front treatment) | `web/src/viewModes/maths.ts`, `web/src/render/viewModeGlsl.ts` | `behindFragment` (CPU), `vmEval` (GLSL) |
| 11. View mode: partial peelback (focus mask, jump flood, window `r(z)`) | `web/src/viewModes/maths.ts`, `web/src/render/viewModeGlsl.ts` | `peelFragment` (CPU), `vmEval` and the mask and flood passes (GLSL) |
| 12. Floating element detection (contact graph, main component) | `web/src/cleanup/analysis.ts` | `analyse` (floating rule) |
| 13. Penetration schedule (sweep, intersect, orientation, opening status) | `web/src/penetrations/analysis.ts` | see the file header |
| Geometry queries (ray all-hits, distance, samples) | `web/src/render/geometry.ts` | `BvhGeometryProvider` |
| Update sequence and per-frame easing | `web/src/controller.ts` | `XrayController.reclassify`, `updateSightlines`, `tick` |
| UI, input, debounce, status bar | `web/src/app.ts`, `web/src/ui/statusBar.ts` | `ViewerApp`, `StatusBar` |
| Ghost, focus and edge passes; order-independent transparency | `web/src/render/renderer.ts`, `shaders.ts`, `ghostMath.ts`, `oitMath.ts` | `XrayRenderer` |

The report's algorithms 4 to 6 are not tagged in the code.

### Deviations from the report

1. **Selection always joins Focus, whatever its class.** Algorithm 1 line 1 keeps only selected elements whose class is in
   `focusClasses`, so selecting furniture, a footing or a slab gave an empty Focus. Here every selected element is Focus. The
   ConnectedRun expansion (ports and systems) still applies only to selected elements whose class is in `focusClasses`. Context
   excludes the whole Focus set, so selecting a slab makes the other slabs and walls Context. The tiered variant puts a selected
   element of any class into the top tier.
2. **Far elements that block a sightline ghost.** The report casts rays only against Host + Near, so an exterior wall 3 m from the
   duct between camera and duct never ghosts. With `sightlines.occluderScope = 'all'` (default) every Context element is a ray
   candidate. Host and Near use `target = alphaMax + (alphaMin - alphaMax) * occlusion^gamma * proximityWeight`. Far elements have
   no proximity weight; they get `farWeight` (0.7) and a ceiling of 1: `target = 1 + (alphaMin - 1) * (occlusion^gamma * farWeight)`.
   A Far element that blocks nothing stays opaque; one that blocks the whole focus settles at 0.40 with the defaults. Pins and floors
   apply to Far too. `occluderScope = 'near'` restores the report exactly.
3. **Stacked occluders are weighted by depth order.** The report credits every occluder on a ray with 1 hit, so three slabs over the
   same rays land on the same alpha and composite into a veil. The ray caster returns hits ordered towards the camera; order `k = 0`
   is nearest the camera. `sightlines.layerWeighting` sets the credit: `front` (default) `layerFalloff^k` (0.5: 1, 0.5, 0.25),
   `budget` 1 if `k < layerBudget` (default 2) else 0, `uniform` 1 (the report). A single occluder per ray always has credit 1, so the
   worked example is the same in every mode. With the test fixture (three 250 mm slabs, 300 mm apart) `front` gives occlusions
   1.0 / 0.5 / 0.25 and target alphas 0.15 / 0.36 / 0.50 from the top slab down (`tests/stacked-layers.test.ts`).

## Known limitations

Rendering and picking

- "Focus in front" draws the focus with the depth test off; it is never occluded, including by opaque far elements.
- Ghost blending is order independent only when float colour buffers exist (weighted blended OIT); without them, overlapping ghosts blend in draw order.
- Picking uses the CPU BVH, ignores explode offsets, and treats non-focus elements below 0.3 alpha as click-through; with a view mode on it also skips what the mode removes (approximate for the peel window rim).
- Smoothing is per frame, not per unit time, so convergence depends on frame rate. Swiftshader frame times are CPU rasterisation, not GPU numbers.
- With X-ray off everything is opaque and user hides are not applied. Viewpoint rules of Algorithm 7 (floor underfoot, exterior wall) are not implemented; `occluderScope = 'all'` covers the exterior wall case.
- Caps (behind-only, peel, section) are back faces, not cap polygons: an open mesh shows its back faces in the cap colour, and a ghosted element is cut without a cap.
- Imaging needs float colour buffers (otherwise the style stays `standard`), assumes closed solids, and overlapping elements add up; the peel window is computed at half resolution.
- The section box is axis aligned in the viewer frame and its handles are drawn without depth testing.
- The in-memory distance cache assumes a static model; call `clearCaches()` if geometry changes.

Opening files

- Only what web-ifc can mesh is shown: some `IfcAdvancedBrep`, B-spline, unusual boolean or swept shapes, and IFC4X3 alignment geometry are silently missing; `[ifc-import]` in the console counts products without geometry. Openings web-ifc cannot subtract leave the host solid.
- IFC2X3 and IFC4 are well trodden; IFC4X3 beyond the sample files is untested.
- Memory is about 25 times the file size at 40 MB (file, wasm heap, typed arrays, glb, geometry, BVH); the extraction worker's wasm heap is not returned until it ends. Files of tens of MB are practical, a few hundred MB are not. No streaming, no level of detail.
- Properties are the element's own sets only (no type properties, no bounded, list or table values), at most 24 per element.
- The edge geometry is all or nothing per model. After the early merge the model install is short, but `onModel` hooks of other plugins take about 1 s at 100,000 elements.
- The single-file bundle has no copy of the point cloud worker (it parses on the main thread) and needs `Worker` from a Blob URL and `DecompressionStream`; Firefox and Safari were not tested.
- `localStorage` on `file://` is per browser profile; stored sets and style edits may not survive reloads in some browsers.

Coordination tools

- Cleanup: bounds-based contacts treat a box as solid (turn on `precise contacts` for curved elements); matches are hidden, not deleted.
- Clearance colours whole elements, not regions; the host of the focus always shows as clash. It shares `renderer.state.color` with the cleanup preview and debug colours: switch one off before the other.
- Penetrations: every overlapping MEP and host pair counts, including an element ending inside the host; the schedule is a candidate list. A sidecar without opening bounds reports `unknown` (reconvert, or open the IFC in the browser). At most 500 rows are listed.
- BCF: orthographic cameras are approximated; viewpoint roll, lines, bitmaps and colour alpha are ignored; elements match by GlobalId only; existing topics can change status and gain comments but not other fields; no zip64; pins and annotations reach other tools only as the burned snapshot and the viewpoint selection.
- Point clouds: one cloud at a time; no LAZ (convert with PDAL or LAStools); E57 only with the standard bitPackCodec, without images; auto-align is a coarse bounds-centre match; 3-point alignment and point-to-plane ICP are rigid (uniform scale only for 3 points, on request), so scan drift is not corrected: ICP reports where the fit degrades (3 x 3 plan grid) and `align within` aligns one room at a time; deviation is distance to the nearest surface, measured up to 5 times the tolerance.
- Presets reset and apply settings only; the active mark is a settings comparison and can be cleared by an unrelated animation.

Packaging

- `xray-pack` embeds the model as base64 (4/3 of the glb) and browsers get slow on pages of more than a few tens of MB; one glb per page, IFC and glb cannot be mixed; `--camera` is in the viewer frame; `--preset` and `--open-tool` are skipped with a console warning when the plugin is absent.
- The sample models `building` and `plumbing` have no `IfcRelVoidsElement`, so Host detection uses the geometric fallback; `synth5k` and `debris-demo` have synthetic openings.

## Model sources and licences

- `models/Building-*.ifc` and `models/Infra-*.ifc`: buildingSMART Sample-Test-Files, IFC 4.0.2.1 Simple-Scene set (repository commit
  `80d976a9`, retrieved 2026-10-30).
- `models/AC20-FZK-Haus.ifc`: the KIT FZK-Haus exported from ARCHICAD 20, taken from the IfcOpenShell repository (v0.9.0,
  `docs/ifcopenshell-cpp/models`), whose licence is LGPL-3.0-or-later. The file itself has no licence header; KIT publishes it as a
  freely usable sample, but check upstream before redistributing it outside this reference project. See `models/NOTE.md`.
- `web/public/models/*`: converted from the files above by `tools/ifc2glb.py`; `synth5k` and `debris-demo` are generated by
  `tools/synth_model.py` and `web/public/samples/building-scan.*` and `building-phone-scan.ply` by `tools/make_pointcloud.py` (no external source).
- web-ifc 0.0.78 (MPL-2.0, https://github.com/ThatOpen/engine_web-ifc) reads IFC in the browser. It is used unmodified; the
  single-file viewer and `xray-pack --ifc-reader` embed it and keep the notice in the page. The MPL text is in
  `web/node_modules/web-ifc/LICENSE.md`. `ifcopenshell` (LGPL) stays a build-time tool of the converter.
- three.js, three-mesh-bvh and lil-gui are MIT; versions are pinned in `web/package.json`.
- E57 test fixtures (`web/tests/fixtures/pointcloud/e57-*`): written with pye57 (MIT) / libE57Format (BSL-1.0) by
  `web/tests/fixtures/make_e57_fixtures.py`, both test-time tools only (the viewer's E57 reader is its own code). Two files are copied
  from https://github.com/asmaloney/libE57Format-test-data: `e57-ref-bunny-int32.e57` (libe57.org example data, "Test Data
  License", MIT style) and `e57-las2e57-colour.e57` (LAStools las2e57 output, CC0 1.0).
