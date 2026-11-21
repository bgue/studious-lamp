# Fly-through

A fly-through is a camera trip through **keyframes**. A keyframe is a full saved-view state (camera with up vector, field of view and pseudo-orthographic flag; section box and plane; selection; hides and isolate; exploded context; the settings snapshot; the active preset) plus timing. You edit it in the **Fly-through** section of the **Views** tab of the left sidebar. Every fly-through compiles to a **score** (`src/anim/score.ts`), a timeline of cues that one player plays; the animation script language compiles to the same score.

## The timeline

- **Fly-through list**, **New**, and **⋯** (rename, duplicate, export, import, delete). A model keeps several named fly-throughs; the active one is shown.
- **Add keyframe** adds the current view (camera, cuts, modes, selection, hides, settings) with a thumbnail. The list next to it adds a saved view. **From views** replaces the keyframes with one per saved view; **From sets** with one per selection set, the camera framed on the set (the fly-to framing).
- **Cards** show the thumbnail, name and the move (`to 2 s`, `hold 1 s`). Click a card to select it and go to it. Reorder by dragging the grip, with the arrow buttons on the card, or Alt+Left / Alt+Right; Delete removes the card.
- **Transport**: Play (from the start), Pause, Stop, **From** (play from the selected keyframe), Rec (record a webm). The bar shows the running time, a tick per keyframe, the holds and a playhead; click or drag it to jump.
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

## Storage and privacy

Fly-throughs are stored in `localStorage` under `xray.flythroughs.<name|element count|GlobalId hash>` (the model's identity key, as the markup and BCF tools use), so a renamed file of the same model keeps them and a different model with the same name does not. The first load of a model with the old `xray.flythrough.<modelName>` keyframes imports them (camera, selection and the seven toggles) as a fly-through named **Imported**; the old key stays.

Captions are user text. They live only in the fly-through store and its explicit **Export file** (`xray-flythroughs/1`); they never enter the params, share links, saved views or packed pages.

## Scripts and smoke tests

`window.__xrayFlythrough`: `list`, `active`, `setActive`, `create`, `rename`, `duplicate`, `removeFlythrough`, `setOptions`, `keyframes`, `add({ view?, at?, name?, hold?, ... })`, `update(index, patch)`, `remove`, `move`, `clear`, `buildFromViews`, `buildFromSets`, `play({ fromKeyframe?, from?, restore?, onEnd? })`, `pause`, `resume`, `stop`, `seek`, `step`, `record`, `state`, `compile` (the score), `timing`, `exportJson`, `importJson`. `window.__cinematic.play`, `record`, `stop` and the `keys` getter keep working on the new player. Smoke test: `bench/smoke-flythrough.mjs`.

## Not done (phase 1)

Better recording (fixed frame rate, resolution), HUD labels and hover cues (`label`, `hover`), the Cinematic tour and the saved-view slide show (`views.play`) still use their own simple players.
