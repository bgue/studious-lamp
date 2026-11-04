# Large IFC files

Opening a big IFC file (tens of thousands of elements, 50 to 100 MB) no longer freezes the page. Everything heavy happens in the import worker; the main thread only wraps arrays it receives. Measured numbers are in `web/bench/RESULTS-large-ifc.md` (`node bench/bench-large-ifc.mjs`).

## What changed in the pipeline

```
file --(main: read)--> worker: web-ifc extract --> merge into flat arrays --> edges --> BVH --(transfer, no copy)--> main: wrap --> renderer
```

1. **Extract** (`ifcRaw.ts`, unchanged): web-ifc meshes the products in chunks and reads relations and properties. The result stays inside the worker. web-ifc is disposed before the merge (`CloseModel` runs as soon as extraction ends; the instance is dropped right after the last file).
2. **Merge** (`ifcBuild.ts` `buildMergedData`): the same skip rules, dedupe, storeys, relations, origin shift and Z-up to Y-up rotation as the glb path (they share `prepare` and `placeItem`), but the vertices are written straight into the arrays the renderer draws: `position`, `normal`, `elementId`, a `uint32` `index`, per-element `ranges`, `vertexRanges` and `bounds`. Each element's reader arrays are released as soon as they are copied (`consume`), so the reader data and the merged data never exist in full at the same time.
3. **Edges** (`ifcEdges.ts` `computeEdges`): crease lines with the 30 degree rule of `MergedGeometry`, computed on the merged arrays with typed arrays instead of per-element `EdgesGeometry` objects. Same output, bit for bit (`tests/large-direct.test.ts`).
4. **BVH** (`ifcBvh.ts`): `new MeshBVH(geometry, { indirect: true })`, the options `MergedGeometry.bvh` uses, then `MeshBVH.serialize(..., { cloneBuffers: false })`. Indirect BVHs serialise fine in three-mesh-bvh 0.9.17 (the index buffer is left alone, so only the node buffers and the indirect buffer travel). The main thread deserialises them in `MergedGeometry.fromArrays`, so `merged.bvh` never rebuilds on first use (the first hover or sightline used to freeze for 0.2 s at 20,000 elements and 1.4 s at 100,000).
5. **Hand-off**: the sidecar travels as a JSON string (a few MB parse in tens of ms; 100,000 small relation arrays would take hundreds of ms to deserialise), element records in messages of 2,000, and every typed array as a transferable. `MergedGeometry.fromArrays(arrays)` (a static constructor; the existing constructor and members are untouched) wraps them in a `BufferGeometry`; bounding box and sphere come precomputed from the worker.

The glb build (`buildModelData`, `writeGlb`) is unchanged and is still what the CLI packager (`xray-pack`) uses and what the parity tests compare against. Opening a `.glb` file is unchanged as well. Without a worker (the main-thread fallback) the direct path runs on the main thread, with no prebuilt BVH.

## Options (folder `Open model`)

| Control | Values | Effect |
| --- | --- | --- |
| `edges` | `auto` (default), `all`, `none` | Edge lines of the model. `auto` skips them above 50,000 elements: they are often the largest extra buffer (16 bytes per edge vertex: position and element id) and are slow to draw. `all` always builds them, `none` never. A skipped edge set is an empty geometry, so the renderer needs no change. |
| `properties` | `common` (default), `none` | `none` skips property extraction in the reader (`props: 'none'`): faster, smaller, and hover cards show no property sets. |
| `Model stats` | read-only text | `20,000 elements, 352,000 triangles, 58.0 MB buffers, 9.5 s`: elements, triangles, typed-array megabytes (geometry, edges, BVH) and load seconds of the model on screen. For a model that was not opened from a file in this session the load time reads `n/a`. |

The options apply to the next IFC file you open. They are not stored.

## Status line

`Load status` walks through the stages with counts: `Reading X, 89.6 MB`, `Opening X`, `Meshing 4800 of 100000`, `Reading relations`, `Merging 52000 of 100000 elements`, `Edges 31000 of 100000 elements` (or `Edges skipped (auto: over 50,000 elements)`), `BVH 45% (1.76 M triangles)`, `Transferring geometry`, `Uploading 100000 elements`, then `Loaded 100000 elements in 23.4 s`.

## Tool `largeModel` (action panel)

A drawer with the same stats (elements, triangles, vertices, edge segments, buffers, where the BVH came from, load time, the option values used) and the timings of the last file load: reading, opening, meshing, relations and properties, releasing web-ifc, preparing, merging, edges, BVH, transfer and wrap, GPU upload to the first frames, total. The same numbers are logged once per load as `[ifc-import] {... "stages": {...}}`.

## Responsiveness

Main-thread work during a load is limited to message handling, 2,000-record chunks, one JSON parse, `fromArrays` and the model install. In the headless run at 100,000 elements every main-thread task is under 200 ms except `app.openLoaded` (other plugins' `onModel` hooks, mostly the model tree and class styles: about 1 s at 100,000 elements) and the first frame that uploads the geometry. Measure with a `PerformanceObserver` for `longtask` entries, as `bench/bench-large-ifc.mjs` does.

## Limits

- The extraction itself (web-ifc meshing and property reading) is the largest stage, and its wasm heap is not given back until the worker ends, so peak resident memory is dominated by it. Reading properties is the slowest part in the browser; `properties: none` removes it.
- A second (merge-only) worker, started after the extraction worker is terminated, would cut the peak resident memory by roughly the size of the wasm heap; it was not done because the hand-off of 100,000 element arrays costs more main-thread time than it saves.
- The edge geometry is all or nothing per model; there are no per-element edges for a model that skipped them.
- `Cancel load` ends the worker at once; the final wrap and install on the main thread are short and not interruptible.
