# Imaging: radiograph and MRI looks

A glowing "bone" focus inside "soft tissue" context. The focus set (the selection plus its connected run, as for the other modes) is the bone, everything else visible is tissue. Lives in the `Imaging` folder of the panel (sub-folder `MRI slice`) and in the `Imaging` tool of the action panel; key `m` cycles `standard`, `radiograph`, `mri`. With `style: standard` the renderer is exactly the normal one: the frame is pixel identical to the viewer without the feature (checked by `bench/smoke-imaging.mjs`: the screenshot after visiting radiograph and MRI is byte-for-byte equal to the one before).

| Control | Meaning |
| --- | --- |
| `style` | `standard`, `radiograph` or `mri`. |
| `palette` | `classic` (black background, light blue-white tissue, warm white bone), `negative` (white background, dark ink, deep blue bone), `fluoro` (dark blue-green background, green phosphor tissue). Applies to both styles. |
| `auto exposure` | Default on. Radiograph: measures the thickness distribution and scales the tissue exposure so that the 90th percentile of the non-zero context thickness maps to about 0.8 intensity; `exposure` then multiplies that. See "Auto exposure". |
| `exposure` | Radiograph: scales the attenuation `1 - exp(-exposure * k * T)`; with `auto exposure` on it multiplies the automatic factor (1 = the automatic value). The bone keeps the plain slider value. MRI: the level (a gain on the grey levels). Default 1. |
| `contrast` | Radiograph: linear contrast about an intensity of 0.35. MRI: the window about 0.5. Default 1. |
| `bone glow` | Strength of the glow around the focus (0 off). Default 1. |
| `tissue edges` | Radiograph: faint context edges over the image (no depth test, so they read like a wireframe through the tissue). |
| `MRI slice / axis` | `camera` (a slab square to the view through the focus centre), or `x`, `y`, `z` (viewer axes; `y` is vertical). |
| `MRI slice / thickness (m)` | Slab width, default 0.3. |
| `MRI slice / position` | 0..1 across the focus bounds along the axis (the whole model when nothing is focused). Default 0.5. |
| `MRI slice / scan` | Animates the position 0 to 1 and back; the slider follows. A bright line marks the slab edges. |
| `MRI slice / scan speed` | Fraction of the sweep per second, default 0.25 (a sweep takes 4 s). |

## Radiograph

1. Thickness pass. Every visible element (hidden ones are skipped) is drawn with no depth test and additive blending into an RGBA float target (32 bit when `EXT_float_blend` exists, else 16 bit with a warning in the status line). A front face adds `-z * density`, a back face `+z * density` (`z` = view depth in metres, `gl_FrontFacing`), so the sum per pixel is density times the thickness through closed solids; an open mesh sums to a negative number that is clamped at zero. Context goes to the red channel, the focus to the green one: the focus adds `thickness * 8` whatever its material ("bone is dense").
2. Intensity. `i = 1 - exp(-exposure * auto * k * T)` (`auto` from the next section; the bone channel uses `exposure` alone) with `k` 0.9 for tissue and 1.4 for bone, then the contrast curve, then the palette: the tissue between the background and the tissue colour, the bone mixed over it toward the bone colour, the glow added as the offset from the background toward the glow colour.
3. Density per element comes from its material name, matched on lower-case keywords (first match wins): insulation (also "dämm") 0.05, gypsum, plaster ("gips", "putz") 0.3, glass ("glas") 0.6, concrete ("beton", so also reinforced concrete) 1.0, steel ("stahl", metal, galvanised) 3.0, timber, wood ("holz", spruce, mdf) 0.4, masonry, brick ("ziegel", stone, sand-lime) 0.8, anything else 0.7. It is computed once per model and stored in the alpha channel of the displacement texture (`stateC.a`).
4. Behind-only and peelback cut the thickness pass: it runs the same `vmEval` as the other passes, so a peel window removes the tissue in front of the focus and the bone shows through the remaining tissue; a feather weighs the fragment's thickness by its coverage.
5. Bone glow: the bone intensity is reduced to half resolution with a 2x2 box (so one-pixel lines survive) and blurred separably (9 taps), then once more at quarter resolution with wider taps; the two scales are added by the composite weighted 0.7 and 0.6, times `bone glow`. It uses the idea of the selective bloom (mask, blur, add) but its own tiny blur on the bone channel, so the glow also shows through the tissue and does not depend on the cinematic bloom. The cinematic post effects (AO, depth of field, bloom, vignette) still run on top, because the imaging frame is drawn from `renderer.renderScene()`.

## Auto exposure

On a tall model the thickness through the whole stack of floors is large everywhere, `1 - exp(-k * T)` saturates and the radiograph turns into flat pale blue. With `auto exposure` (default on) the renderer fits the exposure to the picture:

