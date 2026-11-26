# Appendix C. File formats

What the viewer reads, what it writes, and what each file is for. Format names such as `xray-views/1` are written inside the file
as `"schema"`. The number after the slash is the version. The viewer reads its own version. For a newer major version (for example
`xray-views/2`) it stops with a message and does not guess.

## Models

| Format | Read | Write | Notes |
| --- | --- | --- | --- |
| IFC (`.ifc`) | yes | yes, with **Save IFC** (a copy of your file with added data) | IFC2X3 and IFC4 are well tried. IFC4X3 beyond the sample files is untested. |
| IFC zip (`.ifczip`) | yes | no | Read like an IFC. |
| glb (`.glb`) | yes | yes, **Save cleaned model** | Y up, metres, one node per element. |
| Model sidecar (`.json`, `xray-model/1`) | yes | with a converted glb | Next to a glb with the same base name. Holds classes, storeys, properties and relations. Without it, classes are guessed from node names. |
| USDZ | no | yes | Export for AR Quick Look on iPhone and iPad (chapter 31). |

Several IFC files are **federated**: read as one model. Storeys with the same name and elevation (within 1 cm) are merged. An
element with the same GlobalId, class and bounds as an earlier one is skipped. The same GlobalId with a different shape is
renamed `<GlobalId>~<n>`. IFC and glb cannot be mixed in one opening. Only what the reader can mesh is shown (see appendix F).

`Save IFC` writes a block, marked by two comment lines, with the classification, the classification facets (`XR_` property sets, if you tick
**Include classification facets**), review marks and 4D values. It replaces its own
block on the next save and never edits what was in the file. Reviewer names go in only if you tick the box that asks for them.

## Issues and drawings

| Format | Read | Write | Notes |
| --- | --- | --- | --- |
| BCF zip (`.bcf`, `.bcfzip`) | BCF 2.0, 2.1, 3.0 | BCF 2.1 (default), 3.0 | Issues with camera, selected, hidden and coloured elements, clip planes and a picture. Drawings go in a side file inside each issue, which other tools ignore. |
| PDF (`.pdf`) | yes | yes, a marked-up copy | A drawing set: one sheet per page. Drawings are written as real PDF annotations. Encrypted PDFs are not supported. |
| Drawings of a view (`xray-markup-set/1`) | yes | yes | The file of drawings. The format name is the old one and stays, so older files keep working. Also embedded in a PDF report so it can be read back. |
| Issue report | no | PDF and CSV | For a meeting. |

## Point clouds

| Format | Read | Notes |
| --- | --- | --- |
| LAS 1.0 to 1.4 | yes | Not compressed. Point formats 0 to 10. |
| LAZ | no | The viewer says to convert it with PDAL or LAStools. |
| E57 | yes | The standard bit-pack codec only. No images. Several scans are merged. |
| PLY | yes | ASCII, binary little and big endian. |
| PCD | yes | ASCII, binary, binary compressed. |
| XYZ, TXT | yes | Text. `x y z`, optionally with intensity or colour. |
| PTS | yes | The first line is the point count. |

The kind of file is taken from its first bytes, so a wrongly named file still opens. One cloud at a time. The default budget is
3,000,000 points drawn.

## Schedules (4D)

| Format | Read | Write | Notes |
| --- | --- | --- | --- |
| Primavera P6 export (`.xer`) | yes | no | The schedule. One at a time. |
| 4D configuration (`.4d.json`, `xray-4d-config/1`) | yes | yes | How activity codes, user fields and WBS levels map to location, trade and zone. Dropping one on the viewer loads it as a configuration. |
| Storyboard (`.pdf`) | no | yes, **Storyboard PDF** or `xray-4d storyboard` | Still frames of the film with date, week, running work and the legend (27A.2). It is a picture book, not a file you can read back. |
| 4D plan (`xray-4d-plan/1`) | `xray-4d`, packed pages | `xray-4d plan` | What each element does at each date. Used by the player and by `xray-4d`. It also ends in `.4d.json`, like the configuration. The `schema` field tells them apart. |
| LinkML dataset (JSON) | yes | yes | Assignments, activity links and ties, with their review state. See below. |
| IFC 4D (`Xray_4D`, `IfcTask`) | yes | yes | Accepted values inside an IFC copy. |

