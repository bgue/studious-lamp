# 2. Opening the viewer and a model

You have an IFC file from an architect or an engineer. You want to look at it now, without installing a program, without
sending the file to a server and without waiting for a conversion. Or you have no file yet and want to see what the
viewer does. Or the file is very large and the page seems to hang.

The viewer reads IFC files itself, in your browser. It turns each file into the same internal form it uses for its own
sample models, then draws it. Reading a large file takes seconds to minutes, so the work runs in a background worker, and
a status line tells you which step it is on. If the file cannot be read, one line says so and the model on screen stays.

## 2.1 Start from `xray-viewer.html` or from source

**Try it (single file).**

1. Find `xray-viewer.html` (in the zip it is named like `xray-viewer-v12-20261101-ab12cd3.html`, with a version, a date and
   a short code). Double-click it. Use Chromium, Edge or Chrome.
2. The page opens with a sample model on screen. You see the building, the top bar above it, a tree on the left and a
   tabbed column on the right.
3. Click an element. A duct is a good start. The parts that block your view of it turn faint.
4. Press `X` to switch x-ray off and on. Press `?` to see the list of keys.

**Try it (from source).** You need Node 22 and npm.

1. In a terminal, go to the `web` folder and run `npm install`, then `npm run dev`.
2. Open `http://127.0.0.1:5173/?model=building`.
3. Steps 3 and 4 above are the same.

The part after `?model=` picks the model. The values are `building`, `fzk-haus`, `plumbing`, `process-plant`, `synth5k`,
`debris-demo` and `procedural`. If the value is unknown or its model cannot load, the viewer shows the in-memory
`procedural` model and a red message at the top.

**How it works.** The single file holds the program, the sample models and the IFC reader in one page. It has no
dependencies and makes no network requests. A normal build of the served app cannot be opened by double-click, because
browsers block its scripts when a page comes from `file://`. This is why the single file exists.

**Limits and gotchas.** Selection sets and class styles are kept per model name in your browser's storage. On a page
opened from a file, some browsers do not keep that storage between visits, so stored sets and style edits may be gone the
next time. Firefox and Safari are untested.

## 2.2 Open IFC, IFCZIP, glb by button or drop

**Try it.**

1. Open the **Parameters** tab of the right sidebar. The first folder is **Open model**. (The first button of the tool
   strip on the left of the canvas does the same.)
2. Click **Open IFC or glb file** and choose a file. You may choose several files. Or drag the files onto the page.
3. Watch **Load status**. It counts through the steps and ends with `Loaded <N> elements in <S> s`.
4. The model replaces the one on screen. Its name is `file:` and the first file name, with ` +N more` when you opened
   several.

**Accepted files.** `.ifc`, `.ifczip` (a zipped IFC) and `.glb`. A glb may come with a `.json` file of the same base
name that holds the element data. A `.json` file alone is not accepted. A glb without that `.json` file still opens,
but the viewer has to guess each element's class from its name ("slab", "wall", "beam", "column", "duct", "pipe", "tray"),
and the guess is "Unknown" when none fits.

**Several IFC files at once.** This is how you check a structural, an architectural and an HVAC model together. The viewer
joins them into one model, called *federated*:

- the storeys with the same name and the same height (within 1 cm) become one storey;
- an element that has the same GlobalId, class and bounds as an earlier one is skipped (it is the same part, listed twice);
- an element with the same GlobalId but a different shape is kept and gets the name `<GlobalId>~<n>`.

You cannot mix IFC and glb files in one load, and you cannot load several glb files at once.

**Read a load error.** Wrong input gives one line in **Load status** and in the red segment of the status bar at the
bottom. The model you had stays on screen. The cases are: IFC mixed with glb, several glb files, a lone `.json`, an
unsupported file type, an empty file and a corrupt file. An IFC file that the reader cannot read gives `This IFC file could
not be read: it may be damaged or not an IFC file (<name>)`. Over 100 MB in total, the viewer warns and carries on. **Cancel
load** stops a load that is running and keeps the current model.

