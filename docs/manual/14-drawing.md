# 14. Drawing on a view

## 14.0 The problem

A view shows the right moment. But "the right moment" can still hide the point. The wall in the picture is one of nine. The duct
is one of forty. People on a site call, point at their screens and say "that one, there". You need to do the same thing in a file.

On paper you would circle the spot with a red pen. You do the same here. A **drawing** is a cloud, arrow, text box, callout,
shape or pen line on a view. A view that carries at least one drawing is a *view with drawings*. It is still one view, listed once,
in the Views tab.

## 14.1 Tools: view-locked or attached to the model

**The idea.** Draw a red circle on a photograph of a building. Now walk around the building. The circle stays on the photograph,
so from a new angle it points at the wrong thing. A drawing on a 3D model has the same problem. A drawing can solve it in
one of two ways, and the viewer picks one for each drawing.

- **Attached** to the model. The viewer works out what the drawing sits on (a surface, some elements, a box of space, a
  measurement) and keeps the drawing there. Orbit, and it stays on the wall.
- **View-locked**. The drawing belongs to the picture, not the model. It is exact from the camera of the view and fades as you
  orbit away. A small pin stays behind on the spot. Click the pin and the camera flies back to the view.

**Try it.** Use the **FZK-Haus** sample.

1. Open **FZK-Haus**. Orbit until you face the front, with the roof in view.
2. In the left sidebar, open the **Views** tab (or press `K`, which opens it on **With drawings**).
3. Click **Draw on this view**. Nothing is selected in the list, so the viewer saves the current state as a view first (for
   example `View 1`). A small toolbar floats at the bottom centre of the model area.
4. Hover over the first icons to read their names. Click **Cloud**, then drag a rectangle round a window. You get a red
   outline with scalloped edges.
5. Click **Arrow**, then drag from empty space to the door. A red arrow with a head appears.
6. Click **Callout**. A text box shows in the toolbar: type `Check the lintel`. Click the wall. A text box with a leader line
   appears at the wall.
7. Click **Select**, then drag the cloud a little. The drawing moves with the drag.
8. Orbit by dragging with the right mouse button, which still orbits while a tool is active. The cloud stays on the window.
   The arrow, if it landed on nothing, is view-locked: it fades as you leave the view and leaves a pin.
9. Press `Ctrl+Z` to undo the last change, `Ctrl+Shift+Z` to redo. Click **Done**. The toolbar goes away.

The view appears under **With drawings** with `✎ 3`. Click its row: the view is restored and its detail opens in place of the
list. `‹ Views` goes back.

> Picture: the drawing toolbar over FZK-Haus with a cloud on a window, an arrow, and a callout reading "Check the lintel".

**The tools.**

| Group | Tool | How |
| --- | --- | --- |
| Select | Select | Click selects. Drag moves a shape or a text box |
| Cloud | Cloud | Drag a rectangle. Edges are scalloped |
| Cloud | Cloud draw | Draw a closed outline. It is simplified, then scalloped |
| Annotate | Callout | Click an element. A text box with a leader line, which follows the element |
| Annotate | Text | Click the model. A plain text box at that point |
| Annotate | Pointer | Click an element. An arrow pointing at it, with optional text |
| Highlight | Marker | A wide translucent stroke, yellow by default |
| Highlight | Highlight box | Drag a translucent box |
| Shapes | Rectangle, Ellipse, Line, Arrow | Drag |
| Shapes | Polyline, Polygon | Click each corner. Double click, `Enter` or **Finish** ends it. A click on the first corner closes a polygon |
| Shapes | Pen | Draw a freehand line |

There is also **Link a measurement...** in the view detail. It lists the measure tool's measurements (chapter 10) and
copies one into a drawing with its own dimension line and length.

**Colours and weights.** Five colours: red (the default for clouds and shapes), yellow (the default for highlights), blue,
green and black. Each tool remembers its colour. Line weights run from 1 to 4. **Fill** fills closed shapes. A selected
drawing takes colour, weight and fill changes.

**Keys while you draw.** `Ctrl+Z` and `Ctrl+Shift+Z` undo and redo (100 steps per view). `Delete` removes the selected drawing.
`Escape` cancels the drawing in progress, then returns to **Select**, then deselects. While a tool is active the left button
draws. The middle and right buttons still orbit and pan. Touch and pen draw too. The global undo of chapter 3 stands aside
while you draw.

**Edit later.** For a view that has drawings the row menu says **Edit drawings** in place of **Draw on this view**. In an
issue's detail, **Edit drawings** applies the view and opens the toolbar.

## 14.2 Attached drawings: why a cloud on a wall stays on the wall

**What happens when you finish a shape.** The viewer shoots a ray from the camera through points along your stroke. It looks at
what the rays hit and chooses an attachment:

