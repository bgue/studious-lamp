# Point clouds (as-built check)

Open a laser scan or photogrammetry cloud next to the model and answer one question: is this duct where the model says it is. The cloud is drawn as points in the main scene (depth tested against the model, also when the model is ghosted), aligned to the model, and compared with the model's surfaces. Points are coloured green, amber or red by how far they are from the nearest surface.

Where: the `Scan` tool in the action panel (a drawer), the `Point cloud` folder in the parameter panel, and the command palette. Scripting: `window.__xrayPointCloud`. Drop a `.las`, `.ply`, `.pcd`, `.xyz`, `.pts` or `.txt` file anywhere on the viewer to open it (a capture-phase listener claims the drop before the model loader, only when every dropped file has one of these extensions; a `.laz` drop is claimed too, to show the conversion hint).

## Workflow

1. `Open point cloud`, or drop the file. The status line shows the original and the shown count, the format and the parse time.
2. Check the placement. Clouds written in the model's IFC project coordinates (what most survey and scanning tools export for a building) land in place with `coordinates` = `project`. A cloud already in viewer coordinates (metres, Y up, shifted like the model) uses `viewer`. A cloud in its own scanner frame needs `Auto-align to model`, then the manual `offset x/y/z` and `rotation (deg)`.
3. Select the elements to check (optional) and pick `deviation scope`: `all elements` measures the distance to the nearest surface anywhere in the model, `focus only` to the surfaces of the current focus set (the selection and what Algorithm 1 treats as focus). Set `tolerance (m)` (default 0.02) and press `Compute deviation`.
4. Read the colours, the legend (bottom right of the viewer) and the numbers in the status line and the drawer.

Panel entries (`Point cloud` folder), exactly: `Open point cloud`, `visible`, `point size`, `colour by` (rgb, intensity, height, classification, deviation), `point budget`, `coordinates` (project, viewer), `Auto-align to model`, `offset x`, `offset y`, `offset z`, `rotation (deg)`, `Compute deviation`, `tolerance (m)`, `deviation scope` (all elements, focus only), `Remove point cloud`, read-only `Point cloud status`. The drawer adds `size attenuation` and an explicit `Apply budget` button. Palette actions, without default keys: `pointcloud.open`, `pointcloud.toggle`, `pointcloud.deviation`. The params document has a `pointcloud` section with the display and alignment settings only (not the data): visible, pointSize, sizeAttenuation, colourBy (a deviation colouring is stored as rgb, since the result is not part of the document), budget, coordinates, offset, rotationDeg, tolerance, scope.

## Formats

