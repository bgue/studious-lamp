# 6. Imaging looks and context

Ghosting works well when you want to see one part through the others. But sometimes the question is different. Where is
the dense part of the building? What does a slice through the middle look like? Where on the earth does this building
stand? And when you present to a client, you want a picture that looks good, not only one that is correct.

This chapter covers three things that change how the model is drawn, without changing what is in it. Two *imaging* looks
borrow from medicine: the radiograph (an x-ray picture) and the MRI slice. A *map* puts a satellite or street picture under
the building. *Cinematic effects* add glow, fog, shadows and camera moves for presentations.

## 6.1 Radiograph and MRI slice

**The idea.** In a radiograph, thick, dense material blocks more of the rays, so it shows brighter. The viewer does the
same. It adds up the thickness of material along each line of sight, weighted by how dense the material is, and turns the
total into brightness. Your selection is the *bone*: drawn bright and glowing. Everything else is *tissue*, a soft picture
of how much material lies there. There are no ghosts. A wall seen edge-on, which is thick along your view, shows bright. A
thin window shows dim.

**Try it.**

1. Open **FZK-Haus**. Click a window.
2. Click **Radiograph** in the top bar (or press `Shift+2`). The picture turns into a black-background x-ray: the house in
   light blue-white, the window as warm white bone with a glow.
3. Orbit. Walls seen along their length shine more than walls seen face-on.
4. Press `M`. The look changes to **MRI**: a thin grey slice through the selection, crisp, and a faint picture of the rest.
5. Open the **Parameters** tab. At the top is a **Render style** list (**Standard**, **Radiograph**, **MRI**) and below
   it an **Imaging** folder. Choose a different `palette`: `classic` (black ground, light blue-white tissue), `negative`
   (white ground, dark ink, deep blue bone) or `fluoro` (dark blue-green ground, green tissue).
6. Press `M` again to go back to **Standard**.

> Picture (imaging-three-looks): the same view of FZK-Haus in Standard, Radiograph (classic) and MRI.

**Controls (folder `Imaging`).**

- `exposure` (1) and `contrast` (1): how bright and how hard the picture is.
- `auto exposure` (on): a tall stack of floors would make every pixel thick and turn the picture flat pale blue. With auto
  exposure, the viewer measures the thickness in the current view, every few frames, and sets the brightness so that a typically
  thick spot (the 90th percentile of the picture) reaches about 80 % brightness. Your `exposure` slider multiplies that. `1` is the automatic
  look and `2` is one doubling brighter. The bone keeps the plain slider value, so it stays bright. Orbiting into a thicker
  stack dims the picture a little.
- `bone glow` (1): strength of the glow around the selection. `tissue edges`: faint outlines over the picture.
- Material counts. The viewer reads the material name of each element and gives it a density: insulation 0.05, plaster and
  gypsum 0.3, timber 0.4, glass 0.6, anything else 0.7, brick and masonry 0.8, concrete 1.0, steel 3.0. Steel therefore
  shows much brighter than concrete of the same thickness. The selection counts as dense whatever its material.

**MRI slice (folder `MRI slice`).** A slab of the model through the selection. Inside the slab you see a crisp cut: solid
elements are cut and painted flat in a grey set by the density of the material, and the selection is white. Outside the
slab you see a faint radiograph. `axis` is `camera` (square to your view, through the selection) or `x`, `y`, `z`
(`y` is vertical). `thickness (m)` is the width of the slab (0.3). `position` runs from 0 to 1 across the selection (the
whole model with no selection). `scan` moves the slab to and fro, with a bright line at its edges. `scan speed` is the
share of a sweep per second (0.25, so a sweep takes 4 s).

**How it works.** The viewer draws every visible element into a hidden picture, adding thickness times density instead of
colour. A front face adds, and a back face subtracts, so the sum along a line is the thickness through closed solids. Then it
turns the sum into brightness with a smooth curve, colours it with the palette, and adds the glow for the bone.

**What still applies.** Hides and isolates, class styles that hide, far mode `hidden`, the section box and plane, and behind-only
and peelback all still work. The ghost settings do not, because there are no ghosts. The panel dims the folders that have no
effect (Tiers mode, Sightlines, Overrides, the ghost controls of Display) and labels them `not used in radiograph`. A note
under **Render style** says so.

**Limits and gotchas.**

- An imaging look shows only while x-ray is on. Press `X` and the normal view returns, with the look kept. Choosing a look
  by hand (`M`, the list or the tool) turns x-ray on. A preset does not: it sets what it names, and `radiograph` sets x-ray on itself.
- It needs float colour buffers in your graphics card. Without them the look stays Standard, and the status line says why.
  Without a float-blend extension the sum is in 16 bit and loses precision far from the camera.
- It assumes closed solids. An open mesh adds nothing, and a flipped one adds a negative thickness. Overlapping elements
  (for example a window that was not cut out of its wall) add up.
- Hover highlight, sweep reveal, depth grading, fog and the dressing's sky are not part of an imaging frame.
- In VR and AR the standard look is drawn instead.

## 6.2 Map under the model

**The idea.** A building is not alone. A satellite picture or a street map under it shows the road, the neighbours and the
north direction, which helps in site meetings. To get it, the viewer must ask a map server for pictures of a place, and that
tells the server where the project is. For this reason the map is off by default, and the viewer asks first.

