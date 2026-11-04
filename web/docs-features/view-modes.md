# View modes: behind-only and partial peelback

Two renderer features that decide per fragment, not per object, what hides the focus. The focus is the controller's focus set (the selection plus its connected run, or the whole system when the selected element belongs to one); with nothing selected, or with X-ray off (the classification is then empty), both modes are inactive. A large slab that crosses the cut is split: part of it is removed, the rest stays. Both live in the `View modes` folder of the panel (sub-folders `Behind only` and `Peelback`) and can be on at the same time (the peel wins inside its window). With both off the frame is identical to the viewer without them (a byte-for-byte equal screenshot is part of `bench/smoke-viewmodes.mjs`).

## Behind only

Show what is behind the focus, not what is in front of it.

The cut plane is perpendicular to the view direction (the camera's forward vector) and passes through the focus at its nearest point to the camera, moved `offset (m)` toward the camera. It is recomputed every frame from the camera and the 8 bounds corners of every focus element (the exact nearest point of each box). Context fragments on the camera side of the plane get the front treatment; fragments behind it are drawn fully solid (alpha 1, opaque pass), whatever the sightline alpha says, unless `keep x-ray behind` is on. The focus is never cut.

| Control | Meaning |
| --- | --- |
| `enabled` | On or off (key `b`). Needs a selection (the focus). |
| `front treatment` | `cut`: discard. `ghost`: the front part goes through the ghost / OIT path at `front alpha`, independent of the sightline result. `cut + cap`: discard, and paint the back faces the cut reveals with the flat `cap colour` (light hatch, no lighting), so solids look sectioned. Key `Shift+b` cycles. |
| `offset (m)` | Default 0.2. Positive keeps a margin of solid context around the focus; negative cuts into the focus. For `horizontal`, the plane is the focus top plus the offset. |
| `front alpha` | Default 0.12. Used by the `ghost` treatment. |
| `orientation` | `camera` (default): follows the view. `locked`: freezes the current plane while you orbit (it is taken again when the focus changes or the mode is switched on). `horizontal`: a plan cut, the plane at the focus top plus the offset, everything above it is removed. |
| `apply to` | `all context` (default) or `occluders only` (Host, Near, and Far elements that block the focus: occlusion greater than zero in the last sightline run). |
| `keep x-ray behind` | Fragments behind the plane keep their sightline alpha instead of becoming solid. |
| `cap colour` | Colour of the cap of `cut + cap`. |

How an element is split between passes: the opaque pass draws the fragments behind the plane (also of elements that the sightline pass made translucent) and discards the front ones; the ghost pass draws the front ones (treatment `ghost`) and discards the behind ones. Edges follow the same rule, so no edges float in a cut (in `ghost` the front edges are drawn faintly). The cap is the opaque pass being double sided: a back face that is visible behind the plane can only be seen through a cut, so painting every such back face in the cap colour sections a solid. Caps are painted for closed solids only (see "Closed solids" in `docs-features/section.md`): an open element (a single-sided pane or sheet) behind the plane shows its back faces shaded like any other face.

## Peelback (partial peelback)

A screen-space cutaway after Burns and Finkelstein 2008 and Coffin and Hoellerer 2006. It cuts a window through whatever is in front of the focus, shaped like the focus silhouette, and leaves the rest of each obstructing element in place.

Method (GPU path):

1. The focus set is rendered into a half resolution RGBA32F target with depth (red: view depth in metres, green: 1 where there is focus).
2. A jump flood (seed pass, then jumps of 256, 128, ... 1 half-resolution pixels, then 1 again: 10 cheap full-screen passes) gives every pixel the position of the nearest focus pixel and that pixel's depth.
3. In the context passes (opaque, ghost / OIT, edges) a fragment is cut when it lies in front of the nearest focus depth `zf` by more than the depth tolerance (default 0.2 m plus the screen distance in metres (it covers a host surface seen at up to 45 degrees), so the flush, obliquely seen host wall of a window is left alone; config field `depthEps`, not in the panel) and its screen distance to that pixel, converted to metres with the projection at the focus depth (as the spec asks for r0), is below `r(z) = radius + slope * (zf - z)`. The window therefore widens toward the viewer like an angled cutaway, with a wall that follows the silhouette.

| Control | Meaning |
| --- | --- |
| `enabled` | On or off (key `p`). Needs a selection. |
| `radius (m)` | Window radius at the focus depth, default 0.4 m. `Alt+=` / `Alt+-` grow and shrink it by 25 %. |
| `slope` | Extra radius per metre between the fragment and the focus, default 0.6. |
| `feather (m)` | Soft edge, default 0.08: coverage rises smoothly from 0 to 1 over this width, and the fragments in it fade out through the ghost pass instead of being discarded. |
| `rim band` / `rim colour` | A band of the accent colour on the surface at the window edge (default on). |
| `cap colour` | Colour of revealed back faces (same trick as behind-only): a back face that was not cut and lies within the window's reach plus 0.5 m of depth is painted flat. Where the window cuts through a thick slab this shows the angled funnel wall. |
| `outside` | `x-ray`: peel plus x-ray outside the window (default). `solid`: peel only, everything outside the window is solid, alpha 1. |
| `apply to` | `all context` or `occluders only`. |
| `animate` | The radius grows from 0 to its value over 500 ms (ease out) when the mode is enabled and when the selection changes. |

CPU fallback: when float render targets are unavailable (no `EXT_color_buffer_float`) or their framebuffer is incomplete, the same test runs against up to 16 ellipses, one per focus element (the largest on screen), computed on the CPU from the projected bounds and passed as uniforms. Distance to an ellipse is approximated as `(|q| - 1) * min(axis)` with `q` in ellipse units. `window.__xrayViewModes.status().peelPath` reports `gpu-jfa`, `cpu-ellipse` or `off` (also logged once to the console), `renderer.setPeelPath('cpu')` forces the fallback for tests.

The mask and flood are rebuilt only when the camera, the viewport, the element state or the focus set changed; a still camera costs nothing extra.

### Picking

The BVH picker works on the undisplaced geometry and knows nothing about the shaders, so by default clicks go through cuts as if they were not there. Because that would select things you cannot see, `renderer.pick` additionally skips a hit that a view mode removes: for behind-only, a hit on the front side of the plane (also when that part is ghosted at less than 0.3 alpha, the existing click-through rule); for the peel, the same `r(z)` rule evaluated on the CPU against the focus bounds projected to screen ellipses. That is an approximation (the rendered window follows the true silhouette, the pick test the projected bounds, so they differ by a few pixels at the rim) and the feather is treated as cut below 50 % coverage. Explode offsets are ignored by picking, as before.

## Hover highlight hook

`renderer.setHoverHighlight(id: number | null, color?: [r, g, b])` tints that element (and brightens its edges) with a uniform that is compared with the element id in the shaders. It does not touch the state flags, which the controller rewrites on every tick. `null` clears it.

## Scripting and params

- `window.__xrayViewModes = { config, setBehind(partial), setPeel(partial), status() }`. `setBehind` and `setPeel` take any subset of the config fields (`enabled`, `frontTreatment`, `offset`, `frontAlpha`, `orientation`, `applyTo`, `keepXrayBehind`, `capColour`; `enabled`, `radius`, `slope`, `feather`, `rimBand`, `rimColour`, `capColour`, `outside`, `applyTo`, `animate`) and return the names they could not use.
- Params section `viewModes` (`{ behind, peel }`, shared in the URL).
- Actions: `mode.behind` (`b`), `mode.behind.cycleTreatment` (`Shift+b`), `mode.peel` (`p`), `mode.peel.grow` (`Alt+=`), `mode.peel.shrink` (`Alt+-`).

## Developer notes

- Pure maths: `src/viewModes/maths.ts` (plane from camera and focus corners, `r(z)`, feather, metres to pixels, JFA reference, screen ellipses, pick test), settings and validation in `config.ts`, the occluder mask in `occluders.ts`. Tests: `tests/viewmodes-*.test.ts`.
- GLSL: `src/render/viewModeGlsl.ts` (`vmEval` is the one per-fragment function shared by the mesh and edge shaders, plus the mask and flood passes). It mirrors `behindFragment` and `peelFragment` in `maths.ts`.
- Renderer: `setBehind`, `setPeel`, `setViewModeMask`, `setHoverHighlight`, `peelPath`. Per-element occluder flag in the alpha channel of the second state texture. The vertex shaders stop rejecting by alpha when a mode is on (`vmAny`), so an element's triangles can go to either pass and the fragment shader decides.
- The OIT composite is also drawn when a mode may create ghost fragments out of opaque elements (behind `ghost` treatment, peel feather).
- Cost with both modes off: a few uniforms and two extra flat varyings; no extra pass. With the peel on: one mask draw of the focus (vertex work over the merged geometry, like the bloom mask) and 10 full-screen half-resolution passes, only on frames where the camera or state changed.
- Smoke test: `SMOKE_PORT=5311 node bench/smoke-viewmodes.mjs [fzk|synth|all]` writes `bench/vm-*.png` and `bench/vm-synth-*.png`.

## Limits

- The peel window is the nearest-focus-pixel field at half resolution: a 1 to 2 pixel stair step at the rim (hidden by the feather).
- The peel uses one depth per focus pixel, so a focus that is deep along the view axis (a duct running away from the camera) cuts with the depth of its nearest silhouette pixel.
- Back faces are the only cap: a thick solid cut by a peel shows its far wall, not a cap at the cut itself. Only closed solids get the cap colour (`section.md`, "Closed solids").
- Context drawn by other plugins into the scene with their own materials is not cut.
- Picking is approximate for the peel (see above) and ignores the feather and the rim.
