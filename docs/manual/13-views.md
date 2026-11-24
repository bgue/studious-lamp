# 13. Views

## 13.1 Why views

A model has 80,000 elements. Your colleague has a question about one wall behind one duct. You can write "level 2, grid C, behind the
supply duct, with the ceiling cut away". Then you hope they find it. Or you can send the exact moment: the camera, what is
hidden, what is cut, what is selected. A sentence about a model is long and vague. A picture of the right moment is short and exact.

The viewer keeps these moments as **views**. A view is a captured moment: the camera, what is shown, hidden, cut and selected,
and the look of the model at that time. A view may also carry **drawings** (chapter 14). A page of a PDF drawing set is a view
too (chapter 16).

There are only two nouns in this part of the manual. A view is a moment. An **issue** is a problem someone must act on, and it
points at one or more views (chapter 15). If you want to say "look at this", make a view. If you want to say "someone must fix
this", make an issue from a view.

Every view of the loaded model lives in one place: the **Views** tab in the left sidebar, next to **Model** and **Sets**. The
**Issues** tab holds issues and nothing else.

## 13.2 Save, name, reorder, restore, and what a view stores

**The idea.** Think of a view as a bookmark with a memory. A browser bookmark remembers a page. A view remembers a page of the
model *and* how you were looking at it. When you open it, the viewer puts everything back, so your colleague sees what you saw.

A view is one rung of a ladder. The ladder has five rungs. Each stores more than the one before, except the last, which is a
view in a shorter form.

| Rung | What it stores | Camera? | Where you meet it |
| --- | --- | --- | --- |
| Mode | A one-click look: one of Solid, Ghost, Radiograph, Glow, Cutaway | No | Top bar (chapter 4) |
| Preset | A saved look: settings only | No | Parameters tab, keys `1`-`9` (chapter 4) |
| View | Camera, section, selection, hides, isolate, exploded storeys and the look. May carry drawings | Yes | Views tab |
| Keyframe | A copy of a view's state, plus travel time, hold, ease and a caption | Yes | Fly-through section of the Views tab (chapter 22) |
| Share link | One view as a web address. No drawings, no picture | Yes | **Copy link** in the view menu |

Read the table from the top. A mode changes the look. A preset is a look you named. A view adds *where you stand* and *what you
picked*. A keyframe is a view with a time on it. A share link is a view that fits in a message.

**Try it.** Use the **FZK-Haus** sample.

1. Open the **Sample Projects** folder in the Parameters tab and choose **FZK-Haus**. The house appears.
2. Click a window to select it. Orbit to look at it from outside, a little from above.
3. In the left sidebar, open the **Views** tab. At the top is a box with the hint **View name (optional)** and a button **Save view**.
4. Type `Window from outside` and press `Enter` (or click **Save view**). A row appears in the list: a drag grip, the number 1, the
   name, and a one-line summary of what the view holds, such as `x-ray · 1 selected`. Hover over the row to see a thumbnail next
   to the sidebar.
5. Orbit away. Hide a wall with the model tree. Select something else.
6. Click the row `Window from outside`. The camera turns back over about 0.4 s, the hidden wall returns, and the window is
   selected again. The row is marked as the last view you restored.
7. Click **Save view** with the name box empty. You get `View 2`. A name that is already taken gets a number added.
8. Rename a view: click the **⋯** at the end of its row and choose **Rename**, or focus the row and press `F2`.
9. Reorder: drag the grip of a row up or down, or focus a row and press `Alt+ArrowUp` or `Alt+ArrowDown`. The numbers follow
   the list order.

The key `Ctrl+Shift+S` does the same as **Save view** from anywhere. `Shift+PageUp` and `Shift+PageDown` step to the previous and
next view. (`PageUp` and `PageDown` alone still move the storey up and down.)

> Picture: the Views tab with three views, the chips All / With drawings / On sheets / In an issue above the list, and the
> thumbnail showing next to the hovered row.

**The row menu (⋯).** The menu has **Update from current**, **Draw on this view** (**Edit drawings** once the view has
drawings), **Make issue** (**Open issue** if the view is already in one), **Details**, **Rename**, **Duplicate**, **Copy
link** and **Delete**. **Update from current** keeps the name and replaces the camera and state with what you see now. It is
one undo step. **Duplicate** makes a plain copy without drawings. **Delete** asks for a second click.

**Filters.** Four chips sit above the list:

- **All**: every view of the loaded model.
- **With drawings**: views that have at least one drawing. The key `K` opens the Views tab on this chip.
- **On sheets**: PDF pages. This chip swaps the list for the sheets pane (chapter 16).
- **In an issue**: views an issue points at, with or without drawings.

The box **Filter views** matches the name, the note and the title of the issue the view is in. A row shows `✎ 3` when the
view has 3 drawings, `Sheet` for a PDF page and `Issue` when an issue points at it.

**Play.** The **▶ Play** button steps through the views in list order and loops. The list beside it sets the time on each view:
2, 4, 6 or 10 s. `Escape` or a press on the canvas stops it. This is a slideshow. For a smooth camera path with holds and
captions, build a fly-through (chapter 22).

