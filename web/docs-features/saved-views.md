# Views

A **view** is a captured moment: the camera plus the look of the model. A view may carry **drawings** (clouds, arrows, text, callouts, shapes and pen, attached to the model in 3D or view-locked, [markup.md](markup.md)). A page of a PDF sheet is a view too: its drawings are the sheet's drawings ([sheets.md](sheets.md)). An **issue** points at views and adds status, comments and history ([issues.md](issues.md)). Views live in the **Views** tab of the left sidebar (next to Model and Sets), are stored per model in the browser, can be exported, imported and shared as a link, and can be packed into an `xray-pack` page. Design and mapping from the older saved views and sketches: `docs/design/views-and-issues.md`.

## One list

The tab lists **every view of the loaded model**: the saved views, the views that only have a drawing layer (older sketches, views opened from a BCF file or a drawings PDF, views of issues) and the pages of PDF sheets. The chips filter it:

| Chip | Shows |
| --- | --- |
| All | every view |
| With drawings | views that have at least one drawing |
| On sheets | the PDF pages: the sheets pane (`Open PDF`, each PDF with its pages as thumbnails; [sheets.md](sheets.md)) takes the place of the list |
| In an issue | views that are a viewpoint of an issue, with or without drawings |

A row shows the name, the summary, `✎ n` when there are drawings, `Sheet` for a PDF page and `Issue` when the view is in an issue (the full title is in the tooltip; the detail says `In issue: <title>` with `Open issue`). The filter box matches name, note and issue title. Pure code: `src/views/unified.ts` (`buildEntries`, `filterEntries`, `filterCounts`).

**One entry point per intent.**

- `Save view` (the box and button at the top, `Ctrl+Shift+S`): the camera and the look as a view.
- `Draw on this view` (button at the top, row menu `⋯`, detail): on the selected view (the marked row) or, with none marked, on the current state, which is saved as a view first. The view is restored, the drawing toolbar comes up. A saved view without a drawing layer gets one the first time; from then on the row menu says `Edit drawings`.
- `Make issue` (row menu, detail): the detail of the view opens with the chooser `New issue` / `Add to: <issue>`. The issue points at the view; it is not a copy. A view that is in an issue has `Open issue` instead.
- `New issue` (Issues tab): captures the current view, saves it in this list, then opens the topic dialog.

**Click a row**: a plain view is restored. A view with a drawing layer is restored and its **detail** opens in place of the list (`‹ Views` goes back): title, note, `In issue` / the `Make issue` chooser, `Edit drawings`, `Restore view`, `Update view`, `Export PDF`, `Export JSON`, page size and picture quality for the PDF, `Delete view`, the drawing list with the attachment chip, and the `3D · Plan · Section` switch when the drawings are tied to the model ([issues.md](issues.md), "Plan and Section views"). Deleting a view that is in an issue asks first; the issue keeps its camera and loses the drawings.

Below the list, the drawings part of the tab holds `Open file` (a PDF or JSON with views and drawings, or drop it on the page), `Other models (n)` (views made on another model, hidden here, with `Open`, `Move to this model`, `Delete view`) and the banner for older views that still carry comments or a status ("N views have comments or a status. Make issues of them?"). The fly-through section ([flythrough.md](flythrough.md)) stays at the bottom of the tab.

## How a view with drawings is kept

Two stores stay as they were and the tab shows them as one list: the saved views (`localStorage`, `xray-views/1`) and the drawing layers (the work store in IndexedDB `xray-work`, documents `xray-markup-set/1`). A saved view may carry `drawings: "<id of its drawing layer>"`; without it, or when the layer is gone (deleted, another model), the view is plain. A drawing layer that no saved view claims (an older sketch, a layer made from a BCF viewpoint) is listed as a view of its own, built from its own camera and picture. Nothing is converted when the model loads. A view without a saved view behind it has no number and no grip, and cannot be duplicated; the other actions work. The link is not in a share link or in the params section `views` (a layer id means nothing elsewhere).

## What a view stores

| Part | Stored as | Restored by |
| --- | --- | --- |
| Camera | position, target, screen up (a roll of the view cube survives), vertical field of view, the pseudo-orthographic flag | the gizmo turn (`turnTo` in `src/gizmo/camera.ts`): an eased slerp over 400 ms, or a jump when `smooth moves` is off, the system asks for reduced motion, or the view opens at boot |
| Section box and plane | the `section` params section (box enabled, explicit `min` / `max`, plane axis, offset, flip, tilted normal, caps) | `applyParams` of the section plugin; the box is not refitted because `min` / `max` are explicit |
| Other clip planes | `clip`: the planes of a BCF viewpoint that was applied when the view was saved (only when the section tool had nothing on) | `renderer.setClipPlanes` |
| Selection (the focus) | GlobalIds | `app.selectIds` (one classification run) |
| Hides, pins, isolate | GlobalIds; when more than half of the model is hidden (an isolate, `Shift+H`) the view stores the visible elements instead (`hides.mode: "show"`) | the override sets, then Algorithm 7 |
| Exploded context | `exploded: true` | `window.__cinematic.explode()` after the selection (a selection change collapses it) |
| X-ray, view modes, imaging, sightlines, display, cinematic, rendering, clearance, tiers | the params snapshot (`xray-params/1` keys) | only the sections that differ from the current state are applied |
| Active preset | its id, for the summary and the filter | not re-applied (the params already hold its effect); marked active again in the presets panel (`window.__xrayPresets.markActive(id)`), until a setting changes |
| Thumbnail | 160 x 100 JPEG data URL, cropped to cover | shown on hover and in the grid |

