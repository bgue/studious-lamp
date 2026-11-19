# Save IFC (ticket T2): measurements

Machine: shared; other agents ran heavy work in parallel the whole time (load average 27 to 40 on this box during every run below), so
absolute times are inflated several-fold and noisy. Conditions are stated per number. Headless Chromium with swiftshader.

## Save on a large file (acceptance: JS heap growth under 50 MB)

`node bench/bench-ifc-save.mjs --file /tmp/xray-big-ifc-t2/big-115000.ifc --label t2` (file made by `tools/make_big_ifc.py -n 115000`: 103 MB,
115,000 elements, all classified by the rules). Heap read after two forced GCs, before and after the save; `target: 'none'` (the blob is built,
nothing is written to disk). Raw data: `bench/ifc-save-large-t2.json`.

| Where the block is built | Save time (load avg 35) | Heap before | Heap after | Growth kept | Peak growth during the save |
| --- | --- | --- | --- | --- | --- |
| save worker | 19.2 s | 402.8 MB | 402.9 MB | 0.1 MB | 23.5 MB |
| main thread (fallback, `forceMainThread`) | 21.5 s | 402.8 MB | 403.1 MB | 0.3 MB | 113.9 MB |

The output is 107 MB (original 103 MB + a 116-line block; rule-classified signature groups collapse to a few property sets), ends with the
original `ENDSEC; END-ISO-10303-21;`. Acceptance met: the growth after the save is below 1 MB; even the peak of the main-thread fallback
(114 MB) is the plan objects of 115,000 results, not file bytes. The 19 s are mostly the plan and block for 115,000 elements under load 35:
in node, `planSave` took 0.13 s and `emitAdditions` 2.9 s for 100,000 elements at load 26 (8.4 s before a fix below). Not re-measured on a quiet machine, so the
design budget "50,000 elements under 1 s" is **not confirmed** here (it is 3x better than before the fix, and the load factor is unknown).

Fix made while measuring (a T1 file, small): `schemaHash(schema)` was computed once per element in `elementProps`; it is now cached per schema
object (`additions.ts`). That took the 100,000-element emit from 8.4 s to 2.9 s under the same load.

## Import time (acceptance: within 2 %)

The import now also reads, per file, `GetMaxExpressID`, the IfcProject line and the IfcClassification ids, and the last 64 KB of the buffer
(`saveInfoOf`, `tailBlockBase`). Measured in node on `big-20000.ifc` (18 MB): those calls take 0.12 ms + 0.11 ms against an extraction of 7.9 s
(0.003 %, load avg about 30).

End to end, `bench/bench-large-ifc.mjs --n 20000` three runs each of the snapshot of the T1 commit (`ddaf2bc`, served with `--root`) and of this tree, alternating,
dev server, load avg 27 to 32 throughout:

| | wall ms, runs 1 to 3 | median | mean |
| --- | --- | --- | --- |
| before (ddaf2bc) | 34,421 / 25,538 / 15,365 | 25,538 | 25,108 |
| after (T2) | 31,803 / 24,215 / 28,138 | 28,138 | 28,052 |

The spread inside each group (15 to 34 s) is far larger than 2 %, so the end-to-end comparison cannot resolve 2 %; the isolated cost above is the
meaningful number. Peak JS heap: before 114 to 130 MB, after 116 to 127 MB (same range).

## Other numbers

- FZK-Haus (2.5 MB, 82 elements), API save through the worker: 290 to 690 ms including the download; 131 lines added, +14 KB.
- Tests: `ifcsave-app.test.ts` 18 tests (about 55 s, two federated real imports).

# Save cleaned copy (ticket T5): measurements

Same machine and the same caveat as above: 4 CPUs, load average 20 to 27 during every run (other agents working), so absolute times are
inflated and noisy. Headless Chromium with swiftshader.

## 100 MB synthetic file, end to end (acceptance: under 10 s)

`node bench/bench-ifc-clean.mjs --file /tmp/xray-big-ifc/big-100000.ifc --label t5` (`tools/make_big_ifc.py -n 100000`: 89.6 MB, 1,510,643
entity lines, 100,000 elements). The page opens the file, then `__xrayIfcSave.saveCleaned({ ids, target: 'none', withClassification: false })`
removes every 7th duct and pipe segment: 5,715 elements, 82,868 lines (the elements, their placements, geometry, property sets, styled items
and the trimmed or emptied relations), output 84.6 MB. Time from the call to the finished Blob, which includes reading the 90 MB file,
indexing, planning, writing the output in 4 MB chunks and the transfer back. Raw data: `bench/ifc-clean-large-t5.json`.

| Where | Time, load avg 25 to 27 | Heap growth kept | Peak heap growth |
| --- | --- | --- | --- |
| save worker, run 1 (cold) | 3.4 s (3.96 s wall) | -0.9 MB | 5.4 MB |
| main thread (fallback), run 2 | 3.7 s | -0.8 MB | 331 MB (the file, the index and the output live on the page heap) |
| save worker, run 3 | 1.7 s | -0.8 MB | 4.4 MB |

Acceptance met with a margin of about 3x even under load. In node (vitest, same load), the phases on this file were: index 2.3 s (40 MB/s is
the design floor; this is about 39 MB/s under load 22, so the floor is met but not by much on a loaded box), plan 0.7 s, write 0.85 s.
Two quadratic spots were found and fixed while measuring on `big-20000`/`big-100000`: a relation that lists a storey's 2,500 elements was
re-parsed once per removed element (now edited once per round), and the strong-reference count of a style shared by thousands of styled items
was recounted per deletion (now cached). Before the fixes a 20,000-element file took 3.1 s to plan; after, 0.3 s.

Memory: bytes of the file + the index (about 0.8x the file) + the output, as designed. The page heap does not move in worker mode.

## Other numbers

- `ifcsave-removal.test.ts` and `ifcsave-removal-fzk.test.ts` (20 random non-host elements of FZK-Haus removed, re-opened in web-ifc and
  ifcopenshell): 32 tests, 7.7 s together.
- Cleaned `Building-Architecture.ifc` (smoke step 8): 1 of 9 elements, 142,325 to 137,716 bytes, 0.6 s in the worker.
- Plain Save IFC now also scans the file once when it carries no markers (to find Xray lines that lost them, design 1.4); that is one streaming
  pass (`scanStep`): 3.1 s on the 90 MB file at load average 16, so about 3 s more for a Save IFC of a file without markers.
