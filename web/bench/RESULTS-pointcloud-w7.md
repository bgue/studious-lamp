# Point cloud, wave 7: normals in ICP, room by room, picking behind walls, Stop ICP, E57 messages

Data: `public/models/building` with `public/samples/building-phone-scan.ply` (phone LiDAR style scan of one room,
heading 37 degrees, 1.5 cm noise, the truth in its header) and `public/samples/building-scan.ply` (survey scan of the
whole house in project coordinates, 5 mm noise, truth = identity). Node numbers from `tests/pointcloud-icp-building.test.ts`
and `tests/pointcloud-normals.test.ts`; browser numbers from `bench/smoke-pointcloud-align.mjs` (swiftshader, a machine
shared with 3 other agents, so the times are long).

## 1. Thin-wall bias and the wrong-face stall: normal compatible ICP

ICP now estimates a normal per sample point (PCA in a denser copy of the cloud), orients it (towards the scanner when
the file's origin lies in the cloud, else by occlusion), and matches each point only with the closest model surface
whose normal is within 40 degrees (and faces the same way when oriented; the convention is measured per run). Points
without a plane around them are left out.

Translation error against the truth (at the room centre), 20 000 point sample, keep vertical:

| Case | Before | After |
| --- | --- | --- |
| Phone scan, start at the truth (Node) | 2.44 mm (2.3 mm sideways, towards the plumbing wall's far face) | 0.48 mm |
| Phone scan, start 10 deg / 0.3 m off (Node) | 2.63 mm | 0.44 mm |
| Phone scan, start -15 deg / 0.5 m off (Node) | 2.55 mm | 0.56 mm |
| Phone scan, after 4 clicked pairs (browser) | 0.0004 deg / 2.4 mm (wave 6) | 0.014 deg / 0.12 mm |
| Survey scan, 10 deg off, no heading search (Node) | 0.484 deg / 23.3 mm (locked on the wrong faces of the 20 cm walls) | 0.006 deg / 0.20 mm |
| Survey scan, 10 deg off, with the heading search (Node) | 0.005 deg / 0.21 mm | 0.006 deg / 0.19 mm (same within noise) |
| Synthetic room, 2.4 cm thin wall, 1.5 cm noise (`pointcloud-normals.test.ts`) | 4.66 mm sideways | 0.25 mm (0.24 mm with the far face removed from the model) |

The survey scan already had little bias (5 mm noise is far below its 20 cm walls); there the gain is the basin: the
stall without the heading search is gone (survey: 13 000 of 20 000 sample points get a normal, 10 000 an orientation by
occlusion; 97 percent of those agree with the model's face directions). Phone scan (browser): 16 400 of 20 000 sample points get a normal, 15 700 an orientation (towards the scan start); agreement
with the model's face directions 0.97 (Node).

## 2. Drift: align within a region, and the drift diagnostic

`align within` (whole cloud, section box, selection + 0.5 m) limits the ICP sample and the 3-point solve to a box.
After every ICP run a 3 x 3 plan grid reports the local misfit (the translation that would fit each cell alone).

Phone scan bent by a 1 degree per metre heading drift (Node): whole-cloud fit, per-cell residual medians 9.5 to 12.0 mm
(noise dominated, nothing to see), local misfit worst 7.7 mm in the north-east against 2.6 mm typical: the status line
names the north-east. That region (the cell plus 25 cm) fitted on its own: median distance 14.7 mm -> 12.7 mm (the noise
floor is about 10 mm).

## 3. Picking behind opaque model surfaces

`pickCloudAt` skips cloud points deeper than the first opaque model surface under the cursor (hidden elements and
ghosts below alpha 0.5 do not count; the clipped side of a section plane does not either). Browser check: view through
the left outer wall at a floor spot of the room behind it: with the wall selected (alpha 1) no cloud point is picked;
with the wall ghosted (another element selected) the floor point behind it is picked. Before, both returned the floor
point behind the wall.

## 4. Stop ICP

Reproduced (Playwright, real click on the button text `Stop ICP` after starting ICP from the drawer): the button moved
with every status change (y 387 px idle, 371 px while running, 420 px after the result: the status line above it
changed height), Playwright needed 7 to 10 s on this machine to get a stable target, and by then the run had ended: the
click landed on `Refine (ICP)` and started a new run (status "trying start heading 6 of 7" a second after the click). No
popover was involved (the help popover has `pointer-events: none`). Fix: the drawer's status line never shrinks while the
drawer is open (and scrolls beyond 7 lines), the button acts on the label the user saw (`data-mode`), and a click within
0.6 s after it turned back to `Refine (ICP)` does not start a run. The smoke now starts a long run and clicks
`[data-mode="stop"]` with a real Playwright click: the run is cancelled, the alignment stays, the button's y does not
change.

## 5. E57 messages

Unsupported codec: "E57: scan is compressed with the codec "zipCodec", which this viewer cannot read (it reads
bitPackCodec, the one the E57 standard defines). Export the scan again without extra compression, or convert it:
CloudCompare (save as E57 or LAS), or pdal translate in.e57 out.las." Photos next to points: "the 2 photos in the file
(images2D) are not shown, only the points" (a warning in the status line); photos only: "holds 2 photos (images2D) and
no 3D points, so there is nothing to draw. Export the scan with its point cloud."

## Browser (bench/smoke-pointcloud-align.mjs)

| Step | Wave 6 | Now |
| --- | --- | --- |
| 3-point (4 clicked pairs) | 0.08 deg / 5.5 mm | 0.076 deg / 5.5 mm (unchanged) |
| ICP after the 3 points | 0.0004 deg / 2.4 mm | 0.014 deg / 0.12 mm, oriented normals |
| ICP from 10 deg / 0.3 m, keep vertical | 2.4 to 3.5 mm | 0.011 deg / 0.26 mm |
| ICP from 10 deg / 0.3 m + 1 deg tilt, full 3D | 2.4 to 3.5 mm | 0.047 deg / 1.35 mm |
| ICP from -15 deg / 0.5 m, keep vertical | 2.4 to 3.5 mm | 0.016 deg / 0.20 mm |
| ICP within a section box (west half of the room) | - | 0.007 deg / 0.46 mm |
| Median deviation after ICP | 9.5 mm | 9.5 mm (noise: 10 mm expected) |
| Stop ICP, real click | not clickable (the click started a new run) | stops the run; the click took 20 s on the loaded machine, the button stayed at y 443.9 px |
| Picking behind an opaque wall | picked the floor behind it | nothing picked; through the ghosted wall the floor point is picked |

ICP run times in this session were 60 to 140 s (the machine ran 3 other agents' browsers; wave 6 measured 6.5 s);
the normal estimate before each run is time sliced too (cancellable with Stop ICP).
