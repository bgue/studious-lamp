# 19. Parameters, properties and saving

You tuned the look for an hour, classified 3,000 elements and reviewed half of them. Then you close the tab. What is still there
tomorrow? What can you hand to a colleague, and what goes into the IFC file that the next person opens in another program?
Without a clear answer, people either lose work or send things they did not mean to send.

## 19.1 Export and import parameters

### The idea

The viewer has hundreds of settings: ghosting, sightlines, display, imaging, classification. **Parameters** are all of them
written as one JSON file, format `xray-params/1`. Think of it as a recipe card for the look. It names every element by its IFC
GlobalId and never by an internal number, so it still applies after the model is converted again.

### Try it

1. Open **FZK-Haus** from **Sample Projects** and change something visible, for example **alphaMin** in the folder **Sightlines (Alg 2)**, which sets how strong the ghosting is.
2. In the **Parameters** tab of the right sidebar, open the folder **Export / import**.
3. Click **Export JSON**. Your browser saves a small file. Name it after the project.
4. Change the setting back by hand, so the look differs from the file.
5. Click **Import JSON** and choose the file. The look from the file returns. If a value cannot be used, the viewer lists it and keeps the default.
6. Click **Copy share URL**. The link carries the main settings and the camera.

### How it works

The file holds one block per part of the viewer. It also carries the selection sets, class styles, material aliases, shortcut
keys and the saved views of the model. Tools register their own blocks (cleanup, measure, view modes, classification and more),
so a new tool joins the file without changes to the format. An unknown block or value is reported and skipped, not misread.

The same document is used in four places: the export, presets (a preset is a partial parameters document), `xray-pack
--params` (chapter 30) and share links. A share link carries only a small part (model, classification, sightlines, display, camera,
view modes, imaging, section), and only the values that differ from the factory state. The receiver needs the same model.

### Limits and gotchas

- A parameters file is not a model. It does not contain geometry, and it does not carry a model that is not already open.
- API keys, the Hugging Face token and thumbnails never go into it. Neither does your reviewer name.
- A share link applies to the receiver's factory state. A page with different class styles or plugins can look slightly different.

## 19.2 Read every property set and quantity

### The idea

An element in an IFC file carries more than a name. It carries property sets (fire rating, material, system) and quantities
(length, area, volume). These are the facts that checks and queries use. You can read all of them without leaving the viewer.

### Try it

1. In **FZK-Haus**, click a wall.
2. Open the **Properties** tab of the right sidebar.
3. At the top you see the GlobalId, class, name, storey, material and x-ray bucket (focus, host, near or far). Click **Copy GlobalId** to put the id on the
   clipboard. Paste it in a mail or a ticket: it names this element in every version of the model.
4. Below, the list **Properties (4 of 9)** shows the properties and quantities that pass the filter. To see all of them, tick **all properties in
   sidebar** in the **Hover info** folder of the **Parameters** tab. The `⋯` menu on a row and the right-click menu let you select all
   elements with this value, copy it, or save it as a criteria set.
5. Select five elements. The tab shows the first and says "+ 4 more selected".

### How it works

The tab follows the selection and refreshes four times a second. Two settings of the Hover info folder decide what shows: whether
all properties appear in the sidebar, and which property names the filter lets through. The viewer shows what the file
contains. A large model opened with the lighter `properties` option shows fewer (see 2.4).

Classification results join the list as the `XR_Classification` set, because they are written as ordinary properties.

### Limits and gotchas

- Properties are read-only. The only values the viewer writes are the classification results, and those only in memory
  until you save (19.3).
- Only properties that were loaded are shown. A very large model is opened with a capped number per element.

## 19.3 Save IFC and Save cleaned IFC

### The idea

Your results live in the page. When you close the tab they are in the browser's storage at best. **Save IFC** writes them into a
copy of the file you opened, so they travel with the model and open in any IFC tool. It is like writing notes in the margin of a
photocopy: the original page is untouched, and the margin notes are on a new sheet.

### Try it

You need the IFC file itself. A model opened from a sample or a `.glb` has no source file (see Limits).