**Try it.**

1. In the **Parameters** tab, open the **Map** folder.
2. Switch on `show map under model`. A notice reads "Map tiles are fetched from <provider>; this reveals the project's
   location to them." Nothing is requested until you accept.
3. Click **Show the map**. The ground under the model fills with tiles over a moment. The status line under `location` says where the place
   came from: `From IfcMapConversion (EPSG:25832)`, `From IfcSite`, `Manual` or `Unknown`.
4. Choose `provider`: **Esri World Imagery** (satellite), **OpenStreetMap** (street map) or a **custom XYZ template**. The
   viewer asks again for a new provider.
5. Change `opacity` and `radius (m)` (the disc around the model, 150 by default).

**Where the model is.** The viewer looks in this order: a place you set by hand; the map conversion in the IFC file
(`IfcMapConversion` with a projected coordinate system, if it is a UTM zone in WGS 84, ETRS89 or NAD83; other systems
are not supported); the latitude, longitude and true north of the IFC site; otherwise unknown, and nothing is drawn. If it is
unknown or wrong, click **Align manually...**: type `latitude, longitude` (paste from any map) and the bearing of the
model's +Y axis from true north in degrees. Or drag on the ground (hold `Shift` to turn it). **Top view** looks straight
down. **Done** keeps the place and **Cancel** drops it. **Use the model's own place** forgets your manual place.

**How it works.** A flat disc of tiles is drawn 2 cm under the lowest storey, behind the model. The detail of the tiles
follows the camera distance, so a tile pixel is about a screen pixel. Tiles load nearest first and fade in. The map is not
part of the model: you cannot pick it, measure it, or classify it, and the section planes do not cut it. You see it from
above only. From below it is not drawn, so an x-ray view from underneath stays clear.

**Privacy, in short.**

- The map is off at every start. The switch is never stored.
- With the map off, the viewer makes no network request, including the single file.
- The map is in no share link, view, preset or packed page. An API key or custom URL is kept for the visit only and sent only
  to the tile server. The place you set by hand is stored per model, in the browser.
- OpenStreetMap asks for light use only. Do not use it for heavy or bulk viewing.
- The attribution of the provider shows at the bottom right while the map is drawn.

**Limits.** The radiograph and MRI looks draw the model only. A placed PDF sheet (chapter 16) is drawn over the map.

## 6.3 Cinematic effects

**The idea.** These effects change how the picture looks and feels. They do not change the classification or which parts
fade. Use them to present, not to analyse: a haze or a glow can hide the thing you are checking.

All are in the **Cinematic** folder of the **Parameters** tab. Several are on by default. Others are off.

| Effect | What it does | On by default |
| --- | --- | --- |
| **Camera fly-to** | The camera glides to what you select. `Framing margin` (2.2) sets how much room is left. `Closest distance (m)` (4 m) stops it going too near a small part. | Yes |
| **Staggered reveal** | Occluders fade one after another, spreading outward from the focus. | Yes |
| **Sweep reveal** | A bright stripe wipes from the camera through the occluders as they fade. `Mode`: `stagger`, `sweep` or `both`. | Yes |
| **Scene dressing** | A gradient sky, distance fog, key and fill light, an optional ground shadow. | Yes |
| **Depth grading** | Ghosts well in front of the focus are tinted darker and bluer. | Yes |
| **Focus bloom** | A soft halo around the selection only. | No |
| **Edge glow** | A glowing outline. `glow scope`: the focus, the focus with host and near parts, or all. The Glow mode of the top bar uses `focus`. | No |
| **AO + vignette** | Soft shading in creases, and darker corners. These cost frame rate. | No |
| **Exploded view** | Parts slide apart (5.3). | Off until you click |

`Subtle pulse` makes the halo and the outline breathe slowly, about every 3 seconds, to draw the eye.

**Try it.** Select a duct in the Building model. Switch on **Selective bloom** and **Edge glow**. The duct gets a soft halo
and a bright outline. Or click **Glow** in the top bar, which does both with a good setting. Select another element: the
camera glides, and the walls fade in a ripple. Now apply the preset `presentation` (open the **Presets** tool and choose
it). It switches on scene dressing, bloom, fly-to, reveal and the sweep in one step.

**How it works.** The glow is drawn from a mask of the focus only, so context never glows. The bloom strength is held at a
maximum of 0.175, because larger values washed the selection out. A link or view that stores a stronger value is held at
that value. Effects that need more graphics work (AO, bloom) lower the frame rate on a weak machine.

**Limits and gotchas.**

- Turn the effects off when you judge a picture. Fog and sky shift colours, bloom softens edges, and AO darkens creases that
  are not there.
- If you do not want the stripe of the sweep reveal, set its `Mode` to `stagger` or switch it off.
- The older **Tour** folder steps through your saved selection sets one by one. For a presentation, build a fly-through
  from views (chapter 22), which has timing, captions and video export.

## See also

- Chapter 4: top-bar modes and presets, where Radiograph and Glow are one click.
- Chapter 5: cuts, which work in the radiograph too.
- Chapter 22: fly-throughs for presentations. Appendix G: what the map sends.
