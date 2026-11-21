# Fly-through

A fly-through is a camera trip through **keyframes**. A keyframe is a full saved-view state (camera with up vector, field of view and pseudo-orthographic flag; section box and plane; selection; hides and isolate; exploded context; the settings snapshot; the active preset) plus timing. You edit it in the **Fly-through** section of the **Views** tab of the left sidebar. Every fly-through compiles to a **score** (`src/anim/score.ts`), a timeline of cues that one player plays; the animation script language compiles to the same score.

## The timeline

- **Fly-through list**, **New**, and **⋯** (rename, duplicate, export, import, delete). A model keeps several named fly-throughs; the active one is shown.
- **Add keyframe** adds the current view (camera, cuts, modes, selection, hides, settings) with a thumbnail. The list next to it adds a saved view. **From views** replaces the keyframes with one per saved view; **From sets** with one per selection set, the camera framed on the set (the fly-to framing).
- **Cards** show the thumbnail, name and the move (`to 2 s`, `hold 1 s`). Click a card to select it and go to it. Reorder by dragging the grip, with the arrow buttons on the card, or Alt+Left / Alt+Right; Delete removes the card.
- **Transport**: Play (from the start), Pause, Stop, **From** (play from the selected keyframe), **Rec** (record a video: options dialog, see Export). The bar shows the running time, a tick per keyframe, the holds and a playhead; click or drag it to jump.
- **Timing**: *Constant speed* (default, metres per second, by arc length of the camera path; the turn of the view direction counts too) or *Seconds per move* (the same time for each move). **Look at selection** keeps the camera pointed at the selection of each keyframe. **Loop** repeats it.
- **Editor of the selected keyframe**: name, Go to, Update (replace the state with the current view), Insert after, Delete, **Travel** (seconds into this keyframe; empty uses the timing), **Hold** (pause on arrival), **Ease**, **Fade** and its length, **Switch at** (start, middle or end of the move), caption title and text.

While the Views tab is open with the section expanded, the camera path is drawn in 3D as a dashed line with a small camera marker per keyframe (the selected one white). It is off during playback, recording and thumbnail capture.

## What plays

`compileFlyThrough` (`src/anim/flythrough.ts`) makes:

- One **cameraPath** cue: a centripetal Catmull-Rom spline (alpha 0.5: it passes through every pose, no cusps, no overshoot on uneven spacing) through the camera positions and targets; up vector and field of view interpolate along it. Between keyframes the camera moves at constant speed by arc length. At the start, the end and around every hold the speed ramps smoothly (a sine ramp of at most 1.4 s); a keyframe that is passed without a hold does not slow the camera. A hold is the same pose listed twice, with two times.
- A **view** cue per keyframe: the settings snapshot blends (numbers) over the move with an eased curve; booleans, strings, lists, the preset mark and the exploded flag switch at the keyframe's *Switch at* (default: at arrival). The section is part of the settings, so a moving section box animates.
- **Visibility** cues for the elements that differ between two keyframes: newly shown elements fade in, newly hidden elements fade out, over the last 40 % of the move (per keyframe: fade on or off, fade length). Fading writes the per-element alpha (`renderer.state.alpha`) after the controller step, like the staggered reveal; the hide is applied when the fade ends. Without fade the change switches at *Switch at*.
- A **select** cue shortly before arrival (0.8 s, at most 30 % of the move), so the cinematic reveal that follows a selection runs while the camera arrives. The selection fly-to is off while a score plays.
- A **caption** cue at arrival, as long as the hold (2.5 s without a hold), as a lower third over the canvas.

## While it plays

Space pauses and resumes, Left and Right go to the previous and next keyframe, Escape stops. A press or a wheel turn on the canvas stops it and leaves the camera where you took it. When it ends or is stopped (not by a press on the canvas), camera, selection, hides, settings, explode and the active preset are put back as they were before Play. Depth of field and motion blur (Cinematic > Fly-through) apply during playback.

## The score player

`src/anim/player.ts` (clock, pause, seek, loop, cue order) and `src/anim/viewerHost.ts` (the viewer side) implement `ScorePlayerApi` and register with `setScorePlayer`; `getScorePlayer()` returns it.

| Cue | Behaviour |
| --- | --- |
| `cameraPath` | as above; `easeAt` (additive) switches the ease off per pose |
| `camera` | `pose` (position, target, up, field of view, ortho), `frame` (the elements, with the fly-to framing: margin and closest distance), `view` (a saved view by name), `orbitDeg` (about the elements or the target, around world up); blends with the cue's ease |
| `param` | one setting by its params path (`sightlines.alphaMax`); a number blends with the ease, other values switch at `switchAt` (default end) |
| `preset` | a preset id, else a top-bar mode id; switches at `switchAt` |
| `view` | a whole state: numbers in `params` blend, the rest (including selection, hidden, isolate, explode, preset) switch; its camera is used only when no `cameraPath` covers the cue |
| `visibility` | `showAll`, then `isolate`, `show`, `hide`; with `dur > 0` the elements that appear or disappear fade, else they switch at `switchAt` |
| `select` | the elements (or none); `switchAt` default start |
| `caption` | the lower third for the cue's length |
| `label`, `hover` | phase 2: skipped |
| other kinds | skipped |

Element references (`globalIds`, `query` in the criteria language, `set` by name, `selection`, `all`) are resolved once when playback starts; `selection` is read when its cue runs. A seek restores the state and replays every cue up to the new time.

The two legacy-only settings `post.ao` and `post.vignette` (ambient occlusion and vignette of the old fly-through toggles) are accepted as `param` paths; they are not part of the params document.

## Export (video)

