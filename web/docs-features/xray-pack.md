# xray-pack: a model plus a viewer in one HTML file

`xray-pack` wraps your model in the X-ray viewer and writes **one self-contained `.html` file**: no server, no network, opens from `file://` or an email attachment. The model is converted at pack time, and you choose the starting parameters, selection, tools and camera. Typical sizes: 2.2 MB for the FZK house, 1.2 MB for the three-file Building set (the viewer itself is about 1.1 MB).

```
node tools/xray-pack.mjs <inputs...> -o <out.html> [options]
npm run pack -- <inputs...> -o <out.html> [options]     # same thing
xray-pack ...                                           # after `npm link` / installing the package (package.json "bin")
```

## Inputs

- One or more `.ifc` / `.ifczip` files. They are federated into one model with the viewer's rules (merged storeys, duplicate GlobalIds skipped, clashes renamed), in the order given.
- Or one `.glb`. A `model.json` with the same basename next to it is used as the sidecar (without it, element classes are guessed from node names).

IFC files are converted in node by the **same TypeScript reader the browser uses** (`src/model/ifcRaw.ts` extract with web-ifc's node wasm, then `src/model/ifcImport.ts` build), not by the Python converter, so there is one code path. Node cannot run those files directly (vite-only imports), so `tools/pack/convert.mjs` bundles `tools/pack/reader-entry.ts` with vite's build API into `tools/pack/reader.mjs` (git-ignored; rebuilt in about a second when it is missing or older than `src/model`).

## Options

| Option | Meaning |
| --- | --- |
| `-o, --out <file>` | Output `.html` (required). Existing files are only replaced with `--force`. |
| `--params <file.json>` | An `xray-params/1` document, partial allowed. Export one from the viewer's Export / import folder. Applied with the viewer's own `applyParams`; unknown keys are reported once in the browser console. |
| `--preset <name>` | Preset (name or id) applied before the params. Needs the presets plugin (`window.__xrayPresets.apply`); without it a console warning is logged. |
| `--select <list>` | Comma-separated GlobalIds and `class:IfcDuctSegment` entries, selected at start (selecting makes them the focus). Entries missing from the model are warned about at pack time and in the console. |
| `--title <text>` | Page title (default: the model name). |
| `--name <name>` | Model name in the picker and params (default: basename of the first input). |
| `--tools <ids>` | Comma-separated action-panel tool ids to show, in order. Reserved ids: `open, presets, xray, viewModes, imaging, section, measure, clearance, penetrations, bcf, pointcloud, xr, cleanup, largeModel`. Default: all. |
| `--open-tool <id>` | Open this tool's drawer at start (must be in `--tools` when that is given). |
| `--kiosk` | Start with the model tree and the parameter dock collapsed, and without the top bar. |
| `--no-topbar` | Hide the top bar (the four visualisation modes and the search host) without a kiosk page. Writes `topBar: false` into `__xrayBoot`. |
| `--camera px,py,pz:tx,ty,tz` | Camera position and target in the viewer frame: metres, Y up, shifted by the sidecar's `originShift`. Easiest to copy from an exported params file (`camera.position`, `camera.target`). |
| `--views <file.json>` | Saved views (`xray-views/1`, from the Views tab > Export) added to the Views tab of the page. Views without a name or camera are skipped with a warning; GlobalIds missing from the model are warned about. See [saved-views.md](saved-views.md). |
| `--open-view <name>` | A saved view of `--views` (name, id or 1-based number) opened at start, after everything else. Needs `--views`. |
| `--ifc-reader` | Also embed the in-browser IFC reader (worker + wasm, gzip + base64) so the recipient can open more IFC files. Adds about 1.2 MB. Default: left out. |
| `--samples` | Also embed the sample models (building, fzk-haus, plumbing). Adds about 1.8 MB. |
| `--force` | Overwrite the output. |
| `--quiet` | Print nothing except errors. |
| `-h, --help` | Usage. |

Exit codes: `0` ok, `1` usage error (bad option, missing `-o`, output exists), `2` input error (unreadable or invalid input, bad params file, conversion failed, template build failed). Errors are one line on stderr, prefixed `xray-pack:`.

## What the page does at start

`window.__xrayBoot` (see `XrayBoot` in `src/tools/registry.ts`) is read once, after the first model installs (`src/plugins/boot.ts`), in this order: page title, preset, params, camera, selection, open tool, kiosk, saved view (`openView`). The views plugin adds `__xrayBoot.views` to the Views tab on the first model. The toolbar plugin reads `__xrayBoot.tools` itself. The initial model is `__xrayBoot.model`, else `?model=`, else the first embedded model, else `building`.

## Templates

`xray-pack` uses `dist-single/xray-template.html` (no reader) or `xray-template-ifc.html` (with `--ifc-reader`), built by `node tools/build-single-file.mjs --template [--variant ifc|none]` (`npm run template`). They hold the app and no sample models. If a template is missing or older than `web/src` (or the build scripts) it is rebuilt automatically, which takes a few seconds. Packing replaces the text between `/* XRAY-PACK:INJECT-BEGIN */` and `/* XRAY-PACK:INJECT-END */` with the embedded models (`window.__xrayEmbeddedModels = { name: { glb: base64, json: sidecar } }`) and `window.__xrayBoot`, and the `<title>`. `npm run bundle` is unchanged.

## Examples

```
# an IFC with the viewer's defaults
node tools/xray-pack.mjs ../models/AC20-FZK-Haus.ifc -o fzk.html

# three federated IFC files, the duct selected, panels hidden for a presentation
node tools/xray-pack.mjs Building-Structural.ifc Building-Architecture.ifc Building-Hvac.ifc \
  -o building.html --name building --select class:IfcDuctSegment --kiosk --title "Building review"

# a tuned look from an exported params file, with only three tools and the measure drawer open
node tools/xray-pack.mjs public/models/building.glb -o review.html --params tuned.json \
  --tools xray,section,measure --open-tool measure --camera 12,8,14:0,3,0

# a recipient who may want to open their own IFC files too
node tools/xray-pack.mjs model.ifc -o viewer.html --ifc-reader
```

Params file (partial documents are fine):

```json
{ "schema": "xray-params/1", "sightlines": { "alphaMin": 0.05, "layerWeighting": "budget" } }
```

CI: convert every IFC in a folder into its own viewer.

```
mkdir -p public-html
for f in ifc/*.ifc; do
  node web/tools/xray-pack.mjs "$f" -o "public-html/$(basename "${f%.*}").html" --params ci-params.json --force --quiet || exit 1
done
```

Or in GitHub Actions: run `npm ci` in `web/`, then the loop above, then upload `public-html/` as an artifact. The first pack builds the template (a few seconds); later ones reuse it.

## Timings (this machine, node 22, one run each)

| Pack | Convert | Whole command |
| --- | --- | --- |
| `AC20-FZK-Haus.ifc` (82 elements) | about 1.0 s | about 1.1 s with a fresh template |
| `Building-Structural + Architecture + Hvac` federated (26 elements) | about 0.5 s | about 0.6 s |
| Template build (once, or after a `web/src` change) | | about 2 s without, 3.5 s with the reader |

## Limits

- IFC reading is done by web-ifc in one process: very large files (hundreds of MB) can run out of memory, as in the browser. The output embeds the model as base64 (4/3 of the glb size) inside the HTML, and browsers get slow to open pages of more than a few tens of MB.
- One glb per page; glb files are not federated. IFC and glb cannot be mixed in one run.
- `--select` GlobalIds are those of the converted model (a renamed duplicate carries a `~n` suffix).
- `--camera` is in the viewer frame, not IFC coordinates.
- `--preset` and `--open-tool` depend on other plugins (`window.__xrayPresets`, `window.__xrayToolbar`); if a plugin is absent the request is skipped with a console warning, never an error.
- `--kiosk` goes through the panels' own actions, which remember the collapsed state in that browser's local storage. The top bar (`topbar.md`) is hidden by `kiosk` and by `topBar: false`; the bar is read by the topBar plugin itself, not by the boot sequence, so a params document with `topBar.visible: false` hides it too.
- Packed pages show the top bar by default: its four modes apply built-in presets, so `--preset` and a mode click agree.
- The output is built from the current `web/src`: pack with the viewer version you want the recipient to have. IFC files in the page are not re-converted when the viewer changes.
- `web-ifc` (MPL-2.0) is embedded unmodified with `--ifc-reader`; the licence notice stays in the page.
