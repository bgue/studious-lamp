# Truth bench: process-plant

Truth: ../models/Process-Plant.truth.json (tools/make_process_plant_ifc.py --seed 1; Labels are the design intent set when each element was created, from the schema descriptions; no classifier output was used. Piping: process services and the flare line are PIP/PRC, cooling water, steam and condensate are PIP/UTL (flare alt UTL), all with division 40; fittings, spool joints, nozzle flanges, tees and spectacle blinds follow their line (a nozzle flange alt: the equipment's sub-discipline). Valves are PIP/VLV; a regulating valve with an F-tag is a control valve, INS/CTL; transmitters and gauges are INS/SNS. Pumps, their motors and baseplates are PIP/PMP division 43 (motor alt division 26, baseplate alt EQP, SUP); exchangers with channel and saddles are PIP/HTX division 42; drums and skirts are PIP/VES division 43. Pipe sleepers, T-supports and riser guides are PIP/SUP division 40 (alt 05 steel or 03 concrete); cable tray supports and the tray riser stanchion follow the tray, ELE/CND (alt division 05). Foundations under equipment are CIV/FND, under rack and platform steel STR/FND, both division 03. Rack steel is STR (COL, BEM, BRC; base plates BRC), platform grating STR/SLB, stair and railings ARC/STA division 05. Masonry exterior walls are load bearing, STR/WLS 04; the block partition is ARC/WAL 04; floor and roof slabs are STR/SLB 03 (roof alt division 07). Doors ARC/DOR and windows ARC/WIN, division 08. Paving, roads and kerbs CIV/PAV 32, fence posts CIV/LND 32, drain trench CIV/DRN 33. Switchboards ELE/PWR, cable tray ELE/CND, luminaires ELE/LTG, division 26. The battery-limit marker board is a sign that fits no discipline: GEN/UNC with division 10. IfcSpace and IfcOpeningElement are not kept by the converter and have no entry.). 1294 elements with truth in 114 signatures; 0 elements without truth, 0 truth entries without an element.
"cal" = shipped temperatures (the app's auto mode), "raw" = T 1. Strict/lenient: lenient also accepts the truth's alt. cover/prec at minConfidence 0.6. s/sig = seconds per signature on the app's path (main + chained sub request). Rules and majority have confidence 1 (majority: the class share); a rules no-match is an abstain.

## discipline

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1294 | 68% | 68% | 99% | 69% | 0.31 | 1% | 0.0 |
| majority | 1294 | 50% | 50% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1294 | 52% | 52% | 0% | - | 0.54 | 0% | 1.0 |
| xsmall raw | 1294 | 52% | 52% | 0% | - | 0.54 | 0% |  |
| base2 cal | 1294 | 63% | 63% | 71% | 88% | 0.24 | 11% | 3.8 |
| base2 raw | 1294 | 54% | 54% | 27% | 79% | 0.26 | 11% |  |
| d3 cal | 1294 | 84% | 84% | 25% | 100% | 0.35 | 9% | 8.1 |
| d3 raw | 1294 | 82% | 82% | 54% | 83% | 0.21 | 10% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 114 | 60% | 60% | 96% | 62% | 0.38 | 4% | 0.0 |
| majority | 114 | 61% | 61% | 0% | - | 0.12 | 0% | 0.0 |
| xsmall cal | 114 | 45% | 45% | 0% | - | 0.36 | 0% | 1.0 |
| xsmall raw | 114 | 45% | 45% | 0% | - | 0.36 | 0% |  |
| base2 cal | 114 | 70% | 70% | 82% | 81% | 0.25 | 1% | 3.8 |
| base2 raw | 114 | 64% | 64% | 25% | 61% | 0.30 | 1% |  |
| d3 cal | 114 | 82% | 82% | 18% | 100% | 0.40 | 6% | 8.1 |
| d3 raw | 114 | 81% | 81% | 41% | 79% | 0.29 | 9% |  |

## sub_chained (right only when discipline and sub match)

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1294 | 68% | 68% | 99% | 69% | 0.31 | 1% | 0.0 |
| majority | 1294 | 20% | 20% | 0% | - | 0.21 | 0% | 0.0 |
| xsmall cal | 1294 | 9% | 9% | 1% | 0% | 0.19 | 0% | 1.0 |
| xsmall raw | 1294 | 9% | 9% | 0% | - | 0.06 | 0% |  |
| base2 cal | 1294 | 33% | 33% | 20% | 36% | 0.21 | 11% | 3.8 |
| base2 raw | 1294 | 21% | 21% | 4% | 89% | 0.13 | 11% |  |
| d3 cal | 1294 | 64% | 65% | 72% | 82% | 0.15 | 9% | 8.1 |
| d3 raw | 1294 | 63% | 64% | 86% | 69% | 0.24 | 10% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 114 | 60% | 60% | 95% | 63% | 0.37 | 5% | 0.0 |
| majority | 114 | 23% | 23% | 0% | - | 0.18 | 0% | 0.0 |
| xsmall cal | 114 | 12% | 12% | 4% | 0% | 0.18 | 0% | 1.0 |
| xsmall raw | 114 | 12% | 12% | 0% | - | 0.04 | 0% |  |
| base2 cal | 114 | 44% | 44% | 32% | 64% | 0.14 | 1% | 3.8 |
| base2 raw | 114 | 30% | 30% | 10% | 82% | 0.12 | 1% |  |
| d3 cal | 114 | 65% | 66% | 65% | 82% | 0.09 | 6% | 8.1 |
| d3 raw | 114 | 63% | 64% | 79% | 71% | 0.20 | 9% |  |

## sub_oracle

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1294 | 68% | 68% | 99% | 69% | 0.31 | 1% | 0.0 |
| majority | 1294 | 55% | 55% | 34% | 82% | 0.00 | 0% | 0.0 |
| xsmall cal | 1294 | 19% | 19% | 38% | 34% | 0.35 | 0% | 1.0 |
| xsmall raw | 1294 | 19% | 19% | 4% | 100% | 0.15 | 0% |  |
| base2 cal | 1294 | 52% | 52% | 20% | 96% | 0.15 | 0% | 3.8 |
| base2 raw | 1294 | 52% | 52% | 17% | 100% | 0.19 | 0% |  |
| d3 cal | 1294 | 74% | 74% | 90% | 78% | 0.20 | 0% | 8.1 |
| d3 raw | 1294 | 74% | 74% | 92% | 76% | 0.25 | 0% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 114 | 60% | 60% | 95% | 63% | 0.37 | 5% | 0.0 |
| majority | 114 | 39% | 39% | 28% | 50% | 0.13 | 1% | 0.0 |
| xsmall cal | 114 | 40% | 40% | 46% | 65% | 0.18 | 1% | 1.0 |
| xsmall raw | 114 | 40% | 40% | 6% | 100% | 0.20 | 1% |  |
| base2 cal | 114 | 59% | 59% | 30% | 88% | 0.14 | 1% | 3.8 |
| base2 raw | 114 | 59% | 59% | 20% | 100% | 0.25 | 1% |  |
| d3 cal | 114 | 73% | 74% | 92% | 77% | 0.17 | 1% | 8.1 |
| d3 raw | 114 | 73% | 74% | 94% | 77% | 0.21 | 1% |  |

## division

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1294 | 65% | 75% | 99% | 66% | 0.34 | 1% | 0.0 |
| majority | 1294 | 50% | 50% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1294 | 20% | 23% | 8% | 21% | 0.22 | 0% | 1.0 |
| xsmall raw | 1294 | 20% | 23% | 0% | - | 0.12 | 0% |  |
| base2 cal | 1294 | 22% | 28% | 14% | 20% | 0.29 | 0% | 3.8 |
| base2 raw | 1294 | 22% | 28% | 11% | 7% | 0.27 | 0% |  |
| d3 cal | 1294 | 29% | 29% | 19% | 85% | 0.17 | 0% | 8.1 |
| d3 raw | 1294 | 29% | 29% | 19% | 85% | 0.17 | 0% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 114 | 54% | 62% | 96% | 57% | 0.43 | 4% | 0.0 |
| majority | 114 | 61% | 62% | 0% | - | 0.12 | 0% | 0.0 |
| xsmall cal | 114 | 26% | 28% | 12% | 36% | 0.11 | 0% | 1.0 |
| xsmall raw | 114 | 26% | 28% | 0% | - | 0.19 | 0% |  |
| base2 cal | 114 | 18% | 21% | 7% | 63% | 0.21 | 0% | 3.8 |
| base2 raw | 114 | 18% | 21% | 4% | 80% | 0.08 | 0% |  |
| d3 cal | 114 | 27% | 30% | 26% | 73% | 0.22 | 0% | 8.1 |
| d3 raw | 114 | 27% | 30% | 26% | 73% | 0.22 | 0% |  |

## division_app (only when building_element >= 0.5)

Per element

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 1294 | 65% | 75% | 99% | 66% | 0.34 | 1% | 0.0 |
| majority | 1294 | 50% | 50% | 0% | - | 0.00 | 0% | 0.0 |
| xsmall cal | 1294 | 20% | 23% | 8% | 21% | 0.22 | 0% | 1.0 |
| xsmall raw | 1294 | 20% | 23% | 0% | - | 0.12 | 0% |  |
| base2 cal | 1294 | 22% | 28% | 14% | 20% | 0.29 | 0% | 3.8 |
| base2 raw | 1294 | 22% | 28% | 11% | 7% | 0.27 | 0% |  |
| d3 cal | 1294 | 22% | 22% | 16% | 92% | 0.20 | 35% | 8.1 |
| d3 raw | 1294 | 22% | 22% | 16% | 92% | 0.20 | 35% |  |

Per signature

| arm | n | strict | lenient | cover@0.6 | prec@0.6 | ECE | GEN/UNC/abstain | s/sig |
|---|---|---|---|---|---|---|---|---|
| rules | 114 | 54% | 62% | 96% | 57% | 0.43 | 4% | 0.0 |
| majority | 114 | 61% | 62% | 0% | - | 0.12 | 0% | 0.0 |
| xsmall cal | 114 | 26% | 28% | 12% | 36% | 0.11 | 0% | 1.0 |
| xsmall raw | 114 | 26% | 28% | 0% | - | 0.19 | 0% |  |
| base2 cal | 114 | 18% | 21% | 7% | 63% | 0.21 | 0% | 3.8 |
| base2 raw | 114 | 18% | 21% | 4% | 80% | 0.08 | 0% |  |
| d3 cal | 114 | 18% | 19% | 17% | 79% | 0.25 | 33% | 8.1 |
| d3 raw | 114 | 18% | 19% | 17% | 79% | 0.25 | 33% |  |

## Chained versus oracle sub-discipline

| arm | level | chained | oracle | gap | chained, discipline right | chained wrong discipline | oracle right, chained wrong | of which discipline wrong |
|---|---|---|---|---|---|---|---|---|
| rules | element | 68% | 68% | 0 pts | 100% | 411/1294 | 0 | 0 |
| rules | signature | 60% | 60% | 0 pts | 100% | 46/114 | 0 | 0 |
| majority | element | 20% | 55% | 34 pts | 41% | 652/1294 | 446 | 446 |
| majority | signature | 23% | 39% | 17 pts | 37% | 44/114 | 19 | 19 |
| xsmall cal | element | 9% | 19% | 10 pts | 17% | 619/1294 | 202 | 100 |
| xsmall cal | signature | 12% | 40% | 28 pts | 27% | 63/114 | 37 | 22 |
| xsmall raw | element | 9% | 19% | 10 pts | 17% | 619/1294 | 202 | 100 |
| xsmall raw | signature | 12% | 40% | 28 pts | 27% | 63/114 | 37 | 22 |
| base2 cal | element | 33% | 52% | 19 pts | 52% | 473/1294 | 246 | 235 |
| base2 cal | signature | 44% | 59% | 15 pts | 63% | 34/114 | 17 | 14 |
| base2 raw | element | 21% | 52% | 32 pts | 38% | 592/1294 | 448 | 293 |
| base2 raw | signature | 30% | 59% | 29 pts | 47% | 41/114 | 37 | 18 |
| d3 cal | element | 64% | 74% | 10 pts | 77% | 211/1294 | 132 | 132 |
| d3 cal | signature | 65% | 73% | 8 pts | 79% | 20/114 | 11 | 11 |
| d3 raw | element | 63% | 74% | 11 pts | 77% | 227/1294 | 148 | 148 |
| d3 raw | signature | 63% | 73% | 10 pts | 78% | 22/114 | 13 | 13 |

## Timing

| arm | signatures | load s | wall s (all runs) | s/sig (app path) | s/sig (all calls) |
|---|---|---|---|---|---|
| rules | 114 | 0.0 | 0.0 | 0.00 | 0.00 |
| majority | 114 | 0.0 | 0.0 | 0.00 | 0.00 |
| xsmall | 114 | 1.3 | 127.6 | 1.00 | 1.11 |
| base2 | 114 | 2.6 | 502.3 | 3.77 | 4.40 |
| d3 | 114 | 14.2 | 1055.7 | 8.15 | 9.25 |

## Top confusions (per element, cal; truth -> predicted, count)

### discipline

- rules: PIP -> MEC (204); PIP -> STR (79); PIP -> PLB (59); ELE -> STR (49); PIP -> (abstain) (12)
- majority: CIV -> PIP (230); STR -> PIP (208); ELE -> PIP (160); INS -> PIP (27); ARC -> PIP (26)
- xsmall: CIV -> ARC (228); PIP -> MEC (110); PIP -> ARC (105); ELE -> STR (47); STR -> ARC (46)
- base2: CIV -> GEN (136); PIP -> PLB (118); CIV -> ARC (74); ELE -> STR (49); PIP -> STR (38)
- d3: CIV -> GEN (74); ELE -> PIP (46); STR -> GEN (30); PIP -> MEC (23); ARC -> CIV (16)

### sub_chained

- rules: PIP/UTL -> MEC/HYD (193); PIP/SUP -> STR/BRC (79); PIP/UTL -> PLB/SUP (51); ELE/CND -> STR/BRC (49); PIP/HTX -> (abstain) (6)
- majority: PIP/UTL -> PIP/PRC (244); CIV/PAV -> PIP/PRC (186); ELE/CND -> PIP/PRC (134); STR/BEM -> PIP/PRC (84); PIP/SUP -> PIP/PRC (83)
- xsmall: CIV/PAV -> ARC/FIN (186); PIP/UTL -> PIP/SUP (154); PIP/PRC -> PIP/SUP (135); ELE/CND -> ELE/WIR (85); PIP/SUP -> ARC/FIN (74)
- base2: PIP/UTL -> PIP/PRC (244); CIV/PAV -> GEN/UNC (136); ELE/CND -> ELE/DEV (85); PIP/PRC -> PLB/DRN (79); ELE/CND -> STR/BEM (49)
- d3: PIP/UTL -> PIP/PRC (220); CIV/PAV -> GEN/UNC (48); ELE/CND -> PIP/SUP (46); STR/FND -> GEN/UNC (30); CIV/LND -> GEN/UNC (26)

### sub_oracle

- rules: UTL -> HYD (193); SUP -> BRC (79); UTL -> SUP (51); CND -> BRC (49); VLV -> EQP (7)
- majority: UTL -> PRC (244); SUP -> PRC (83); BRC -> BEM (46); COL -> BEM (30); FND -> BEM (30)
- xsmall: UTL -> VLV (243); PAV -> ERT (186); PRC -> VLV (135); CND -> WIR (85); BEM -> WLS (68)
- base2: UTL -> PRC (244); CND -> DEV (85); SUP -> PRC (79); CND -> PWR (49); PAV -> ERT (48)
- d3: UTL -> PRC (244); CND -> WIR (46); BRC -> COL (24); HTX -> SUP (4); PMP -> PRC (4)

### division

- rules: 40 -> 23 (200); 40 -> 05 (79); 40 -> 22 (57); 26 -> 05 (49); 40 -> 25 (24)
- majority: 32 -> 40 (212); 05 -> 40 (189); 26 -> 40 (160); 03 -> 40 (40); 43 -> 40 (16)
- xsmall: 40 -> 22 (224); 32 -> 03 (212); 40 -> 23 (150); 26 -> 23 (111); 05 -> 03 (75)
- base2: 40 -> 05 (363); 40 -> 22 (243); 32 -> 03 (186); 05 -> 03 (30); 32 -> 04 (26)
- d3: 40 -> 22 (396); 05 -> 13 (103); 40 -> 25 (103); 40 -> 46 (71); 26 -> 25 (49)

### division_app

- rules: 40 -> 23 (200); 40 -> 05 (79); 40 -> 22 (57); 26 -> 05 (49); 40 -> 25 (24)
- majority: 32 -> 40 (212); 05 -> 40 (189); 26 -> 40 (160); 03 -> 40 (40); 43 -> 40 (16)
- xsmall: 40 -> 22 (224); 32 -> 03 (212); 40 -> 23 (150); 26 -> 23 (111); 05 -> 03 (75)
- base2: 40 -> 05 (363); 40 -> 22 (243); 32 -> 03 (186); 05 -> 03 (30); 32 -> 04 (26)
- d3: 40 -> 22 (303); 40 -> (abstain) (273); 05 -> 13 (97); 05 -> (abstain) (79); 32 -> 03 (48)
