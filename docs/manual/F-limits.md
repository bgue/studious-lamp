# Appendix F. Limits and known issues

Read this before you promise something to a client. It is grouped by what you were doing. Items marked *experimental* or
*untested* have not been confirmed on real devices or browsers.

## Browsers and where it runs

- Chromium, Edge and Chrome are the tested browsers. **Firefox and Safari were not tested**, and the single-file build in particular needs `Worker` from a blob address and `DecompressionStream`.
- A software renderer (for example in a virtual machine) is slow. Frame times measured there are not graphics-card numbers.
- On a `file://` page, `localStorage` belongs to the browser profile. Stored sets and style changes may not survive a reload in some browsers (appendix H).

## Seeing

- **Focus in front** draws the focus with the depth test off. It is never hidden, not even by an opaque far element.
- **Ghosting is order independent only where the graphics card gives float colour buffers.** Without them, overlapping ghosts blend in draw order.
- **Imaging** (radiograph, MRI) needs float colour buffers. Without them the look stays standard and the status line says why. It assumes closed solids; overlapping elements add up; the peel window is computed at half resolution.
- **Caps are back faces, not cap polygons.** An open mesh shows its back faces in the cap colour. A ghosted element is cut without a cap.
- **The section box is axis aligned** in the viewer frame. Its handles are drawn without a depth test, so a handle behind the model still shows.
- **Peelback** uses one depth per focus pixel. A duct that runs away from the camera is cut at the depth of its nearest outline pixel. The rim of the window can show a 1 to 2 pixel step.
- **With x-ray off**, everything is opaque and your hides are not applied.
- **Smoothing is per frame**, not per second, so the speed of a fade depends on the frame rate.
- **Picking** uses the CPU. It ignores explode offsets. Elements below 0.3 opacity are click-through unless they are the focus. With a view mode on, it also skips what the mode removes.
- **The orthographic switch is an approximation.** It uses a very narrow field of view with the camera moved back.
- **The map** is a flat disc under the model, seen from above only. It is not cut by sections and cannot be measured on.

## Opening files

- Only what the IFC reader can mesh is shown. Some advanced B-rep, B-spline, unusual boolean and swept shapes are missing without a message, and so are IFC4X3 alignment shapes. The console counts products without geometry as `[ifc-import]`. Openings that the reader cannot subtract leave the host solid.
- IFC2X3 and IFC4 are well tried. IFC4X3 beyond the samples is untested.
- Memory is about 25 times the file size at 40 MB. Files of tens of MB are practical. A few hundred MB are not. There is no streaming and no level of detail.
- Properties are the element's own sets only: no type properties, no list or table values, at most 24 per element.
- The edge lines are all or nothing per model. Above 50,000 elements, `auto` skips them.
- Over 100 MB in total the loader warns and carries on.
- IFC and glb cannot be mixed in one opening. Only one glb at a time.

## Cleaning and checking

- **Cleanup**: bounds-based contacts treat a box as solid (use `precise contacts` for curved elements). Matches are hidden, not deleted. Simplification shows in the saved file, not in the live view.
- **Clearance** colours whole elements, not regions. The host of the focus always shows as a clash. It shares colour state with the cleanup preview: switch one off before the other.
- **Penetrations**: every overlapping MEP and host pair counts, including an element that ends inside the host. The list is a list of candidates to review. A model without opening data reports `unknown`. At most 500 rows are listed.
- **Point clouds**: one at a time. No LAZ. E57 only with the standard codec and without images. Auto-align is a coarse match of bounds centres; 3-point alignment and ICP are rigid, so scan drift is not corrected. Deviation is the distance to the nearest surface, measured up to 5 times the tolerance.

## Views, drawings, issues and sheets

- Views are per browser and per model name. The same model opened from a file under another name has its own list. Export and import to move them.
- A view's thumbnail is taken at save time and can show a half-faded ghost. A view imported without thumbnails shows "no picture" until you update it.
- A view link carries differences from the receiver's factory look, so a viewer with another configuration can look slightly different.
- **BCF**: orthographic cameras are approximated. Viewpoint roll, lines, bitmaps and colour opacity are ignored. Elements match by GlobalId only. Existing issues can change status and gain comments, but not other fields. No zip64. Pins and drawings reach other programs only as the burned-in picture and the viewpoint selection.
- Drawings that are attached to the model are projected on screen with no depth test: a cloud on a wall still shows when another element hides that wall from the new camera.
- A region is a box aligned to the IFC axes, not an oriented box.
- 3D drawings and issues are kept in the browser's IndexedDB, not in a file. Export to share them, or to keep them if site data is cleared.
- **PDF sheets**: placing works for plan sheets only. A geo-referenced PDF in a coordinate system other than the model's is not converted. Marked-up PDFs were checked structurally, not opened in Acrobat or Bluebeam. Text in a free-text annotation is drawn in Helvetica, and other characters become `?` in the picture (the text itself is kept). The whole file is rewritten on export. Encrypted PDFs are not supported.

## Classification and revisions

- Classification answers carry a confidence. Low confidence means review, not an error.
- A decision model in the browser downloads its weights on first use from the internet (appendix G).
- The property difference of a revision sees only what the viewer loaded. Writing back adds data and never edits existing data.
- A revision snapshot store keeps 3 snapshots per file name and 300 MB in all, oldest first.

## 4D

- One schedule per model at a time. A baseline is not loaded in the viewer.
- The configuration screen edits the first source of each attribute only. The model side of the configuration is read from the file and not edited in the tab.
- The review list shows the first 60 suggestions, and the unlinked list the first 40 groups.
- Zones come from IFC groups named with "zone". Others are added by hand.
- The Python converter does not read back the `Xray_4D` values, so a glb sidecar carries none. Open the IFC.
- One edge glow colour pair is used while the film plays: amber for active work, red for critical work. The film does not move the camera by itself; use camera cues.

## Presenting and sharing

- Fly-through captions and scripts are your own text. They are never in a link, a view or a preset.
- A packed page grows with the model: base64 makes it 4/3 of the glb. Browsers get slow on pages of more than a few tens of MB. One glb per page. Pack with the viewer version you want the recipient to have.
- `--preset` and `--open-tool` are skipped with a console warning when the part they need is not in the build.
- The retired **tour** feature (a path through selected elements) exists only as an older settings folder. Use fly-throughs.

## AR and VR (experimental)

- Tested only against an emulated headset. No device was tried.
- In a session the viewer leaves out radiograph and MRI looks, the peel window, ambient shading, bloom and depth of field, and order-independent ghosting.
- No teleport. No depth sensing: real objects do not hide the model.
- Field AR has no tilt in the registration, no photo in snapshots (a page cannot read the camera picture), no persistent anchors on Android Chrome, and a cut that is a box.
- iPhone and iPad have no WebXR in any browser. AR Quick Look shows a static export without registration.

## Samples

- The `building` and `plumbing` samples have no opening relations, so penetration host detection uses the geometric fallback. `synth5k` and `debris-demo` have made-up openings.
- The FZK-Haus is a freely published sample. Check its licence upstream before you redistribute it outside a trial.
