# Classification facets: a scheme, a namespace, a standard tree

Status: design, 2026-11-26. Builds on `web/docs-features/classify.md` (discipline, sub-discipline, MasterFormat division) and
`web/docs-features/cleanup.md` (floating, tiny, strays, duplicates, degenerate).

## 1. Why facets

A building element is described along several independent questions: who owns it, who builds it, when, where it sits, what it
is made of, which way it points, and what it really is when the IFC class is generic. One code list (MasterFormat) cannot answer
all of them, and a messy model's own tree (one storey, everything in it, half the elements `IfcBuildingElementProxy`) answers
none. So the classifier answers each question separately, as a **facet**, and the viewer builds a standard tree from the facets.

## 2. The facets

| Facet | Question | Values (codes) | How it is decided |
| --- | --- | --- | --- |
| `Discipline` (exists) | Who owns it? | ARC, STR, MEC, PLB, ELE, FPR, CIV, ... (the shipped schema) | rules, then the decision model |
| `Trade` | Who builds it (the work package)? | EARTH, CONC, STEEL, TIMBER, MASON, ROOF, FACADE, GLAZ, DRYLN, FINISH, DOORS, MECH, PLUMB, ELEC, FIRE, LIFT, SITE, OTHER | rules (class + discipline + material), then the model; feeds the 4D **Map** step (trade) |
| `Placement` | Where does it sit and what does it carry? | `Exposure`: EXT, INT, BOUNDARY; `LoadBearing`: true/false | the element's own `Pset_*Common.IsExternal` / `LoadBearing` when present and plausible, geometry (envelope test, section 5), then the model |
| `Material` | What is it mainly made of? | CONCRETE, STEEL, TIMBER, MASONRY, GYPSUM, GLASS, ALUMINIUM, INSULATION, PLASTIC, STONE, EARTH, OTHER | IFC material names and layer sets (rules), then the model |
| `Phase` | When in the job is it built? | SUBSTR, FRAME, ENVELOPE, SERVICES, FITOUT, EXTERNAL | rules from Trade + Placement + storey, then the model |
| `Orientation` | Which way does it point? | `Class`: HORIZONTAL, VERTICAL, INCLINED, (for linear elements) ALONG_X, ALONG_Y, DIAGONAL; numbers: `Tilt` (degrees from horizontal), `Azimuth` (degrees from model +X), `Upright` (true/false/unknown) | geometry only (section 4); the model only judges whether an orientation is *plausible* for the class |
| `ClassRepair` | What is it, if the IFC class is generic or wrong? | a suggested IFC4 class and predefined type | rules (names, type names, geometry shape), then the model; offered only for `IfcBuildingElementProxy`, `IfcBuiltElement` without type, and classes the geometry contradicts |

Not every facet asks the model. Orientation is measured; Placement and Material read the model's own data first. The model is
the fallback that turns names and context into a choice, exactly as for Discipline today.

## 3. The namespace

All properties the viewer writes for classification live in property sets named **`XR_<Facet>`**. `XR_` is already the prefix
of `XR_Classification` (since the first classifier release). `Pset_` is reserved by buildingSMART and must not be used.

Every facet set has the same **core fields**, so a query, a report or another tool reads all facets the same way:

