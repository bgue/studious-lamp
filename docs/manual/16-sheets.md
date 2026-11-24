# 16. PDF sheets: the drawings you already have

## 16.0 The problem

Most projects still run on PDF drawing sets: plans, sections, details with title blocks. The architect marks the plan with a
red cloud. The engineer marks the same plan in another colour. The 3D model knows none of this. People then flip between a PDF
reader and the viewer and try to match the two by eye.

## 16.1 Open a drawing set: pages are views you can draw on

**The idea.** Open a PDF and it becomes a **sheet set**: one **sheet** for each page. A sheet is a page of a PDF drawing set,
shown as a view you can draw on. It behaves like any other view of this part of the manual. It can carry drawings (the same
tools as chapter 14), it can be put in an issue (chapter 15), and it is listed in the Views tab. One difference: a sheet view
has no 3D camera to restore. When you click it, a flat page opens over the model area.

All sheets live behind one chip of the Views tab, **On sheets**.

**Try it.** The repository holds two sample PDFs for this. `sample-sheet.pdf` has 2 pages, with walls, a title block and three
annotations that someone else made. Any PDF drawing works as well.

The sample PDFs are not in the **Sample Projects** menu. They come with the source: `web/public/samples/sample-sheet.pdf` and
`geo-sheet.pdf` in the source zip or the repository. When you run the viewer from source, they are also served at
`/samples/sample-sheet.pdf`, so you can download one from your own viewer's address and open it.

1. Open **FZK-Haus** so that a model is loaded. The model stays loaded under the sheet.
2. In the left sidebar, open the **Views** tab and click the chip **On sheets**. The list is replaced by the sheets pane.
3. Click **Open PDF** and choose `sample-sheet.pdf`. (You can also drop a `.pdf` on the page, or use the action
   **Sheets: open a PDF** from the command palette.) The PDF appears with its 2 pages as thumbnails.
4. Click page 1. A 2D view covers the model area, between the top bar and the status bar. At top left is **Back to model**. The
   bar also has page arrows, **Fit**, a list of views on this sheet, **Draw** and **Make issue**.
5. Pan by dragging the empty page. Zoom with the wheel (about the cursor), the `+` and `-` keys, the buttons, or a two-finger
   pinch. `0` fits the page. About a quarter of a second after you stop zooming, the page draws again sharp at that zoom.
6. The three annotations that were already in the PDF show as one read-only view called **Imported annotations**. Select a
   shape: you see its author and its text. A read-only view refuses edits.
7. Click **Copy to editable drawings** on that view. You get an editable copy, and the original stays read-only.
8. Click **Draw**. The same floating toolbar as in 3D appears (without the 3D-only **Pointer**). Click **Cloud** and drag a
   rectangle on the plan. Click **Done**.
9. Click **Back to model**. The model returns as you left it.

> Picture: a sample sheet open over FZK-Haus with a cloud on the plan, and the bar above it showing Back to model, Fit and Draw.

**How it works.** The first time you open a PDF, the viewer loads two libraries, one to read and draw pages and one to write
PDFs. Nothing leaves your computer. In the single file build the libraries are embedded and unpacked on first use. A PDF
that is protected with a password is refused with a message. Opening the same file twice finds the first copy.

**Drawings on a page** are stored as points of the PDF page, so they stay put when you pan or zoom. Line widths, text and badges
scale with the sheet size, so an A1 sheet gets thicker lines than an A4 sheet, and one line weight looks right on both.
Text and callout take the text you typed in the toolbar, then a click on the page.

**Make an issue from a sheet.** Click **Make issue** in the bar, or on the view in **On sheets**. The issue points at the view as
usual. Because a sheet has no camera, the issue's picture is a snapshot of the part of the page your drawings cover, with a
margin of at least a quarter of the page. The issue also keeps a reference to the PDF. When you export BCF (chapter 17), the PDF
travels inside the file. Once a view has an issue, the button reads **Open issue**.

## 16.2 Place a sheet in the model; overlay model and sheet

**The problem.** A plan on a page is flat and floats beside the model. You want to see the plan lie on the floor of the model,
and you want your cloud on the plan to point at the real wall below it.

**The idea.** A sheet is *placed* when you tell the viewer where it lies in the model. You show two matching points: one on the
sheet and the same one in the model, then a second pair. Two pairs fix position, rotation and scale. A third pair adds a check on
the fit. After that, the sheet knows where it is.

The sheets pane says it per sheet: `Not placed`, `Placed (manual, 2 points)`, `Placed (manual, ±N mm)` (three or more points),
`Placed (manual, scale 1:100)` or `Placed (geo)`. Each sheet has the actions **Place in model…** (**Place again…** once placed),
**Show in 3D**, **Model overlay** and **Remove placement**.

**Steps (any plan sheet and a model that match).**

1. In the sheets pane, click **Place in model…**. The placement view opens: the sheet on the left, the plan of one storey on
   the right. Choose the storey in the list (lowest first). On a phone the two sides show one after the other.
2. Click point A on the sheet, then the same point in the model. The model clicks snap to the corners of the cut outlines, then
   to their edges (12 px).