The params snapshot is `collectParams()` minus the sections a view never stores: document metadata, `camera` and `overrides` (stored by the view itself), `selectionSets`, `classStyles`, `materialAliases`, `keymap`, `views`, and tools with their own documents (`bcf`, `markup`, `xr`, `pointcloud`, `measure`, `hoverInfo`, `gizmo`, `penetrations`, `cleanup`). Restoring merges the view's params over the **factory state** (the params right after the first model loaded) and applies only the top-level sections whose value differs from the current one, in one `applyParams` call without reclassification; the selection then reclassifies once. A partial view (a share link, a hand-written views file) therefore resets what it does not name.

Elements are referred to by GlobalId, so a view survives a reload or a reconversion of the model. GlobalIds the loaded model lacks are reported in the status bar (`View "Roof": 3 elements not in this model (...)`) and the rest still applies.

## The Views tab

- **View name** box and **Save view** (`Ctrl+Shift+S`). An empty name gives `View 1`, `View 2`, ...; a taken name gets a number.
- **Play** / **Stop** steps through the views in list order (it loops), with the dwell time from the list next to it (2, 4, 6 or 10 s, remembered). Escape (taken while playing, so the selection stays) or a press on the canvas stops it. With reduced motion the camera jumps instead of turning.
- **Grid toggle**: one line per view (default) or a grid of thumbnails (better on a phone). Remembered in `localStorage` `xray.views.ui`.
- **Export** downloads `xray-views-<model>-<date>.json` (`xray-views/1`, with thumbnails). **Import** adds the views of such a file: a view with an id already in the list replaces it only when it is newer; other views are added with a unique name.
- **Filter views** matches the name, the note or the title of the issue the view is in (saved views also match the preset id).
- Rows: drag grip · number · name (click: restore) · one-line summary (`x-ray · box · behind · radiograph · isolate 3 · 2 selected`) · **⋯**. Hovering a row shows the thumbnail next to the sidebar. The last restored view is marked.
- **⋯** menu: Update from current (keeps the name and id; also captures the drawings again), Draw on this view / Edit drawings, Make issue / Open issue, Details, Rename (also `F2` on a row), Duplicate (a plain copy, without the drawings), Copy link, Delete (second click confirms; a view in an issue asks in its detail).
- Reorder: drag the grip (pointer events, so touch works), or `Alt+ArrowUp` / `Alt+ArrowDown` on a row. `ArrowUp` / `ArrowDown`, `Home`, `End` move between rows; `Delete` opens the menu.

Keys (rebindable, group `Views` of the cheat sheet): `views.save` `Ctrl+Shift+S`, `views.prev` `Shift+PageUp`, `views.next` `Shift+PageDown` (`PageUp` / `PageDown` alone stay storey up / down), `views.play` and `views.open` unbound.

## Persistence and formats

- `localStorage` key `xray.views.<model name>` holds an `xray-views/1` document: `{ "schema": "xray-views/1", "model": "fzk-haus", "views": [ ... ] }`. Storage that throws is tolerated (the views last for the session, and the tab says so).
- One view:

```json
{ "id": "vmw3...", "name": "Window box behind", "created": "...", "updated": "...",
  "camera": { "position": [6, 5.5, 13], "target": [-3.95, -1.8, -4.8], "up": [0.2, 0.9, -0.3], "fov": 45, "ortho": false },
  "selection": ["1TAI4ouKX4Xx4lBDZlu..."], "hides": { "mode": "show", "ids": ["..."] }, "pins": ["..."],
  "exploded": true, "preset": "behind-only",
  "params": { "xray": true, "section": { "box": { "enabled": true, "min": [..], "max": [..] } }, "viewModes": { ... } },
  "thumb": "data:image/jpeg;base64,..." }
```

- Versioning: readers accept `xray-views/1`, a bare list of views (taken as version 1) and a single shared view (`xray-view/1`). A newer major version (`xray-views/2`) is refused with a message instead of being misread. Unknown fields are dropped, a missing id, time, up vector or field of view is filled in, entries without a name or a camera are skipped and listed.
- Params section `views`: the list without thumbnails, so `Export JSON` of the parameters carries the views; it is **not** in the share URL (`#p=`), and presets neither capture it nor count it in their "still active" hash. Applying it merges like Import; views deleted in this session are not brought back (so "Reset to defaults" does not resurrect them).
- Restoring a view ends an applied BCF viewpoint first (`clearViewpoint`): its hides, colours, clip planes, pin and callouts go. A view saved while a viewpoint was applied holds its hides, selection and planes itself.
- During an AR or VR session (field AR sets its own look, cut box and camera, and puts them back on exit) views are not saved, updated or restored: the status bar says to leave the session first, and Play stops.
- Share link for one view: `?model=<model>#view=<base64url of { schema: "xray-view/1", model, view }>`. The thumbnail is left out, the camera is rounded to 0.1 mm and the params are reduced to the leaves that differ from the factory state (typically 300 to 900 characters). On load it is applied once after the first model (jump, no animation), not saved, and removed from the address; "Press Save view to keep it". A link for another model says so in the status bar.