1. Open `models/AC20-FZK-Haus.ifc` from the source folder with **Open IFC or glb file**, then classify it (chapter 18).
2. In the **Open model** folder, click **Save IFC**. (The command palette entry **Save IFC...** does the same.)
3. The dialog lists each file with its size, schema and the number of elements that carry data. Choose **Write**: all classified
   elements, or only the reviewed ones.
4. Leave **Include reviewer names and comments** off unless you mean it. It is off every time you open the dialog.
5. Click **Save IFC** in the dialog. Where the browser supports it you choose the destination and the file streams to disk. Otherwise it downloads.
6. The result is `AC20-FZK-Haus.xray.ifc`. Open it in another IFC program and look for the property sets below.
   If you classified with facets (chapter 18A), leave **Include classification facets** ticked and look for `XR_Trade` and `XR_Placement`
   on a wall.

To drop what cleanup hid (chapter 9): run cleanup, click **Hide matches**, then in the **Model cleanup** folder click **Save
cleaned copy...**. The dialog first plans the removal and shows a report. Nothing is written until you press **Save cleaned copy**.

### How it works

The saved file is **your original, byte for byte**, plus one block of new lines inserted before the end of the data section. No
original line is edited, removed or renumbered. The file is not parsed again at save time, so a 1 GB model costs only the block in
memory. Nothing leaves your computer.

| Data | Written as |
| --- | --- |
| Classification | `IfcClassification` and one `IfcClassificationReference` per code; each element is linked to its most specific code |
| Classification values | The property set of the schema (default `XR_Classification`) |
| Review state | `Xray_Review`: status, unsure, confidence, who proposed it, when reviewed, commit id; after a revision walk also `RevisionStatus` and `RevisionBaseline` |
| Cleanup marks | `Xray_Cleanup`: `FlaggedForRemoval`, the rules and the reason. Nothing is removed |
| Classification facets | `XR_Trade`, `XR_Placement`, `XR_Material`, `XR_Phase`, `XR_Orientation`, `XR_ClassRepair` and the concrete sets (chapters 18A, 18B), if you tick the box |
| 4D | `Xray_4D`: `Location`, `Trade`, `Zone` of accepted assignments, if you tick the box |

The set names are `Xray_...` and not `Pset_...`, because the `Pset_` prefix belongs to buildingSMART. IFC2X3, IFC4 and IFC4X3 are
supported. For another schema the button stays disabled and the dialog names the schema.

The block is bracketed by two comments. Saving again **replaces** the block and never adds a second one, so the same state gives
the same bytes. If another program stripped the comments, the viewer finds its sets and relations by name and takes them out
first, so nothing is written twice.

**Several files.** A model opened from several IFC files is saved as one output per source, named `<stem>.xray.ifc`. Elements
that appeared in two files exist only in the first; their twins get no data, and the dialog says how many.

**Save cleaned copy** writes `<stem>.cleaned.ifc`: your file **without** the elements cleanup hid. Removing an element means its
line goes, every relationship that mentions it is repaired, and geometry or property sets that nothing else uses are swept out.
A wall that still hosts a door or window is kept and marked `KeptBecause`. An assembly goes only when all its parts go. Project,
site, building, storey and space are never removed. Neighbouring ducts lose their connection to a removed one. The copy is
derived, and the name says so.

### Choices and settings

- **Write**: all classified, or only reviewed.
- **Include reviewer names and comments**: adds `ReviewedBy` and `Comment`. API keys, tokens and pictures have no way in, whatever
  you tick.
- **Include classification facets**: on when Classify has facet results. Every classified element gets its `XR_` property sets, each
  with `Code`, `Label`, `Confidence`, `Source`, `Model`, `NeedsReview` and its own fields. Numbers are written as real numbers.
  `XR_ClassRepair` is only a suggestion: the element's IFC class is not changed.
- **Mark cleanup matches**: marks what cleanup hid. Elements you hid by hand are not marked.
- **Also write the classification** and **Remove walls even if a door or window stays**, on the cleaned copy.

### Limits and gotchas