3. Click point B on the sheet, then in the model.
4. The fit shows at once as the model overlay on the sheet. For a better fit, click **Add point** (up to 8 points). The viewer
   fits them by least squares and shows the misfit in millimetres.
5. Alternatively click **Use drawing scale**: type the scale (the 100 of 1:100), pick one pair of points, and give the rotation in
   degrees, counter-clockwise (0 when the drawing and the model share north).
6. Click **Accept** to keep it, **Redo** to start the points again, or **Cancel**. **Undo point** removes the last pick.

If drawings on that sheet would move away from the elements they are attached to, **Accept** first asks: **Place anyway** or
**Keep editing**. Nothing changes until you decide.

**Model overlay.** Click **Model overlay**, in the sheet view or on the sheet. The viewer draws the model's plan cut as thin
outlines over the PDF, lined up through the placement. The cut is the plane 1.2 m above the storey, as in a Plan view (13.3). A slider
sets the opacity. With three or more points you also see `Misfit ±N mm`. If the walls on the outline match the walls on the
paper, the fit is right.

**Show in 3D.** Puts the placed sheet in the 3D view as a flat picture 3 cm above its floor. A slider in the sheets pane sets its
opacity. Picks, measurements and classification ignore it, and the section planes cut it.

**Attachments through a sheet.** When you draw on a placed plan sheet, the viewer decides what the drawing is attached to from
what the plan cut shows beneath it: an element under a text, the elements inside a closed outline, a line along up to 5
elements, or otherwise a box of space (a `region`) from the floor to the next storey. **Make issue** on such a view adds a
real 3D view to the issue, framing those elements, next to the sheet snapshot. The view then has the **3D · Plan · Section**
switch (13.3).

**Geo-referenced PDFs.** Some PDFs carry real-world coordinates. If the PDF's coordinate system is projected, and it is the same
as the one in the model (read from its IFC map conversion), the viewer places the sheet by itself and marks it `Placed (geo)`, at
the storey whose name the sheet mentions, or the lowest. Otherwise it places nothing and says why, with the **Place in model…**
button next to the reason. Examples of its messages: "The PDF is in EPSG:25832 and the model in EPSG:31467", "lat/long without a
projection this viewer can apply", "the model has no IfcMapConversion". It never guesses.

## 16.3 Export a marked-up PDF; import existing annotations

**Export.** In the sheets pane, **Export marked-up PDF** (once for each PDF) writes a copy of the original in which your drawings
are real PDF annotations. The page itself is not touched. They sit on a layer named `X-ray markups`, so you can switch the layer
off in Acrobat or Bluebeam. Each annotation carries its colour, width, text and a date.

Clouds export as cloud-style polygons, rectangles as squares, ellipses as circles, arrows and lines as lines (with an arrowhead
for an arrow), pen strokes and markers as ink, and text and callouts as free text. Exporting again *replaces* the earlier ones
rather than doubling them. If you delete the last drawing of a page and export again, the page is clean.

The author field says "X-ray" unless you typed a name in that view. It is never a stray reviewer name.

**Import.** When a PDF opens, its annotations are read in.

- The ones the viewer wrote earlier come back as editable views, one for each view they came from, with their titles. So a
  file you export and open again round-trips.
- Annotations from other tools (square, circle, line, polyline, polygon, ink, free text, highlight, text note, strike-out)
  become one read-only view for each page, called **Imported annotations**. They are drawn with their colour and shape. Fills
  and custom appearances of foreign annotations are not reproduced. **Copy to editable drawings** makes an editable copy.
- Links, widgets, form fields, popups and hidden annotations are ignored.

## 16.4 Where a sheet is kept

The PDF bytes are saved in this browser (IndexedDB, in a store of their own, one record per file, found again by a checksum).
The views you drew on it are saved with it. After a reload the sheets and views are back. The PDF bytes, and the placement, are never
in a share link, a saved view, a preset or the URL. Without IndexedDB (a private window) the store lives in memory and says so.

## 16.5 Limits and gotchas

- Placement works for **plan** sheets only. Elevation and section sheets cannot be placed yet, and nothing attaches through them.
- One sheet, one level. A sheet showing several storeys is not handled.
- A geo-referenced PDF in a coordinate system other than the model's is not converted. Degrees are projected only for UTM codes
  the viewer knows. Other systems, such as Gauss-Krüger, are placed by hand.
- Export was checked with PDF libraries and a PDF reader. It was not opened in Acrobat or Bluebeam.
- Text in exported free text is drawn in Helvetica. Other characters become `?` in the picture of the annotation, but the text
  itself stays in the annotation. On a rotated page the text box does not rotate with the page.
- The whole file is rewritten on export. Encrypted PDFs are not supported.
- Some fonts that are not embedded, and some image types, may not draw.
- A placement belongs to the model it was made on. The sheet is hidden with the sheets of other models.
- Older files: PDFs that carry drawing data from the earlier drawing tool still restore it when opened. Any other PDF is a
  sheet set.

## 16.6 See also

Chapter 14 (the drawing tools), chapter 15 (issues, and the PDF report), chapter 17 (the PDF inside a BCF file).