| Attached to | Meaning |
| --- | --- |
| `surface` | The outline lies on one to five elements. The points are projected onto their surfaces |
| `elements` | A list of elements. They get a selection tint while the drawing is selected |
| `region` | A box of space fitted to what lies inside a closed outline. It shows as a box with scalloped edges, right from any angle |
| `measurement` | A measurement link |
| `penetration` | The pair of a pipe and the wall it crosses (chapter 11) |
| `point` | A point in empty space (text boxes) |
| none | View-locked |

You can read the choice as a chip on the selected drawing: `Attached to: 2 pipes · change` or `View-locked · change`. Click
**change** to pick another: **Elements (current selection)**, **Surface**, **Region**, **Measurement (pick)**, **Penetration
(pick)** or **View-locked**. A change is one undo step.

The chip also explains the rule of thumb. Lines that follow a surface (arrows, lines, pen strokes, polylines) become `surface`
when at least 70 % of their points land on at most 5 elements. A closed shape over many elements becomes a `region`. Anything
unclear stays view-locked.

**After an orbit.** An attached drawing is always drawn at its target and never fades. If its target is hidden or isolated away,
it is drawn dim with a `target hidden` hint, so it does not float in space. A view-locked drawing is at full strength while
the view direction is within 10 degrees and the eye within 20 % of the scene scale. It fades to nothing at 25 degrees or
50 %, and a pin remains. The setting **View-locked drawings in 3D** (Parameters tab, folder **Drawings**) chooses how they show:
`near view + pin` (the default), `pin only` or `hidden`.

**After a revision.** A drawing remembers which element it sits on and where, relative to that element. If a new revision moves
the element, the drawing moves with it. If the element is reshaped (a longer wall), the viewer projects the outline onto the
reshaped surface again. If it cannot land (more than 30 % of the points miss, the element is gone, or it moved more than
3 m or 1.5 times its own size), the drawing is **detached**. A detached drawing is drawn view-locked and flagged in the
panel. It never floats, and it is never moved silently. The model is a revision, so the issue may already be designed
out. Chapter 20 shows how to walk a revision.

**Plan and Section.** Only tied drawings (any attachment except none) enable the **3D · Plan · Section** switch of 13.3.

## 14.3 Export a view with its drawings as PDF or JSON

Open the view's detail (click its row). It has **Page size** (A4 or Letter, landscape), **Picture quality**, **Export PDF**
and **Export JSON**.

**PDF.** Page 1 shows the view without drawings, with the author, date, counts and a block "How to get back to this view": three
steps, plus a clickable link when the page is served over http or https. Page 2 shows the same picture with the drawings burned
in and numbered. Pages 3 and up hold the table of drawings. **Picture quality** is `screen`, `150`, `200` (default) or `300` dpi.
The picture is rendered off screen with the viewer's own x-ray look. The PDF also carries the JSON inside it as an attached
file, so one PDF is the whole view.

**JSON.** The same data as a file you can drop back on the viewer.

**Getting back.** Open the same model, then drop the PDF or the JSON on the page, or use **Open file** in the lower part of the
Views tab. The camera, section, hides, colours, selection and preset return, and the drawings come with them. The status line
says how many views and drawings opened. If the file names elements the model lacks, the drawings stay at their stored 3D points
and the view skips those elements. A file made on a different model is kept under **Other models (n)**, hidden, with **Open**,
**Move to this model** and **Delete view**.

**What is in the files.** The PDF and JSON carry author names, because you export them on purpose. They carry no secrets or
settings of other tools. Share links never carry drawings or names (13.4).

## 14.4 Where drawings are kept

Drawings are saved in this browser (in IndexedDB, one record per model) and come back when the same model loads. A view made on
one model is never restored on another. Saves follow changes after a short quiet moment (800 ms). Without IndexedDB (a private
window) nothing is kept, and the session works as before.

**Clear all drawings and issues for this model** (at the bottom of the Issues tab and of the drawings part of the Views tab)
removes them from the session and from the saved copy. It takes two clicks, and the second names the counts. Views of other
models and PDF sheet views stay.

Drawings never go into a share link, a preset or a packed page.

## 14.5 Limits and gotchas

- A drawing has no status and no comment thread. Those belong to an issue (chapter 15).
- A shape drawn from a camera far from the view's camera is mapped onto a plane, so from the side it looks skewed. Attach it
  (**change**) if that matters.
- **Update view** captures the view again from the current camera. Shapes stay `on the model` (default) or `on the screen`, which
  makes them view-locked. Choose before you click.
- The two-finger pinch is not used by the drawing tools.
- The drawings of a view are not drawn while a fly-through plays (chapter 22). Only the camera and the look play.
- Old files: drawing sets from before the two-noun change open as before. Comments and a status that an old set carried are not
  on a view any more. See 15.5.

## 14.6 See also

Chapter 13 (what a view is), chapter 15 (turn a view into an issue), chapter 16 (drawing on a PDF page).
