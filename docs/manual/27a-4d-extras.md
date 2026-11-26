# 27A. Temporary works and the storyboard PDF

Two extras of the 4D film. The film shows the building. A site meeting also asks where the scaffold is, and a report wants paper.

## 27A.1 Temporary works: scaffold, falsework, formwork

### The idea

A building does not rise out of thin air. Before a masonry wall goes up, scaffold goes up beside it. Before a slab is poured, props and
formwork go under it. A film without them looks like parts appearing from nowhere, and a client sees no reason for the gaps. The film can
build **temporary works** from rules you write once: **scaffold** along walls, **falsework** (props) under slabs and beams, and **formwork**
(panels) on concrete. They go up before the work they serve, stand while it is built, and come down after it.

### Try it

1. Open **FZK-Haus 4D**. In the **Film** step, open **Temporary works**. The sample has rules for scaffold on the external walls, props under the
   first-floor slab and formwork on the ground slab, the downstand beam and the first-floor slab.
2. Press **Play**. Watch the external walls: yellow scaffold stands two days before the masonry and comes down during the facade work.
   Props (blue) and formwork (brown) appear under the slabs.
3. Switch **Show in the film** off. The film plays without them. The rules stay.
4. Click **Add rule**. Choose kind `formwork`, a query such as `class = 'IfcBeam'`, erect `1` day before, strike `3` days after. Play again.

> Picture (temp-works-fzk): the FZK-Haus mid-film with yellow scaffold along an outer wall and blue props under a slab.

### How it works

A rule has a **kind**, a query for the permanent elements it serves, an **erect** time and a **strike** time. Times are either "during an
activity" or "N days before the work starts / N days after it ends", with defaults (scaffold up 1 day before and down 1 day after, falsework
down 14 days after for curing, formwork down 3 days after). The query is the one of chapter 8. Elements that have no work of their own in the plan
are not served.

The viewer groups the served elements by storey and by the activity that builds them, so there is one scaffold per floor and one set of props
per slab. Pieces are simple boxes: standards, ledgers, boards and guard rails for scaffold; props on a grid with head beams for falsework; panels
for formwork. They appear in build order (scaffold bottom up, striking top down), follow the explode offset of their storey, and cannot be picked,
so they never block a click on the building. The director treats them as context. A scaffold that goes up near a caption adds "Scaffold up on
Erdgeschoss" to it.

### Choices and settings

- **Show in the film** is their own layer switch. The rules are saved in the 4D configuration (`temporaryWorks`) and travel in `Export .4d.json`.
- `xray-4d plan` reads the rules. `--no-temporary-works` leaves them out. `render` and `pack` show whatever the plan carries (32.2).

### Limits and gotchas

- They are not IFC elements. Nothing is added to the IFC, the link report or the schedule, and they have no activities of their own.
- The geometry comes from bounding boxes. A diagonal wall gets a box-shaped scaffold, and corners are not merged.
- Falsework and formwork do not check clashes with each other. Props avoid walls only.
- Times use calendar days, not working days.
- Nothing is drawn outside the film.

## 27A.2 Storyboard PDF: stills for a report

### The idea

A video does not go on a wall or into a progress report. A **storyboard** is a PDF of still frames of the film at chosen dates. Each frame has
its date, week number and the work going on, and the colour legend is repeated on every page.

### Try it

1. On **FZK-Haus 4D**, press **Storyboard PDF** in the film bar.
2. Wait while the viewer plays the film's own camera and takes one frame for each date. It draws frames at 960 x 540 pixels as JPEG.
3. The PDF downloads. It starts at the first work in the model, not at the start of the schedule, so you do not get empty-site frames. Open it:
   about 20 weekly frames on 4 A4 landscape pages, 3 across.


> Picture (storyboard-page): one A4 page of the FZK-Haus storyboard with three frames, their captions and the legend at the foot.

### How it works

Each caption lists the date and `Week n`, then the top three running activities (most elements first) and `+N more`. A frame with no activity
says `Complete` at the end or `No work in the model`. The title block names the project, the data date, the date it was made and the page. The
last day of the window is always the last frame. Frames carry no on-screen display, because the date and legend are on the page. The text is Helvetica, so
characters outside Latin-1 print as `?`.

### Choices and settings

From the command line (32.2) you choose the spacing and page: `--every week|month|milestone|N`, `--page A4|A3`, `--cols 1..8`, `--script`
for the camera, `--size`. The viewer uses a frame every week on A4, 3 across.

### Limits and gotchas

- At most 200 frames.
- Without a script, the camera stays where the model opens. Use a script or a director film for a better view.

## See also

- Chapter 27: style, the director and recording. Chapter 8: the query in a rule's `for`. Chapter 28: the `.4d.json` that holds the rules. Chapter 32: `xray-4d storyboard`.