| Property | Type | Meaning |
| --- | --- | --- |
| `Code` | label | the chosen code, e.g. `CONC` |
| `Label` | label | its human name, e.g. `Concrete works` |
| `Confidence` | real 0-1 | calibrated probability of `Code` (1 for a measured value or a manual choice) |
| `Source` | label | `rule`, `model`, `geometry`, `ifc` (the element's own property), `manual`, `batch-learned` |
| `Model` | label | the provider and model id for `model` / `batch-learned`; empty otherwise |
| `NeedsReview` | boolean | below the facet's review threshold, or two sources disagree |
| `SchemeVersion` | label | `xr-facets/1` |

Facet-specific fields, added to the core:

- `XR_Placement`: `Exposure` (EXT/INT/BOUNDARY; `Code` repeats it), `LoadBearing` (boolean), `ExposureSource`, `LoadBearingSource`.
- `XR_Orientation`: `Tilt`, `Azimuth` (degrees, 0.1 precision), `Upright` (boolean or empty), `PrincipalAxis` (`X`, `Y`, `Z` or empty), `Plausible` (boolean: the orientation suits the class; false flags "wall lying flat").
- `XR_ClassRepair`: `OriginalClass`, `SuggestedClass`, `SuggestedPredefinedType`, `Applied` (boolean; true only after a person accepts it and saves).
- `XR_Trade`: `WorkPackage` (free text, empty unless a project table maps codes to its own packages).
- `XR_Classification` (exists) keeps its fields unchanged; it is the Discipline facet. It gains `SchemeVersion`.

Rules for the namespace:

- One property set per facet; no facet writes into another facet's set. A facet that is switched off writes nothing.
- No personal data in any `XR_` set: no reviewer names, no user names (as for 4D links).
- The sets live in the loaded model and in exports (CSV, JSON). Writing them into a saved IFC is opt-in in the IFC save dialog
  ("Classification facets"), like the 4D links; `XR_ClassRepair.Applied = true` rewrites the class only on that save.
- Older sets (`Xray_4D`, `Xray_Review`, `Xray_Cleanup`) keep their names; they are not classification facets. A later change may
  alias them under `XR_` with read compatibility; this design does not rename them.
- In the query language the full name is `XR_Trade.Code`; a bare `Trade` is offered as an alias for the facet's code (the query
  engine already resolves a bare property name when only one set has it; `Code` is in every facet, so the alias is the facet name).

## 4. Orientation, measured

For each element, from its world-space triangles (already in memory for picking):

1. Principal axes by PCA of the vertex positions, weighted by triangle area (so a dense end does not dominate). Eigenvalues give
   the shape: linear (one large axis: beams, columns, pipes, ducts, members), planar (two large: walls, slabs, roofs, plates),
   compact (all similar: equipment, furniture).
2. `Tilt` and `Azimuth`: for linear elements, of the main axis; for planar elements, of the plane normal (a slab's normal is
   vertical, Tilt 0 of the plane = horizontal; a wall's normal is horizontal).
3. `Class`: planar with a vertical normal (within 5°) = HORIZONTAL; with a horizontal normal (within 5°) = VERTICAL; else INCLINED.
   Linear: vertical axis = VERTICAL; horizontal axis = ALONG_X / ALONG_Y (within 5° of the model grid axes) or DIAGONAL; else INCLINED.
   Compact: by its bounds' longest horizontal side, Class = HORIZONTAL with Azimuth only.
4. `Upright` for elements that have a "top": doors, windows, stairs, furniture, equipment: the side with more horizontal area at
   the base than the top, or the type's local +Z mapped to world +Z (from the placement matrix, when the IFC carries it). Unknown
   when neither tells.
5. `Plausible`: a small table per class: IfcWall VERTICAL; IfcSlab HORIZONTAL or INCLINED (ramps, roofs); IfcColumn VERTICAL or
   INCLINED; IfcBeam ALONG_X/ALONG_Y/DIAGONAL/INCLINED; IfcDoor/IfcWindow VERTICAL and Upright; IfcRoof any; pipes and ducts any.
   An implausible combination sets `NeedsReview` and appears in the messy-model checks (section 8). The decision model is asked
   only when the class is generic (a proxy), to judge the combination from names.

Cost: one pass, O(triangles), done in slices in a worker-friendly pure function; 100 000 elements in seconds.

## 5. Placement: exterior or interior

1. The element's own `Pset_*Common.IsExternal` / `LoadBearing` when present, unless geometry contradicts it badly (an "external"
   wall in the middle of the plan): `Source = ifc`.
