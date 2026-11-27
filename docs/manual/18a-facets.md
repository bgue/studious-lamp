# 18A. Facets, the classification tree and colours

A discipline label answers one question: who is this for? A site manager asks other things. Who builds this wall? Is it
inside or outside? Is it load-bearing? When does it go up? Is that door upside down? One label cannot carry all of that, and
a model with 20,000 elements is too big to tag by hand.

## 18A.1 Facets: more questions, one answer each

### The idea

A **facet** is one more question the classifier answers about every element, with its own short list of allowed codes. The
discipline of chapter 18 stays. Six facets sit beside it. Think of a library book: it has one shelf (the discipline), but also an
author, a year and a language. You find it by any of them.

| Facet | Question | Example codes |
| --- | --- | --- |
| **Trade** | Who builds it? | `CONC`, `STEEL`, `TIMBER`, `MASON`, `ROOF`, `GLAZ`, `DOORS`, `MECH`, `ELEC` |
| **Placement** | Where does it sit? Does it carry load? | `EXT` (outside), `INT` (inside), `BOUNDARY` (on the envelope); load-bearing yes or no |
| **Material** | What is it made of? | `CONCRETE`, `STEEL`, `TIMBER`, `MASONRY`, `GLASS` |
| **Phase** | When is it built? | `SUBSTR`, `FRAME`, `ENVELOPE`, `SERVICES`, `FITOUT`, `EXTERNAL` |
| **Orientation** | Which way does it point? | `HORIZONTAL`, `VERTICAL`, `INCLINED`, `ALONG_X`, `ALONG_Y`, `DIAGONAL` |
| **ClassRepair** | What is it really? | `KEEP`, or a suggested class such as `IfcColumn` |

The answers are written back to the elements as properties in a **namespace** called `XR_`. Each facet gets one property set,
`XR_Trade`, `XR_Placement` and so on. The prefix says "made by the viewer", the way `Pset_` says "made by buildingSMART". Every set
has the same core fields, so a query for one facet works for all:

| Field | Meaning |
| --- | --- |
| `Code`, `Label` | the chosen code and its name |
| `Confidence` | 0 to 1; 1 for a measured or manual value |
| `Source` | `rule`, `model`, `geometry`, `ifc` or `manual` |
| `Model` | the provider and model, when the source is `model` |
| `NeedsReview` | true when the answer is weak, close or implausible |
| `SchemeVersion` | `xr-facets/1` |

A facet adds its own fields: `XR_Placement.LoadBearing`, `XR_Orientation.Tilt`, `.Azimuth`, `.Upright`, `.Plausible`,
`XR_ClassRepair.SuggestedClass`, and a free-text `XR_Trade.WorkPackage` that only you fill in.

### Try it

Use **FZK-Haus** (Sample Projects).

1. Open the **Classification** tab. Open the **Facets** folder. Every facet has a switch, all on.
2. Click **Classify all**. The facets run after the discipline.
3. In the search bar type `count where Trade = 'CONC'`. The house has 15 concrete elements.
4. Type `count where Placement = 'BOUNDARY' and class like 'IfcWall%'`. (The walls of FZK-Haus are `IfcWallStandardCase`, so `class = 'IfcWall'` would find none.) The external walls sit on the envelope. The house has 8 of them.
5. Click a wall. The **Facets** folder shows its facet values with confidence and source. Open the Placement picker, choose
   another code and the source turns to `manual`. A manual value wins over every other source and is kept for this model.
6. Type `where XR_Orientation.Plausible = FALSE`. A wall lying flat or a door upside down would appear here.


> Picture (facets-folder): the Facets folder of the Classification tab with the six switches and the facet values of one wall.

### How it works

The facets are decided cheapest first, like the discipline (18.1).

- **Rules.** Trade comes from the IFC class, the discipline and the material: an `IfcSlab` of concrete is `CONC`, an `IfcDoor`
  is `DOORS`. Material comes from a keyword table over the material name, type name and element name. Phase comes from Trade,
  Placement, load-bearing and whether the level is below ground.
- **Geometry.** Placement does not trust the label alone. For a wall, door or window the viewer shoots rays outward from both
  faces. Clear on one side and blocked on the other is `BOUNDARY`; blocked on both is `INT`; clear on both is `EXT`. When the
  file says `IsExternal` and the rays disagree with high confidence, the rays win, the source says `geometry` and the element
  needs review. Orientation is measured only: the viewer fits the element's triangles and reads whether it is a line, a plane or
  a lump, and how it is tilted. Elements with a top (doors, windows, stairs) are checked for being upright.
- **The decision model.** Only what the rules leave open goes to the model: one typed question per facet, once per kind of element.
  The answers share the cache and calibration of chapter 18.
- **ClassRepair** looks only at proxies, untyped building elements and elements whose shape contradicts the class. It only
  suggests. The class in the file is never changed.

