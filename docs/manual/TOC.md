# X-ray BIM viewer: user manual, table of contents

Revised TOC (analysed and restructured; the earlier draft is in git history). Paths are relative to `/home/user/xray-ref`; `wd/` = `web/docs-features/`. Each section line says what the reader can do afterwards.
Reader tags: **[C]** coordinator / site engineer, **[P]** 4D planner, **[D]** integrator / developer. Untagged = everyone.

Order: learn to look (I-II), find and organise (III), check (IV), coordinate (V), enrich data (VI), change versions and write back (VII), present (VIII), plan in 4D (IX), hand over (X), automate (XI).

---

## Part I. Getting started

### 1. What the viewer is and the x-ray idea in one page
Sources: `README.md` (intro), `SPEC.md` (Focus / Context / Host / Near / occluder), `docs/SETTINGS.md` (Glossary)
- 1.1 Focus, context, occluder: explain in two sentences why a wall ghosts when you select a duct.
- 1.2 What runs where: tell the single file, the served app and a packed page apart, and know that nothing is uploaded.
- 1.3 Who reads which part: pick your route through the manual.

### 2. Opening the viewer and a model
Sources: `README.md` (Quick start, Opening your own files), `wd/large-ifc.md`, `SPEC.md` (Opening files)
- 2.1 Start from `xray-viewer.html` or from source: get a model on screen.
- 2.2 Open IFC, IFCZIP, glb by button or drop; federate several IFC files; read a one-line load error.
- 2.3 Sample Projects: try the viewer with no data of your own.
- 2.4 Large models: choose `edges` and `properties` options and read Load status for a 100,000-element file.

### 3. The screen and moving around
Sources: `wd/topbar.md`, `wd/toolbar.md`, `wd/right-sidebar.md`, `wd/gizmo.md`, `wd/pointer-modes.md`, `wd/hover-info.md`, `wd/undo.md`
- 3.1 The screen map: name the top bar, left sidebar (Model, Sets, Views, Issues), tool strip, right sidebar (Properties, Classification, Parameters, Script, 4D, Revision), gizmo and status bar.
- 3.2 Moving around: orbit, pan, zoom (BIM-style mouse), Arrow vs Hand [R/G], Walk mode, the Navigation style setting, the view cube, home and projection buttons.
- 3.3 Select, hover cards and the Properties tab: read any element's data.
- 3.4 Undo and redo for view, selection and settings; what is not undoable.
- 3.5 On a phone: bottom sheets and the folded sidebars.
- 3.6 What's new: the card on the first start of a new version, Show all changes, the command palette action. (`wd/whats-new.md`) The card reads `CHANGELOG.md`; "Unreleased" is never shown.
- 3.7 Keyboard, focus and F6, command palette, cheat sheet [?]: do common actions without the mouse. (`wd/keyboard.md`)

---

## Part II. Seeing through the model

### 4. X-ray: let the structure get out of the way
Sources: `README.md` (Viewing), `SPEC.md`, `docs/SETTINGS.md` (X-ray, Classification Alg 1, Sightlines, Display, Overrides), `docs/REPORT-appendix-N.md`
- 4.1 Switch x-ray on [X] and select a duct: see only the blockers ghost.
- 4.2 Tune ghosting (alpha range, gamma, buffer, far mode, tiers, depth grading) until it reads right.
- 4.3 Pins, hides and class styles: keep or remove specific things regardless of the algorithm. `README.md` (Class styles)
- 4.4 Top-bar modes: Solid, Ghost, Radiograph, Glow, Cutaway [Shift+1..4]. `wd/topbar.md`
- 4.5 Presets and keys 1-9; save your own. `wd/presets.md`

### 5. Cutting and peeling (one clipping system)
Sources: `wd/view-modes.md`, `wd/section.md`, `wd/gizmo.md`
- 5.1 Behind-only and partial peelback: look at what is behind the focus, not in front.
- 5.2 Section box and section plane with caps; drag handles; fit to selection.
- 5.3 Exploded storeys: separate floors without changing picking.
- 5.4 One clipping system: the section tool, issue viewpoints and Plan/Section views all set the same cut planes.

### 6. Imaging looks and context
Sources: `wd/imaging.md`, `wd/map.md`
- 6.1 Radiograph and MRI slice: pick a palette and read thickness as brightness.
- 6.2 Map under the model: turn it on knowing it sends the location to a tile server.
- 6.3 Cinematic effects (bloom, edge glow, fly-to, sweep reveal, scene dressing): use them for presentations, not analysis. `docs/SETTINGS.md` (Cinematic)