**How it works.** A background worker reads the IFC with a library called web-ifc. It builds the shapes of the elements
(the *mesh*), reads the relations between them (which wall has which opening, which duct connects to which), and reads the
properties. Then it merges everything into the arrays the screen draws. Nothing leaves your computer. The reader leaves out
the parts that are not objects you would select: spaces, sites, buildings, storeys as objects, grids, annotations and
openings. (The openings are used. They cut holes in their hosts.) The model is moved so that its centre sits at the origin,
and the up direction is converted to the viewer's own.

**Limits and gotchas.**

- Only what web-ifc can build is shown. Some complex shapes (`IfcAdvancedBrep`, B-spline, unusual boolean or swept
  shapes) and IFC4X3 alignment geometry are silently missing. An opening that cannot be cut leaves the host solid.
- IFC2X3 and IFC4 are well tested. IFC4X3 beyond the sample files is untested.
- Colours may differ from other programs: the viewer uses the surface colour in the file, and falls back to a colour per
  class when the file has none.
- The properties it reads are the element's own property sets, at most 24 per element. Type properties are not read.

## 2.3 Sample Projects

**Try it.**

1. In the **Parameters** tab, open the **Sample Projects** folder, right under **Open model**.
2. Open the **Model** list and choose **FZK-Haus**. Wait until the loading message goes.
3. The model on screen is replaced by a small house. Choose **Building (Simple-Scene)** to get a building with
   HVAC ducts.

The list holds the models that ship with the viewer, with readable names.

- **Building (Simple-Scene)**: structural, architectural and HVAC models of one building, federated. Use it for ducts
  behind slabs (chapter 4).
- **FZK-Haus**: a small house exported from ArchiCAD, with windows and a roof. Use it for cutting (chapter 5).
- **Plumbing**: a plumbing model.
- **Process plant**: a synthetic process unit with pipes.
- **Synthetic 5k**: a generated building with 5,000 elements and 7 storeys. It is the benchmark model.
- **Debris demo**: a generated building with 400 elements and deliberate rubbish, used in chapter 9.
- **Procedural**: a small model built in memory. It is the fallback when nothing else loads.
- **FZK-Haus 4D**: FZK-Haus with a construction schedule, for chapters 24 to 28.

Models you opened from files follow the samples in the list, for this visit only.

**Limits and gotchas.** The single file carries Building, FZK-Haus, Plumbing, Debris demo and Process plant. It does not
carry Synthetic 5k. Its entry reads "needs the served app or the zip", and choosing it leaves the current model in place.
The sample names are also the keys under which sets, presets, views and share links are stored, so they never change.

## 2.4 Large models

A file with 100,000 elements and 90 MB used to freeze the page. Now the heavy work runs in the background, and the page
stays usable. It still takes time: the example in the documentation is `Loaded 100000 elements in 23.4 s`. Two options
make it faster.

| Option (folder **Open model**) | Values | What it does |
| --- | --- | --- |
| `edges` | `auto` (default), `all`, `none` | The outline lines of the model. `auto` skips them above 50,000 elements, because they are the largest extra buffer and slow to draw. `none` never builds them. `all` always does. |
| `properties` | `common` (default), `none` | `none` skips reading properties: a faster, smaller load. Hover cards and the Properties tab then show no property sets. |

Set the options before you open the file. They apply to the next IFC file only, and are not stored.

**Try it.** Set `properties` to `none` and `edges` to `none`. Open your large file. Read **Load status**. It walks through
the steps: `Reading`, `Opening`, `Meshing 4800 of 100000`, `Reading relations`, `Merging`, `Edges` (or `Edges skipped
(auto: over 50,000 elements)`), `BVH` (the structure that makes picking and sightlines fast), `Transferring geometry`,
`Uploading`, and last `Loaded N elements in S s`. **Model stats** then shows elements, triangles, memory in megabytes and
load seconds. The **Large model** tool in the tool strip shows the same numbers with the time of each step.

**Limits and gotchas.**

- Memory is about 25 times the file size at 40 MB. Files of tens of megabytes are practical. A few hundred megabytes are
  not. There is no streaming and no level of detail.
- Reading properties is the slowest step in the browser. `properties: none` removes it.
- Edges are all or nothing. If the model skipped them, no element has outlines.
- After the load, the model tree and the class styles need about 1 s more at 100,000 elements.
- Cancel load stops the worker at once.

## See also

- Chapter 3: the screen and moving around.
- Chapter 9: cleaning a messy model (the Debris demo).
- Appendix H: troubleshooting load errors.
