# Model cleanup

The `Model cleanup` folder in the panel finds debris in a model and hides it without changing the model. Typical use: "hide floating elements smaller than 0.5 m". Nothing is deleted; `Restore cleanup` brings everything back.

## Workflow

1. Set the rules (all combinable).
2. `Preview matches` tints the matches magenta and frames them when fewer than 50 (matches inside walls are hidden behind opaque neighbours; use `Select matches` to see them in focus).
3. `Hide matches` adds them to the viewer's hide set, with provenance: cleanup remembers which ids it hid.
4. `Restore cleanup` removes only what cleanup hid. Elements you hid yourself (the eye icon, `Hide selected`) stay hidden, also when cleanup matched them too.
5. `Export report` downloads JSON (`xray-cleanup/1`) with ids, globalIds, classes, names and reasons.

Changing any rule cancels the preview. Rules are stored per model in localStorage `xray.cleanup.<model>` and appear in the params document as the `cleanup` section (rules and `applyOnLoad`, not the match list). With `apply on load` the rules are run and applied whenever the model loads.

Commands (command palette, no default key): `cleanup.preview`, `cleanup.hide`, `cleanup.restore`. Scripting: `window.__xrayCleanup = { analyse(rules?), preview(), hide(), restore(), setRules(patch), lastReport }`.

## Rules

| Folder | Controls | Meaning |
| --- | --- | --- |
| Floating | `enabled`, `size metric`, `threshold`, `mode`, `contact tolerance (m)`, `precise contacts` | Elements not connected to the main structure and smaller than the threshold |
| Tiny | `enabled`, `max size (m)` | Largest bounds dimension below the limit (default 0.05 m), connected or not |
| Distant strays | `enabled`, `distance factor` | Bounds centre further than k times the robust radius from the median centre (k = 6): geo-reference markers, objects at the origin |
| Duplicates | `enabled` | Same class, same triangle count, bounds within 2 mm: the lowest id stays, the others (which z-fight) match |
| Degenerate | `enabled` | No triangles, non-finite bounds, a bounds dimension below 0.1 mm, or a non-physical class (annotation, space, grid, virtual element, ...) that slipped through |
| Classes | `proxies`, `furniture`, `accessories and fasteners` | Quick class toggles: IfcBuildingElementProxy; IfcFurnishingElement, IfcFurniture, IfcSystemFurnitureElement; IfcDiscreteAccessory, IfcFastener, IfcMechanicalFastener |

### Floating

- Contact graph: two elements touch when the gap between their bounds is at most the contact tolerance (default 10 mm). Built by sort-and-sweep along the widest axis, close to O(n log n) plus the touching pairs (20,000 boxes in about 0.2 s).
- Components are the connected components of that graph. The main structure is the component with the largest total bounds volume (not the element count, so thousands of small pipe pieces cannot outrank the slabs and walls). The main component never matches.
- `size metric`: `largest dimension (m)` (default, threshold 0.5), `bounds volume (m³)`, `mesh volume (m³)` (absolute value of the signed tetrahedron sum; closed meshes only, open ones use the bounds volume), `triangle count`. The threshold is remembered per metric.
- `mode`: `single elements` matches only elements with no contact at all; `small clusters` matches whole components whose union is below the threshold (dimension and bounds volume of the union box; mesh volume and triangle count are sums).
- `precise contacts`: a bounds contact is kept only when the mesh surface distance is also within the tolerance, which drops diagonal elements whose boxes overlap but whose meshes do not. For speed, a pair is only refined when at least one side is smaller than the threshold.

Each match carries its reason, for example `floating lone element, no contacts: largest dimension 0.300 m < 0.500 m`.

## Limits

- Bounds based contacts treat a box as solid: an element inside the box of a large curved element counts as touching it unless `precise contacts` is on.
- Hidden matches stay in the model; sightlines, picking and the focus set ignore them (they are in `userHides`). Hidden elements are removed from the selection.
- Preview tints the render colour and is cleared by any rule change, `Hide matches` or a model change.