---

## Part III. Finding and organising elements

### 7. Model tree and search
Sources: `wd/search.md`, `README.md` (Navigation), `wd/right-sidebar.md`
- 7.1 Browse the Model tree; keys; hide, isolate, show.
- 7.2 Search bar: find elements, commands, presets, views, sets, settings.
- 7.3 WHERE queries typed into search: filter by class or property.

### 8. Selection sets and the query language (taught once, used everywhere)
Sources: `wd/sets-query.md`, `README.md` (Selection sets)
- 8.1 Save the selection as a static set.
- 8.2 Build a criteria set (`class = 'IfcWall' AND ...`) that updates itself.
- 8.3 Export and import sets; use a set as a target elsewhere (4D, scripts, issues).

### 9. Cleaning a messy model
Sources: `wd/cleanup.md`, `README.md` (debris-demo)
- 9.1 Find floating, tiny, distant, duplicate and degenerate elements; preview, hide, restore.
- 9.2 Know that nothing is deleted, and when to save the result (see 19.3).

---

## Part IV. Measuring and checking

### 10. Measure and clearance
Sources: `wd/measure.md`
- 10.1 Point-to-point and element-to-element distances with snapping.
- 10.2 Clearance colouring: see which context elements are too close to the focus.

### 11. Penetrations
Sources: `wd/penetrations.md`
- 11.1 List where MEP crosses hosts and whether an opening exists.
- 11.2 Raise findings as issues (see 15.3).

### 12. As-built scans
Sources: `wd/pointcloud.md`
- 12.1 Load a LAS/E57/PLY/PCD/XYZ cloud and align it to the model.
- 12.2 Colour by deviation: judge whether a duct is where the model says.

---

## Part V. Views and issues: capturing and coordinating

Product model (decided 2026-11-23): two nouns. A **view** captures a moment (camera, what is shown, cut and selected) and may
carry **drawings**; a page of a PDF sheet is a view too. An **issue** is a problem someone must act on (status, assignee,
comments) and points at one or more views. "Sketch" and "markup" are retired as user words (glossary: "formerly").
BCF is only the exchange format. Sources: `wd/saved-views.md`, `wd/issues.md`, `wd/markup.md`, `wd/sheets.md`, `wd/bcf.md`,
`docs/design/views-and-issues.md` (written with the product change).

### 13. Views: capture a moment, come back to it
- 13.1 Why views: the model is too big to describe in words; a view is a sentence that points.
- 13.2 Save, name, reorder, restore a view; exactly what a view stores (and the ladder: mode, preset, view, keyframe, share link).
- 13.3 Plan and Section of a view: a derived orthographic look at what a view is about.
- 13.4 Export, import and share a view.

### 14. Drawing on a view
- 14.1 Clouds, arrows, text, callouts, shapes, pen; view-locked or attached to the model.
- 14.2 Attached drawings: why a cloud on a wall stays on the wall when you orbit, and after a revision.
- 14.3 Export a view with its drawings as PDF or JSON.

### 15. Issues
- 15.1 When something needs an owner: make an issue from a view (or several).
- 15.2 Status, priority, assignee, due date, comments, history.
- 15.3 Issues from checks: penetrations and clearance results, deduplicated.
- 15.4 Reports: PDF and CSV for a meeting.

### 16. PDF sheets: the drawings you already have
- 16.1 Open a drawing set; pages are views you can draw on.
- 16.2 Place a sheet in the model (and geo-referenced PDFs); overlay model and sheet.
- 16.3 Export a marked-up PDF with real annotations; import existing annotations.

### 17. Exchanging issues: BCF
- 17.1 Open and export BCF 2.0/2.1/3.0; what survives a round trip; derived Plan/Section viewpoints.

---

## Part VI. Classification and model data

### 18. Classifying elements
Sources: `wd/classify.md`, `wd/right-sidebar.md`, `docs/SETTINGS.md` (Classify drawer)
- 18.1 Run rules and a decision model (in-browser, WebGPU, endpoint); understand confidence.
- 18.2 Review: Accept, Change, Unsure; the review walk.
- 18.3 Code lists: use the default schema or import a Throughline `Discipline` list; export results.
- 18.4 [D] Calibration and truth files (`web/tools/classify-truth.mjs`).