- The viewer keeps only a handle on the file you opened, never its bytes. A model opened from a sample, a link or a `.glb` has no
  source. The dialog offers **Attach the source IFC...** and accepts the file when at least 99 % of the elements match by id.
  If you moved or renamed the file on disk, attach it again.
- The save adds data. It never edits existing data. The added lines were checked with web-ifc and IfcOpenShell without new
  validation errors, but reading them still needs a tool that understands IFC.
- The cleaned copy reads the whole file once in a worker. A source above 1 GB is refused for a cleaned copy. Plain **Save IFC**
  has no such limit.
- A file with structural analysis models gets a warning on the cleaned copy. Accept the loss of connections.
- Fly-throughs are not saved into the IFC.

## 19.4 What is saved where

### The idea

Several places hold your work, and each has a different reach. Some stay on this computer. Some travel in a file you choose to
make. A few things are never written anywhere, on purpose.

### Try it

Run this check once on a model you care about. Close the tab, open the page again with the same model, and see what is still there.
Saved views, selection sets, fly-throughs, scripts, drawings, issues and 4D data come back. A share link, a parameters file or a
`.xrayanim` file you did not export does not exist. Then clear the site data of the page, and see everything in browser storage go.
Nothing you exported goes with it.

### How it works

| Where | What is in it | Who sees it |
| --- | --- | --- |
| **IFC copy** (`.xray.ifc`, `.cleaned.ifc`) | Classification, review state, cleanup marks, 4D location, trade and zone. Reviewer names only if you tick the box | Whoever you give the file to |
| **Browser storage**, per model (local storage and IndexedDB) | Saved views, selection sets, fly-throughs and their on-screen display, saved scripts, classification cache, manual overrides, review log, revision snapshots and sessions, 4D mapping and links, drawings, issues, sheets; the reviewer name; the panel fold state | Only this browser profile, on this computer |
| **Share link** | A small part of the settings, as differences from the factory state; one view; or one preset | Anyone with the link, who needs the same model |
| **Parameters file** (`xray-params/1`) | All settings, sets, class styles, shortcuts and saved views (no thumbnails) | Whoever you give it to |
| **Exports of a feature** | Views (`xray-views/1`), fly-throughs (`xray-flythroughs/1`), scripts (`.xrayanim`), the 4D configuration (`.4d.json`), the 4D links as a LinkML dataset, classification results (CSV, JSON), the review log, the revision report, a view with its drawings as PDF or JSON | Whoever you give it to |
| **Packed page** (`xray-pack`) | The model, plus only what you name on the command line: parameters, preset, selection, camera, views, fly-throughs, scripts, 4D plans | Whoever opens the page |
| **Never written anywhere** | API keys (Jev, d3), the Hugging Face token, pictures of elements (never in any file the viewer writes), the original IFC bytes (only a handle) | Nobody |

Browser storage is keyed by the model's identity (its name, its element count and a hash of its GlobalIds), not by its file name.
A renamed file of the same model keeps its work. A different model with the same name does not inherit it.

Three things are worth remembering.

**Your name is personal data.** The reviewer name is stored in this browser, written into the review log and the exports that
carry commits, and into the IFC only if you tick the box. It is never in a share link, saved view, preset, parameters file,
packed page or the property values of the elements.

**Keys and pictures stay local.** An API key is kept for the tab by default, or in this browser if you choose "remember". It is
sent only to the address you configured. It is not a setting, so it cannot get into any file.

**Caption text and scripts are yours.** They live in the browser store and in the export you make. A packed page carries a
script only when you name its file.

### Limits and gotchas

- Browser storage can be missing: a private window, blocked site data, or a page opened from `file://` in some browsers. The
  viewer then works for the session and says it did not save. Export what matters.
- Clearing site data deletes everything in browser storage. Exports are the backup.
- A view in a share link is an address, and addresses end up in mail and chat. Share it as you would any link to a model.
- Appendix G lists the stored items in detail.

### See also

Chapter 13 (views), chapter 29 (share links), chapter 30 (packed pages), appendix G (privacy and data).