2. Geometry: the building's envelope as the 2D outline of each storey (union of wall and slab footprints, already computable from
   bounds), and rays from the element's centre outwards in 8 horizontal directions against walls, windows, doors, curtain walls,
   roofs: an element with a clear ray to the outside on one side and building on the other is BOUNDARY (envelope); one with no
   clear ray is INT; one outside the outline is EXT. Roofs and the top slab: BOUNDARY. `Source = geometry`.
3. Load-bearing: structural classes (IfcColumn, IfcBeam, IfcFooting, IfcPile, structural slabs and walls from discipline STR or a
   thick concrete or masonry wall) by rule; otherwise the model.

This facet drives the temporary-works rules: scaffold on BOUNDARY walls, falsework under load-bearing slabs and beams, formwork on
CONCRETE walls, slabs, columns and beams.

## 6. The standard tree (classification view)

The left sidebar's **Model** tab gains a switch at the top: **Model tree** (the IFC spatial tree, as today) | **By classification**.
By classification shows the same elements in a **standard tree** built from the facets, independent of how the file was organised:

```
Phase                     SUBSTR, FRAME, ENVELOPE, SERVICES, FITOUT, EXTERNAL
  Discipline              ARC, STR, MEC, ...
    Trade                 CONC, MASON, ...
      Element group       the (repaired) IFC class, e.g. Walls, Slabs, Doors
        Element           name, with storey and confidence badges
```

- **Levels are configurable**: a "Group by" control picks 1 to 4 levels from the facets (Phase, Discipline, Trade, Placement,
  Material, Orientation, Storey, IFC class); presets: **Construction** (Phase › Trade › class), **Ownership** (Discipline ›
  sub-discipline › class), **Envelope** (Placement › Material › class), **Standard (UniFormat II)** (below). The choice is a
  per-viewer convenience.
- **Standard (UniFormat II)**: a fixed tree of UniFormat II levels 1-3 (A Substructure › A10 Foundations › A1010 Standard
  Foundations; B Shell › B20 Exterior Enclosure › B2010 Exterior Walls; C Interiors; D Services; E Equipment & Furnishings; F
  Special; G Building Sitework). Each element is mapped by a table from (Phase, Placement, class, Trade, Discipline) to a UniFormat
  code; the mapping table ships as JSON next to the schema (`public/classification/uniformat2.json`) and is user-editable like the
  schema. MasterFormat stays as the work-results code on each element. (Uniclass 2015 / OmniClass trees can be added later as
  further mapping tables; the tree code is the same.)
- Every node shows a count, the share needing review (an amber badge), and the eye toggle; clicking a node selects its elements;
  the keyboard works exactly as in the model tree (`src/ui/treeKeys.ts`). Elements with no value for a level go under "Not
  classified" at that level, so nothing disappears.
- The tree is computed from the facet properties, not stored; it updates when a classification changes.

## 7. The classification viewer

A **Classification** look for the 3D view, driven from the same tree:

- **Colour by** any facet (today: discipline only) with a legend; the legend's rows are the tree's first-level nodes, clicking one
  isolates it, the eye hides it.
- **Confidence shading**: elements below the review threshold drawn with a hatched or desaturated tint, so doubtful areas show.
- **Disagreement**: where two sources disagree (the IFC says external, geometry says interior), a small marker on the element and a
  row in the review list.
- The review walk (`Shift+R`) gains a facet filter: walk only Trade, only ClassRepair, etc.
- Everything is a query: each node and legend row is a set of the form `XR_Trade.Code = 'CONC' and XR_Phase.Code = 'FRAME'`, so
  "Save as set", sharing and scripts work with the same expressions.

## 8. Batch mode

**Classify all** (Classification tab; also `__xrayClassify.batch({ facets, scope })` and the CLI `xray-classify` if added later):

1. Scope: the whole model, the selection, a set, or only "not classified / needs review".
2. Group by signature (class, type name, name pattern, material, dimensions; the existing signature), so 10 000 elements become a
   few hundred questions.