**Rec** (Views tab) and **Record** (Script tab) open the options dialog and export the score as a video file. The export is **deterministic and frame by frame**: the viewer's own animation loop is stopped, and for frame *i* the exporter advances the score player by exactly 1 / fps, runs the viewer's frame (controller step, draw, post effects), copies the canvas into a 2D canvas of the video size, draws the HUD layer over it, and hands the picture to the encoder. Nothing uses the wall clock, so a slow machine (or a software renderer) makes a slow export, never a stuttering video; the video always holds duration x fps frames at timestamps 0, 1/fps, 2/fps, and so on. While it runs the viewer is **busy**: an overlay blocks the mouse and the keys and shows *Frame n of N*, the time left and **Cancel** (Escape does the same). When it ends, is cancelled or fails, camera, selection, hides, settings and the render size are put back exactly.

| Option | Choices |
| --- | --- |
| Size | the window, 1280 x 720, 1920 x 1080, 2560 x 1440, 3840 x 2160. The renderer draws at that size (pixel ratio 1; the canvas on screen keeps its layout) and goes back to the window size afterwards. Sizes the graphics card cannot draw are scaled down with the aspect kept; sides are made even (video encoders need it) |
| Frame rate | 24, 30 or 60 |
| Quality | small file, balanced, high quality: 0.04, 0.08 or 0.16 bits per pixel and frame (1 to 120 Mbit/s) |
| Format | automatic, MP4, WebM, PNG sequence |
| Captions and labels | composite the HUD layer (`src/anim/hud.ts`) into every frame when it has something to draw; the layer gets `recording: true` and a pixel ratio of video height / window height, so text keeps its size relative to the picture |
| File name | from the fly-through or script name; unusual characters become dashes |

**Encoders.** WebCodecs `VideoEncoder` through the muxer library **mediabunny** (1.65.2, MPL-2.0, pinned in package.json; loaded on first export with a dynamic import: the main bundle does not grow, the single file build inlines it; no network request). *Automatic* uses MP4 with H.264 (`avc1`, the level chosen from size and rate, High, then Main, then Constrained Baseline) where the browser can encode it, else WebM with VP9, else VP8. *MP4* never falls back to WebM and *WebM* never uses H.264; a browser that cannot do the asked one says so. Key frames every 2 s.

**Fallbacks.** A browser without WebCodecs records in **real time** with `MediaRecorder` of a composite canvas at the window size (webm, or mp4 for Safari; the HUD is composited too), and a browser with neither writes a **PNG image sequence in a zip** (store-only, `frame-000001.png` ...; at most 65535 frames and 4 GB; it needs memory, so keep it short). The PNG sequence can also be chosen on purpose.

**Time.** The dialog warns that 2560 x 1440 and 4K take long on a slow machine and has **Time a few frames**: it renders 4 test frames at the chosen size and says how long the whole video takes. During the export the overlay shows the time left from the mean frame time and warns when it passes 5 minutes.

`window.__xrayRecord`: `capabilities()`, `options()`, `dialog(subject, score, name)`, `run(score, opts?, { download? })`, `flythrough(opts?, { download? })` (opts: `size` also as a custom `WxH`, `fps`, `quality`, `format`, `hud`, `name`), `cancel()`, `busy`, `last`, `lastBlob()`. `window.__cinematic.record()` keeps the old real-time recorder (webm, window size, 30 fps) for existing scripts. Smoke test: `bench/smoke-video-export.mjs`.

**Limits.** The sightline pass (Algorithm 2) still runs on timers after a camera change, so a frame with sightlines on may show the result of a nearby pose; time-based effects that start from the wall clock (the staggered reveal, sweep and pulse) follow the export's own frame clock from the moment they start. Video export is off inside a headset session.

## Kiosk pages (xray-pack)

`xray-pack --flythroughs file.json --scripts a.xrayanim,b.xrayanim --autoplay flythrough:Tour --loop` puts fly-throughs (an `xray-flythroughs/1` file from the fly-through export) and animation scripts into the packed page. The Views and Script tabs list them (a name that already exists is not added twice), and `__xrayBoot.autoplay` (`{ flythrough: name }` or `{ script: name }`, `loop: true`) plays one when the page starts, again and again with `loop`. A press or a wheel turn on the canvas stops it, as always. The fly-through store is keyed by the model's identity, so the packed fly-throughs belong to the packed model. See [xray-pack.md](xray-pack.md).

## Storage and privacy

Fly-throughs are stored in `localStorage` under `xray.flythroughs.<name|element count|GlobalId hash>` (the model's identity key, as the markup and BCF tools use), so a renamed file of the same model keeps them and a different model with the same name does not. The first load of a model with the old `xray.flythrough.<modelName>` keyframes imports them (camera, selection and the seven toggles) as a fly-through named **Imported**; the old key stays.

Captions are user text. They live only in the fly-through store and its explicit **Export file** (`xray-flythroughs/1`); they never enter the params, share links, saved views or packed pages.

## Scripts and smoke tests

`window.__xrayFlythrough`: `list`, `active`, `setActive`, `create`, `rename`, `duplicate`, `removeFlythrough`, `setOptions`, `keyframes`, `add({ view?, at?, name?, hold?, ... })`, `update(index, patch)`, `remove`, `move`, `clear`, `buildFromViews`, `buildFromSets`, `play({ fromKeyframe?, from?, restore?, onEnd? })`, `pause`, `resume`, `stop`, `seek`, `step`, `record` (opens the dialog), `state`, `compile` (the score), `timing`, `exportJson`, `importJson`. `window.__cinematic.play`, `record`, `stop` and the `keys` getter keep working on the new player. Smoke test: `bench/smoke-flythrough.mjs`.

## Not done

The old Cinematic tour and the saved-view slide show (`views.play`) still use their own simple players (see the notes of phase 3). Saving fly-throughs into the IFC is not done.
