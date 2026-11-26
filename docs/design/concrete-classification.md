# Concrete elements: facets, namespace, and preparation for rebar matching

Status: design, 2026-11-26. Extends `docs/design/classification-facets.md` (facets, the `XR_<Facet>` namespace, core fields).

## 1. Why concrete gets its own family

Concrete elements carry most of a structure's cost, schedule (pours, formwork, curing, falsework) and the reinforcement. Rebar,
mesh, tendons and embeds must later be matched to the element they reinforce, which needs every concrete element to have a
stable identity, a known role, a local frame and measured faces. A generic "Material = CONCRETE" is not enough.

Which elements: every element whose `XR_Material.Code` is CONCRETE, plus IFC classes that are concrete by nature
(IfcFooting, IfcPile, slabs/walls/columns/beams with a concrete material or a `Pset_ConcreteElementGeneral`), plus precast
classes. Masonry, steel and timber elements are not in this family.

## 2. Standards first

IFC4 already defines concrete properties. The facets read them first (`Source = ifc`) and only fill gaps:

| IFC4 property set | Properties we read | Our field |
| --- | --- | --- |
| `Pset_ConcreteElementGeneral` | `StrengthClass`, `ExposureClass`, `ReinforcementStrengthClass`, `ConcreteCover`, `ConcreteCoverAtMainBars`, `ConcreteCoverAtLinks`, `ReinforcementVolumeRatio`, `ReinforcementAreaRatio`, `CastingMethod` (INSITU / PRECAST), `AssemblyPlace` (SITE / FACTORY), `StructuralClass` | `XR_ConcreteSpec.*`, `XR_ConcreteReinforcement.*`, `XR_ConcreteMethod` |

The implementation checks these names against the IFC4 property set definitions (ifcopenshell's pset templates in the skill's
environment, or the buildingSMART documentation) and reads IFC2x3 files with whatever subset they carry.
| `Pset_PrecastConcreteElementGeneral`, `Pset_PrecastConcreteElementFabrication` | `TypeDesignator`, `ProductionLotId`, `PieceMark` | `XR_ConcreteMethod.Code = PRECAST`, `XR_ConcreteElement.Mark` |
| Predefined types (`IfcSlab.PredefinedType` FLOOR/ROOF/BASESLAB/LANDING, `IfcFooting` PAD_FOOTING/STRIP_FOOTING/PILE_CAP/FOOTING_BEAM, `IfcWall` SHEAR/RETAININGWALL/ELEMENTEDWALL, `IfcBeam` T_BEAM/LINTEL/SPANDREL, `IfcColumn`, `IfcPile`) | the predefined type | `XR_ConcreteElement.Code` (rule) |

On IFC save (opt-in, "Classification facets"), empty standard properties may be filled from our facets, marked as derived in a
`XR_ConcreteSpec.Derived` list; existing values are never overwritten.

## 3. The facets (namespace `XR_Concrete*`)

Each set carries the core fields of the facets design (`Code`, `Label`, `Confidence`, `Source`, `Model`, `NeedsReview`,
`SchemeVersion = xr-concrete/1`) plus its own fields.

### 3.1 `XR_ConcreteElement`: what the element is (structural role)

Codes:

| Group | Codes |
| --- | --- |
| Foundations | `PAD_FOOTING`, `STRIP_FOOTING`, `RAFT`, `PILE_CAP`, `PILE`, `GRADE_BEAM`, `PLINTH` |
| Slabs | `SLAB_ON_GRADE`, `SUSPENDED_SLAB`, `FLAT_SLAB`, `RIBBED_SLAB`, `WAFFLE_SLAB`, `TRANSFER_SLAB`, `TOPPING`, `LANDING` |
| Frame | `BEAM`, `DOWNSTAND_BEAM`, `UPSTAND_BEAM`, `TRANSFER_BEAM`, `COLUMN`, `PIER` |
| Walls | `WALL`, `SHEAR_WALL`, `CORE_WALL`, `RETAINING_WALL`, `BASEMENT_WALL`, `PARAPET` |
| Other | `STAIR`, `RAMP`, `CORBEL`, `CURB`, `EQUIPMENT_PAD`, `PRECAST_PANEL`, `OTHER` |

Extra fields: `Mark` (the element's piece mark or a generated stable mark, see 4), `Storey`, `HostGroup` (the pour group,
see 3.5).

Decided by: predefined type and class (rule), names and type names (rule: "PC", "pile cap", "core", "transfer"), geometry
(thickness, aspect, orientation from `XR_Orientation`, contact with ground from the lowest storey and the Placement facet),
then the decision model with the codes above as options.

