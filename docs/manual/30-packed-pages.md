# 30. Packed pages with xray-pack  [D]

## The problem

You want to hand a client the model and the look you prepared: the duct selected, the ceiling peeled, a fly-through ready. They
will open it on a laptop in a meeting room with no network and no admin rights. A link will not do, because it needs the model
somewhere. A zip with a viewer and a model does not do either, because someone has to open the right file in the right order.

## The idea

`xray-pack` is a command-line tool. It takes your model, converts it, and writes **one `.html` file** that holds the viewer, the
model and your starting choices. Double-click the file and the viewer opens already set up. No server, no install, no network.
It opens from `file://` or from an email attachment.

The comparison is a slide deck saved as a self-running presentation. The audience does not need your software, and the deck
starts on the slide you chose.

New words, defined once:

- **packed page**: the `.html` file that `xray-pack` writes.
- **boot document**: the small block of choices inside the page (look, selection, camera, tools). The viewer reads it once, when the first model has loaded.
- **kiosk page**: a packed page with the side panels hidden, often playing a film by itself.
- **parameters file**: an `xray-params/1` file, exported from the viewer's **Export / import** folder.

You need Node 22 and the viewer's `web/` folder with `npm install` done. Commands run from `web/`.

## 30.1 Pack IFC/glb into one HTML; set params, preset, selection, camera

### Try it: pack the FZK house

1. In a terminal, go to the `web/` folder.
2. Run this command.

   ```
   node tools/xray-pack.mjs ../models/AC20-FZK-Haus.ifc -o fzk.html
   ```

3. It takes about 1 second and writes `fzk.html`, about 2.2 MB. The first pack also builds the viewer template, which takes a few seconds more.
4. Double-click `fzk.html`. The viewer opens with the house loaded.
5. Run the same command again. It stops with a message, because the file exists. Add `--force` to replace it.

`npm run pack -- <inputs> -o <out.html>` does the same thing.

### What goes in

- One or more `.ifc` or `.ifczip` files. Several files are federated into one model, in the order you give them, with the same rules as in the viewer.
- Or one `.glb`. A `model.json` with the same base name next to it is its sidecar. Without it, classes are guessed from node names.
- IFC and glb cannot be mixed in one run. Only one glb fits on a page.

IFC files are read by the same code the browser uses, so a packed model matches what you would see by opening the file.

### Set the starting look

| Option | What it does |
| --- | --- |
| `--params file.json` | Apply an exported parameters file. A partial file is fine. |
| `--preset name` | Apply a preset (name or id) before the parameters. |
| `--select list` | Select these elements at start: GlobalIds and `class:IfcDuctSegment` entries, comma separated. |
| `--camera px,py,pz:tx,ty,tz` | Camera position and target, in metres, Y up, in the viewer's frame. |
| `--title text`, `--name name` | Page title, and the model's name in the picker. |
| `--views file.json`, `--open-view name` | Add saved views, and open one at start. |

Order of events when the page starts: title, preset, parameters, camera, selection, open tool, kiosk, saved view,
fly-throughs and scripts, autoplay. A later step wins over an earlier one.

The easiest way to get a camera is to set it in the viewer, click **Export JSON** in the **Export / import** folder, and copy
`camera.position` and `camera.target` from the file. The camera is in the viewer's frame, not in IFC coordinates.

Selecting a duct at start makes it the focus, so the x-ray is already doing its job when the page opens.

### Choose what the recipient sees

| Option | What it does |
| --- | --- |
| `--tools ids` | Show only these tools in the action panel, in order. |
| `--open-tool id` | Open this tool's drawer at start. `classify` opens the Classification tab. |
| `--no-topbar` | Hide the top bar only. |
| `--kiosk` | Fold the model tree and the right sidebar and hide the top bar. |
| `--ifc-reader` | Also embed the IFC reader, so the recipient can open their own IFC files. Adds about 1.2 MB. |
| `--samples` | Also embed the sample models. Adds about 1.8 MB. |

The tool ids are `open`, `presets`, `xray`, `viewModes`, `imaging`, `section`, `measure`, `clearance`, `penetrations`, `bcf`,
`pointcloud`, `xr`, `cleanup` and `largeModel`.

A common review page:

```
node tools/xray-pack.mjs Building-Structural.ifc Building-Architecture.ifc Building-Hvac.ifc \
  -o building.html --name building --select class:IfcDuctSegment --kiosk --title "Building review"
```

### Exit codes and messages

`0` means done. `1` is a usage error (a bad option, a missing `-o`, an output file that exists). `2` is an input error (an
unreadable file, a bad parameters file, a failed conversion). Errors are one line on stderr that starts with `xray-pack:`.
Warnings, such as a GlobalId that is not in the model, are printed at pack time and again in the browser console.

### One run per folder (CI)

