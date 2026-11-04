# X-ray reference implementation: specification

Reference implementation of the BIM X-ray mode described in the report
"BIM X-Ray Vision: Technical Implementation Report". It targets small IFC
files (converted offline to glb plus a JSON sidecar) and arbitrary glb files,
rendered in WebGL with three.js.

Report summary, so this file stands alone:

- Focus: objects of interest (the selected MEP run). Drawn opaque, in front.
- Context: objects eligible to ghost (concrete structure on nearby storeys).
- Host: context objects that intersect or contain a focus object.
- Near: context objects within a buffer radius of a focus object, not Host.
- Far: remaining context. Drawn normally or hidden. Never ghosted.
- Occluders = Host + Near. Only these change alpha.
- Algorithm 1 (static): classify into buckets, compute proximityWeight in [0,1].
- Algorithm 2 (per camera move): sample focus surfaces, cast rays to the
  camera, count hits per occluder, occlusion = hits / samples,
  importance = occlusion^gamma * proximityWeight,
  target = alphaMax + (alphaMin - alphaMax) * importance,
  clamp to opacity floor, then smooth: alpha += k * (target - alpha).
- Algorithm 3: coarse-to-fine candidate filtering (AABB, then OBB/mesh).
- Algorithm 7: opacity floors from pins (user, category, viewpoint).
- Algorithms 8/9 (stretch): category tiers, e.g. steel > pipes > concrete.

## Stack

| Concern | Choice | Why |
| --- | --- | --- |
| IFC to glb | Python 3.13, ifcopenshell 0.9 | Robust geometry with openings applied, full relationship access |
| Viewer | three.js 0.187, TypeScript, Vite 8 | Fastest mainstream WebGL path; one merged geometry, one draw call per pass |
| Ray casting | three-mesh-bvh 0.9 | All-hits accelerated raycast for sightline sampling |
| Tests | vitest 5 | Pure-TS algorithm tests, no GPU |
| UI | lil-gui | Parameter sliders and toggles |
| Headless check | Preinstalled Playwright Chromium with swiftshader | Screenshots and FPS in CI-like runs |

Package versions are pinned in `web/package.json`. Do not add npm
dependencies without noting it in your report. Do not run `npm install`
concurrently with another agent; if you must add a package, add it with
`npm install --save <pkg>@<version>` once and say so.

## Repository layout

```
xray-ref/
  SPEC.md                      this file
  models/*.ifc                 public IFC inputs (buildingSMART Simple-Scene set)
  tools/ifc2glb.py             converter: IFC -> glb + model.json         [Agent A]
  tools/synth_model.py         synthetic benchmark model generator        [Agent A]
  web/
    package.json, tsconfig.json
    public/models/*.glb, *.json   converter output                        [Agent A]
    src/types.ts               shared contracts (fixed; do not change shape without noting)
    src/algo/classify.ts       Algorithm 1 + 3                              [Agent C]
    src/algo/sightlines.ts     Algorithm 2                                  [Agent C]
    src/algo/overrides.ts      Algorithm 7                                  [Agent C]
    src/algo/tiers.ts          Algorithms 8/9 (stretch)                     [Agent C]
    src/model/loader.ts        glb + json -> SceneModel + geometry          [Agent B]
    src/model/ifcImport.ts     RawModel[] -> glb + sidecar -> LoadedModel; worker client   [Agent P]
    src/model/ifcRaw.ts        web-ifc extraction to RawModel (worker side)                [Agent P]
    src/plugins/fileLoader.ts  "Open model" panel folder, file picker, drag and drop       [Agent P]
    src/render/geometry.ts     GeometryProvider over merged geometry + BVH  [Agent B]
    src/render/renderer.ts     ghost pass, focus pass, edge pass            [Agent B]
    src/app.ts, index.html     integration, UI, debug overlay               [Agent D]
    tests/*.test.ts            vitest                                        [Agent C, D]
    bench/                     headless FPS and timing scripts              [Agent D]
```

## Model format

### glb

- One glTF node per element. `node.name` = IFC GlobalId (or any unique string for non-IFC glb).
- `node.extras = { id: number, ifcClass: string }` where `id` is the index into `model.json.elements`.
- One mesh per node, one primitive, triangles, `POSITION` and `NORMAL`, `uint32` indices.
- Units metres, Z up in the IFC sense converted to glTF Y up by the converter
  (rotate -90 degrees about X). Model shifted so its bounds centre is near the origin;
  the shift is recorded in `model.json.originShift`.
- Base colour per element stored in `model.json.elements[i].color` (RGBA 0..1), not in glTF materials,
  so the viewer owns all material state.

### model.json (sidecar)