### 3.2 `XR_ConcreteMethod`: how it is made

Codes: `CAST_IN_PLACE`, `PRECAST`, `POST_TENSIONED`, `TILT_UP`, `COMPOSITE_DECK` (concrete on metal deck), `UNKNOWN`.
Decided by: `Pset_PrecastConcreteElement*` present → PRECAST; names ("PT", "post-tension", "PC", "precast", "hollowcore",
"tilt"); IfcTendon elements nearby → POST_TENSIONED candidate; else the decision model; default CAST_IN_PLACE with low
confidence (never silently).

### 3.3 `XR_ConcreteSpec`: the specification

Fields (not one code; `Code` holds the strength class, e.g. `C30/37`):
- `StrengthClass`: normalised to EN 206 `Cxx/yy` when given in EN form, or kept as given with `StrengthUnit` for ACI
  (`f'c 4000 psi`, `32 MPa`). A rule table parses common forms ("C30/37", "C30", "B35", "4000 psi", "32MPa", "f'c=5 ksi").
- `ExposureClass`: EN 206 classes (`X0`, `XC1`-`XC4`, `XD1`-`XD3`, `XS1`-`XS3`, `XF1`-`XF4`, `XA1`-`XA3`, several allowed,
  comma-separated) or ACI 318 categories (`F0`-`F3`, `S0`-`S3`, `W0`-`W2`, `C0`-`C2`). Read from IFC/names; otherwise a
  *suggestion* from Placement (EXT/BOUNDARY → XC4/XF1, below ground → XC2, INT → XC1) with `NeedsReview = true`, never final.
- `Standard`: `EN206` or `ACI318` (from the strength form, or a project setting).
- `CoverNominal` (mm), `CoverMainBars`, `CoverLinks`: from IFC; else from the project's cover table by role and exposure (a
  JSON table next to the schema, editable), `Source = rule`, `NeedsReview` on first use.
- `FireResistance` (e.g. `R60`, `REI90`) from `Pset_*Common.FireRating`.
- `Derived`: the names of the fields this set filled that were empty in the IFC.

### 3.4 `XR_ConcreteReinforcement`: reinforcement intent and, later, what was matched

Fields:
- `Code`: `REINFORCED`, `POST_TENSIONED`, `FIBRE`, `PLAIN`, `UNKNOWN`.
- `Scheme`: for slabs `ONE_WAY` / `TWO_WAY`, for walls `SINGLE_LAYER` / `DOUBLE_LAYER`, for beams and columns `LINKS` (from
  spans and supports, rule; else model; else empty).
- `RatioEstimate` (kg/m³): a typical value by role (a table: footings 80-100, slabs 90-120, beams 150-200, columns 180-250,
  walls 60-100, transfer elements 250+), for take-off before rebar exists. `Source = rule`.
- Filled by the rebar matcher (later work, section 5): `BarCount`, `MeshCount`, `TendonCount`, `MatchedMass` (kg),
  `MatchedRatio` (kg/m³), `RatioCheck` (`OK` / `LOW` / `HIGH` against the estimate).

### 3.5 `XR_ConcreteGeometry`: measured, the basis for matching (no model)

All measured from the element's geometry (pure functions, like `XR_Orientation`):
- `Volume` (m³, closed meshes; bounds-based estimate flagged otherwise), `FormworkArea` (m²: side and soffit faces, not top
  faces of slabs or faces against ground or other concrete), `TopArea`, `SoffitArea`.
- The **local frame**, written as `FrameOrigin` (x y z), `FrameX`, `FrameY`, `FrameZ` (unit vectors, text "x y z"), chosen by
  role: slabs: Z up, X along the main span (the longer support spacing; else the longer side); walls: Z up, X along the wall,
  Y out of the face (the exterior face for BOUNDARY walls); beams: X along the axis, Z up; columns: Z along the axis, X along the
  longer section side; footings: Z up, X along the longer side.
- In that frame: `Length`, `Width`, `Depth`/`Thickness` (m), `SectionShape` (`RECT`, `CIRC`, `T`, `L`, `I`, `IRREGULAR`).
- `Faces`: a compact list of the planar faces with their local-frame names (`TOP`, `BOTTOM`, `SIDE_X+`, `SIDE_X-`,
  `SIDE_Y+`, `SIDE_Y-`, `END_+`, `END_-`), areas and whether each is against another concrete element (a construction joint)
  or the ground. This is what a bar's position is tested against ("bottom layer, X direction, 40 mm cover").