1. After the thickness pass a small reduction pass decimates the thickness target to a 64 x 64 float grid (one sample per cell, 4,096 samples).
2. Every 4th frame (the first one at once) the grid is read back **asynchronously** (`readRenderTargetPixelsAsync`: a fenced pixel buffer, no pipeline stall, no GPU stall warning).
3. On the CPU the context channel (red) is filtered to the non-empty samples (more than 0.001; open meshes and the background add nothing), the 90th percentile `T90` is taken (`nonZeroPercentile`), and `auto = -ln(1 - 0.8) / (k * T90)` with `k = 0.9` (`autoExposureFor` in `src/imaging/maths.ts`; limits 0.002 to 40; fewer than 24 non-empty samples: no measurement).
4. The factor is smoothed in the log domain, 40 % of the gap per measurement; a change below 2 % is ignored so a still camera does not breathe (`smoothExposure`).

The slider multiplies the result, so `exposure 1` is the automatic look and `2` is one doubling brighter. The bone (focus) channel keeps the plain slider value, so the bone stays as bright as before whatever the model. The MRI style does not use the automatic exposure at all (its level and its faint context are as before), and no measurement is taken while it is on. The measure follows the camera and the model, so orbiting into a thicker stack dims the picture a little and moving out brightens it. The first frame of a session or after a resize shows the plain exposure for two or three frames until the first readback has landed. Without `EXT_color_buffer_float` the readback is not possible: the factor stays 1 and the status line says so. The status line shows the current factor (`auto exposure x0.04`); `window.__xrayImaging.status()` returns it as `autoExposure`.

Params field `imaging.autoExposure` (boolean). Checked on `fzk-haus` (the window as bone: `bench/imaging-radiograph-classic.png`, floors and walls readable as before) and on `synth5k` (a 22 m tall stack of seven storeys with a duct riser: `bench/imaging-synth-radiograph.png`, which saturated to flat pale blue without it, now shows the floors, walls and columns).

## MRI

A slab through the focus bounds at `position`, `thickness` wide.

- Inside the slab: a crisp section drawn with depth. The ray enters the slab at its near plane; everything between the camera and that plane is cut. Of what is left, the nearest surface decides. A back face means the ray starts inside a solid, so it is painted as a flat cap in the grey of that element's density (the back-face method, also used by behind-only; the cap is the cut surface wherever the back face really is, so a thin slab through a thick slab still shows a complete cap; only closed solids get a cap, a back face of an open element is drawn shaded like a front face, see `section.md`, "Closed solids"). A front face inside the slab is drawn shaded in the same grey. A front face beyond the slab shows nothing (and hides what is behind it). Grey level = `0.16 + 0.7 * (1 - exp(-0.9 * density))`, the focus is full white. Exposure and contrast are level and window.
- Outside the slab: faint tissue, the radiograph accumulation at 30 % (the focus at 45 %), so the context stays readable.
- `scan`: the slab edges are lit with a thin bright band (on the faces and caps near the slab boundary).

## Scripting and params

- `window.__xrayImaging = { config, set(partial), status() }`. `set` takes any subset of the settings and returns the names it could not use.
- Params section `imaging` (`{ style, palette, exposure, autoExposure, contrast, boneGlow, tissueEdges, mri: { axis, thickness, position, scan, scanSpeed } }`, shared in the URL).
- Action: `imaging.cycle` (`m`).

## Cost (when on)

Radiograph: one thickness pass (the merged geometry again, additive overdraw, full resolution float target), four small blur passes at half and quarter resolution, one full-screen composite, and (with tissue edges) one edge draw. MRI: the thickness pass, one slab pass (4x multisampled RGBA8 target with depth; most fragments are discarded), the blur passes and the composite. No OIT, no ghost pass, no sweep and no hover tint are drawn in an imaging frame (the shaders of the normal passes are not used). Off: one `if` in `renderScene`.

## Developer notes

- Pure maths: `src/imaging/maths.ts` (density table, attenuation, contrast, palettes, MRI grey, window / level, slab, scan timing) and `config.ts`. Tests: `tests/imaging-maths.test.ts`.
- GLSL: `src/render/imagingGlsl.ts`, generated from the same constants. Renderer: `setImaging`, `renderImaging`, `imagingSupported`, `imagingStatus`. The thickness and slab passes reuse `MESH_VERT` and `vmEval` / `clipCut`.
- Smoke test: `SMOKE_PORT=5361 node bench/smoke-imaging.mjs [fzk|synth|all]` writes `bench/imaging-*.png`.

## Limits

- Needs float colour buffers (`EXT_color_buffer_float` or the half float one); otherwise the style silently stays `standard` (the status line says why). Without `EXT_float_blend` the thickness sums in 16 bit and loses precision far from the camera.
- In a WebXR session the standard renderer draws instead (`webxr.md`).
- Thickness assumes closed, consistently wound solids; an open mesh contributes nothing (clamped) and a flipped one adds negative thickness.
- Overlapping elements (a window inside the wall that was not cut) add up.
- The MRI cap takes the density of the element whose back face is hit: where two solids overlap the nearer back face wins.
- The scan line is geometry based: it appears on surfaces and caps near the slab edges, not as a plane in empty space.
- Hover highlight, sweep reveal, depth grading, fog and the dressing's background are not part of an imaging frame.