```json
{
  "schema": "xray-model/1",
  "source": { "files": ["Building-Structural.ifc"], "converter": "ifc2glb.py", "ifcSchema": "IFC4" },
  "units": "m",
  "originShift": [x, y, z],
  "storeys": [ { "id": 0, "name": "Level 1", "elevation": 0.0 } ],
  "elements": [
    {
      "id": 0,
      "globalId": "2O2Fr$t4X7Zf8NOew3FLOH",
      "expressId": 123,
      "ifcClass": "IfcSlab",
      "name": "Slab:Generic 250mm",
      "storey": 0,
      "material": "Concrete",
      "color": [0.8, 0.8, 0.8, 1.0],
      "bounds": [minx, miny, minz, maxx, maxy, maxz],
      "file": "Building-Structural.ifc"
    }
  ],
  "relations": {
    "voids": [[hostId, openingExpressId]],
    "fills": [[openingExpressId, fillerId]],
    "hosts": [[fillerId, hostId]],
    "ports":  [[elementIdA, elementIdB]],
    "systems": [ { "name": "Supply Air", "elements": [3, 4, 5] } ]
  }
}
```

- `bounds` are in the glb coordinate frame (after shift and Y-up conversion).
- `hosts` is derived by the converter from voids and fills: filler -> opening -> host.
- `ports` are element-level pairs derived from IfcRelConnectsPorts / IfcDistributionPort.
- Opening elements (IfcOpeningElement) are not exported as geometry.
- A glb without a sidecar is still loadable: the loader synthesises elements from nodes,
  with `ifcClass` taken from `extras.ifcClass`, else guessed from the node name
  (contains "slab", "wall", "beam", "column", "duct", "pipe", "tray"), else "Unknown".

### Opening files in the browser

The viewer can also produce this format itself, from the user's own files (`src/plugins/fileLoader.ts`, `src/model/ifc*.ts`):

- `.ifc` / `.ifczip` are read in the browser with web-ifc 0.0.78 (MPL-2.0) in a module Web Worker (`ifcRaw.ts` is the web-ifc
  side, `ifcWorker.ts` the worker), which returns a neutral `RawModel` per file: elements with world Z-up metre geometry, storeys,
  voids, fills, element-level ports and systems, keyed by express id. `build` in `ifcImport.ts` is pure TypeScript and applies the
  converter's conventions (`tools/ifc2glb.py` is the reference): the skip list of classes (`IfcOpeningElement`, `IfcSpace`,
  `IfcSite`, `IfcBuilding`, `IfcBuildingStorey`, `IfcAnnotation`, `IfcSpatialZone`, `IfcExternalSpatialElement`, `IfcGrid`,
  `IfcVirtualElement`) and the `origin` / `geo-reference` marker proxies, Z-up to Y-up by rotating vertex data, the overall bounds
  centre shifted to the origin (`originShift`), vertex normals welded and smoothed with a 30 degree crease, storey by containment
  (walking aggregates up) with the nearest-storey-at-or-below fallback, `hosts` from voids and fills, `ports` resolved to element
  pairs, systems from `IfcRelAssignsToGroup`, class-default colours where the file has no surface style.
- Several IFC files are federated exactly as the converter does: consecutive element ids, storeys merged by name and elevation
  within 1 cm, an element with the same GlobalId, class and bounds as an earlier one is skipped, the same GlobalId with different
  geometry is renamed `<GlobalId>~<n>`.
- The result goes through the same path as a converted model: `build` writes glb bytes and the `xray-model/1` sidecar in memory
  (`source.converter` is `web-ifc 0.0.78 (in-browser)`) and calls `parseModel(glb, sidecar)`. A `.glb` (optionally with a
  `.json` sidecar of the same base name, or any `.json` whose `schema` is `xray-model/1`) goes straight to `parseModel`.
