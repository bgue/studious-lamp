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
