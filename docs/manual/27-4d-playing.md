# 27. Playing and recording the 4D film

## 27.1 Style, scrub, play [P]

You have accepted links. Now the film has choices to make. Do you show the plan or what really happened? Do unbuilt parts
vanish or stay as a faint ghost? Is it 2 minutes for a client or a look at the next 6 weeks for a site meeting? The
answers change the film, not the links, so you can try several without redoing any work.

### The idea

The **Style** section, in the **Film** step of the 4D tab, holds those choices. **Play** builds the **4D plan** from the accepted links, hands it to the
player (chapter 21) and plays it. The plan says, for each element and date, one of these states:

| State | Look in the film |
| --- | --- |
| future | hidden, or a faint ghost if you choose |
| existing | solid, slightly greyed |
| active | fades in, tinted in its trade colour, with an edge glow; red glow if the activity is critical |
| complete | solid in its own colour, no glow |
| removed | fades out in red, then hidden |
| behind | red tint (variance view only) |
| ahead | a green flash on completion (variance view only) |

Because the active work is also the x-ray focus (chapter 1), the viewer ghosts whatever stands in front of it. Services
being fitted inside a closed wall stay visible without hiding the building.

### Try it

1. Choose **FZK-Haus 4D** in Sample Projects. The 4D tab opens on the **Film** step, with the film bar at the top.
2. In the **Film** step, open **Style**. (The Style section lives in the Film step, the last of the three steps of chapter 24.)
   Set **Unbuilt parts** to `faint ghost`, then press **Play**. The finished house is faintly there and
   fills in as work runs.
3. Set **X-ray active work** off and play again. Whatever stands in front of the active work is no longer ghosted, so walls can hide it. Turn it back on.
4. Change **Window** to `look ahead N weeks` with 6. The film starts at the data date and shows the next six weeks; what
   was built before the data date is already standing.
5. Drag the date slider. While a film plays it seeks. From a stop, it starts the film paused at that date.
6. Press `Space` to pause. The player's keys, transport and HUD are the ones from chapter 21.

> Picture (4d-style): the Style section with View, Unbuilt parts, Window and Film length visible.

### Reading the screen

While the film runs, the HUD draws:

- **Schedule date** (top left), the week, `Planned x %` and, when the plan has actuals, `Actual y %`.
- **Activities** below it: `Now: n activities`, the five with the most elements, each with a swatch in its trade colour.
  A critical activity has a red outline.
- **Also under way (not in the model)**: a line under "Now" that appears while an activity you marked **Not modelled**
  (chapter 26) is running, for example "Also under way (not in the model): Earthworks, Drainage". It names at most two, then
  "+N more". It has no elements to show, so without the line the film would look idle while that work goes on.
- **S-curve** (top right): planned progress over the whole window, actual progress up to the last actual sample, and a
  marker for now.
- **Milestone caption** (top centre), held for the milestone hold you set.
- **Colour legend** (bottom left, above the strip): the trades that appear in the film, each with its colour (at most 8, then "+N
  more"), and a key to the states: Planned (a faint ghost), Active (trade colour with a bright edge), Built, Existing, Removed (red),
  Critical (red outline), and Behind and Ahead when the plan has actuals or you use the variance view. Temporary works add their own
  colours. The panel is light on dark, so a video looks the same in any viewer theme.
- **Schedule strip** (along the bottom, above the progress bar): a thin Gantt band over the film's dates. One row per trade (the 12 that start
  first, the rest folded into "Other"), one bar per activity, critical ones edged in red, running ones bright, milestones as amber
  diamonds, and a white marker for today's date. It shows where in the whole job the film is.
- **Data-date tick** on the progress bar: an amber mark where the data date sits in the film.

The display options are the ones of 21.1 (the **On-screen display** block of the Views tab). The legend and the strip also have a
switch each in **Style** (**Legend**, **Strip**, both on) that travels with the 4D file, and they appear in the video and in a packed page.
They are drawn only while a 4D film runs, never in a plain fly-through.

## 27.2 Style choices that matter

| Option | Values | What it changes |
| --- | --- | --- |
| View | planned, actual to date then forecast, variance | which dates drive the film |
| Unbuilt parts | hidden, faint ghost | what is shown before an element is built |
| Window | whole job, look ahead N weeks, date range | which stretch of the schedule |
| Film length by | seconds, or days per second | one of the two; default 120 s (sample 90 s) |
| Pace | warp, fixed | warp gives busy weeks more screen time |
| Camera | director, fixed, none | see 27.3 |
| Explode | auto, each floor apart, off | made by the director; see 27.3 |
| Section box | auto, off | made by the director |
| Fade in (s) | seconds, or auto | how long a new part takes to appear, and a removed one to disappear. Auto is 10 % of the activity or 0.6 s, the shorter. 0 is at once, with no fade |
| Issues and drawings in the film | on, off | off (default) hides the pins and drawings while the film plays and puts them back after; on keeps them |
| Camera per floor | a saved view for each storey | see 27.3 |
| Finale | none, dolly, orbit | what the camera does after the last work; see 27.3 |
| Legend, Strip | on, off | the colour legend and the schedule strip |
| Labels | 0 to 12 | most activity labels at once |
| Critical float | hours, or driving path only | what counts as critical |

