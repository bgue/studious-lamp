# 12. As-built scans

## The problem

The design says the duct runs 300 mm from the wall. On site it was fitted by hand. Someone scanned the room with a laser
scanner or a phone, and now you have millions of points and a model. Is the duct where the model says? Looking at the two
side by side tells you little. You need the viewer to say, point by point, how far the scan is from the model.

## The idea

A **point cloud** is what a scanner records: a very large number of points on the surfaces it saw. The viewer draws it
in the same scene as the model, so you can orbit them together. Then it does two things.

First, it **aligns** the cloud to the model. A scanner does not know where the building's origin is. Alignment moves and
turns the cloud so that the real wall sits on top of the modelled wall.

Second, it measures **deviation**: for every point, the distance to the nearest model surface. Points within your
tolerance turn green, points up to twice the tolerance turn amber, points further out turn red. Where the duct was fitted
50 mm off, its points are red, and the rest of the room is green. That is the as-built check.

## 12.1 Load a cloud and align it

### Try it

1. Open **Sample Projects** and choose **Building (Simple-Scene)**.
2. Open the **Scan** tool in the tool strip. In the drawer press **Open point cloud**, or drop a scan file anywhere on the viewer.
   Use the file `building-scan.las`. The scans are not in the **Sample Projects** menu and the single file does not carry them. You find them in the folder `web/public/samples` of the source or of the zip.
3. The status line shows the file's point count, how many are shown, the format and the parse time. The points appear in
   the model.
4. Look at `coordinates`. The sample is in project coordinates (what survey tools write), so it is set to `project` and
   lands in place. If a cloud lands far away or lying on its side, try `viewer` instead.
5. To try alignment, open `building-phone-scan.ply` instead. This is a scan of one room from a phone, in its own frame, and it
   will not land in place. Set `coordinates` to `viewer`, because phone scans are Y-up.
6. Press **Align by 3 points**. Click a point on the cloud, then the same feature on the model, such as a floor corner.
   A cyan numbered circle marks the cloud point and an orange numbered square the model point. Do this 3 times or more, using
   features that are far apart.
7. The drawer lists the leftover error of each pair and the overall RMS. Press **Apply alignment**.
8. Press **Refine (ICP)**. The cloud settles onto the surfaces. The status line reports how far it moved and the remaining error.
9. If you slip, **Undo alignment** steps back through the last 20 actions. **Reset alignment** clears everything.

### Formats

| Format | Notes |
| --- | --- |
| LAS 1.0 to 1.4 | uncompressed only; colour, intensity and classification are read |
| LAZ | not supported. The viewer says how to convert it (PDAL or LAStools) |
| E57 | the usual output of terrestrial scanners and many phone apps; all scans in the file are merged |
| PLY | ascii or binary |
| PCD | ascii, binary, compressed |
| XYZ, TXT, PTS | text, with optional colour and intensity |

The format is read from the first bytes of the file, so a wrongly named file still opens. Files over 5 MB are read in the
background, with progress in the status line.

### What each alignment step does

| Step | Use it when | What it does |
| --- | --- | --- |
| `coordinates` | always, first | says which frame the file is in: `project` (IFC, Z up) or `viewer` (Y up) |
| `offset x/y/z`, `rotation (deg)` | a small fix by hand | nudges the cloud, in m and degrees |
| **Auto-align to model** | the scan covers the whole building | puts the centres together and tries four headings |
| **Align by 3 points** | the scan covers part of the building, or auto-align missed | solves the move and the turn from pairs you click |
| **Refine (ICP)** | after a rough fit | pulls the cloud onto the surfaces |

Two switches matter. `keep vertical` is on by default. It solves only the heading and the move, because phone and
tripod scans are level, and a tilt is nearly always a clicking error. `allow scale` is off. A scan is in metres, so a scale far
from 1 is a warning sign. Only 3-point alignment can change the scale.

`align within` limits 3-point alignment and ICP to the section box or the selection. This is how you check one room at a
time: put a section box around the room, set `align within` to section box, refine, then compute deviation. The next
room needs a new box and a new fit.