### 18A. Facets, the classification tree and colours
Sources: `wd/classify.md` (Facets, Classification tree and colours), `wd/classification-tree.md`, `docs/design/classification-facets.md`
- 18A.1 Facets (Trade, Placement, Material, Phase, Orientation, ClassRepair) and the `XR_` namespace with its core fields; try them on FZK-Haus.
- 18A.2 The By classification tree: presets Construction, Ownership, Envelope, Standard (UniFormat II); Custom; **+set**.
- 18A.3 Colour by facet and Confidence shading.

### 18B. Concrete elements
Sources: `wd/classify.md` (Concrete), `docs/design/concrete-classification.md`
- 18B.1 Why concrete is special; the five `XR_Concrete*` sets (geometry, role and mark, method, spec, reinforcement intent); how they prepare rebar matching.

### 19. Parameters, properties and saving
Sources: `wd/ifc-save.md`, `docs/design/ifc-save-and-revision.md`, `README.md` (Settings and tooltips), `docs/SETTINGS.md`
- 19.1 Export and import parameters (`xray-params/1`).
- 19.2 Read every property set and quantity; copy a GlobalId.
- 19.3 Save IFC and Save cleaned IFC: write classification, review and cleanup marks into a copy of the file; **Include classification facets** writes the `XR_` sets.
- 19.4 What is saved where: one table (IFC copy, browser storage, share link, params, exports, 4D files).

---

## Part VII. Revisions

### 20. Comparing a new model version
Sources: `wd/revision.md`, `docs/design/ifc-save-and-revision.md`
- 20.1 Start a revision walk with base and head models.
- 20.2 Walk only changed elements; carry earlier decisions forward; bulk rules.
- 20.3 Resume after a reload; export the CSV report; use it on a phone.

---

## Part VIII. Presenting

### 21. One player behind every "Play"
Sources: `wd/flythrough.md`, `wd/4d-playback.md`, `wd/animation-script.md`
- 21.1 Fly-throughs, scripts, 4D films and kiosk autoplay are one timeline played by one player: pause, scrub, keys, restore at the end, the HUD.

### 22. Fly-throughs
Sources: `wd/flythrough.md`
- 22.1 Build a fly-through from saved views with timing, holds, easing, fades, captions.
- 22.2 Play, pause, scrub; use the on-screen HUD.
- 22.3 Export video (MP4/WebM, 720p to 4K, PNG sequence, recorder fallback).

### 23. Animation scripts
Sources: `wd/animation-script.md`, `wd/animation-script-guide.md`, `wd/animation-script-grammar.md`
- 23.1 Write a first script (`fly to class IfcPump over 3 seconds`) and Run.
- 23.2 Fades, captions, loops over sets; read error messages.
- 23.3 [D] Grammar reference.

### 23A. Scripts that decide: logic, text and reuse
Sources: `wd/animation-script-guide.md` (13 to 15), `wd/animation-script-grammar.md` (2.1, 2.2, 4.1)
- 23A.1 `if`/`else`, `repeat while|until|with`, `exit repeat`, `next repeat`. 23A.2 Handlers and functions. 23A.3 `show`/`hide issues` and `drawings`, `fade new elements`.
- 23A.4 Element properties, text tests, lists and chunks, maths, seeded random. 23A.5 `param` and `use`.

---

## Part IX. 4D

### 24. 4D in one page: what you need
Sources: `docs/design/4d-xer-animation.md`, `wd/4d-schedule.md`
- 24.1 Describe the chain XER + model -> assignments -> links -> plan -> film.
### 25. Mapping elements to location, trade, zone
Sources: `wd/4d-mapping.md`
- 25.1 Assign manually; accept proposals from storeys, zones, class or the classifier; read coverage.
### 26. Linking the schedule
Sources: `wd/4d-schedule.md`, `wd/4d-linking.md`
- 26.1 Open a `.xer`; configure codes and WBS; link; resolve ties and suggestions; read the link report.
- 26.2 Save accepted links into the IFC (`Xray_4D.ActivityIds`).
### 27. Playing and recording the 4D film
Sources: `wd/4d-playback.md`, `wd/4d-director.md`, `wd/4d-schedule.md`
- 27.1 Style, scrub by date, play; read the HUD (S-curve, milestones, legend).
- 27.2 Let the director frame it, edit the resulting script, record. Style: Each floor apart, Fade in (s), Issues and drawings in the film, Camera per floor, Finale; the colour legend and the schedule strip.

### 27A. Temporary works and the storyboard PDF
Sources: `wd/4d-temporary-works.md`, `wd/4d-storyboard.md`
- 27A.1 Scaffold, falsework and formwork from rules. 27A.2 Storyboard PDF from the film bar; `xray-4d storyboard`.
### 28. Exchanging 4D data
Sources: `schema/linkml/README.md`, `.4d.json` in `wd/4d-schedule.md`
- 28.1 Import and export `.4d.json` and the LinkML dataset.

