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
| Floating | `enabled`, `size metric`, `threshold (m)`, `mode`, `contact tolerance (m)`, `precise contacts` | Elements not connected to the main structure and smaller than the threshold |
| Tiny | `enabled`, `max size (m)` | Largest bounds dimension below the limit (default 0.05 m = 50 mm), connected or not |
| Distant strays | `enabled`, `distance factor (× radius)`, `min gap (m)`, `max size (m)` | Bounds centre further than k times the robust radius from the median centre (k = 6): geo-reference markers, objects at the origin. Optional: at least `min gap` outside the box of the main model, and no larger than `max size` (0 turns either limit off) |
| Duplicates | `enabled` | Same class, same triangle count, bounds within 2 mm: the lowest id stays, the others (which z-fight) match |
| Degenerate | `enabled` | No triangles, non-finite bounds, a bounds dimension below 0.1 mm, or a non-physical class (annotation, space, grid, virtual element, ...) that slipped through |
| Classes | `proxies`, `furniture`, `accessories and fasteners` | Quick class toggles: IfcBuildingElementProxy; IfcFurnishingElement, IfcFurniture, IfcSystemFurnitureElement; IfcDiscreteAccessory, IfcFastener, IfcMechanicalFastener |

### Units

Every threshold names its unit in its label. Lengths follow the `length unit` list at the top of the folder (`mm`, `cm` or
`m`, default `m`; also in the Cleanup drawer): `threshold (mm)`, `contact tolerance (mm)`, `max size (mm)`, `min gap (mm)`.
The number converts when the unit changes; the rules always store metres, so the params document, `setRules` and the report
stay in SI units (`tiny.maxSize: 0.05` is 50 mm). The unit is a viewer preference (localStorage `xray.cleanup.lengthUnit`),
not part of the rules. Volumes are in m³ (`threshold (m³)` for the volume metrics), the triangle metric is a count
(`threshold (triangles)`) and the strays factor is a multiple of the robust radius (`× radius`).

### Floating

- Contact graph: two elements touch when the gap between their bounds is at most the contact tolerance (default 10 mm). Built by sort-and-sweep along the widest axis, close to O(n log n) plus the touching pairs (20,000 boxes in about 0.2 s).
- Components are the connected components of that graph. The main structure is the component with the largest total bounds volume (not the element count, so thousands of small pipe pieces cannot outrank the slabs and walls). The main component never matches.
- `size metric`: `largest dimension` (default, threshold 0.5 m), `bounds volume` (m³), `mesh volume` (m³; absolute value of the signed tetrahedron sum; closed meshes only, open ones use the bounds volume), `triangle count`. The list shows the names without units (the threshold label carries the unit); the stored values keep their old spelling (`largest dimension (m)`, `bounds volume (m³)`, ...). The threshold is remembered per metric.
- `mode`: `single elements` matches only elements with no contact at all; `small clusters` matches whole components whose union is below the threshold (dimension and bounds volume of the union box; mesh volume and triangle count are sums).
- `precise contacts`: a bounds contact is kept only when the mesh surface distance is also within the tolerance, which drops diagonal elements whose boxes overlap but whose meshes do not. For speed, a pair is only refined when at least one side is smaller than the threshold.

### Distant strays

The median of the element centres is the model centre and the median distance from it is the robust radius r. An element
whose centre lies further than `distance factor` × r matches. Two optional limits narrow that down:

- `min gap (m)`: the element must also lie at least this far outside the box of the elements within k × r (the main model).
  Use it to keep things that sit just beside a long or spread-out model.
- `max size (m)`: only elements whose largest bounds dimension is at most this match, so a large misplaced part (a site model,
  a second building) is not hidden as debris.

Each match carries its reason, for example `floating lone element, no contacts: largest dimension 0.300 m < 0.500 m` or
`distant stray: 312 m from the model centre > 6.00 x robust radius 10.8 m, 300 m outside the main model >= 5.00 m`.
Reasons are always in metres.

## Limits

- Bounds based contacts treat a box as solid: an element inside the box of a large curved element counts as touching it unless `precise contacts` is on.
- Hidden matches stay in the model; sightlines, picking and the focus set ignore them (they are in `userHides`). Hidden elements are removed from the selection.
- Preview tints the render colour and is cleared by any rule change, `Hide matches` or a model change.