```
mkdir -p public-html
for f in ifc/*.ifc; do
  node web/tools/xray-pack.mjs "$f" -o "public-html/$(basename "${f%.*}").html" --params ci-params.json --force --quiet || exit 1
done
```

Run `npm ci` in `web/` first. Upload `public-html/` as the artifact of the build. The first pack builds the template; the rest
reuse it.

## 30.2 Kiosk pages: autoplay and loop a fly-through, script or 4D plan; limits and size

A kiosk page runs without anyone touching it: a screen in a site office, a stand at a fair, a lobby display.

### Try it: a looping fly-through

1. In the viewer, load FZK-Haus. Build a fly-through in the **Views** tab (chapter 22). Name it "Overview".
2. In the fly-through section, open the **⋯** menu of the fly-through list and click **Export file**. You get an `xray-flythroughs/1` file, say `overview.json`.
3. Pack the model with the film.

   ```
   node tools/xray-pack.mjs ../models/AC20-FZK-Haus.ifc -o kiosk.html --kiosk \
     --flythroughs overview.json --autoplay flythrough:Overview --loop
   ```

4. Open `kiosk.html`. The panels are folded and "Overview" plays. It starts again from the beginning when it ends.
5. Press or turn the wheel on the canvas. The film stops. That is the way out of a kiosk loop.

### The options

| Option | What it does |
| --- | --- |
| `--flythroughs file.json` | Add fly-throughs to the Views tab of the page. A name that exists is not added twice. |
| `--scripts a.xrayanim,b.xrayanim` | Add animation scripts. The file name without its ending is the script name. |
| `--plans a.4d.json` | Add 4D plans (chapter 28). The file name without `.4d.json` is the plan name. |
| `--autoplay flythrough:Name`, `script:Name` or `plan:Name` | Play this when the page starts, after everything else. |
| `--loop` | With `--autoplay`: play again and again. |

`--autoplay` needs the matching `--flythroughs`, `--scripts` or `--plans` with that name. With `plan:`, the first `--scripts`
file adds its camera moves and captions to the film of the plan. The command `xray-4d pack` (chapter 32) makes this kiosk page for you.

Scripts and fly-through captions are your own text. They go into a packed page only when you name the file yourself (chapter 29
lists what never travels).

### Size

| Pack | Size |
| --- | --- |
| FZK house | about 2.2 MB |
| Building (three IFC files) | about 1.2 MB |
| The viewer itself | about 1.1 MB |
| `--ifc-reader` | adds about 1.2 MB |
| `--samples` | adds about 1.8 MB |

The model is stored as text (base64), so it takes 4/3 of the glb size. Browsers get slow to open pages of more than a few tens of MB.

## How it works

The tool keeps a template: the viewer with no model. When you pack, it converts the model, then replaces a marked block in the
template with the embedded models and the boot document. It also sets the page title. The template is rebuilt by itself, in a
few seconds, when it is missing or older than the viewer source.

When the page opens, the viewer reads the boot document once, after the first model has loaded. If the page holds no
`--ifc-reader`, the recipient can still open the packed model but not other IFC files.

### [D] Names for developers

The boot document is `window.__xrayBoot` (type `XrayBoot`). The initial model is `__xrayBoot.model`, else `?model=`, else the
first embedded model, else `building`. Embedded models live in `window.__xrayEmbeddedModels = { name: { glb, json } }`. The
templates are `dist-single/xray-template.html` and `xray-template-ifc.html`, built by `node tools/build-single-file.mjs
--template`. The pack reader is bundled from `tools/pack/reader-entry.ts` into `tools/pack/reader.mjs`, which Git ignores.

## Choices and settings

All choices are the command-line options above. `-h` prints usage, `--quiet` prints only errors.

## Limits and gotchas

- Very large IFC files (hundreds of MB) can run out of memory at pack time, as in the browser.
- One glb per page. IFC and glb cannot be mixed.
- `--select` GlobalIds are those of the converted model. A renamed duplicate carries a `~n` ending.
- `--preset` and `--open-tool` depend on other parts of the viewer. If a part is missing, the request is skipped with a console warning, never an error.
- `--kiosk` folds the panels through their own actions, which remember the folded state in that browser's storage. The recipient's browser may open the page with panels folded on the next normal visit too.
- A packed page is built from the viewer source at pack time. Pack with the version you want the recipient to have. A model in a page is not converted again when the viewer changes.
- The IFC reader inside `--ifc-reader` is web-ifc (MPL-2.0), unmodified. Its licence notice stays in the page.
- Firefox and Safari were not tested for the single-file build.
- Packed pages never contain API keys, tokens, reviewer names or pictures (appendix G).

## See also

- Chapter 22 and 23: fly-throughs and animation scripts, the things a kiosk plays.
- Chapter 32: `xray-4d`, which packs a 4D film into a kiosk page.
- Chapter 29: the lighter ways to share, and what never goes into a page.