### How it works

The cloud and the model are one scene, and points are depth tested against the model. So a point behind a wall is hidden,
also when the wall is ghosted. The cloud is drawn before the ghost pass, so it stays visible behind ghosts.

Three points are the least that fix a position, and more pairs average out your clicking error. The viewer solves for the
move and turn that best fits all pairs. ICP does the same without clicks: it samples about 20,000 points, finds for each
the closest model surface (taking the direction of the surface into account, so a point does not jump to the other face of a
thin wall), and repeats up to 30 times, throwing away the worst 15 percent each round. If the result is worse than the
start, it keeps the old alignment and says so.

After ICP the drawer shows a 3 x 3 grid of the remaining error over the plan. If one corner is much worse, the scan has
probably drifted: a long phone walk bends slowly. A rigid fit cannot fix that. That is what room-by-room is for.

### Limits and gotchas

- One cloud at a time.
- A point cloud is a sample. The **point budget** (3 million by default, up to 10 million) caps how many points are
  drawn. A larger file is sampled evenly at random. Changing the budget does not read the file again.
- ICP has a narrow reach: about 15 degrees and half a metre. Start with 3 points if the scan is far off.
- You cannot measure on the cloud. Points are picked only for alignment.
- In a single-file page the file is read on the main thread, so a big cloud blocks the page for a moment.

## 12.2 Colour by deviation

### Try it

1. With the sample scan aligned to the **Building** model, leave `tolerance (m)` at 0.02 (2 cm) and `deviation scope` at `all elements`. Press **Compute deviation**.
2. The points colour: green within 2 cm, amber from 2 to 4 cm, red from 4 to 10 cm, grey beyond 10 cm. A legend appears
   at the bottom right of the view, and the status line gives the share within tolerance, the median and the 95th percentile.
3. Look for the duct. In the sample scan it was displaced on purpose by 80 mm. Its points are red, and the walls are
   mostly green.
4. Select the duct. Set `deviation scope` to `focus only` and compute again. Now every point is measured against the duct
   only. The rest of the room turns grey, because it is not near the duct.

### Reading the colours

| Colour | Distance d from the nearest surface, with tolerance `tol` |
| --- | --- |
| green | `d` up to `tol` |
| amber | `d` above `tol` up to 2 `tol` |
| red | `d` above 2 `tol` up to 5 `tol` |
| grey | `d` above 5 `tol`, unrelated |

Grey is not an error. It is the scan of something the model does not contain: furniture, a person, another room. With
`focus only` nearly everything else is grey.

### How it works

For each shown point the viewer asks the model's geometry for the nearest surface, up to 5 times the tolerance away. For
a cloud with more than 500,000 shown points it uses an even sample of 500,000. It works in slices of 8 ms, so the page
stays usable and shows progress. Changing the alignment, the budget, the coordinates, the tolerance or the model throws
the result away, because it no longer describes what is on screen.

Amber and red points are drawn a second time on top of everything, so a displaced duct inside a ghosted wall still shows.

### Choices and settings

- `tolerance (m)`: default 0.02. Set it to the tolerance your specification gives for the work you check.
- `deviation scope`: `all elements` or `focus only`.
- `colour by`: `rgb`, `intensity`, `height`, `classification` or `deviation`.
- `point size`, `size attenuation`, `visible`.
- The alignment and display settings are in the parameters document (19.1). The points themselves are not. Reopen the file next
  time.

### Limits and gotchas

- Deviation is the distance to the **nearest** surface, not along a wall's normal, and it does not know which side of the
  surface the point is on. A point 5 cm behind a wall counts as 5 cm off.
- Distances beyond 5 times the tolerance are not measured.
- A bad alignment shows as deviation everywhere. If the whole room is amber, fix the alignment before you blame the duct.
- Points are plain squares of one colour. There is no level-of-detail tree, so very large clouds are shown as a sample.
- Scanned clouds miss surfaces that the scanner could not see. A missing patch is not a deviation.

## See also

- 10.2 Clearance: distances between model elements.
- 2.2 Opening files.
- 19.1 Parameters document.