**What exactly a view stores.** The camera (position, target, roll, field of view, and whether it is the pseudo-orthographic
projection of the `P` key). The section box and plane. The selection. Hidden elements, pins and isolate. Whether the storeys are
exploded. The x-ray, mode, imaging, sightline, display and cinematic settings. The active preset (as a mark, so the preset panel
shows it as active). A small thumbnail.

A view does *not* store your measurements, class styles, sets, keyboard bindings, classification results or other tools'
own data. It names elements by GlobalId, so it survives a reload or a re-conversion of the model. If the loaded model lacks some
of the elements, the status bar says so (for example `View "Roof": 3 elements not in this model`), and the rest still applies.

## 13.3 Plan and Section of a view

**The problem.** You drew a cloud on a duct in a perspective view. Your colleague asks: "Where is that, in plan?" Without a
plan you walk them through the storeys.

**The idea.** When a view's drawings are tied to something real in the model (a wall, a pipe, a region, a measurement), the
viewer can work out a plan and a section of that thing on demand. Nothing is stored for them. They are worked out from the
drawings each time.

A view with tied drawings shows a three-way switch: **3D · Plan · Section**. You find it in the view detail, in the issue detail
(under each view) and in the drawing toolbar. A view with only view-locked drawings, or none, has no switch. Chapter 14 explains
tied and view-locked.

- **3D** is the view's own camera. It also puts back the section you had before.
- **Plan** is an orthographic camera looking straight down, north up, with one horizontal cut 1.2 m above the storey. A target
  that lies wholly above the cut (ceiling pipes) is cut 0.3 m above its top. A short target of up to 1.5 m that the cut would
  slice through is cut 0.05 m above its top, so it shows whole. Taller targets (walls, columns) are cut at 1.2 m, like a plan drawing.
- **Section** is an orthographic vertical cut through the middle of the target. It looks into a wall face, or along a long
  element from the side the view was made on.

**Try it.** First make a drawing (steps in 14.1), then in the view detail click **Plan**. The camera goes overhead and the model is
cut. Click **Section** for the vertical cut. Click **3D** to return. If you moved the section tool in between, your change stays.

How it works: the switch uses the viewer's pseudo-orthographic projection (a 2 degree field of view with the camera moved back)
and the same cut planes as the section tool (chapter 5). Your own section is remembered when you leave 3D and put back when you
return. The switch is one camera move on the undo stack, but the cut planes are not.

When you export an issue as BCF, the Plan and the Section of each tied view are written as two more viewpoints in the file, so
other tools can show them (chapter 17).

## 13.4 Export, import and share a view

**Export and Import.** At the top of the Views tab, **Export** downloads a file named `xray-views-<model>-<date>.json` with all
saved views of this model, thumbnails included. **Import** adds the views of such a file. A view with an id that is already in
the list replaces it only when it is newer. Other views are added with a unique name. The file holds the *link* to a view's
drawings (an id), not the drawings. To move drawings, export the view's PDF or JSON from its detail (14.3).

**Copy link.** In the row menu, **Copy link** puts a web address on the clipboard. It looks like `?model=<name>#view=...`.
Whoever opens it, with the same model, gets the camera and look applied once, with no animation, and the link is removed from
the address bar. The view is not saved until they click **Save view**. A link made for another model says so in the status
bar.

What a share link carries: the name, the camera (rounded to 0.1 mm), the selection and hides, and the settings that differ
from the receiver's factory state. Typical length: 300 to 900 characters. What it never carries: drawings, thumbnails, and
reviewer names. A person's name only ever appears in files you export on purpose (an issue's comments, a drawing PDF).

**Packed pages.** A packed page (chapter 30) can carry views and open one first. The views also travel in the *Export
parameters* file, which includes the list without thumbnails.

## 13.5 Choices and settings

- **Grid toggle** (the button next to **Export**): one line per view, or a grid of thumbnails, which suits a phone. The viewer
  remembers your choice.
- **Smooth moves** (a setting): with it off, a restore jumps instead of turning. The system's reduced-motion request does the
  same.
- The dwell time of **Play** (2, 4, 6 or 10 s), which the viewer remembers.

## 13.6 Limits and gotchas

- Views are kept per browser and per model name. The same model opened under another file name has its own list. Use
  **Export** and **Import** to move views.
- The exploded state is a flag. The viewer explodes again for the restored selection with your current explode settings, so it
  matches only if those did not change.
- The thumbnail is taken at save time, with whatever the ghost animation shows at that frame. A view imported without
  thumbnails shows "no picture" until you click **Update from current**.
- A share link carries the settings as differences from the receiver's factory state. A page with a different configuration file
  or different plugins can look slightly different.
- During an AR or VR session, views are not saved, updated or restored. Leave the session first.
- Opening an older file: views saved before the two-noun change still load. Old drawing sets that no view claims are listed
  as views of their own, with their own camera and picture. Nothing is converted until you act on one. Such a view has no number,
  no reorder grip and no **Duplicate**.

## 13.7 See also

Chapter 14 (drawing on a view), chapter 15 (making an issue from a view), chapter 22 (fly-throughs built from views),
chapter 29 (what a share link carries).
