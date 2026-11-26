# 4D playback

The score player plays a **4D plan** (`FourDPlan`, `src/schedule/types.ts`; design in `docs/design/4d-xer-animation.md`) as a film of the building going up, and has cue kinds to help it: `tint`, `explode`, `collapse`, `focus` and `sectionBox`. The HUD draws the schedule date, % complete, an S-curve, the current activities, milestone captions and a legend over it, and the video export includes all of it. Code: `src/anim/fourd/` (looks, runners, state lookup, demo plan), `src/anim/hud/fourd.ts` (HUD drawing), `src/anim/viewerHost.ts` (the viewer side).

## The `schedule4d` cue

```ts
{ at: 0, dur: 60, kind: 'schedule4d', plan: { name: 'tower' } }   // or the FourDPlan inline
```

- **The plan** is inline or by name from a small registry: `registerPlan(name, plan)` (`src/anim/fourd/plans.ts`, also `window.__xray4d.registerPlan`). An unknown name skips the cue with a message.
- **Time.** The plan's `timeMap` (plan time in ms to video seconds, piecewise linear) is scaled to the cue's `dur`: progress 0 is the first point of the map, progress 1 the last. A flat stretch of the map (a hold at a milestone) keeps the plan time still while the film goes on.
- **Elements** are matched to the model by GlobalId once when playback starts. A plan element the model does not have is skipped.
- **State per element** at plan time *t* is the state of its latest interval that started by *t*; before the first interval it is `future`, and after the last the last state holds. The runner keeps a pointer into one list of all interval starts sorted by time, so a frame costs the number of intervals that start in between (plus the few elements still fading), not the number of elements. A **seek** (or any step back in time) evaluates from scratch, so the picture never depends on how the time got there.
- **At the end** of the play (end of the score, Stop, a seek) the visibility, alpha, tints, glow, focus (selection), explode offsets and the section box are put back as they were. While the score goes on after the cue has ended, the final picture stays.

## Looks per state

| State | Look |
| --- | --- |
| `future` | hidden, or with `style.unbuilt: 'ghost'` a faint ghost (alpha 0.06) |
| `existing` | visible, slightly desaturated (22 % toward grey) |
| `active` | visible, fades in over the fade time (below: by default the first 10 % of its interval or 0.6 s of video, the shorter), tinted 70 % in its trade colour, with edge glow. Critical task (`plan.tasks[].critical`): the glow is red |
| `complete` | visible, own colour, no glow |
| `removed` | fades out tinted red over the fade time, then hidden |
| `behind` | red tint (60 %), glow like active |
| `ahead` | a green flash that fades over the fade time |

### Fade-in time

How long a newly built element takes to fade in, and a removed one to fade out, in seconds of film:

- **Default**: 10 % of the activity's interval or 0.6 s, the shorter.
- **`style.fadeIn`** (seconds, in the 4D tab: Style > **Fade in (s)**, with **Auto** for the default): that many seconds, but never longer than the activity itself. 0 shows new parts and removes old ones at once (no fade and no green flash).
- **`schedule4d.fadeIn`** (a field of the cue) wins over the style for that cue.
- **`fadeDefault`** cue `{ seconds }` sets the fade time from that moment on: activities that start after it use it (an element that is already fading keeps the time it started with), and so do `visibility` cues without a duration (`dur: 0`), which then fade over `seconds` on the clock instead of switching at once. `seconds: 0` is at once. A seek replays the cues, so the picture never depends on how the time got there.

Trade colours come from `style.colours` by trade, else a default palette by trade name (structure amber, steel blue, envelope cyan, services green, fit-out purple, and so on; unknown trades get a stable colour from a short list). The glow is the renderer's edge glow (`renderer.setEdgeGlow`, with an additive `accent` set for the red critical glow), and it takes over from the Cinematic edge glow while the film plays. With `style.xrayFocus` the **active elements are the x-ray focus**: they are selected quietly (no fly-to), which is what the sightlines make the focus from, and only when the active set changes and at most every 0.25 s of video. Hidden elements use the hides of the overrides, so the sightlines ignore elements that are not built yet; the sightlines re-run at most every 0.4 s on screen and every frame in a video export.

