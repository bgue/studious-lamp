# 27. Playing and recording the 4D film

## 27.1 Style, scrub, play [P]

You have accepted links. Now the film has choices to make. Do you show the plan or what really happened? Do unbuilt parts
vanish or stay as a faint ghost? Is it 2 minutes for a client or a look at the next 6 weeks for a site meeting? The
answers change the film, not the links, so you can try several without redoing any work.

### The idea

The **Style** section holds those choices. **Play** builds the **4D plan** from the accepted links, hands it to the
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

1. Choose **FZK-Haus 4D** in Sample Projects. The 4D tab opens with the film bar at the top.
2. Open **Style**. Set **Unbuilt parts** to `faint ghost`, then press **Play**. The finished house is faintly there and
   fills in as work runs.
3. Set **X-ray active work** off and play again. Whatever stands in front of the active work is no longer ghosted, so walls can hide it. Turn it back on.
4. Change **Window** to `look ahead N weeks` with 6. The film starts at the data date and shows the next six weeks; what
   was built before the data date is already standing.
5. Drag the date slider. While a film plays it seeks. From a stop, it starts the film paused at that date.
6. Press `Space` to pause. The player's keys, transport and HUD are the ones from chapter 21.

> Picture: the Style section with View, Unbuilt parts, Window and Film length visible.

### Reading the screen

While the film runs, the HUD draws:

- **Schedule date** (top left), the week, `Planned x %` and, when the plan has actuals, `Actual y %`.
- **Activities** below it: `Now: n activities`, the five with the most elements, each with a swatch in its trade colour.
  A critical activity has a red outline.
- **S-curve** (top right): planned progress over the whole window, actual progress up to the last actual sample, and a
  marker for now.
- **Milestone caption** (top centre), held for the milestone hold you set.
- **Legend** (bottom left): trade colours of the work in progress, "Critical", and "Behind" and "Ahead" if the plan has
  actuals.
- **Data-date tick** on the progress bar: an amber mark where the data date sits in the film.

The display options are the ones of 21.1 (the **On-screen display** block of the Views tab).

## 27.2 Style choices that matter

| Option | Values | What it changes |
| --- | --- | --- |
| View | planned, actual to date then forecast, variance | which dates drive the film |
| Unbuilt parts | hidden, faint ghost | what is shown before an element is built |
| Window | whole job, look ahead N weeks, date range | which stretch of the schedule |
| Film length by | seconds, or days per second | one of the two; default 120 s (sample 90 s) |
| Pace | warp, fixed | warp gives busy weeks more screen time |
| Camera | director, fixed, none | see 27.3 |
| Explode, Section box | auto, off | made by the director |
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

If the director is missing from the build, or it fails, the film keeps the current camera, and a note in the Style and Play
sections says so. Nothing breaks.

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
- Temporary works such as formwork and scaffolding are not modelled. Only demolition has a `removed` state.
- A software renderer needs minutes for a short film; plan a long render for a machine with a GPU.

## See also

- Chapter 21: the player, keys and the HUD. Chapter 13: saved views (not the same as the film's View option).
- Chapter 23: animation scripts. Chapter 22: video export.
- Chapter 32: rendering the film from a command line.
