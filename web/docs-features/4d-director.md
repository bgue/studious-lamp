# The 4D director

The director reads a 4D plan (`build.4d.json`) and the bounding boxes of the model and decides what the camera does, when the building
explodes, where a section box clips, what is captioned and which activities are labelled. It writes **score cues** that sit on top of a
`schedule4d` cue covering the film, and one line of explanation for every decision. Design: `docs/design/4d-xer-animation.md`
(section 5). Code, pure TypeScript with no viewer or DOM: `src/schedule/director.ts` (the rules) and `src/schedule/directorScript.ts`
(the script writer). Same plan, model and options give the same cues.

```ts
const { cues, notes } = directFourD(plan, model);            // model: element boxes and storeys by GlobalId (a FourDModel fits)
const text = scriptFromPlan(plan, { cues, notes, noteTimes }, { planName: 'Tower A' });   // an editable .xrayanim
```

`directFourD(plan, model, opts)` returns `{ cues, notes, noteTimes }`. Cue times are video seconds from the start of the film (option
`start` moves them, `duration` rescales the plan's time map; default: the time map's span, starting at 0). The `notes` are
`mm:ss.s  YYYY-MM-DD  what and why`, one per decision.

## The rules

- **Interest region.** The film is sampled every 0.5 s. The interest set at a moment is the elements that are active during the next
  4 s (6 s for the calm profile): the active ones and those about to start, the ones that change state in that window weighing three
  times as much. Its box, without the outer 5 % when there are 20 elements or more, is the region.
- **Shot.** Wide when the region diagonal is 55 % of the model's or more (frames everything), medium from 20 %, close below.
  Moves are `camera` cues with `{ frame: { globalIds } }` (the elements that reach the sides of the region) or `{ frame: { all } }`.
  A shot lasts at least 4 s (6 s calm). A new shot only when the shot type changes, the region moved by more than its own size,
  or its size changed a lot. The film opens with a wide shot.
- **Comfort.** The camera never moves while the building explodes or collapses; camera moves start at least 3 s apart (shots are
  4 s apart); the up axis is never touched. In a gap of 8 s or more with no move there is a slow orbit (4 degrees a second, at most 90).
  Style `camera: 'fixed'` and `'none'` emit no camera moves.
- **Explode.** When the interest set is on 3 or more storeys at once (a storey counts with 5 % of the active elements, at least one),
  for 6 s or more, `explode storeys by 1.5` (2 s), a hold, and `collapse` (2 s) when the work concentrates again. A model with two
  storeys explodes when both have work and the upper storey roofs over the lower work. The camera reframes wide after the explode.
  Style `explode: 'off'` emits none.
- **Beats.** At up to 3 phase milestones (names such as "complete", "closed", "weathertight", "topping-out", or all milestones when none
  match; at least 12 s apart) an 11.6 s beat: `focus` on the whole building, explode, a wide shot, a 70 degree orbit, collapse, and
  `focus active` again. The camera does nothing else meanwhile.
- **Section box.** When all active work, for 6 s or more, is on one storey and inside the envelope (inside the storey's footprint, not on
  its edge), `section box around storey "..."`; `section box off` when the work leaves (or the next storey's box). Never together with
  an explode. Style `sectionBox: 'off'` emits none.
- **Focus.** The schedule4d runner follows the active work by itself (`style.xrayFocus`); `focus` cues appear only in the beats.
- **Captions** at each milestone (merged when several fall on one moment, shortened or dropped when too close), and a title caption at
  the start (the milestones at the start are folded into it). Style `captions: false` emits none.
- **Labels** on the largest active activities, at most `style.labels` at a time (option `labels` overrides), each 3 to 8 s, on the element
  of the activity nearest to the middle of its active elements, with the fields `activity`, `percent`, `finish` (4D fields of the HUD).

## The script

`scriptFromPlan` writes the film as a readable script: a header, the `schedule` statement, then one `at date` (or `at milestone`) block for
every moment the director acts, several cues of one moment in a `together` block, and the notes as comments before the blocks. Dates carry
a time (`"2027-05-21T22:08"`) when the moment is not at midnight; a moment inside the hold of a milestone is `at milestone` plus a `wait`.
Compiling the script with the plan (`compileScript(text, { plans })`) gives cues equivalent to the director's: same kinds and settings,
times within a few milliseconds (a test checks this on synthetic plans and on the FZK-Haus sample). A cue the language cannot say is left
out with a comment that says so.

In the viewer, **Open as script** in the film bar of the 4D tab does the same for the film on screen and opens the text in the Script tab (see [4d-schedule.md](4d-schedule.md)).

## The CLI

```
xray-4d script build.4d.json --model model.ifc [--style calm|dynamic] [--labels N] [--no-explode] [--no-section] \
               [--name NAME] -o film.xrayanim [--notes notes.txt]
```

The plan carries the model identity but no geometry, so the director needs the model: `--model` takes the IFC file (read with the node IFC
reader of `xray-pack`) or the sidecar `.json` it produces. The plan elements must be in the model (exit 3 when fewer than half are).
`--name` is the plan name written in the `schedule` statement (default: the plan file name); the host registers the plan under that
name (`registerPlan`) before it compiles the script. The script is compiled once before it is written; the notes also go to `--notes`.
