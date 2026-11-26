# 18B. Concrete elements

A quantity surveyor asks for the volume of concrete per storey. The formwork crew asks how many square metres of side form. The
engineer asks which slab carries which column. The rebar detailer asks which bars belong to which slab. A model gives each concrete
element a class and a shape, and nothing else. Every one of those questions starts with the same chore: find the element, say what it is
for, measure it, name it.

## 18B.1 Why concrete is special

### The idea

Most building materials arrive finished. Concrete is made on site, in a mould, around steel. So a concrete element is not just
a shape. It is a shape plus a **role** (what job it does), a **method** (cast in place or precast), a **specification** (strength,
exposure, cover) and an **intent** for its reinforcement. Cost, formwork, pours and bars all hang on those. Without them, a slab
on grade and a suspended slab are the same `IfcSlab`.

The viewer works this out for concrete elements and writes five property sets, `XR_ConcreteGeometry`, `XR_ConcreteElement`,
`XR_ConcreteMethod`, `XR_ConcreteSpec` and `XR_ConcreteReinforcement`. They use the `XR_` namespace and the core fields of 18A.1.

**How this prepares rebar matching.** A later step will match scanned or modelled bars to concrete elements. For that it needs a stable
name for each element (the **mark**), a local frame to say which way is "along the slab", the named faces and the elements that bear on
each other, and a guess of how it is reinforced and how heavily. These sets are exactly that. The matcher itself is not built yet; its
fields (`BarCount`, `MatchedMass`, `RatioCheck` and so on) stay empty.

### Try it

Use **FZK-Haus**.

1. In the **Classification** tab, open the **Facets** folder and check that **Concrete** is on. Click **Classify all**. Concrete runs
   after the facets and looks at the whole model at once, because marks and pour groups need every concrete element.
2. Select the ground slab, named **Bodenplatte**. In the Facets folder read its concrete sets: role `SLAB_ON_GRADE`, mark `SG0-01`.
3. Type `count where ConcreteElement = 'SLAB_ON_GRADE'` in the search bar.
4. Type `sum XR_ConcreteGeometry.Volume by Storey` to total the measured concrete per storey.
5. Type `where XR_ConcreteSpec.NeedsReview = TRUE`. These are elements whose strength, exposure or cover was suggested, not read.


> Picture (concrete-sets): the concrete sets of the Bodenplatte in the Facets folder, with role, mark, volume and formwork area.

### How it works

**Which elements.** Elements whose material is concrete; footings and piles unless another material is named; and slabs, walls, columns,
beams, stairs and the like that carry a concrete property set. Masonry, steel and timber are not in the family.

**Geometry** is measured, not guessed. For each element the viewer finds a local frame (slab: Z up, X along the longer side; wall: X
along the wall, Y out of the face; beam: X along the axis; column: Z along the axis). In that frame it reads:

- `Volume`, and `FormworkArea`: the faces that are not facing up and not against other concrete or the ground. A volume that could
  only be estimated from the bounding box is marked and flagged for review.
- `TopArea`, `SoffitArea`, `Length`, `Width`, `Thickness`, `SectionShape` (`RECT`, `CIRC`, `T`, `L`, `I`, `IRREGULAR`).
- `Faces`: the named planar faces (`TOP`, `BOTTOM`, `SIDE_X+`, `END_-`, ...), with area, and what each touches (concrete, ground).
- `Supports` and `Carries`: which concrete elements it rests on and which rest on it.

**Role** (`XR_ConcreteElement.Code`) is one of about 35 codes: `PAD_FOOTING`, `RAFT`, `SLAB_ON_GRADE`, `SUSPENDED_SLAB`, `BEAM`,
`TRANSFER_BEAM`, `COLUMN`, `WALL`, `SHEAR_WALL`, `RETAINING_WALL`, `STAIR` and others. It comes from names ("Bodenplatte", "pile cap"),
the predefined type, the class, then geometry: a slab at ground level on the lowest storey is a slab on grade, a slab resting on walls or
columns above ground is suspended. Where a rule is unsure, the model is asked with only the roles allowed for that class: a slab is never
asked whether it is a column.

**Mark** is a stable name. The viewer uses the IFC piece mark or tag if it is there and unique. Otherwise it makes one from the role prefix,
the storey and a number: `SG0-01` (slab on grade, storey 0, first), `S1-03` (suspended slab, storey 1, third). The numbering follows position,
not file order, so the same model always gives the same marks. **Pour groups** (`PG-1-2`) gather touching cast-in-place elements on one storey.

**Method** is `CAST_IN_PLACE`, `PRECAST`, `POST_TENSIONED`, `TILT_UP`, `COMPOSITE_DECK` or `UNKNOWN`, read from IFC data and names; foundations
are cast in place.

**Spec** holds the strength class (EN 206 `C30/37`, or ACI `4000 psi`), the exposure class, cover in millimetres and fire resistance. It reads
the IFC properties first, then the text of material, type and name, then a table. **Exposure is never decided by a rule or a model.** With
nothing in the file it is a suggestion from placement and level (for example `XC4` for outside) and the set needs review. A cover taken from the
table needs review too, until you confirm it.

**Reinforcement intent** is `REINFORCED`, `POST_TENSIONED`, `FIBRE`, `PLAIN` or `UNKNOWN`, a `Scheme` (slabs one-way or two-way, walls single or
double layer, beams and columns with links) and a `RatioEstimate` in kg/m3 with a `MassEstimate`. The ratio is the IFC value if present, otherwise
a table by role (for example 175 for beams, 215 for columns). It is an estimate, not a design.

### Choices and settings

- Role, method and reinforcement type can be set by hand for the selected element. A manual value wins over rules and model.
- The cover table is a file, `classification/concrete-cover.json`. Edit it to match the project specification.
- Queries: `ConcreteElement`, `ConcreteMethod`, `ConcreteSpec` and `ConcreteReinforcement` stand for `XR_<Set>.Code`. `contains` tests text:
  `where XR_ConcreteSpec.ExposureClass contains 'XD'`.
- CSV and JSON exports gain a column for each field. **Include classification facets** in Save IFC writes the concrete sets too (19.3).

### Limits and gotchas

- Face contacts are sampled, so areas carry about 1 % noise.
- A model with closed meshes gives exact volumes. Open meshes give a bounding-box volume, and the element is flagged.
- The rebar matcher, a concrete tree preset, concrete colouring and a quantity summary are planned, not built.
- Strength, cover and fire resistance are never asked of the decision model. If your IFC has none, they are `UNKNOWN` or suggested.

## See also

Chapter 18A (facets and the tree), chapter 8 (queries), 19.3 (saving into the IFC), chapter 20 (carrying decisions into a new version).
