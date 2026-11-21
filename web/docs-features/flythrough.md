# Fly-through

A fly-through is a camera trip through **keyframes**. A keyframe is a full saved-view state (camera with up vector, field of view and pseudo-orthographic flag; section box and plane; selection; hides and isolate; exploded context; the settings snapshot; the active preset) plus timing. You edit it in the **Fly-through** section of the **Views** tab of the left sidebar. Every fly-through compiles to a **score** (`src/anim/score.ts`), a timeline of cues that one player plays; the animation script language compiles to the same score.

## The timeline

- **Fly-through list**, **New**, and **⋯** (rename, duplicate, export, import, delete). A model keeps several named fly-throughs; the active one is shown.
- **Add keyframe** adds the current view (camera, cuts, modes, selection, hides, settings) with a thumbnail. The list next to it adds a saved view. **From views** replaces the keyframes with one per saved view; **From sets** with one per selection set, the camera framed on the set (the fly-to framing).
- **Cards** show the thumbnail, name and the move (`to 2 s`, `hold 1 s`). Click a card to select it and go to it. Reorder by dragging the grip, with the arrow buttons on the card, or Alt+Left / Alt+Right; Delete removes the card.
- **Transport**: Play (from the start), Pause, Stop, **From** (play from the selected keyframe), Rec (record a webm). The bar shows the running time, a tick per keyframe, the holds and a playhead; click or drag it to jump.
- **Timing**: *Constant speed* (default, metres per second, by arc length of the camera path; the turn of the view direction counts too) or *Seconds per move* (the same time for each move). **Look at selection** keeps the camera pointed at the selection of each keyframe. **Loop** repeats it.
- **Editor of the selected keyframe**: name, Go to, Update (replace the state with the current view), Insert after, Delete, **Travel** (seconds into this keyframe; empty uses the timing), **Hold** (pause on arrival), **Ease**, **Fade** and its length, **Switch at** (start, middle or end of the move), caption title and text, **Label selection** with the **fields** to show (empty: name, class, storey) and **Hover card**. Both need a selection in the keyframe (select, then Update).
- **On-screen display**: the HUD settings of the model's fly-throughs (see [The HUD](#the-hud)): **Progress bar**, **Compass**, **Scale bar**, **Label size** and where captions show.

While the Views tab is open with the section expanded, the camera path is drawn in 3D as a dashed line with a small camera marker per keyframe (the selected one white). It is off during playback, recording and thumbnail capture.

## What plays

`compileFlyThrough` (`src/anim/flythrough.ts`) makes:

