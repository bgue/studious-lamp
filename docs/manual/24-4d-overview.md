# 24. 4D in one page: what you need

## 24.1 The chain from schedule to film

A client asks to see how the house goes up, week by week. You have two good things: a model that shows the finished
house, and a schedule that says what happens when. Neither one knows about the other. The schedule has an activity called
"Ground floor masonry". The model has a few dozen walls. Nothing says which walls belong to that activity. Until someone
says so, you cannot film the build.

### The idea

Think of a cooking show. The **schedule** is the recipe: steps in order, each with a time. The **model** is the pile of
ingredients on the counter. To film the dish being made, someone must write on every ingredient which step uses it.
Then the film is easy: at each step, the right ingredients arrive.

4D is that job, in five stages. Each stage makes one thing you can look at and correct.

1. **Schedule and model.** You bring a Primavera P6 export (`.xer`) and an IFC model. The schedule lists activities with
   dates. The model lists elements with a class, a storey and a name.
2. **Location, trade and zone.** Each element gets three labels: where it is (its **location**, usually a storey), what
   kind of work builds it (its **trade**) and which part of the site it is in (its **zone**). Each activity gets the
   same three labels from its schedule codes. Matching labels are the bridge.
3. **Links.** A **link** (4D) joins one activity to the elements it builds or removes. A link says why it exists:
   "same location and trade", or "the activity name says slab".
4. **The 4D plan.** The plan states what each element is doing at each date: not yet built, being built, built, removed.
   It also holds the time map that squeezes two years into a few minutes of film.
5. **The film.** The player (chapter 21) plays the plan. Elements appear when their activity runs, the work in progress
   stays visible, and the date and progress sit on screen.

Why five stages and not one button? Because each guess can be wrong, and you want to catch it where it is cheap to fix.
A wrong label is easy to see in the Coverage section of the Map step. A wrong link is easy to see on the link report. A wrong frame in a
finished film is not.

### The 4D tab: a film bar and three steps

All of this happens in the **4D** tab of the right sidebar. At the top sits the **film bar**: **Play**, **Pause**, **Stop**, the
date slider, **Record** and **Open as script**. It stays in view while you work below it. It also shows how far the linking
has come, in one line, for example "82 of 82 elements linked · 15 of 15 modelled activities have elements · 25 not in the model".

Under the film bar are three **steps**. Click one to see its sections; the others are hidden until you click them.

| Step | Sections | What you do there |
| --- | --- | --- |
| **Map** | Values, Assign, Suggest, Coverage | give elements a location, trade and zone (chapter 25) |
| **Link** | Schedule, Configure, Link, Decided links, Not in the model | open the schedule, say what its codes mean, link, decide (chapter 26) |
| **Film** | Style, Save IFC with 4D links, Import / Export | choose the look, save the links, exchange files (chapters 27 and 28) |

Each step shows its state under its name: a check mark when it is done, a count when it needs you (for example "3 ties" or
"2 to decide"), or "not started". The tab opens on **Link** while there is no schedule, and on **Film** once the schedule is
linked. The step you pick is a convenience of your viewer. It is not in share links or saved views.

The steps are in this order because each one feeds the next. You can skip **Map**: the linker can work from storeys and
classes alone, as the sample does.

### Proposed and accepted: people decide, machines propose

Every label and every link has a **status**.

| Status | Meaning | Does it drive the film? |
| --- | --- | --- |
| proposed | a machine (or a rule of thumb) suggests it | no |
| accepted | a person said yes, or a deterministic rule made it | yes |
| rejected | a person said no | no, and it is not suggested again |
| superseded | replaced by a newer accepted record | no (kept as history) |

The viewer, the command line and the agent skill all follow one rule: only accepted records reach the film, the IFC file
or the schedule file. A suggestion from the classifier or from an agent is a good first draft. It is never silently
promoted. This matters because a 4D film is often shown to a client as "the plan". A wrong guess that nobody reviewed
becomes a wrong promise.