The option called **View** here (planned, actual, variance) is not a saved view from chapter 13. It picks which set of dates
the plan uses:

- **Planned**: early dates, or a baseline if there is one.
- **Actual**: actual dates where they exist, remaining dates after the data date.
- **Variance**: the plan against a reference (a baseline, else the target dates). At the data date, an element planned
  finished but not done is **behind**, and one done before its planned finish is **ahead**.

### The time map: two years in 90 s

The film does not run at a steady speed. The time map works like this:

1. Only working time counts. Weekends and holidays take almost no screen time.
2. With pace **warp**, a day with many changes gets more seconds, within 0.3 to 3 times the average, so the clock
   never jumps.
3. Each milestone holds for the milestone hold (default 1.5 s) with its caption.
4. The whole thing is scaled to the film length.

That is why the date on screen moves fast in quiet weeks and slowly when the walls go up.

## 27.3 The director

With **Camera: director**, the director adds to the film: where the camera goes, when the building explodes by storey,
when a section box clips to one storey, which captions appear and which activities are labelled. Its rules in short:

- The camera looks at where the work will be in the next 4 s. It chooses wide, medium or close by the size of that region,
  holds a shot for at least 4 s and never moves while the building explodes.
- When work spreads over 3 or more storeys for 6 s, it explodes the storeys, then collapses them when work concentrates.
- When all active work is inside one storey for 6 s or more, it clips a section box to that storey.
- At up to 3 big milestones such as "Building weathertight" it does a short beat: the whole building, an orbit, back to the work.

**Each floor apart.** In **Style**, **Explode: each floor apart** moves the storeys away from each other around the floor being built. That floor
is the x-ray focus and its name is on a caption; the other storeys are context. The storeys close again before the work moves on. It is for a film
where you want to see inside a multi-storey building as it rises. It does not use the work-spread explode or the milestone beats, and it never
opens a section box while the floors are apart. A model with fewer than two storeys gets no explode, and the notes say so. The FZK-Haus 4D sample
builds its ground floor and its roof storey apart.

**Camera per floor.** A floor can have its own camera. In **Camera per floor**, one row per storey, pick a **saved view** (chapter 13) for that
floor. When all the work in a shot is on that floor, the camera glides to the view instead of framing the elements. Leave a row empty
for Automatic. From a command line: `xray-4d plan --zone-camera "Erdgeschoss=EG south"` (32.2). The choice is kept in the 4D file.

**Finale.** **Finale: dolly** gives the end a slow dolly-in on the finished building, then a 90 degree orbit with a caption (the last milestone's
name, or "Complete"). **Orbit** is the orbit and caption alone. The film becomes 14 s (8 s for orbit) longer. It works with the director camera only.
The FZK-Haus 4D sample uses the dolly.

If the director is missing from the build, or it fails, the film keeps the current camera, and a note in the Film step
says so. Nothing breaks.

### Edit the film as a script

The director's decisions can be written as a readable animation script (chapter 23). Press **Open as script** in the film bar.
The viewer builds the plan as **Play** would, runs the director, and opens the result in the **Script** tab under the
project's name, not yet saved. Press **Run** there and the same film plays. **Save** keeps it in your list of scripts.

The script has a header, the `schedule` statement, then one `at date` block for every moment the director acts, with a
comment saying why. The command line makes the same script (chapter 32):
`xray-4d script build.4d.json --model model.ifc -o film.xrayanim`. You can change a
shot, move a caption or add `mode cutaway` for an interior phase, then run it in the Script tab (chapter 23) or hand it to
`xray-4d render --script`. Check the script after editing: the Script tab and `xray-4d` both compile it, and show errors
with line numbers.

The command line does not use the director by itself. `xray-4d render`, `pack` and `all` play the plan with the current camera,
unless you give them a script made by `xray-4d script`.

## 27.4 Record

**Record** opens the video export dialog for the same film (chapter 22). Export is frame by frame, so the speed of your
computer does not change the video, and the HUD is part of the picture. On a machine without a GPU the software renderer
is slow; short windows and small sizes are kind to it.

## 27.5 How it works

The film is one item on the player's timeline (chapter 21). It reads the plan on every frame. A frame costs the number of
elements that change, not the number of elements. A seek, or any step back, evaluates from scratch, so the picture never
depends on how the time got there. When the play ends, visibility, tints, glow, the quiet selection, explode offsets and the
section box go back as they were.

## 27.6 Limits and gotchas

- One pair of glow colours: amber for active, red for critical. Other cinematic glows are off while the film plays.
- An element that is both an x-ray occluder and fading in shows the schedule's value.
- A baseline `.xer` is not loaded in the viewer yet. Variance in the viewer compares with the target dates.
- Temporary works are drawn only in the film and are not part of the IFC model (27A.1). Only demolition has a `removed` state for the building itself.
- A software renderer needs minutes for a short film; plan a long render for a machine with a GPU.

## 27.7 More in the next chapter

Temporary works (scaffold, falsework, formwork) and the storyboard PDF are in chapter 27A.

## See also

- Chapter 27A: temporary works and the storyboard PDF. Chapter 21: the player, keys and the HUD. Chapter 13: saved views (not the same as the film's View option).
- Chapter 23: animation scripts. Chapter 22: video export.
- Chapter 32: rendering the film from a command line.