---

## Part X. Sharing and packaging

### 29. Sharing without a server
Sources: `README.md` (share links), `wd/saved-views.md`, `wd/presets.md`
- 29.1 Share link: what it carries and what it never carries.
- 29.2 Send a single file.
### 30. Packed pages with xray-pack  [D]
Sources: `wd/xray-pack.md`, `web/tools/xray-pack.mjs --help`
- 30.1 Pack IFC/glb into one HTML; set params, preset, selection, camera.
- 30.2 Kiosk pages: autoplay and loop a fly-through, script or 4D plan; limits and size.
### 31. AR and VR (experimental)
Sources: `wd/webxr.md`
- 31.1 VR walk, tabletop AR, field AR at real size on site.

---

## Part XI. Automation

### 32. xray-4d command line  [P][D]
Sources: `wd/xray-4d.md`, `wd/4d-linking.md`
- 32.1 `inspect`, `link`, `plan`, `script`, `render`, `storyboard`, `pack`, `all`; weekly CI run; IFC write-back.
### 33. The agent skill ifc-4d-schedule  [D]
Sources: `skills/README.md`, `skills/ifc-4d-schedule/SKILL.md`
- 33.1 Install; link a schedule with an agent; review proposals.
### 34. SQL, MCP and LinkML  [D]
Sources: `schema/linkml/README.md`, `schema/linkml/xray_4d.yaml`
- 34.1 Use the SQL tables and JSON Schema; proposed/accepted/superseded rows.
### 35. Scripting hooks and plugins  [D]
Sources: `README.md` (Development, Plugin architecture), `SPEC.md` (Extensions, Shared contracts), `wd/toolbar.md`
- 35.1 `window.__xray*` objects; add an action or tool.

---

## Appendices
- A. Keyboard reference and shortcut editor: `wd/keyboard.md`, `docs/SETTINGS.md` (Keyboard, Shortcut sheet)
- B. Settings reference (generated): `docs/SETTINGS.md`; `web/tools/gen-settings-doc.mjs`
- C. File formats (and the changelog): IFC/IFCZIP/glb/sidecar, storyboard PDF, BCF, PDF, point clouds, XER, `xray-params/1`, `xray-views/1`, `xray-flythroughs/1`, `xray-sets/1`, `xray-markup-set/1`, `.xrayanim`, `.4d.json`, LinkML. Sources: `SPEC.md`, feature docs
- D. Presets table (14)
- E. Glossary: `docs/SETTINGS.md` (Glossary)
- F. Limits and known issues: `README.md` (Known limitations), `wd/*` Limitations
- G. Privacy and data: what is stored in localStorage, what the map sends, `reviewed_by`, what share links and packed pages exclude
- H. Troubleshooting (load errors, Firefox/Safari untested, file:// storage)

---

## Overlaps to resolve

1. **Issues vs Sketches vs BCF vs markup vs sheet sketches.** One drawing engine, two containers, BCF is the file format, and the old names (markup, BCF drawer, topic) still appear in the docs. Present one decision table (13.1), use "issue / sketch / sheet sketch", mention BCF only as the file format, and put "formerly" names in the glossary.
2. **Saved views vs fly-through keyframes vs presets vs top-bar modes vs share links.** All are bundles of camera and settings. Teach them as a ladder: mode = one click on a preset; preset = look only, never camera; view = camera + look + selection/hides; keyframe = a view + timing; share link = a view as a URL. Include a table of what each stores.
3. **Several "play" features.** Fly-through, animation script, 4D plan and kiosk autoplay all use the one score player and HUD. Explain the player once (Part VIII), then show how each source feeds it.
4. **View modes folder vs Imaging vs top-bar modes vs presets 3-9.** The same renderer features reached from four places. Name the controls once and list entry points.
5. **Section: box/plane vs gizmo strip vs BCF clip planes vs sketch Plan/Section.** Explain one clipping system and the places that use it.
6. **Where tools live.** BCF, Markup and Classify were once drawers and are now tabs; the toolbar doc keeps pointers. Use the current layout only.
7. **4D appears in four places** (tab, CLI, agent skill, LinkML). Write one workflow chapter and cross-reference each interface.
8. **Save IFC vs Save cleaned IFC vs share link vs params export vs Export in 4D/classify.** Add a "what do I save where" table in 18.
9. **Search vs Sets criteria query vs Script queries.** One query language; teach it once (8.2) and link.