## Dynamic element references

`{ schedule: 'active' | 'completed' | 'critical' | 'future' }` (an `ElementRef`) is resolved **when the cue runs** from the state of the `schedule4d` cue that started last: `active` is the active and behind elements, `completed` the complete and ahead ones, `critical` the active elements of critical tasks, `future` those not started. Without a `schedule4d` cue it is empty. It works wherever an element reference does (`focus`, `tint`, `camera` frame, `label`, ...). The state after the cue ends is its final one.

## The helper cues

| Cue | Behaviour |
| --- | --- |
| `tint` | `{ elements, colour }` fades the colour in over the cue (80 % toward it, with the cue's ease); `colour: null` fades the tint the elements have now out and removes it |
| `explode` | `{ mode: 'storeys' \| 'radial', factor? }` moves every element, eased over the cue. `storeys` lifts each storey by `factor` times the median storey spacing of the model; `radial` pushes elements out from the model centre by `factor` times their distance. A second explode continues from where the building is |
| `collapse` | eases the explode back to 0 and clears the offsets. The Cinematic explode of the user is not touched and writes its offsets again afterwards |
| `focus` | `{ elements }` sets the x-ray focus (a quiet selection) once at the start; `null` gives it back to the selection as it was. While a `focus` on elements is held, the schedule's own follow-the-active-work focus waits; `focus { schedule: 'active' }` (or `null`) gives it back |
| `sectionBox` | `{ around, margin? }` with `around` elements or `{ storey: 'Level 3' }` (by name) closes the section box in from the model (or from the box that is on) to the box around them plus the margin (default: the section tool's margin), eased over the cue; `around: null` opens it out to the model and switches it off at the end |

| `overlays` | `{ issues?, drawings? }` shows or hides the issue pins and the drawings from this moment (see below) |
| `fadeDefault` | `{ seconds }` the default fade for what appears or disappears from here on (see Fade-in time) |

## Issues and drawings while a score plays

Issue pins and drawings (the pins of the issues, the drawings on the model including the view-locked ones, the sketches of sheets in 3D) are review marks, not part of a film. **Whenever any score plays** (fly-through, script, 4D film, packed-page autoplay, `xray-4d render`, video export) they are hidden, and **put back exactly as they were** when playback ends or is stopped. The hiding is a CSS class on the page that hides the overlay layers (`bcf-markup`, `markup`, `sheet-sketches`), so nothing of the issue and drawing state is touched and nothing needs to be remembered; the pins and drawings keep their own on and off switches.

Ways to change it, strongest first: an `overlays` cue switches them during playback (a field it does not name stays); `PlayOptions.overlays` (`{ issues?, drawings? }`) sets the state at the start; a 4D plan whose style has `issuesInFilm: true` (4D tab, Film step > Style > **Issues and drawings in the film**; part of the style, so it travels in the `.4d.json` and in the plan) keeps both; a fly-through can keep them with its own option (see [flythrough.md](flythrough.md)). The default is both hidden. The video export frames hold the 3D view and the HUD (the pins and drawings are not drawn into them); the export plays the same score, so the viewer behaves the same while it runs.

## HUD items

While a `schedule4d` cue runs the HUD layer draws, besides captions and labels:

- **Schedule date** (top left): the date, `Week n · year` (ISO week) and `Planned x %` and, when the plan has actuals up to now, `Actual y %`. The date also replaces the `m:ss / m:ss` clock on the progress bar.
- **Activities** (below it): `Now: n activities`, the 5 with most elements, each with a swatch in its trade colour (outlined red when critical) and its element count.
  Activities marked `notModelled` in the configuration (work the model does not contain) have no elements and no row; while they run, one dim line under the rows reads `Also under way (not in the model): A, B +N more` (at most two names; `FourDView.notInModel`).
- **S-curve** (top right, below the compass when it is on): planned progress over the whole window, actual progress up to the last actual sample, a marker for now.
- **Milestone caption** (top centre): the plan's milestone names, held for `style.milestoneHold` seconds of video from the moment the film reaches them, with a short fade.
- **Colour legend** (bottom left, above the strip; `src/anim/hud/legend.ts`, content in `src/anim/fourd/legend.ts`): the trade colours of the trades that appear in the film (at most 8, then `+N more`) and the state key: `Planned` (ghost view), `Active` (trade tint with a bright edge), `Built`, `Existing` and `Removed` (red) when the plan has them, `Critical` (red outline), `Behind` and `Ahead` in the variance view or when the plan has actuals, and the colours of temporary works when the plan carries them (`plan.temporary`: `{ colour, label? }` or a list of them). Fixed light-on-dark panel, so a video looks the same whatever the viewer theme. It wraps to the width it has (compact on a phone) and falls back to one run-on line when the top left is crowded.
- **Schedule strip** (along the bottom, above the progress bar; `src/anim/hud/strip.ts`): a thin Gantt band over the film's date range. One row per trade (the 12 trades that start first, the others folded into one `Other` row), one bar per activity, critical activities with red edges, the running bars bright and the others dim, milestones as amber diamonds on a row of their own, the current date as a white marker with its label. The legend sits above it, so the two never overlap.
- **Data-date mark** on the progress bar: an amber tick where the plan's `schedule.dataDate` sits in the film.

The options are in the **On-screen display** block of the fly-through section of the Views tab (and in `HudSettings`, `src/anim/hud/settings.ts`): `scheduleDate`, `sCurve`, `activities`, `milestones` and `legend`, all on by default. They are saved with the other HUD options.

The legend and the strip are also part of the film's **style** (they travel in the `.4d.json` and in the plan): `legend: 'on' | 'off'` and `strip: 'on' | 'off'`, both on when absent. Film step > Style has a switch for each; `xray-4d plan` and `xray-4d render` take `--legend on|off` and `--strip on|off`. The legend is drawn when both the HUD option and the style say on. Both are drawn by the HUD layer only while a `schedule4d` cue runs, so a plain fly-through never shows them; the video export and the packed page's autoplay use the same layer and show them. A storyboard PDF repeats the legend once per page: see [4d-storyboard.md](4d-storyboard.md).

## Showing it without a schedule: the demo plan

`window.__xray4d` (installed with the fly-through plugin):

```js
const plan = __xray4d.demoPlan();               // groups the loaded model by storey bottom-up, 4 trades by IFC class,
                                                // a milestone per storey, a critical chain through the structure tasks
__xray4d.play(plan, 20, extraCues);             // a score with one schedule4d cue of 20 s (+ extra cues), played
__xray4d.state(0.5, plan);                      // counts of element states at half of the window (or at a plan ms)
__xray4d.live();                                // hidden / tinted / glowing / active counts and the plan time of the running cue
__xray4d.bench(plan, 120);                      // ms per frame of the state update alone
```

`buildDemoPlan(model, options)` (`src/anim/fourd/demoPlan.ts`) is the pure version used by the tests. The smoke tests are `bench/smoke-4d-play.mjs` (play, HUD, restore, video export of a 2 s clip).

## Limits

- One edge glow colour pair: active work glows amber, critical work red; the other glow scopes of the Cinematic settings are off while the film plays.
- Tints and alphas are written to the renderer state after every controller step, so an element that is both an x-ray occluder and fading in shows the schedule's value.
- The film does not move the camera: use `camera` cues (frame `{ schedule: 'active' }`) or the director of the planned `xray-4d` CLI.