## Packed pages

```
node tools/xray-pack.mjs model.ifc -o review.html --views views.json --open-view "Roof cut"
```

`--views` takes an exported views file (or a bare list, or a shared single view); views without a name or a camera are skipped with a warning, GlobalIds missing from the packed model are warned about, and a file saved on another model gets a warning. `--open-view` (name, id, name ignoring case, or 1-based number) must be in the file and needs `--views`. The boot document gets `views` (an `xray-views/1` document) and `openView`. On the first model the views plugin merges `__xrayBoot.views` into the views stored for that model (by id, newer wins), once: the ids and `updated` stamps it offered are kept in `localStorage` `xray.viewsPacked.<model>`, so a packed view the user deleted (or edited) does not come back when the page is opened again; a page packed again with a newer version of that view offers it again; `plugins/boot.ts` opens `openView` last, after preset, params, camera, selection, tool and kiosk.

## Scripting

`window.__xrayViews`: `list()` (every view: saved views and views that only have drawings; `id` is a saved view id or a layer id, with `drawings`, `hasDrawings`, `sheet`, `set`, `issue`, `note`), `entries(filter?)` (`all`, `drawings`, `sheets`, `issue`), `withDrawings()`, `filter` and `setFilter(f)`, `open(filter?)`, `drawOn(key)` (makes the drawing layer when there is none, shows the toolbar; returns the layer id), `drawOnCurrent(name?)` (saves the current state as a view with a drawing layer), `makeIssue(key, { topic? })` (returns the issue guid), `get(key)`, `save(name?)`, `restore(key, { animate })` (returns `{ name, missing, skipped, applied }`), `update(key)`, `rename(key, name)`, `duplicate(key)`, `remove(key)`, `move(from, to)`, `next()`, `prev()`, `play(dwellMs?)`, `stop()`, `playing`, `active`, `shareUrl(key)`, `exportJson(withThumbs?)`, `importJson(text)`, `camera()`, `lastRestore`. A key is an id, a name or a 1-based position (`restore`, `drawOn` and `makeIssue` also take the id of a view that only has drawings). `window.__xrayIssues.open('sketches' | 'sheets')` opens this tab on `With drawings` / `On sheets`.

## Developer notes

- `src/views/model.ts`: types, `xray-views/1` parsing and versioning, list operations, hides compaction and GlobalId remapping, params diff / merge, share encoding, storage. `src/views/capture.ts`: capture, restore plan, state apply (testable with a fake app). `src/views/thumb.ts`: the thumbnail (render a frame and read the canvas in the same task, like the BCF snapshot; no `preserveDrawingBuffer`). `src/views/unified.ts`: the merged list, filters and the plans of the entry points (pure). `src/views/panel.ts`: the tab. `src/plugins/views.ts`: wiring, camera move, clip planes, explode, play, share, boot. The sidebar gained `addSidebarTab()` for plugin tabs.
- Tests: `tests/views-unified.test.ts`, `tests/views-model.test.ts`, `tests/views-capture.test.ts`, `tests/views-pack.test.ts`. Smoke: `SMOKE_PORT=5651 node bench/smoke-views.mjs` (fzk-haus and synth5k: 3 views each, reload, restore with numeric checks, play, share link in a fresh context; phone layout; packed page from `file://`). Screenshots `bench/views-*.png`.

## Limits

- The orthographic mode is the viewer's approximation (2 degree field of view, camera moved back); a view saved in it restores it, but the perspective field of view to return to is the one of the current session.
- The exploded state is a flag: the explode is recomputed for the restored selection with the current explode settings, so it matches when those did not change.
- Thumbnails are captured from the canvas at save time (with whatever the ghost animation shows at that frame); a view imported from a file without thumbnails shows "no picture" until you update it.
- Views are per browser and per model name: the same model opened from a file under another name has its own list (export and import to move them).
- A shared link carries the params as differences from the receiver's factory state: a page with a different `xray.config.json` or different plugins can show a slightly different look.
- Playing loops until stopped; the transition is the 400 ms gizmo turn. For a smooth camera path with timing, holds and fades, use the **Fly-through** section below the list (see `flythrough.md`): its keyframes are copies of saved-view states (**From views** builds one per saved view).
- Fly-through keyframes point at saved views. The drawings of a view are not drawn during playback of a fly-through (left as it was; only the camera and the look play).
- A viewpoint of an issue that has no drawing layer (a script made the topic) shows in the issue detail only; `Edit drawings` gives it a layer and then it is listed here.
