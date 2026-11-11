# Truth bench: water-works

Truth: /home/user/xray-ref/models/independent/Water-Works.truth.json (tools/make_independent_plant_ifc.py --seed 1 (independent water treatment works; labels set at element creation, not in the IFC); Labels are design intent, set where each element is created, from the descriptions in default-schema.json only (not from any classifier rule, and not in the IFC). A pipe, fitting or valve takes the line it belongs to: process and chemical lines inside the works are PIP/PRC (division 40), instrument air and air-scour lines PIP/UTL, manual valves PIP/VLV, hangers and sleepers PIP/SUP; buried yard mains and sewers are CIV/UTL or CIV/DRN (division 33); piping inside the administration building follows its trade (MEC/HYD, PLB/SUP, PLB/DRN, PLB/STM, FPR/SPR). Process pumps, blowers, filters and chemical tanks are PIP (division 43; 46 for treatment equipment such as filters, mixers and scrapers). Motors are ELE/PWR. Control valves, transmitters and analysers are INS (division 40; 25 for controllers and junction boxes). Equipment plinths outside buildings are CIV/FND, inside buildings STR/FND. Concrete basin floors are STR/SLB and basin walls STR/WLS. Paving and kerbs are CIV/PAV (32), fence, gate and trees CIV/LND. Wherever a second answer is defensible it is listed in alt: subDiscipline (same discipline) and division are used by the lenient column; alt.discipline and alt.also (cross-discipline "DISC/sub" pairs) are informational only. Elements with no name, or a proxy class where a proper one exists, keep the label of what they really are.). 1469 elements with truth in 371 signatures; 0 elements without truth, 0 truth entries without an element.
"cal" = shipped temperatures (the app's auto mode), "raw" = T 1. Strict/lenient: lenient also accepts the truth's alt. cover/prec at minConfidence 0.6. s/sig = seconds per signature on the app's path (main + chained sub request). Rules and majority have confidence 1 (majority: the class share); a rules no-match is an abstain.

## Summary (per element)

Strict accuracy per question; cover/prec at 0.6 for the discipline and the chained sub-discipline; ECE and GEN/UNC rate of the discipline; mean state bytes and tokens of the representative (tokens: d3 arms, the Qwen tokenizer on the state text); s/sig as in the tables below. hybrid-*: the app's pipeline with final rules, see the arm list in bench/real-classify-truth.mjs.

| arm | discipline | sub chained | sub oracle | division | division (app) | disc cover | disc prec | sub cover | sub prec | disc ECE | disc GEN | state B | state tok | s/sig |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rules | 66.6% | 62.0% | 63.2% | 55.4% | 55.4% | 92.6% | 71.9% | 92.3% | 67.2% | 0.28 | 7.4% |  |  | 0.0 |
| majority | 24.3% | 12.4% | 46.2% | 23.9% | 23.9% | 0.0% | - | 0.0% | - | 0.00 | 0.0% |  |  | 0.0 |
| xsmall cal | 41.9% | 15.5% | 31.9% | 26.0% | 26.0% | 0.0% | - | 0.0% | - | 0.28 | 0.3% | 230 |  | 4.6 |
| xsmall raw | 41.1% | 15.2% | 31.9% | 26.0% | 26.0% | 1.5% | 0.0% | 0.0% | - | 0.26 | 0.3% | 230 |  |  |
| base2 cal | 60.7% | 43.8% | 63.5% | 36.1% | 36.1% | 82.4% | 68.6% | 38.0% | 71.3% | 0.16 | 0.1% | 230 |  | 5.3 |
| base2 raw | 60.9% | 36.4% | 63.5% | 36.1% | 36.1% | 32.2% | 83.7% | 15.9% | 85.0% | 0.12 | 0.7% | 230 |  |  |
| d3 cal | 59.4% | 55.3% | 85.2% | 41.8% | 32.9% | 40.4% | 80.4% | 60.3% | 72.5% | 0.10 | 19.7% | 230 | 84 | 8.7 |
| d3 raw | 59.4% | 55.3% | 85.2% | 41.8% | 32.9% | 40.4% | 80.4% | 76.9% | 63.3% | 0.10 | 19.7% | 230 | 84 |  |
| hybrid-d3 cal | 80.5% | 74.1% | 85.3% | 55.1% | 53.4% | 73.1% | 91.8% | 85.0% | 82.9% | 0.05 | 6.6% | 230 | 84 | 3.4 |
| hybrid-d3 raw | 80.5% | 74.1% | 85.3% | 55.1% | 53.4% | 73.1% | 91.8% | 90.1% | 80.0% | 0.05 | 6.6% | 230 | 84 |  |

hybrid-d3: elements by source, cal {"rules":967,"cache":358,"model":144,"manual":0,"confirmed":0,"corrected":0}

## discipline

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1469 | 67% | 67% | 93% | 72% | 0.28 | 7% | 0.0 |
| majority | 1469 | 24% | 24% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1469 | 42% | 42% | 0% | - | 0.28 | 0% | 4.6 |
| xsmall raw | 1469 | 41% | 41% | 1% | 0% | 0.26 | 0% |  |
| base2 cal | 1469 | 61% | 61% | 82% | 69% | 0.16 | 0% | 5.3 |
| base2 raw | 1469 | 61% | 61% | 32% | 84% | 0.12 | 1% |  |
| d3 cal | 1469 | 59% | 59% | 40% | 80% | 0.10 | 20% | 8.7 |
| d3 raw | 1469 | 59% | 59% | 40% | 80% | 0.10 | 20% |  |
| hybrid-d3 cal | 1469 | 80% | 80% | 73% | 92% | 0.05 | 7% | 3.4 |
| hybrid-d3 raw | 1469 | 80% | 80% | 73% | 92% | 0.05 | 7% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 371 | 65% | 65% | 94% | 70% | 0.30 | 6% | 0.0 |
| majority | 371 | 18% | 18% | 0% | - | 0.06 | 0% | 0.0 |
| xsmall cal | 371 | 39% | 39% | 0% | - | 0.23 | 0% | 4.6 |
| xsmall raw | 371 | 38% | 38% | 2% | 0% | 0.23 | 0% |  |
| base2 cal | 371 | 61% | 61% | 77% | 70% | 0.13 | 0% | 5.3 |
| base2 raw | 371 | 62% | 62% | 32% | 85% | 0.14 | 1% |  |
| d3 cal | 371 | 59% | 59% | 45% | 81% | 0.08 | 16% | 8.7 |
| d3 raw | 371 | 59% | 59% | 45% | 81% | 0.08 | 16% |  |
| hybrid-d3 cal | 371 | 75% | 75% | 72% | 88% | 0.06 | 6% | 3.4 |
| hybrid-d3 raw | 371 | 75% | 75% | 72% | 88% | 0.06 | 6% |  |

## sub_chained (right only when discipline and sub match)

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1469 | 62% | 62% | 92% | 67% | 0.33 | 8% | 0.0 |
| majority | 1469 | 12% | 15% | 0% | - | 0.39 | 0% | 0.0 |
| xsmall cal | 1469 | 16% | 16% | 0% | - | 0.08 | 0% | 4.6 |
| xsmall raw | 1469 | 15% | 15% | 0% | - | 0.09 | 0% |  |
| base2 cal | 1469 | 44% | 49% | 38% | 71% | 0.13 | 0% | 5.3 |
| base2 raw | 1469 | 36% | 39% | 16% | 85% | 0.14 | 1% |  |
| d3 cal | 1469 | 55% | 57% | 60% | 72% | 0.13 | 20% | 8.7 |
| d3 raw | 1469 | 55% | 57% | 77% | 63% | 0.28 | 20% |  |
| hybrid-d3 cal | 1469 | 74% | 76% | 85% | 83% | 0.07 | 7% | 3.4 |
| hybrid-d3 raw | 1469 | 74% | 76% | 90% | 80% | 0.14 | 7% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 371 | 60% | 60% | 92% | 64% | 0.36 | 8% | 0.0 |
| majority | 371 | 7% | 9% | 0% | - | 0.44 | 0% | 0.0 |
| xsmall cal | 371 | 18% | 18% | 0% | - | 0.08 | 0% | 4.6 |
| xsmall raw | 371 | 17% | 17% | 0% | - | 0.08 | 0% |  |
| base2 cal | 371 | 43% | 46% | 44% | 68% | 0.15 | 0% | 5.3 |
| base2 raw | 371 | 40% | 42% | 16% | 87% | 0.09 | 1% |  |
| d3 cal | 371 | 56% | 57% | 58% | 71% | 0.12 | 16% | 8.7 |
| d3 raw | 371 | 56% | 57% | 79% | 64% | 0.27 | 16% |  |
| hybrid-d3 cal | 371 | 69% | 70% | 79% | 78% | 0.12 | 7% | 3.4 |
| hybrid-d3 raw | 371 | 69% | 70% | 89% | 75% | 0.18 | 7% |  |

## sub_oracle

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1469 | 63% | 63% | 92% | 69% | 0.31 | 8% | 0.0 |
| majority | 1469 | 46% | 49% | 7% | 76% | 0.00 | 0% | 0.0 |
| xsmall cal | 1469 | 32% | 32% | 14% | 69% | 0.12 | 0% | 4.6 |
| xsmall raw | 1469 | 32% | 32% | 14% | 69% | 0.12 | 0% |  |
| base2 cal | 1469 | 64% | 68% | 42% | 86% | 0.07 | 0% | 5.3 |
| base2 raw | 1469 | 64% | 68% | 24% | 94% | 0.19 | 0% |  |
| d3 cal | 1469 | 85% | 88% | 66% | 94% | 0.18 | 0% | 8.7 |
| d3 raw | 1469 | 85% | 88% | 85% | 93% | 0.06 | 0% |  |
| hybrid-d3 cal | 1469 | 85% | 88% | 90% | 89% | 0.07 | 0% | 3.4 |
| hybrid-d3 raw | 1469 | 85% | 88% | 94% | 88% | 0.05 | 0% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 371 | 63% | 63% | 92% | 69% | 0.31 | 8% | 0.0 |
| majority | 371 | 33% | 35% | 12% | 79% | 0.15 | 0% | 0.0 |
| xsmall cal | 371 | 42% | 42% | 15% | 79% | 0.10 | 0% | 4.6 |
| xsmall raw | 371 | 42% | 42% | 15% | 79% | 0.10 | 0% |  |
| base2 cal | 371 | 64% | 67% | 50% | 81% | 0.09 | 0% | 5.3 |
| base2 raw | 371 | 64% | 67% | 25% | 90% | 0.17 | 0% |  |
| d3 cal | 371 | 84% | 85% | 66% | 94% | 0.18 | 0% | 8.7 |
| d3 raw | 371 | 84% | 85% | 84% | 91% | 0.04 | 0% |  |
| hybrid-d3 cal | 371 | 85% | 87% | 84% | 90% | 0.05 | 1% | 3.4 |
| hybrid-d3 raw | 371 | 85% | 87% | 92% | 88% | 0.04 | 1% |  |

## division

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1469 | 55% | 66% | 92% | 60% | 0.40 | 8% | 0.0 |
| majority | 1469 | 24% | 24% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1469 | 26% | 34% | 0% | - | 0.16 | 0% | 4.6 |
| xsmall raw | 1469 | 26% | 34% | 0% | - | 0.16 | 0% |  |
| base2 cal | 1469 | 36% | 45% | 16% | 70% | 0.10 | 0% | 5.3 |
| base2 raw | 1469 | 36% | 45% | 16% | 70% | 0.10 | 0% |  |
| d3 cal | 1469 | 42% | 53% | 34% | 69% | 0.14 | 0% | 8.7 |
| d3 raw | 1469 | 42% | 53% | 34% | 69% | 0.14 | 0% |  |
| hybrid-d3 cal | 1469 | 55% | 70% | 67% | 79% | 0.16 | 1% | 3.4 |
| hybrid-d3 raw | 1469 | 55% | 70% | 67% | 79% | 0.16 | 1% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 371 | 58% | 69% | 92% | 63% | 0.37 | 8% | 0.0 |
| majority | 371 | 18% | 19% | 0% | - | 0.06 | 0% | 0.0 |
| xsmall cal | 371 | 23% | 27% | 0% | - | 0.13 | 0% | 4.6 |
| xsmall raw | 371 | 23% | 27% | 0% | - | 0.13 | 0% |  |
| base2 cal | 371 | 42% | 47% | 14% | 87% | 0.10 | 0% | 5.3 |
| base2 raw | 371 | 42% | 47% | 14% | 87% | 0.10 | 0% |  |
| d3 cal | 371 | 46% | 58% | 34% | 74% | 0.07 | 0% | 8.7 |
| d3 raw | 371 | 46% | 58% | 34% | 74% | 0.07 | 0% |  |
| hybrid-d3 cal | 371 | 59% | 73% | 64% | 86% | 0.10 | 1% | 3.4 |
| hybrid-d3 raw | 371 | 59% | 73% | 64% | 86% | 0.10 | 1% |  |

## division_app (only when building_element >= 0.5)

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1469 | 55% | 66% | 92% | 60% | 0.40 | 8% | 0.0 |
| majority | 1469 | 24% | 24% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1469 | 26% | 34% | 0% | - | 0.16 | 0% | 4.6 |
| xsmall raw | 1469 | 26% | 34% | 0% | - | 0.16 | 0% |  |
| base2 cal | 1469 | 36% | 45% | 16% | 70% | 0.10 | 0% | 5.3 |
| base2 raw | 1469 | 36% | 45% | 16% | 70% | 0.10 | 0% |  |
| d3 cal | 1469 | 33% | 41% | 30% | 68% | 0.17 | 21% | 8.7 |
| d3 raw | 1469 | 33% | 41% | 30% | 68% | 0.17 | 21% |  |
| hybrid-d3 cal | 1469 | 53% | 67% | 66% | 79% | 0.16 | 8% | 3.4 |
| hybrid-d3 raw | 1469 | 53% | 67% | 66% | 79% | 0.16 | 8% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 371 | 58% | 69% | 92% | 63% | 0.37 | 8% | 0.0 |
| majority | 371 | 18% | 19% | 0% | - | 0.06 | 0% | 0.0 |
| xsmall cal | 371 | 23% | 27% | 0% | - | 0.13 | 0% | 4.6 |
| xsmall raw | 371 | 23% | 27% | 0% | - | 0.13 | 0% |  |
| base2 cal | 371 | 42% | 47% | 14% | 87% | 0.10 | 0% | 5.3 |
| base2 raw | 371 | 42% | 47% | 14% | 87% | 0.10 | 0% |  |
| d3 cal | 371 | 36% | 44% | 28% | 77% | 0.10 | 26% | 8.7 |
| d3 raw | 371 | 36% | 44% | 28% | 77% | 0.10 | 26% |  |
| hybrid-d3 cal | 371 | 57% | 68% | 63% | 88% | 0.09 | 12% | 3.4 |
| hybrid-d3 raw | 371 | 57% | 68% | 63% | 88% | 0.09 | 12% |  |

## Chained versus oracle sub-discipline

| arm | level | chained | oracle | gap | chained, discipline right | chained wrong discipline | oracle right, chained wrong | of which discipline wrong |
|---|---|---|---|---|---|---|---|---|
| rules | element | 62% | 63% | 1 pts | 93% | 490/1469 | 18 | 18 |
| rules | signature | 60% | 63% | 4 pts | 91% | 129/371 | 14 | 14 |
| majority | element | 12% | 46% | 34 pts | 51% | 1112/1469 | 496 | 496 |
| majority | signature | 7% | 33% | 26 pts | 40% | 303/371 | 97 | 97 |
| xsmall cal | element | 16% | 32% | 16 pts | 37% | 854/1469 | 310 | 275 |
| xsmall cal | signature | 18% | 42% | 24 pts | 45% | 227/371 | 102 | 90 |
| xsmall raw | element | 15% | 32% | 17 pts | 37% | 865/1469 | 314 | 279 |
| xsmall raw | signature | 17% | 42% | 25 pts | 45% | 230/371 | 103 | 91 |
| base2 cal | element | 44% | 64% | 20 pts | 72% | 577/1469 | 292 | 288 |
| base2 cal | signature | 43% | 64% | 22 pts | 70% | 144/371 | 82 | 78 |
| base2 raw | element | 36% | 64% | 27 pts | 60% | 575/1469 | 419 | 267 |
| base2 raw | signature | 40% | 64% | 24 pts | 65% | 141/371 | 102 | 73 |
| d3 cal | element | 55% | 85% | 30 pts | 93% | 596/1469 | 440 | 439 |
| d3 cal | signature | 56% | 84% | 28 pts | 95% | 152/371 | 104 | 103 |
| d3 raw | element | 55% | 85% | 30 pts | 93% | 596/1469 | 440 | 439 |
| d3 raw | signature | 56% | 84% | 28 pts | 95% | 152/371 | 104 | 103 |
| hybrid-d3 cal | element | 74% | 85% | 11 pts | 92% | 287/1469 | 164 | 164 |
| hybrid-d3 cal | signature | 69% | 85% | 16 pts | 93% | 94/371 | 58 | 58 |
| hybrid-d3 raw | element | 74% | 85% | 11 pts | 92% | 287/1469 | 164 | 164 |
| hybrid-d3 raw | signature | 69% | 85% | 16 pts | 93% | 94/371 | 58 | 58 |

## Timing

| arm | signatures | load s | wall s (all runs) | s/sig (app path) | s/sig (all calls) |
|---|---|---|---|---|---|
| rules | 371 | 0.0 | 0.0 | 0.00 | 0.00 |
| majority | 371 | 0.0 | 0.0 | 0.00 | 0.00 |
| xsmall | 371 | 11.4 | 1883.5 | 4.63 | 5.04 |
| base2 | 371 | 26.5 | 2239.3 | 5.30 | 6.02 |
| d3 | 371 | 42.1 | 3531.3 | 8.72 | 9.51 |
| hybrid-d3 | 371 | 42.1 | 0.1 | 3.37 | 3.76 |

## Top confusions (per element, cal; truth -> predicted, count)

### discipline

- rules: PIP -> PLB (236); PIP -> (abstain) (69); MEC -> PLB (41); CIV -> (abstain) (24); CIV -> PLB (23)
- majority: STR -> PIP (227); ARC -> PIP (196); CIV -> PIP (167); ELE -> PIP (135); MEC -> PIP (126)
- xsmall: PIP -> STR (136); PLB -> PIP (103); CIV -> STR (89); ELE -> MEC (84); ARC -> STR (65)
- base2: PIP -> ARC (110); CIV -> ARC (103); PLB -> PIP (82); MEC -> PIP (38); FPR -> PIP (28)
- d3: PIP -> GEN (102); PLB -> PIP (83); CIV -> GEN (68); STR -> GEN (66); FPR -> PIP (43)
- hybrid-d3: PIP -> GEN (61); MEC -> PIP (33); PLB -> PIP (25); CIV -> GEN (20); STR -> CIV (19)

### sub_chained

- rules: PIP/PRC -> PLB/SUP (182); PIP/SUP -> (abstain) (54); MEC/HYD -> PLB/SUP (38); PIP/UTL -> PLB/SUP (38); STR/BEM -> STR/BRC (36)
- majority: PIP/SUP -> PIP/PRC (95); STR/BEM -> PIP/PRC (93); ARC/WAL -> PIP/PRC (74); PLB/SUP -> PIP/PRC (65); CIV/LND -> PIP/PRC (60)
- xsmall: PIP/PRC -> PIP/VLV (94); PIP/SUP -> STR/SLB (64); PLB/SUP -> PIP/VLV (63); ELE/CND -> MEC/DUC (51); CIV/LND -> STR/SLB (41)
- base2: PIP/SUP -> ARC/WAL (72); CIV/LND -> ARC/WAL (51); PIP/UTL -> PIP/PRC (38); MEC/DUC -> MEC/EQP (37); PIP/PRC -> PIP/UTL (34)
- d3: PIP/SUP -> GEN/UNC (81); CIV/LND -> GEN/UNC (58); PLB/SUP -> PIP/PRC (45); FPR/SPR -> PIP/PRC (39); PIP/UTL -> PIP/PRC (32)
- hybrid-d3: PIP/SUP -> GEN/UNC (40); STR/BEM -> STR/BRC (36); PIP/UTL -> PIP/PRC (32); MEC/HYD -> PIP/PRC (30); PLB/SUP -> PIP/PRC (20)

### sub_oracle

- rules: PRC -> SUP (182); SUP -> (abstain) (54); UTL -> SUP (41); HYD -> SUP (38); BEM -> BRC (36)
- majority: SUP -> PRC (95); FND -> BEM (43); HYD -> DUC (40); COL -> BEM (38); UTL -> PRC (38)
- xsmall: PRC -> VLV (173); SUP -> VLV (95); BEM -> SLB (82); WAL -> FIN (74); FND -> SLB (43)
- base2: SUP -> FIX (58); SUP -> EQP (41); UTL -> PRC (38); DUC -> EQP (37); PRC -> UTL (34)
- d3: SUP -> PRC (42); UTL -> PRC (38); SUP -> EQP (18); HYD -> DUC (16); DRN -> ERT (15)
- hybrid-d3: UTL -> PRC (38); BEM -> BRC (36); DRN -> STM (26); HYD -> DUC (16); EQP -> PRC (13)

### division

- rules: 40 -> 22 (230); 40 -> (abstain) (60); 03 -> 05 (50); 23 -> 22 (41); 40 -> 05 (41)
- majority: 26 -> 40 (135); 03 -> 40 (134); 22 -> 40 (126); 23 -> 40 (126); 05 -> 40 (109)
- xsmall: 40 -> 05 (249); 40 -> 03 (71); 26 -> 05 (70); 32 -> 05 (70); 23 -> 05 (62)
- base2: 40 -> 05 (234); 23 -> 05 (95); 22 -> 05 (65); 26 -> 27 (53); 32 -> 05 (51)
- d3: 40 -> 22 (189); 40 -> 05 (82); 26 -> 41 (53); 32 -> 05 (50); 40 -> 03 (42)
- hybrid-d3: 40 -> 22 (189); 40 -> 05 (123); 03 -> 05 (50); 40 -> 25 (30); 04 -> 03 (28)

### division_app

- rules: 40 -> 22 (230); 40 -> (abstain) (60); 03 -> 05 (50); 23 -> 22 (41); 40 -> 05 (41)
- majority: 26 -> 40 (135); 03 -> 40 (134); 22 -> 40 (126); 23 -> 40 (126); 05 -> 40 (109)
- xsmall: 40 -> 05 (249); 40 -> 03 (71); 26 -> 05 (70); 32 -> 05 (70); 23 -> 05 (62)
- base2: 40 -> 05 (234); 23 -> 05 (95); 22 -> 05 (65); 26 -> 27 (53); 32 -> 05 (51)
- d3: 40 -> 22 (189); 40 -> 05 (65); 22 -> (abstain) (62); 32 -> 05 (50); 26 -> (abstain) (42)
- hybrid-d3: 40 -> 22 (189); 40 -> 05 (106); 03 -> 05 (50); 22 -> (abstain) (31); 04 -> 03 (28)