- Parity with the converter is a test (`web/tests/ifc-import-parity.test.ts`): same class counts, element bounds within 1 cm,
  same relation counts, storeys and materials. Documented differences: colours come from web-ifc (surface colour; the converter
  uses ifcopenshell's diffuse colour and its built-in per-class colours for unstyled elements), and meshes are not byte-identical.

## Shared contracts

See `web/src/types.ts`. The important ones:

- `SceneModel`: elements, storeys, relations, as above, plus `byGlobalId`.
- `GeometryProvider`: what the algorithms need from geometry. Implemented by Agent B over
  merged geometry and a BVH. Agent C tests it with a simple box-based mock.
- `ClassificationSettings`, `Classification`, `SightlineSettings`, `OverrideSettings`.
- `RenderState`: per-element alpha, colour, flags that the renderer uploads each frame.

## Defaults (from the report)

| Parameter | Default |
| --- | --- |
| ctxClasses | IfcSlab, IfcWall, IfcWallStandardCase, IfcBeam, IfcColumn, IfcFooting, IfcStair, IfcRoof |
| focusClasses | IfcDuctSegment, IfcDuctFitting, IfcPipeSegment, IfcPipeFitting, IfcCableCarrierSegment, IfcCableCarrierFitting, IfcFlowSegment, IfcFlowFitting, IfcFlowTerminal |
| storeyBand | 1 |
| bufferBase, bufferScale | 0.30 m, 0.50 |
| bufferLo, bufferHi | 0.30 m, 1.50 m |
| samplesPerObject, maxSamples | 64, 500 |
| alphaMin, alphaMax | 0.15, 0.85 |
| gamma | 0.5 |
| smoothingRate | 0.20 |
| userPinFloor | 0.60 |
| edgeAlpha | 0.80 |
| occluderScope, farWeight | all, 0.7 (deviation, see README) |
| layerWeighting, layerFalloff, layerBudget | front, 0.5, 2 (deviation, see README) |
| farMode | opaque |
| ghostColour | cool grey, 20% saturation |

## Rendering design (Agent B)

- Merge all element geometry into one `BufferGeometry` with an `elementId` float attribute
  (one value per vertex). Keep `groups` or an index-range table per element for picking.
- Per-element state lives in a `DataTexture` (RGBA float or 8-bit) indexed by element id:
  colour rgb, alpha, and a flags channel (bit 0 focus, bit 1 hidden, bit 2 pinned, bit 3 selected).
  Uploading the texture is the only per-frame GPU update.
- Three passes over the same geometry, each a `ShaderMaterial` with `onBeforeCompile` or custom GLSL:
  1. Opaque pass: elements with alpha >= 0.999 and not focus. depthWrite on.
  2. Ghost pass: elements with alpha < 0.999 and not focus. depthWrite off, normal blending,
     premultiplied alpha, Fresnel boost `alpha = mix(alpha, 1.0, 0.6 * pow(1 - |n.v|, 3))`,
     backface culling on.
  3. Focus pass: focus elements, opaque, `depthFunc` Always when "in front" is on, else LessEqual.
- Edge pass: `EdgesGeometry` per element (threshold 30 degrees) merged into one `LineSegments`
  with the same `elementId` attribute, drawn after the ghost pass with alpha = max(edgeAlpha, element alpha),
  hidden when the element is hidden.
- Sorting: single merged geometry means no per-object sort. The ghost pass uses weighted blended order-independent transparency (McGuire and Bavoil 2013) when float colour buffers are available, so blend order no longer matters; with it off, blend-order artifacts are expected.
- `GeometryProvider` uses three-mesh-bvh on the merged geometry with `firstHitOnly = false`
  and maps triangle index -> element id through the range table. `surfaceDistance` may use
  `closestPointToGeometry` between per-element sub-geometries, or a bounds-based lower bound
  with a mesh refinement only when the bound is below the buffer.

## Acceptance criteria

1. `npm run typecheck`, `npm test`, `npm run build` pass.
2. `python3 tools/ifc2glb.py models/Building-Structural.ifc models/Building-Architecture.ifc models/Building-Hvac.ifc -o web/public/models/building`
   produces `building.glb` and `building.json` with every IfcWall, IfcSlab, IfcBeam, IfcFooting and
   IfcDuctSegment present, correct storeys, and non-degenerate bounds.
3. Opening `/` shows the building model. Clicking the duct makes it Focus. Slabs and beams it
   passes near ghost with edges visible. Orbiting changes alpha smoothly with no popping.
4. Algorithm tests reproduce the report's worked example on synthetic boxes:
   S1 (slab penetrated) Host weight 1.0; B1 (beam 0.20 m away, buffer 0.60) Near weight 0.741 +/- 0.01;
   W1 (wall 0.55 m away) Near weight 0.02 +/- 0.01; C1 (column 3.0 m away) Far.
   Sightlines from above: S1 occlusion about 0.75, target alpha about 0.24.
5. Benchmark on the synthetic 5,000-element model at 1920x1080 in headless Chromium: report
   frame time, Algorithm 2 time for 300 samples, and Algorithm 1 time. Targets on a laptop GPU:
   16 ms frame, 5 ms sightlines, 50 ms classification. Record actual numbers in `bench/RESULTS.md`
   with the note that swiftshader numbers are not GPU numbers.
6. `README.md` at the repo root: how to convert, run, test, bench, and a short map of the code to the report's algorithms.

## Reporting

Each agent ends with: files written, commands run and their output (truncated), what passes,
what does not, and any deviation from this spec with the reason.