- `Supports`: the GlobalIds of the concrete elements it bears on and that bear on it (contact graph from the cleanup code's
  bounds contacts, refined by face contact), the input for spans and for slab/beam schemes.
- `PourGroup`: elements cast together (touching, same storey, same method CAST_IN_PLACE, same pour-related activity in 4D when
  linked; a slab and its downstand beams are one group). Written to `XR_ConcreteElement.HostGroup` as a stable id
  `PG-<storey>-<n>`.

## 4. Identity

Every concrete element gets `XR_ConcreteElement.Mark`: the IFC piece mark / `Tag` when present and unique, else a generated
stable mark `<role prefix><storey index>-<n>` (`S1-03` = third suspended slab on storey 1, `C0-12`, `W1-04`), numbered in a
fixed order (storey, then position along X then Y of the frame origin) so the same model gives the same marks every time.
Rebar schedules and the matcher refer to marks and GlobalIds, never to names.

## 5. Preparation for rebar matching (the next step, not built by this work)

Bars (`IfcReinforcingBar`), meshes (`IfcReinforcingMesh`), tendons (`IfcTendon`, `IfcTendonAnchor`) and embeds will each get
`XR_ReinforcementLink`:
- `HostGlobalId`, `HostMark`, `HostRole` (the concrete element it reinforces), `Confidence`, `Source` (`ifc` for
  IfcRelAggregates / IfcRelAssignsToProduct / nesting, `geometry`, `name`, `model`, `manual`), `NeedsReview`.
- `Layer` (`TOP`, `BOTTOM`, `SIDE_Y+`, ... from the host's faces), `Direction` (`X`, `Y`, `Z` in the host frame), `Cover`
  (mm, measured to the nearest face), `CoverCheck` (`OK` / `LOW` against `XR_ConcreteSpec.CoverNominal`).
- Matching order: IFC relationships; then geometry (the bar's centreline inside the host solid shrunk by half the cover, with a
  tolerance; BVH queries); then marks in names (bar mark references a host mark); then the decision model to break a tie
  between 2-3 candidate hosts ("Which element does this bar reinforce?" with the candidates' role, mark and position as
  options); bars crossing a joint (starter bars) link to both with `Layer = JOINT`.
- The host's `XR_ConcreteReinforcement` gets the matched counts, mass and ratio.

Everything in section 3 is designed so this matcher needs nothing else: marks, frames, faces, cover and supports are there.

## 6. Queries, tree and viewer

- Queries: `count where ConcreteElement = 'SUSPENDED_SLAB'`, `sum XR_ConcreteGeometry.Volume by XR_ConcreteSpec.StrengthClass`,
  `where XR_ConcreteSpec.ExposureClass contains 'XD'`, `sum FormworkArea by Storey`.
- The standard tree gains a preset **Concrete**: Method › Element role › Strength class › element (by mark), with volume and
  formwork area totals on each node.
- Colour by any concrete facet; "Concrete" quantity summary: volume, formwork area and estimated reinforcement mass by storey
  and role (exportable CSV).
- 4D: the formwork rule of temporary works uses `FormworkArea` faces, and falsework uses SUSPENDED_SLAB / TRANSFER_* with
  `Supports`; pour groups can become 4D pour activities later.

## 7. Decision-model questions

Asked only where rules leave the answer open, once per signature, with calibration and review like the other facets:
1. Element role: options = the codes of 3.1 allowed for the IFC class (a slab is never asked "COLUMN").
2. Method: CAST_IN_PLACE / PRECAST / POST_TENSIONED / TILT_UP / COMPOSITE_DECK.
3. Reinforcement type: REINFORCED / POST_TENSIONED / FIBRE / PLAIN.
4. Slab scheme: ONE_WAY / TWO_WAY (with the measured span ratio in the state).
5. Exposure: never decided by the model; it only suggests, review required (a wrong exposure class is a durability error).

Strength class, cover and fire resistance are read or looked up, never guessed by a model.

## 8. Order of work

1. `XR_ConcreteGeometry` (measured frames, faces, volume, formwork area, supports, pour groups) and `XR_ConcreteElement.Mark`.
2. `XR_ConcreteElement` and `XR_ConcreteMethod` (rules, then model), `XR_ConcreteSpec` (IFC, parsing, tables), `XR_ConcreteReinforcement`
   intent and estimates.
3. The Concrete tree preset, colour, and the concrete quantity summary.
4. Later: the rebar matcher (section 5).
