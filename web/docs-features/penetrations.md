# Penetration schedule

The `Penetrations` tool lists where MEP elements pass through structural hosts, and whether the host has an opening there.

## Definitions

- MEP set: elements whose class is in the classification focus classes (`scope` = `focus classes`, all MEP in the model) or the current focus set only (`focus only`).
- Hosts: context classes whose name contains slab, wall, beam, column, footing or roof.
- Candidate pairs come from a sort-and-sweep over the bounds, then `geometry.intersects` (surface crossing or containment) confirms. A duct running alongside a wall (bounds overlap, meshes do not) is not a penetration.
- Per penetration: `#`, MEP element, host, storey (of the host, else of the element), location (centre of the bounds intersection), orientation, size, host thickness, opening status, gap.
- Orientation comes from the long axis of the element, estimated by a principal-axis fit over 48 surface sample points: elevation of at least 75 degrees = vertical, at most 15 = horizontal, otherwise inclined.
- Size: the two smaller extents of the element bounds, rounded to mm. Approximate for inclined runs (the bounds are not aligned with the section). Host thickness: the smallest host bounds extent.

## Opening status

Openings come from `relations.openings` in the sidecar: `[{expressId, host, bounds}]`, the bounds of each IfcOpeningElement (its geometry is not drawn). `tools/ifc2glb.py` writes them (`relations.openings`, glb frame), the in-browser IFC reader produces the same, and the parity test compares both readers (same openings, same hosts, bounds within 1 cm).

| Status | Meaning |
| --- | --- |
| `opening` | an opening of that host contains the location (bounds containment, 5 mm tolerance), or the element is hosted by that host in `relations.hosts` (filler relation) |
| `none` | the model has opening data, but none of this host's openings contains the location (a host without openings at all counts) |
| `unknown` | the model has no opening data at all (older sidecars, glb files) |

Gap: the smallest clearance between the element cross-section and the containing opening, `(opening extent - element extent) / 2` over the two axes across the run, in mm. Negative means the opening is smaller than the element. Empty when hosted by relation only. If several openings contain the location, the smallest one is used.

## Drawer

Summary counts, filter chips (status, storey, host class), a sortable table (click a header), `Analyse`, `Export CSV` (the filtered rows), and `Create BCF topics` (the selected rows, else the filtered rows). The drawer analyses once when first opened for a model. Clicking a row selects the MEP element, flies the camera to the location (`window.__cinematic.flyTo` when present) and pulses a marker; Ctrl or Shift click selects several rows. Markers on the model: red = no opening, green = opening, grey = unknown (toggle with `markers`). At most 500 rows are listed; filter or export for the rest.

`Create BCF topics` calls `window.__xrayBcf.createTopics(list)` with one object per row: `{ title, description, labels, status, elementIds, elements (GlobalIds of the MEP element and the host), location {x,y,z} (viewer frame), ifcLocation {x,y,z} (IFC world, Z up) }`. When that API is missing the button is disabled with the reason in its tooltip.

CSV columns: id, mep_global_id, mep_class, mep_name, host_global_id, host_class, host_name, storey, orientation, size_a_mm, size_b_mm, host_thickness_mm, status, gap_mm, x_m, y_m, z_m (location in the viewer frame). Text cells starting with `=`, `+`, `-` or `@` get a leading apostrophe so spreadsheets do not run them.

## Panel folder, scripting, params

- Folder `Penetrations`: buttons `Analyse penetrations`, `Export penetrations CSV`; options `scope` (`focus classes`, `focus only`), `markers`.
- `window.__xrayPenetrations = { analyse({scope?, markers?}), rows, summary }`; `analyse` returns `{ rows, summary, ms, mepCount, hostCount, hasOpeningData }`.
- Params section `penetrations` (`scope`, `markers`; not in share URLs). Command `penetrations.analyse` (no default key).

## Limits

- Every overlapping MEP/host pair is a penetration, including an element that ends inside the host or runs along it for a short distance; the schedule is a candidate list for review.
- A host with openings but a sidecar without opening bounds reports `unknown`. Reconvert with the current converter, or open the IFC file in the browser.
- `synth5k` has a synthetic opening (overlap box plus 10 mm) for every MEP/slab overlap, so all its penetrations are `opening` with a 10 mm gap.
