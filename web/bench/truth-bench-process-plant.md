# Truth bench: process plant

**Read this first.** The classifier rules (and so every `hybrid-*` arm, which uses a final rule as it is) were tuned on THIS plant, against THIS truth, in the same work that produced this table. Rules that match the truth's conventions make their own score circular: `rules` at about 100% and every hybrid at about 100% measure how well the rules were fitted to one synthetic unit, not how well they classify a plant they have not seen. The shipped temperatures were also fitted on this plant (5-fold cross-validation by signature, so the temperature numbers are out of fold, the rule numbers are not). The honest estimate of a hybrid is the reference row **"hybrid-d3, OLD rules (offline)"**: the rules as they were BEFORE this tuning (bench-truth, old rules), recombined offline with the current d3 results (the rule when it was final, else d3). It is an offline recombination, not a run of the app. The model-only arms (`xsmall`, `base2`, `d3*`) never see the rules and are the non-circular numbers.

Truth: `models/Process-Plant.truth.json` (tools/make_process_plant_ifc.py --seed 1; design intent set when each element was created, no classifier output used). 1294 elements in 114 signatures, scored per element. "cal" = shipped temperatures (the app's `auto` mode), "raw" = T 1. Lenient also accepts the truth's alternative. cover and prec at minConfidence 0.6. GEN rate = share of answers that are the fallback (GEN, or GEN/UNC for the chained sub question). Rules and majority have confidence 1 (majority: the class share). Data: `bt3/truth-bench.json`.

Arms: rules; majority (trivial baseline); xsmall = deberta-v3-xsmall-zeroshot-v1.1 (app default); base2 = deberta-v3-base-zeroshot-v2.0; d3 = d3-edge, text state, 2000 byte cap (as the app sends it); d3-psets = d3 with the cap raised so no signature is truncated; d3-svg = d3 plus the app's SVG of the element alone; d3-svg-ctx = d3 plus the SVG of the element in its bounding box with its neighbours; d3-svg-ctx-psets = the same with full property sets; hybrid-* = the app's pipeline (a final rule is used as it is, the model answers the rest).

**d3-psets is identical to d3, and d3-svg-ctx-psets to d3-svg-ctx, by construction**: no signature's state reaches the 2000 byte cap (largest full state 597 bytes), so the raised cap changes nothing and the runs are cache hits of their twins (see the state report below).

## Summary

Best model-only discipline (cal, strict): d3 82.5%. Best model-only sub_chained (cal, strict): d3 63.2%. Best model-only division (cal, strict): d3 28.7%.
Geometry did not help d3 on this plant: the SVG arms are far below the text baseline (discipline strict d3 82.5%, d3-svg 41.2%, d3-svg-ctx 31.7%) and the model answers GEN far more often (10% of elements for d3, 58% for d3-svg, 68% for d3-svg-ctx). The hybrids are then equal to each other (the rules decide almost every element).

## Discipline

| arm | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN rate |
|---|---|---|---|---|---|---|
| rules | 99.9% | 99.9% | 99.9% | 100.0% | 0.00 | 0.1% |
| majority | 49.6% | 49.6% | 0.0% | - | 0.00 | 0.0% |
| xsmall cal | 52.2% | 52.2% | 0.0% | - | 0.49 | 0.0% |
| xsmall raw | 52.2% | 52.2% | 0.0% | - | 0.54 | 0.0% |
| base2 cal | 63.4% | 63.4% | 71.3% | 87.7% | 0.24 | 10.5% |
| base2 raw | 54.3% | 54.3% | 27.3% | 78.8% | 0.26 | 10.5% |
| d3 cal | 82.5% | 82.5% | 53.8% | 83.2% | 0.21 | 10.4% |
| d3 raw | 82.5% | 82.5% | 53.8% | 83.2% | 0.21 | 10.4% |
| d3-psets cal | 82.5% | 82.5% | 53.8% | 83.2% | 0.21 | 10.4% |
| d3-psets raw | 82.5% | 82.5% | 53.8% | 83.2% | 0.21 | 10.4% |
| d3-svg cal | 41.2% | 41.2% | 34.2% | 45.0% | 0.34 | 57.9% |
| d3-svg raw | 41.2% | 41.2% | 34.2% | 45.0% | 0.34 | 57.9% |
| d3-svg-ctx cal | 31.7% | 31.7% | 15.0% | 23.7% | 0.40 | 67.9% |
| d3-svg-ctx raw | 31.7% | 31.7% | 15.0% | 23.7% | 0.40 | 67.9% |
| d3-svg-ctx-psets cal | 31.7% | 31.7% | 15.0% | 23.7% | 0.40 | 67.9% |
| d3-svg-ctx-psets raw | 31.7% | 31.7% | 15.0% | 23.7% | 0.40 | 67.9% |
| hybrid-xsmall cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-xsmall raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3 cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3 raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3, OLD rules (offline) cal | 79.1% | 79.1% | 86.2% | 80.6% | 0.20 | 1.2% |
| hybrid-d3, OLD rules (offline) raw | 79.1% | 79.1% | 86.2% | 80.6% | 0.20 | 1.2% |

## Sub-discipline, chained (right only when discipline and sub match)

| arm | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN rate |
|---|---|---|---|---|---|---|
| rules | 99.9% | 99.9% | 99.9% | 100.0% | 0.00 | 0.1% |
| majority | 20.4% | 20.4% | 0.0% | - | 0.21 | 0.0% |
| xsmall cal | 9.1% | 9.1% | 0.0% | - | 0.06 | 0.0% |
| xsmall raw | 9.1% | 9.1% | 0.0% | - | 0.06 | 0.0% |
| base2 cal | 33.3% | 33.3% | 20.5% | 36.2% | 0.21 | 10.5% |
| base2 raw | 20.6% | 20.6% | 4.3% | 89.3% | 0.13 | 10.5% |
| d3 cal | 63.2% | 63.5% | 63.8% | 79.5% | 0.23 | 10.4% |
| d3 raw | 63.2% | 63.5% | 86.3% | 69.4% | 0.24 | 10.4% |
| d3-psets cal | 63.2% | 63.5% | 63.8% | 79.5% | 0.23 | 10.4% |
| d3-psets raw | 63.2% | 63.5% | 86.3% | 69.4% | 0.24 | 10.4% |
| d3-svg cal | 39.3% | 39.3% | 56.2% | 66.3% | 0.49 | 57.9% |
| d3-svg raw | 39.3% | 39.3% | 95.1% | 40.5% | 0.47 | 57.9% |
| d3-svg-ctx cal | 31.5% | 31.5% | 21.9% | 47.9% | 0.31 | 67.9% |
| d3-svg-ctx raw | 31.5% | 31.5% | 93.2% | 33.8% | 0.46 | 67.9% |
| d3-svg-ctx-psets cal | 31.5% | 31.5% | 21.9% | 47.9% | 0.31 | 67.9% |
| d3-svg-ctx-psets raw | 31.5% | 31.5% | 93.2% | 33.8% | 0.46 | 67.9% |
| hybrid-xsmall cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-xsmall raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3 cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3 raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3, OLD rules (offline) cal | 73.1% | 73.4% | 91.0% | 79.5% | 0.22 | 1.2% |
| hybrid-d3, OLD rules (offline) raw | 73.1% | 73.4% | 95.8% | 76.0% | 0.24 | 1.2% |

## Sub-discipline, oracle (asked under the true discipline)

| arm | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN rate |
|---|---|---|---|---|---|---|
| rules | 99.9% | 99.9% | 99.9% | 100.0% | 0.00 | 0.1% |
| majority | 54.9% | 54.9% | 34.3% | 81.5% | 0.00 | 0.1% |
| xsmall cal | 18.9% | 18.9% | 3.8% | 100.0% | 0.15 | 0.1% |
| xsmall raw | 18.9% | 18.9% | 3.8% | 100.0% | 0.15 | 0.1% |
| base2 cal | 52.3% | 52.3% | 19.9% | 96.5% | 0.15 | 0.1% |
| base2 raw | 52.3% | 52.3% | 16.9% | 100.0% | 0.19 | 0.1% |
| d3 cal | 74.2% | 74.5% | 84.0% | 77.2% | 0.13 | 0.1% |
| d3 raw | 74.2% | 74.5% | 92.3% | 76.4% | 0.25 | 0.1% |
| d3-psets cal | 74.2% | 74.5% | 84.0% | 77.2% | 0.13 | 0.1% |
| d3-psets raw | 74.2% | 74.5% | 92.3% | 76.4% | 0.25 | 0.1% |
| d3-svg cal | 69.6% | 69.9% | 79.0% | 76.5% | 0.15 | 0.1% |
| d3-svg raw | 69.6% | 69.9% | 84.8% | 76.7% | 0.21 | 0.1% |
| d3-svg-ctx cal | 64.2% | 64.5% | 57.3% | 65.9% | 0.20 | 0.1% |
| d3-svg-ctx raw | 64.2% | 64.5% | 82.6% | 70.3% | 0.24 | 0.1% |
| d3-svg-ctx-psets cal | 64.2% | 64.5% | 57.3% | 65.9% | 0.20 | 0.1% |
| d3-svg-ctx-psets raw | 64.2% | 64.5% | 82.6% | 70.3% | 0.24 | 0.1% |
| hybrid-xsmall cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-xsmall raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3 cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3 raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx cal | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3-svg-ctx raw | 100.0% | 100.0% | 100.0% | 100.0% | 0.09 | 0.1% |
| hybrid-d3, OLD rules (offline) cal | 73.6% | 74.0% | 92.4% | 78.6% | 0.19 | 0.1% |
| hybrid-d3, OLD rules (offline) raw | 73.6% | 74.0% | 96.1% | 76.7% | 0.23 | 0.1% |

## Division (MasterFormat, ungated)

| arm | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN rate |
|---|---|---|---|---|---|---|
| rules | 99.9% | 99.9% | 99.9% | 100.0% | 0.00 | 0.1% |
| majority | 49.8% | 50.2% | 0.0% | - | 0.00 | 0.0% |
| xsmall cal | 19.7% | 22.7% | 0.0% | - | 0.12 | 0.0% |
| xsmall raw | 19.7% | 22.7% | 0.0% | - | 0.12 | 0.0% |
| base2 cal | 22.1% | 28.1% | 11.4% | 7.5% | 0.27 | 0.0% |
| base2 raw | 22.1% | 28.1% | 11.4% | 7.5% | 0.27 | 0.0% |
| d3 cal | 28.7% | 29.4% | 19.1% | 85.0% | 0.17 | 0.0% |
| d3 raw | 28.7% | 29.4% | 19.1% | 85.0% | 0.17 | 0.0% |
| d3-psets cal | 28.7% | 29.4% | 19.1% | 85.0% | 0.17 | 0.0% |
| d3-psets raw | 28.7% | 29.4% | 19.1% | 85.0% | 0.17 | 0.0% |
| d3-svg cal | 14.8% | 14.8% | 0.0% | - | 0.28 | 0.0% |
| d3-svg raw | 14.8% | 14.8% | 0.0% | - | 0.28 | 0.0% |
| d3-svg-ctx cal | 14.3% | 14.3% | 0.0% | - | 0.17 | 0.0% |
| d3-svg-ctx raw | 14.3% | 14.3% | 0.0% | - | 0.17 | 0.0% |
| d3-svg-ctx-psets cal | 14.3% | 14.3% | 0.0% | - | 0.17 | 0.0% |
| d3-svg-ctx-psets raw | 14.3% | 14.3% | 0.0% | - | 0.17 | 0.0% |
| hybrid-xsmall cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-xsmall raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3 cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3 raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3-svg cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3-svg raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3-svg-ctx cal | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3-svg-ctx raw | 99.9% | 99.9% | 99.9% | 100.0% | 0.09 | 0.0% |
| hybrid-d3, OLD rules (offline) cal | 62.0% | 62.6% | 79.0% | 78.5% | 0.22 | 0.0% |
| hybrid-d3, OLD rules (offline) raw | 62.0% | 62.6% | 79.0% | 78.5% | 0.22 | 0.0% |

## Cost

| arm | mean state tokens (d3 tokenizer) | mean state bytes | s/sig (app path) |
|---|---|---|---|
| rules | - | - | 0.0 |
| majority | - | - | 0.0 |
| xsmall | - | 425 | 1.0 |
| base2 | - | 425 | 3.8 |
| d3 | 167 | 425 | 8.0 |
| d3-psets | 167 | 425 | 8.0 |
| d3-svg | 333 | 806 | 9.8 |
| d3-svg-ctx | 1200 | 2547 | 20.9 |
| d3-svg-ctx-psets | 1200 | 2547 | 20.9 |
| hybrid-xsmall | - | 425 | 0.0 |
| hybrid-d3 | 167 | 425 | 0.1 |
| hybrid-d3-svg | 333 | 806 | 0.1 |
| hybrid-d3-svg-ctx | 1200 | 2547 | 0.2 |

Tokens are the Qwen tokenizer on the state text that d3 reads (SVG included); hybrid arms show the state of the few elements that reach the model. s/sig is the mean wall time per signature of the app path (main plus chained sub request) on 4 CPU cores with onnxruntime-node, fp32; the context SVG request needed up to about 8 GB.

## Effect of the refitted temperatures (cal, per element, before and after)

| arm, question | old temperatures: cover / prec / ECE | refitted: cover / prec / ECE |
|---|---|---|
| xsmall, discipline | 0.0% / - / 0.54 | 0.0% / - / 0.49 |
| xsmall, sub_chained | 0.9% / 0.0% / 0.19 | 0.0% / - / 0.06 |
| base2, discipline | 71.3% / 87.7% / 0.24 | 71.3% / 87.7% / 0.24 |
| base2, sub_chained | 20.5% / 36.2% / 0.21 | 20.5% / 36.2% / 0.21 |
| d3, discipline | 25.0% / 100.0% / 0.35 | 53.8% / 83.2% / 0.21 |
| d3, sub_chained | 72.0% / 82.4% / 0.15 | 63.8% / 79.5% / 0.23 |

"Old" is the first run of this bench (shipped temperatures fitted on rule labels), "refitted" the current run (see calibrationDefaults.ts).

## Geometry flips against d3 text only (strict, per signature, cal)

- d3-svg, discipline: 1 signatures wrong to right, 55 right to wrong. Wrong to right: IfcBuildingElementProxy Drain trench (concrete channel) (10): PLB -> CIV. Right to wrong: IfcColumn UC 305x305x97 (24): STR -> GEN; IfcBeam UB 457x191x67 (68): STR -> GEN; IfcBeam UB 305x165x40 (5): STR -> GEN; IfcSlab Steel grating 2.0 x 2.0 (12): STR -> GEN.
- d3-svg, sub_chained: 1 signatures wrong to right, 36 right to wrong. Wrong to right: IfcBuildingElementProxy Drain trench (concrete channel) (10): PLB/DRN -> CIV/DRN. Right to wrong: IfcColumn UC 305x305x97 (24): STR/COL -> GEN/UNC; IfcBeam UB 457x191x67 (68): STR/BEM -> GEN/UNC; IfcBeam UB 305x165x40 (5): STR/BEM -> GEN/UNC; IfcSlab Steel grating 2.0 x 2.0 (12): STR/SLB -> GEN/UNC.
- d3-svg-ctx, discipline: 0 signatures wrong to right, 63 right to wrong. Right to wrong: IfcSlab Road (concrete) (2): CIV -> GEN; IfcColumn UC 305x305x97 (24): STR -> GEN; IfcColumn SHS 300x300 (6): STR -> GEN; IfcBeam UB 305x165x40 (5): STR -> GEN.
- d3-svg-ctx, sub_chained: 0 signatures wrong to right, 44 right to wrong. Right to wrong: IfcSlab Road (concrete) (2): CIV/PAV -> GEN/UNC; IfcColumn UC 305x305x97 (24): STR/COL -> GEN/UNC; IfcColumn SHS 300x300 (6): STR/COL -> GEN/UNC; IfcBeam UB 305x165x40 (5): STR/BEM -> GEN/UNC.

d3-svg and d3-svg-ctx lose almost entirely on the structural steel, slabs and members that the text state gets right: the extra SVG text is out of distribution for d3-edge and it answers GEN. The one gain is the drain trench (PLB to CIV), where the shape text helps.

## What d3's state holds, and what the cap cuts

The state is JSON: class, name, type (class and name), psets (Attr plus the element's property sets and quantities), hierarchy (storey), parents (the host or parent element with its psets), systems, building_context; an SVG geometry arm prepends a legend and the SVG text after the cap has been applied. **At the app's 2000 byte cap 0 of the 114 signatures are truncated** (the largest full state is 597 bytes), so d3-psets cannot differ from d3 on this plant. The only example of loss is a cap well below the default (500 bytes, 12 of 114 signatures cut): the window state loses the GlazingAreaFraction property and its parent wall's property sets (full 597 B against cut 405 B, below).

```
114 representatives. Full state (level 0): min 301 B, median 437 B, max 597 B, mean 425 B
Top-level keys of the full states: class, name, type, psets, hierarchy, building_context, parents, systems

cap 2000 B: 0 of 114 truncated

cap 1000 B: 0 of 114 truncated

cap 500 B: 12 of 114 truncated; lost (key group: signatures): psets.Pset_DoorCommon.*: 3; psets.Pset_WindowCommon.*: 1; psets.Pset_PipeSegmentTypeCommon.*: 32
  example Window WIN-03
  full 597 B: {"class":"IfcWindow","name":"Window WIN-03","type":{"class":"IfcWindowType","name":"Double glazing 1.6 x 1.2"},"psets":{"Attr":{"ObjectType":"Double glazing 1.6 x 1.2","Tag":"WIN-03","PredefinedType":"WINDOW"},"Pset_WindowCommon":{"GlazingAreaFraction":0.8,"IsExternal":true,"Reference":"W-16"}},"hierarchy":["IfcBuildingStorey: Grade +0.0"],"parents":[{"class":"IfcWall","name":"Control building wall S","psets":{"Attr":{"ObjectType":"Masonry 300 mm","Tag":"W-S","PredefinedType":"STANDARD"},"Pset_WallCommon":{"IsExternal":true,"LoadBearing":true,"FireRating":"EI30"}}}],"building_context":true}
  cut  405 B: {"class":"IfcWindow","name":"Window WIN-03","type":{"class":"IfcWindowType","name":"Double glazing 1.6 x 1.2"},"psets":{"Attr":{"ObjectType":"Double glazing 1.6 x 1.2","Tag":"WIN-03","PredefinedType":"WINDOW"},"Pset_WindowCommon":{"IsExternal":true,"Reference":"W-16"}},"hierarchy":["IfcBuildingStorey: Grade +0.0"],"parents":[{"class":"IfcWall","name":"Control building wall S"}],"building_context":true}

Largest full state (597 B, Window WIN-03): {"class":"IfcWindow","name":"Window WIN-03","type":{"class":"IfcWindowType","name":"Double glazing 1.6 x 1.2"},"psets":{"Attr":{"ObjectType":"Double glazing 1.6 x 1.2","Tag":"WIN-03","PredefinedType":"WINDOW"},"Pset_WindowCommon":{"GlazingAreaFraction":0.8,"IsExternal":true,"Reference":"W-16"}},"hierarchy":["IfcBuildingStorey: Grade +0.0"],"parents":[{"class":"IfcWall","name":"Control building wall S","psets":{"Attr":{"ObjectType":"Masonry 300 mm","Tag":"W-S","PredefinedType":"STANDARD"},"Pset_WallCommon":{"IsExternal":true,"LoadBearing":true,"FireRating":"EI30"}}}],"building_context":true}
```