- One **cameraPath** cue: a centripetal Catmull-Rom spline (alpha 0.5: it passes through every pose, no cusps, no overshoot on uneven spacing) through the camera positions and targets; up vector and field of view interpolate along it. Between keyframes the camera moves at constant speed by arc length. At the start, the end and around every hold the speed ramps smoothly (a sine ramp of at most 1.4 s); a keyframe that is passed without a hold does not slow the camera. A hold is the same pose listed twice, with two times.
- A **view** cue per keyframe: the settings snapshot blends (numbers) over the move with an eased curve; booleans, strings, lists, the preset mark and the exploded flag switch at the keyframe's *Switch at* (default: at arrival). The section is part of the settings, so a moving section box animates.
- **Visibility** cues for the elements that differ between two keyframes: newly shown elements fade in, newly hidden elements fade out, over the last 40 % of the move (per keyframe: fade on or off, fade length). Fading writes the per-element alpha (`renderer.state.alpha`) after the controller step, like the staggered reveal; the hide is applied when the fade ends. Without fade the change switches at *Switch at*.
- A **select** cue shortly before arrival (0.8 s, at most 30 % of the move), so the cinematic reveal that follows a selection runs while the camera arrives. The selection fly-to is off while a score plays.
- A **caption** cue at arrival, as long as the hold (2.5 s without a hold), as a lower third over the canvas.
- A **label** cue (the keyframe's selection, its fields) and a **hover** cue (the first selected element) at arrival, as long as the caption, when *Label selection* or *Hover card* is on.

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
| `caption` | the lower third for the cue's length (drawn by the HUD) |
| `label` | a tag per element with the fields, pinned to the element (drawn by the HUD) |
| `hover` | the hover card of the first element with a leader line (drawn by the HUD) |
| other kinds | skipped |

Element references (`globalIds`, `query` in the criteria language, `set` by name, `selection`, `all`) are resolved once when playback starts; `selection` is read when its cue runs. A seek restores the state and replays every cue up to the new time.

The two legacy-only settings `post.ao` and `post.vignette` (ambient occlusion and vignette of the old fly-through toggles) are accepted as `param` paths; they are not part of the params document.

## The HUD

Everything that shows over the 3D view while a score plays is drawn by **one layer** (`src/anim/hud/layer.ts`, `ScoreHudLayer`) into a 2D canvas context; there is no DOM for HUD content. On screen the layer draws into an overlay canvas (`canvas.xray-hud`, `src/anim/hud/overlay.ts`) that covers the viewer canvas, takes no pointer input, follows the canvas size and the device pixel ratio, is redrawn every frame while a score plays (also while paused) and cleared and hidden otherwise. The layer is registered with `setHudLayer` (`src/anim/hud.ts`); the video export draws the same layer into each frame. It is stateless apart from the score (the score host hands it over in `begin`): the picture depends on the time, the size and the projection of the frame only.

- **Captions**: a lower third with title and text on a dark panel with an accent bar. It fades in and out over 0.3 s (less for a short caption), wraps to the width, keeps 12 px or 4 % of the width from the edges and uses larger text on a phone. The setting *Captions at bottom / top* moves it. When two overlap, the later one shows.
- **Labels** (`label` cue): one tag per element, pinned at the centre of the element's bounding box with a leader line and a dot. Fields: `name`, `class`, `storey`, `material`, `globalid`, `type` (the predefined type or object type) and any property key such as `Pset_WallCommon.FireRating` (shown as `FireRating: 2HR`); the same data as the hover card and the Properties list. A field without a value is left out. Tags are placed greedily (up-right, up-left, down-right, down-left, right, left of the element, the ones nearest the screen centre first) and never overlap each other, the caption, the hover card, the compass or the scale bar. Elements behind the camera or off the frame get no tag. At most 12 tags show; a pill **+N more** counts the rest, and the tags that found no room. Tags fade with the cue.
- **Hover card** (`hover` cue): the content of the hover card (title, class, storey and material, the filtered properties; not the live x-ray line) for the first element of the cue, drawn near the element with a leader line, for the cue's length.
- **Progress bar**: a 3 px bar at the bottom with a mark per chapter (a fly-through: the arrival at each keyframe; a script: the start of each caption and label) and the elapsed and total time. On by default.
- **Compass** (off by default): a north arrow in the top right corner. North is the map's place when the map has one, else the IfcSite `TrueNorth` of the model, else project +Y.
- **Scale bar** (off by default): a round length (1, 2 or 5 times a power of ten metres) at the bottom left, sized from the distance at the centre of the screen.
- **Settings** live in the fly-through document (`hud`: `progress`, `compass`, `scaleBar`, `labelSize` 9 to 28, `captionPosition`), stored and exported with the fly-throughs, per model. They are not in the params or share links. Scripts use the same settings.

Label fields and captions are user choices and user text: they stay in the fly-through store and its export, never in the params, share links, saved views or packed pages.

`window.__xrayFlythrough.hud()`, `setHud(patch)` and `hudState()` (is something drawn, the size, and the last description: caption, labels, hover card, progress, compass and scale with their rectangles) serve scripts and smoke tests.

## Storage and privacy

Fly-throughs are stored in `localStorage` under `xray.flythroughs.<name|element count|GlobalId hash>` (the model's identity key, as the markup and BCF tools use), so a renamed file of the same model keeps them and a different model with the same name does not. The first load of a model with the old `xray.flythrough.<modelName>` keyframes imports them (camera, selection and the seven toggles) as a fly-through named **Imported**; the old key stays.

Captions are user text. They live only in the fly-through store and its explicit **Export file** (`xray-flythroughs/1`); they never enter the params, share links, saved views or packed pages.

## Scripts and smoke tests

`window.__xrayFlythrough`: `list`, `active`, `setActive`, `create`, `rename`, `duplicate`, `removeFlythrough`, `setOptions`, `keyframes`, `add({ view?, at?, name?, hold?, ... })`, `update(index, patch)`, `remove`, `move`, `clear`, `buildFromViews`, `buildFromSets`, `play({ fromKeyframe?, from?, restore?, onEnd? })`, `pause`, `resume`, `stop`, `seek`, `step`, `record`, `state`, `compile` (the score), `timing`, `exportJson`, `importJson`, `hud`, `setHud`, `hudState`. `window.__cinematic.play`, `record`, `stop` and the `keys` getter keep working on the new player. Smoke test: `bench/smoke-flythrough.mjs`.

## Not done

Better recording (fixed frame rate, resolution; the video export is separate work), the Cinematic tour and the saved-view slide show (`views.play`) still use their own simple players.