## 24.2 What you need

- A model: an IFC file (or the FZK-Haus sample). Elements need stable GlobalIds. The links use them as keys, so a
  re-exported model keeps your work.
- A schedule: a `.xer` file exported from Primavera P6. One file can hold several projects; you pick one.
- For a good result, the schedule should say location and trade somewhere: an activity code type called Level or Trade, a
  user field, or a level in the WBS. Chapter 26 shows how to point at it. If it says nothing, the viewer can still
  propose links from activity names, but expect more review.

## 24.3 Try it: watch the finished example

The viewer ships with a worked example, a small two-storey house with a timber roof and a schedule of 46 activities that
starts on 1 March 2027.

1. Open the **Parameters** tab of the right sidebar and the **Sample Projects** folder.
2. In the **Model** list, choose **FZK-Haus 4D**. The viewer loads the house, then the schedule and its configuration,
   links every element it can, builds the plan and opens the **4D** tab on the **Film** step. The **film bar** sits at the top of
   the tab: **Play**, **Pause**, **Stop**, the date slider, **Record** and **Open as script**. It stays in view when you
   switch steps or scroll. Its status line reads "82 of 82 elements linked · 15 of 15 modelled activities have elements · 25 not
   in the model".
3. Press **Play**. The house builds over about 90 s: first the ground slab, then the walls, the roof frame and roof deck,
   then windows, doors, stair and railings. The date, the week and the percentage complete are drawn on the picture.
4. Drag the date slider in the film bar. It scrubs by schedule date: you see the house as it stands on that day.
5. Scrub to 19 May 2027, the data date. One activity is under way: the rafters.

> Picture (4d-film-midway): the FZK-Haus 4D sample mid-film: half-built walls, the date and week top left, the S-curve top right.

### What the example is built to show

The schedule was written to behave like a real one. Walls start while the slab cures. The roof frame goes up before
the roof deck. The windows wait until the roof keeps the rain out, and a milestone, "Building weathertight", marks that
moment. Some activities, such as earthworks, drainage, plaster, screed drying and services, have no geometry in the model. A real
model never has an element for every line of a schedule. You can mark such an activity **Not modelled**. It then stops
counting as a gap and is listed under **Not in the model** in the Link step. The sample has 25 of them marked, which is why
the film bar says "25 not in the model". While one of them is under way, the film's on-screen display adds a line "Also under
way (not in the model)" with its name, so the picture does not look idle (chapter 27).

## 24.4 How it works

Each stage hands a file or a table to the next. Nothing is hidden inside the film.

- Labels are stored as **assignments**: one record per element, attribute and value.
- Links are stored as **activity links**: an activity, a role (build or remove), the elements, a confidence and the
  reasons.
- The plan is a table of intervals per element: from date, to date, state, and which activity.
- The film is one item on the player's timeline. It reads the plan on every frame. Chapter 27 covers it.

You can keep every stage inside the viewer's 4D tab (chapters 25 to 27), run them from a command line (chapter 32), let an
agent do the labour (chapter 33), or work with the records in a database (chapter 34). They read and write the same
files, so you can mix them.

## 24.5 Limits and gotchas

- One schedule per model at a time in the viewer.
- Activities of type milestone, level of effort and WBS summary never drive geometry. Milestones become captions.
- An element no accepted link names has no timeline. The player shows it ghosted. It is listed in the link report.
- An activity with no elements is a gap until you mark it **Not modelled**. Marking it does not link anything; it only says
  that the model has nothing to link.
- Dates have no time zone. The data date is the date P6 last recalculated the schedule.
- 4D is only as good as the labels. If most elements get no location or trade, linking cannot do much.

## See also

- Chapter 25: giving elements a location, trade and zone (the Map step).
- Chapter 26: linking the schedule and reviewing links (the Link step).
- Chapter 27: playing and recording the film (the Film step). Chapter 21: the player.