### The LinkML dataset

The schema is `schema/linkml/xray_4d.yaml`. Two files are made from it: `xray_4d.sql` (SQL tables) and `xray_4d.schema.json`
(JSON Schema). `links.json`, which the viewer writes, validates against the JSON Schema.

- An activity is identified by its P6 Activity ID. An element is identified by its IFC GlobalId. A new XER or a re-exported IFC keeps every assignment and link.
- Rows have a status: `proposed`, `accepted`, `rejected` or `superseded`. Only accepted rows drive the 4D plan and go into the IFC.
- Schedule dates have no time zone (as P6 writes them). Record times (`created_at`, `reviewed_at`) have one.
- `reviewed_by` is personal data. It stays in the dataset. It is never in a link or a packed page, and goes into the IFC only if you ask.

The 4D configuration may hold `temporaryWorks` rules (scaffold, falsework, formwork; chapter 27A) and film style choices such as the finale and
a saved view for each storey. Both are optional: older files work as before.

## Changelog and What's new

`CHANGELOG.md`, at the root of the source, lists what changed in each release, newest first, with a heading `vN - date` for each. It is plain
text. The viewer carries it inside the page, shows the newest release once (3.6), and does not read it from anywhere else. A section named
"Unreleased" holds changes not yet released and is never shown.

## Looks, views and sharing

| Format | Schema | Made by | Holds |
| --- | --- | --- | --- |
| Parameters | `xray-params/1` | **Export / import**, **Export JSON** | All settings. A partial file is fine. |
| Presets | `xray-presets/1` | **Presets** drawer | One or more looks. |
| Views | `xray-views/1` | **Views** tab, **Export** | Views with their thumbnails. A bare list of views is read as version 1. |
| One shared view | `xray-view/1` | **Copy link** | One view, inside a link. |
| Fly-throughs | `xray-flythroughs/1` | Fly-through section, **Export file** | Keyframes, timing, captions. |
| Animation script | `.xrayanim` | **Script** tab, **Export** | Plain text, the script itself. A `.txt` is read too. |
| Sets | `xray-sets/1` | **Sets** tab, **Export** | Fixed sets, and query sets with their query. |
| Shortcuts | `xray-keymap/1` | Shortcut editor, **Export JSON** | Your key changes. |
| Class styles | `xray-config/1` (`xray.config.json`) | By hand, for an installation | Per-class opacity and colour. |
| Classification schema | `xray-classification-schema/1` | By hand | The list of allowed disciplines. |
| Classification review log | `xray-classification-review/1` | Classification tab | Who confirmed what. Contains reviewer names. |
| Field AR site | `xray-xr-site/1` | **Export site** | Point pairs and the registration (chapter 31). |
| Field AR notes | `xray-xr-notes/1` | **Download notes** | Snapshots with head poses. |
| Cleanup report | `xray-cleanup/1` | **Export report** | Elements the cleanup found and why. |
| Revision report | CSV | Revision walk, **Report** | One row per changed element with the verdict. |
| Video | MP4, WebM, PNG sequence | **Rec**, **Record** | Fly-throughs, scripts, 4D films. |

### Version rules

- A reader accepts its own version. A newer major version is refused with a message.
- Unknown fields are dropped. A missing id, time, up vector or field of view is filled in.
- An entry that cannot be read (a view with no name or camera) is skipped and listed. It is never skipped silently.

## What no file ever holds

Parameters, views, presets, links and packed pages never hold API keys, tokens, reviewer names or pictures of elements.
See appendix G.

## Coordinates and units

glb and the sidecar use metres, Y up. IFC is Z up, and the viewer turns it. The model is shifted so that the middle of its bounds is
near the origin. The shift is stored as `originShift`. A camera in a packed page (`--camera`) is in this viewer frame, not in
IFC coordinates.