A facet that is switched off writes nothing, and an empty value is left out. In a query the bare facet name is an alias for its
code: `Trade` is `XR_Trade.Code`. `material` stays the IFC material, so write `XR_Material.Code` for the facet.

### Choices and settings

- The **Facets** folder: a switch per facet, and a manual picker for the selected element.
- Each facet has its own minimum confidence in the schema (`facets.<Facet>.minConfidence`). A schema file without a `facets`
  section loads with the defaults.
- The CSV and JSON exports gain a column for every `XR_<Facet>.<Field>`.

### Limits and gotchas

- Placement by rays reads the model's geometry. A model with open wall faces or missing roofs gives odd answers; the element is
  then flagged for review.
- ClassRepair is a suggestion. To change a class in the IFC you need another tool.
- The disagreement marker is not built yet.
- The review walk can visit facet answers that need review (chapter 18.2): choose **Facets** or **Both** in its **Show** list. A
  confirmed or corrected facet gets the source `human`, and the choice is in the review log.

## 18A.2 The By classification tree

### The idea

The Model tree shows the file's own order: project, building, storey, class. Nobody on site asks for that order. A planner wants
"everything in the frame phase, by trade". A client wants "everything on the envelope, by material". The **By classification**
tree regroups the same elements by what the classifier found, whatever the file's structure.

### Try it

1. On **FZK-Haus**, classify with the facets on (18A.1).
2. In the **Model** tab of the left sidebar, click **By classification** in the switch **Model tree** | **By classification**.
3. In **Group by** choose **Construction**. The tree reads Phase, then Trade, then IFC class. Each row has a count and, in amber,
   the share that needs review.
4. Choose **Envelope** (Placement, Material, IFC class). Open `BOUNDARY` and, under it, `CONCRETE`: the external walls are there. (The material rows read like `CONCRETE Concrete`: the code and its name.)
5. Hover a row and click **+set**. The set editor opens with a query such as `XR_Trade.Code = 'CONC' and XR_Phase.Code = 'FRAME'`.
   Save it. Because it is a query, the set updates itself when the classification changes (chapter 8).
6. Click the eye on a row to hide or show the group. Elements without a value at a level sit under **Not classified**.

> Picture (class-tree-envelope): the By classification tree with the Envelope preset, counts, an amber review share and the +set button.

### How it works

The tree is computed from the `XR_` properties, so it follows every change you make. It groups by 1 to 4 levels. A click selects the
elements of the row. The keys are those of the model tree (appendix A). The filter box filters this tree too.

| Preset | Levels |
| --- | --- |
| **Construction** | Phase, Trade, IFC class |
| **Ownership** | Discipline, Sub-discipline, IFC class |
| **Envelope** | Placement, Material, IFC class |
| **Standard (UniFormat II)** | level 1, 2, 3 (`A`, `A10`, `A1010`) |

**Custom**, or a change to any level list, builds your own. The levels you can pick are Phase, Discipline, Sub-discipline, Trade,
Placement, Material, Orientation, Storey and IFC class.

**UniFormat II** is a standard breakdown by building system. A file of rules (`classification/uniformat2.json`) maps Phase,
Placement, class, Trade and discipline to a code; the first rule that holds wins. **Mapping...** loads your own file. A UniFormat
row has no property to query, so **+set** saves its elements as a plain set. The choice of mode and grouping is kept in your browser only.

### Limits and gotchas

- On FZK-Haus every element reaches at least UniFormat level 2, and 42 of 82 reach level 3. The 40 timber members stay at `B10`,
  because their class cannot tell roof framing from floor framing.
- Elements the facets did not reach stay under **Not classified**. Run **Classify all** first.

## 18A.3 Colour by facet and Confidence shading

### The idea

A tree tells you counts. A picture tells you where. **Colour by** paints the model by one classification, and **Confidence
shading** washes out the elements nobody has checked, so the doubtful areas show up as pale patches.

### Try it

1. On the classified **FZK-Haus**, open the **Classification** tab, section Output. In **Colour by** choose **Trade**.
2. The legend lists each trade with its count and review share. Click the row `CONC`: only the concrete is shown. Click it again for all.
3. Choose **Placement**. The envelope and the interior take two colours.
4. Switch on **Confidence shading**. Elements that need review turn paler, over any colour choice. Click **Select needs review**
   (18.1) to act on them.

### How it works

**Colour by** offers Off, Discipline, Trade, Placement, Material, Phase and Orientation. A legend row can isolate its elements, hide them,
or open **+set** with its query. Confidence shading lowers the saturation and raises the lightness of elements whose answer needs review.

### Limits and gotchas

- Colour by paints the page while you work. It is not an issue, a drawing or a script step.

Colour by is not part of a saved view or of the exported settings: choose it again after reopening the viewer.

## See also

Chapter 18 (the discipline, review and code lists), 18B (concrete), chapter 8 (queries and sets), 19.3 (saving facets into the IFC).