3. Measured and rule facets first (Orientation, Placement from IFC and geometry, Material from material names): no model needed.
4. Model facets in batches: the in-browser NLI and embedding models run batched tensors (32 hypotheses per call); Jev and d3 get
   several questions per request where the API allows; WebLLM one prompt per signature with a shared prefix.
5. **Learn as you review**: with an embedding model loaded, every accepted or manual decision becomes an example; a new signature
   whose nearest accepted examples agree above a threshold gets that label with `Source = batch-learned` and skips the model. The
   examples are kept per model in the browser (like the cache), exportable with the results.
6. Progress, pause, resume, cancel; an estimate (signatures × measured seconds per question for the chosen model); the result
   list sorted by uncertainty so the review walk starts with the doubtful ones.

## 9. Models offered

Added to the `decision` provider's list (transformers.js), each benchmarked with `bench/real-classify-decision.mjs` before any
default changes; the table in classify.md gets their rows:

- Von 1.3 (`onnx-community/von-ONNX`, ModernBERT-large decision model), choice/yes-no/score in one pass.
- `MoritzLaurer/ModernBERT-base-zeroshot-v2.0` and `MoritzLaurer/ModernBERT-large-zeroshot-v2.0` (ONNX in the repositories).
- `onnx-community/deberta-v3-large-zeroshot-v2.0-c-ONNX` (accuracy option for batch runs).
- Embedding models for the batch learner and an `embed` mode: `onnx-community/embeddinggemma-300m-ONNX`, granite-embedding-97m-r2,
  Bekko (July 2026), whichever have ONNX weights loadable by transformers.js 4.3.2.
- Laya (421M) as a local Jev-compatible endpoint (its own server speaks `/v1/systemone`), documented as a Jev setup variant; its
  in-browser build is large (about 524 MB) and is listed with that warning.
- d3-lite, d3-nano, d3-mini as model ids for the `d3` endpoint backend (vLLM nightly).

## 10. Messy-model checks that build on the facets

Cleanup today finds floating, tiny, distant, duplicate and degenerate elements. With facets and geometry it can also find:

1. **Generic objects**: proxies and untyped elements, with a suggested class (ClassRepair), applied on save after review.
2. **Implausible orientation**: walls lying flat, doors upside down, columns on their side (Orientation.Plausible = false), with
   "Fix rotation" proposing the nearest plausible rotation about the element's centre.
3. **Wrong storey**: an element whose base is clearly on another storey's level than the one it is assigned to; suggest the storey.
4. **Missing standard properties**: `IsExternal`, `LoadBearing`, `FireRating` absent; fill `Pset_*Common` from the facets on save
   (opt-in, marked as derived).
5. **Missing types**: identical geometry and names without an IfcType: propose types (one per signature) so schedules and quantities
   group properly.
6. **Bad or duplicate GlobalIds**: invalid base64, duplicates across federated files: regenerate on save, keeping a map.
7. **Unnamed and default names** ("Generic Model 1", "Basic Wall: ..."): propose names from class, type and storey.
8. **Wrong unit scale**: a model 1000× too large or small (a 3 km house); detect from storey heights and door sizes, offer to rescale.
9. **Hosting gaps**: doors and windows not in any wall opening, openings without fillers.
10. **Cross-model duplicates**: the same column in the architectural and structural models of a federation; pick the owner by
    discipline and hide the other.
11. **Naming convention**: names that break a project pattern (a regex per class), listed with a suggested rename.

Each check lists matches with a reason (as the cleanup rules do), selects them, and its fix is undoable and written only on save.

## 11. Order of work

1. Facets engine and namespace: Trade, Placement, Material, Phase, ClassRepair questions and rules; Orientation measured.
2. Batch mode and the new models with the benchmark.
3. The standard tree, the UniFormat mapping and the classification viewer.
4. The messy-model checks of section 10, in the cleanup drawer.