| Format | Read | Notes |
| --- | --- | --- |
| LAS 1.0 to 1.4 | uncompressed | Point formats 0 to 3 and 6 to 8 (4, 5, 9, 10 too: the waveform bytes are skipped by the record length). Scale and offset applied in double. Intensity, classification (5 bits for formats 0 to 5, a full byte for 6 and up), RGB (16 bit; values that fit 8 bit are taken as 8 bit stored in 16). 1.4 files with the legacy count 0 use the 64-bit count. A truncated body is read as far as it goes and reported as a warning. |
| LAZ | no | Rejected with: convert with PDAL (`pdal translate in.laz out.las`) or LAStools (`las2las -i in.laz -o out.las`). Detected by the extension, the compression bit in the point format and the `laszip encoded` VLR. |
| PLY | ascii, binary little and big endian | Vertex properties `x y z`, `red green blue` (or `r g b`, `diffuse_*`), `intensity` (also `scalar_intensity`, `reflectance`), `classification` (also `class`, `label`). `float` and `double` coordinates. Faces and other elements are skipped. Own reader (three's PLYLoader would round double coordinates to Float32 before the offset can be removed). |
| PCD | ascii, binary, binary_compressed | Fields `x y z`, `rgb`/`rgba` (packed float or uint32), `intensity`, `label`. LZF decompression is built in. NaN points (organised clouds) are dropped. |
| XYZ, TXT | text | Whitespace, comma or semicolon separated: `x y z`, `x y z i`, `x y z r g b`, `x y z r g b i`. Comment and header lines are skipped and counted. Colour scale (0..1, 0..255, 0..65535) is detected. |
| PTS | text | First line is the point count; `x y z i`, `x y z r g b`, `x y z i r g b` (intensity before colour, as Cyclone writes it). |

The format is taken from the first bytes (`LASF`, `ply`, `# .PCD`) before the extension, so a mis-named file still opens.

Files over 5 MB are parsed in a Web Worker with progress in the status line; smaller files, and any environment without workers, parse inline. Typed arrays are transferred, not copied.

## Precision

Positions are kept as Float32 relative to the first point, whose double precision coordinates are stored separately. A georeferenced cloud (coordinates around 2 600 000, 1 200 000) therefore keeps millimetres. The large offset only appears in the cloud's 4x4 matrix, which is composed in double and applied by three.js on the CPU in double, so the GPU sees small numbers.

## Point budget

`point budget` (default 3 000 000, slider up to 10 M) caps the points drawn. Decimation is uniform random sampling without replacement (selection sampling, one pass, seeded, exact count, original order). Why not a voxel grid: random sampling is exact, O(n) and a few milliseconds per million points, and it is an unbiased sample, so shares and percentiles measured on it estimate those of the full cloud. A voxel grid evens out density and keeps thin features but needs a cell-size search to hit a budget and is much slower. The worker keeps the full cloud, so changing the budget re-samples it without parsing again (`Apply budget` in the drawer, on release of the slider in the panel). The status line shows `N points, M shown`; the same numbers are in `stats.originalCount` and `stats.shownCount`.

## Alignment

The cloud is drawn with `p' = Ry(theta) (g + base - pivot) + pivot + offset`, where `g` is the Float32 position (axis mapped), `base` the mapped double origin and `pivot` the mapped bounds centre.

- `coordinates` = `project`: the cloud is in IFC project coordinates (Z up). The viewer mapping is `v = (x - sx, z - sz, -(y - sy))` with `s` the model's `originShift` (verified against `tools/glb_common.py`, which rotates (x, y, z) to (x, z, -y) after subtracting the shift; the BCF feature uses the same). 
- `coordinates` = `viewer`: used as is.
- `offset x/y/z` (metres, viewer frame, applied after the mapping) and `rotation (deg)` (about the vertical axis through the cloud's bounds centre; positive turns counter-clockwise seen from above, which is also positive about IFC Z).
- `Auto-align to model` does two things and says so in the status line: it moves the cloud's bounds centre onto the model's bounds centre (all three axes), then tries 0, 90, 180 and 270 degrees about the vertical axis and keeps the angle with the smallest median distance of 2000 sample points to the model (the median is robust to clutter and to the missing parts of an incomplete scan). It is a coarse start, not a registration (no ICP, no scale): refine with the offsets. It replaces the current offset and rotation.

Changing the model, the coordinates mode, the offset, the rotation, the budget or the tolerance clears a deviation result (the colours go back to the previous mode), because it no longer describes what is on screen.

## Rendering

`THREE.Points` in `app.renderer.scene` with a `PointsMaterial` (vertex colours, size in CSS pixels, optional size attenuation where `point size` is the size at the orbit target). The points are in the opaque queue, drawn before the ghost pass: the ghost (which writes depth) then blends over them instead of hiding them, so points stay visible when the model is ghosted, and they are depth tested against opaque meshes. The focus pass is drawn last and in front by the renderer, so it covers points inside the focus element's silhouette. To keep deviation findings visible anyway (a displaced duct inside a ghosted host), the amber and red points are drawn a second time as `pointcloud-findings`, without depth test, after every other pass (they share the buffers); green and unrelated points keep normal depth behaviour. Colour modes: `rgb` (a height ramp when the file has no colour), `intensity` (grey, stretched over the file's range), `height` (viridis ramp over the cloud's height range), `classification` (ASPRS palette), `deviation` (bands, grey until computed). Section planes: when `app.renderer.getClipPlanes()` exists, its planes (normals towards the kept side, the convention three.js clipping uses too) are copied onto the material every frame and `localClippingEnabled` is on. Raycasting is disabled on the cloud, so picking and hover keep using the model.

## Deviation

For each shown point (a stride sample of at most 500 000 when more are shown; then only the measured points are drawn while colouring by deviation) the distance to the nearest model surface is taken with `closestPointToPoint` on the merged geometry's BVH (`all elements`) or on the focus elements' own BVHs (`focus only`, needs a selection). Distances are searched only up to `max = 5 x tolerance`. The work runs on the main thread in time slices of 8 ms (longer when a frame in between was slow) with a `setTimeout` yield between them, so the page stays responsive and shows progress; changing the alignment or removing the cloud cancels it. (A worker with a serialised BVH would give a lighter main thread but needs the model geometry copied and rebuilt there; not done.)

| Band | Distance d | Colour |
| --- | --- | --- |
| within tolerance | d <= tol | green |
| up to twice | tol < d <= 2 tol | amber |
| beyond | 2 tol < d <= 5 tol | red |
| unrelated | d > 5 tol (or no surface that close) | grey |

Statistics (`stats.deviation`, the status line and the drawer): `shareWithin` is the share of related points (d <= max) within the tolerance; `shareWithinOfAll` counts the unrelated ones too; `mean`, `median` and `p95` are over the related points; `unrelatedShare`; counts per band; and, when the cloud has classification codes, `byClass[code] = { n, related, shareWithin, shareRed, median }`. Unrelated points are not an error: they are scan of something the checked elements do not contain (furniture, other objects, a point cloud of a different room). With `focus only`, everything except the selected elements is therefore mostly grey, and the colours and numbers say how well the focus elements are matched.

## Scripting

```js
const pc = window.__xrayPointCloud;
await pc.load(fileOrArrayBuffer, 'scan.las');   // resolves with stats
pc.settings.tolerance = 0.03; pc.controller.setTolerance(0.03);
pc.autoAlign(true);                             // { offset, rotationDeg, description }
const s = await pc.computeDeviation();          // DeviationStats, or null (no cloud, no model, empty focus)
pc.stats;     // { loaded, name, format, originalCount, shownCount, parseMs, decimateMs, mode, warnings, deviation, deviationMs, ... }
pc.remove();
```

## Sample data

`tools/make_pointcloud.py` samples the surfaces of a converted model (default `web/public/models/building`) into a synthetic as-built scan: area-weighted random points, Gaussian noise (sigma 5 mm per axis), the duct displaced 80 mm horizontally and diagonally to the walls (so every face is off by about 57 mm), and a 10 percent band missing from every wall (an incomplete scan). It writes `web/public/samples/building-scan.las` (LAS 1.2, point format 2, 1 mm scale) and `building-scan.ply` (binary little endian: float xyz, uchar rgb, intensity, classification) in IFC project coordinates, unshifted, with ASPRS classes (walls 6, slabs and footings 2, duct 19, the rest 1). About 221 000 points each; the files stay under 6 MB (LAS format 2 is 26 bytes per point). Seeded, so reruns give the same files. Other models: `--model web/public/models/fzk-haus --name fzk-haus-scan`.

## Files and tests

- `src/pointcloud/readers/` (`las`, `ply`, `pcd`, `text`, `rows` fast numeric row scanner, `builder`, `index` detection and entry point), `decimate.ts`, `session.ts` + `worker.ts` + `client.ts` (parse and decimate in a worker or inline), `align.ts` (coordinates, matrix, auto-align), `colour.ts`, `deviation.ts`, `controller.ts` (scene objects, settings, deviation run, legend), `ui.ts` (file input, drop, drawer, lil-gui folder); plugin `src/plugins/pointcloud.ts`.
- Tests `tests/pointcloud-*.test.ts` (fixtures are generated by `tests/pointcloud-helpers.ts`): every reader, header edge cases, LAZ rejection, the coordinate mapping against the real duct of `building.json`, precision, auto-align on a synthetic box, decimation counts and determinism, banding and statistics on a synthetic plane, time slicing.
- `bench/smoke-pointcloud.mjs` (SMOKE_PORT=5381) runs the browser workflow on `/?model=building` and writes `bench/pointcloud-rgb.png` and `bench/pointcloud-deviation.png`.

## Limitations

- One cloud at a time. No LAZ, E57, or PLY with list properties on vertices. No per-point picking or measuring on the cloud.
- Single-file bundles: the worker URL is not inlined, so there the cloud is parsed on the main thread (the loader falls back when the worker fails to start).
- Auto-align is a bounds-centre match plus a 90 degree search, not a registration; scans that cover only part of the building need the manual offsets. No scale estimation.
- Deviation is the distance to the nearest surface, not along a normal, and takes no account of which side of the surface the point is on. Distances beyond 5 x tolerance are not measured.
- Points are square, constant-colour pixels; no eye-dome lighting, no level-of-detail tree. The budget is the only performance control, so very large clouds are a sample.
- The ghost pass with order-independent transparency is drawn from private scenes; the cloud takes part in the main scene's depth only.
