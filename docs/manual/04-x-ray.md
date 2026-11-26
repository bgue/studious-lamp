# 4. X-ray: let the structure get out of the way

At a coordination meeting someone asks, "Where does that duct run above the corridor?" You rotate the model. All you see
is slabs and walls. You hide the ceiling slab and now the floor above looks odd. You hide a wall and the room is no longer
a room. Every fix costs you something else, and you will not remember what you hid.

X-ray avoids that. You select the thing you care about. The viewer finds what blocks it and makes only that faint, in
proportion to how much it blocks. Chapter 1 gave the idea. This chapter shows how to use it, tune it and keep or remove
specific parts by hand. It ends with the top-bar modes and the presets: one click to change the whole look.

## 4.1 Switch x-ray on and select a duct

**Try it.**

1. Open **Building (Simple-Scene)** (2.3). X-ray is on by default. The status bar says so.
2. Click a duct. If you do not see one, orbit until you find one.
3. The duct and the run connected to it stay solid. A slab or a wall in front of it turns faint. You see its outline
   through the faint surface.
4. Orbit. The faint parts change as your point of view changes. A wall that was in your way becomes solid again when you
   walk round it, and a new one fades.
5. Press `X`. All ghosts go solid at once: x-ray is off. Press `X` again.
6. Press `Esc` to clear the selection. With nothing selected there is no focus, so nothing ghosts.

> Picture (xray-on-off): the same view with x-ray on and off, a duct run behind a slab.

**How it works.** (See 1.1 for the idea.) Each time you select something or move the camera, the viewer does two things.
First, it sorts every context part into focus, host, near or far (the classification). This uses only geometry, so it does
not change when you orbit. Second, it draws sightlines from points on the focus to the camera and counts which parts they
cross. That count sets how faint each part becomes. The faintness eases toward its new value by 20 % per step, so you see
a smooth fade and not a flicker. A faint part is drawn with its outline kept, so you still see where it is. By default a reveal effect delays each fade by the part's distance from the focus, so the ghosts appear in a
ripple (6.3).

Ghosts are blended so that the order in which they overlap does not matter (this needs a graphics card feature called
float colour buffers; without it, overlapping ghosts may look uneven).

**Limits and gotchas.**

- If you select something that is not a duct or a pipe, it still becomes the focus. Select a slab and the other slabs and
  walls become the context.
- The connected run is followed only for services (duct, pipe, cable carrier, flow segments and fittings, terminals).
  For a wall you get that wall alone.
- Ghosts fainter than 0.3 opacity cannot be clicked: your click goes to what is behind (3.3).
- **Focus in front** (a display setting, on by default) draws the focus on top of everything, even behind an opaque wall.
  Turn it off if you want solid objects to hide the focus.

## 4.2 Tune ghosting

The defaults suit most models. When a picture does not read right, find the symptom in the list and change one setting.
All the settings are in the **Parameters** tab, in the folders below. Hover for 350 ms to read the tooltip. Appendix B
lists every one.

**Too much ghosted, or too little.** Folder **Classification (Alg 1)** decides which parts count as near the focus.

- `bufferBase (m)` (default 0.30). Raise it and more walls and slabs near the focus fade. Lower it for ghosting close to the
  focus only.
- `bufferScale` (0.50): how much the buffer grows with the size of a focus part. At 0, every part uses the base buffer.
- `bufferLo` (0.30) and `bufferHi` (1.50): the smallest and the largest buffer in metres.
- `storeyBand` (1): how many storeys above and below the focus storey count as context. At 0, only the same storey.

**Ghosts too solid, or too clear.** Folder **Sightlines (Alg 2)**.

- `alphaMin` (0.15): the faintest an occluder gets. Lower it and blockers almost vanish.
- `alphaMax` (0.85): how solid a near part is when it blocks nothing. Raise it to 1 and the parts that do not block stay
  fully solid.
- `gamma` (0.5): the shape of the fade. Below 1, a part that blocks only a few sightlines still fades well. Above 1, only
  strong blockers fade.
- `smoothingRate` (0.20): speed of the fade. At 1 there is no smoothing.
- `samplesPerObject` (64) and `maxSamples` (500): how many sightlines. More is steadier and slower. If the frame rate
  drops while you orbit, lower `maxSamples`. If the ghosting flickers on a long run, raise it.

**A stack of floors turns into a veil.** When three slabs lie over the same duct, all three used to fade the same and
together looked like a white fog. `layer weighting` fixes that. `front` (the default) gives the slab nearest the camera
the most fade, and each slab below it half as much (`layer falloff` 0.5: credits 1, 0.5, 0.25). `budget` fades only the top
`layer budget` layers (default 2). `uniform` fades every layer alike.

**A far wall blocks the view.** `occluder scope` is `all` by default, so a far part that blocks the view also fades, at a
strength set by `far weight` (0.7). Choose `near` to ghost only host and near parts, as in the original report. In
**Display**, `far mode` set to `hidden` removes the far parts. `opaque` (the default) keeps them.

**Outlines and colour.** In **Display**: `edgeAlpha` (0.8) sets how dark the outlines of ghosts are, and never lower than
the ghost itself. `ghost desaturate` (0.8) pulls the colour out of ghosts so the focus stands out. `focus in front` is
described above. `debug colour by bucket` paints focus, host, near and far in separate colours: host red, near orange, far
grey. Use it to understand why something fades, then turn it off.

**Tiers.** Switch on **Tiers mode** (in the top section of the panel) when different kinds of parts compete for the view.
Parts are ranked: services first, then beams and columns, then slabs, walls and footings. A part ghosts only the parts of a
lower tier, so slabs and walls fade most, beams and columns less, and the selection stays solid. Off, every blocker follows
one rule.

**Depth grading.** In the **Cinematic** folder, **Depth-graded ghosting** tints ghosts that lie well in front of the focus
darker and bluer. It helps you read which ghost is nearer.

**See why.** In the **Cinematic** folder, **Sightlines** has a **Show sightlines** button. Click it and thin lines run from
the focus to the camera for a moment: orange lines hit something, blue lines have a free view. Use it to find the cause of
a ghost.

**Limits and gotchas.**

- Raising `samplesPerObject` makes the update slower on a large selection.
- Where this viewer differs from the original report (the selection joins the focus whatever its class, far blockers
  ghost, stacked layers are weighted by depth), the README lists the deviations.
- In Radiograph and MRI looks, most of these settings do nothing and are dimmed (6.1).

## 4.3 Pins, hides and class styles

The algorithm decides automatically. Sometimes you know better. Three tools override it.

**Pin.** Select parts and click **Pin selected** in the **Parameters** tab. A pinned part never fades below the `user pin
floor` (folder **Overrides (Alg 7)**, default 0.60). Use it to keep a column or a wall readable behind ghosts. The default
class floor for columns is 0.50.

**Hide.** Select parts and click **Hide selected** (key `H`). A hidden part is not drawn and does not block any sightline.
`Alt+H` brings back everything you hid. `Shift+H` hides everything except the selection (an isolate). **Clear pins/hides**
undoes both pins and hides. Pins and hides refer to elements by GlobalId, so a view can carry them.

**Class styles.** A style sets a look for all parts of one class or one material. In the **Class styles** folder, open
**Classes**, then a class (the number shows how many parts it has). The fields are:

| Field | Effect |
| --- | --- |
| `alphaMax` | Never more opaque than this, even when nothing blocks. "Steel at most 80 % opaque" is `alphaMax 0.8`. |
| `alphaMin` | How faint an occluder of this class may get. |
| `floor` | A pin floor for the whole class. |
| `color` | Replaces the base colour. |
| `hidden` | Hides the class. |

Class styles can also name a material instead of a class (a *material alias*, for example steel beams and steel columns
under one name "Steel"). Edits are stored per model in the browser. **Reset to config** drops them. **Export JSON** saves
them as `xray.config.json`, and **Import JSON** loads such a file. An installation can ship a default file next to the
viewer. Precedence, lowest first: that file, the model's own styles, then your edits.

**Try it.** In the Building model, select a beam. Click **Pin selected**. Orbit so that a wall is in front of it. The
beam stays clearly visible. Click **Clear pins/hides**.

**Limits and gotchas.** A pin keeps a part at or above a floor. It does not make a part solid if the floor is below 1. A
hidden part is not deleted and returns with `Alt+H` or **Clear pins/hides**. With x-ray off, no hide applies, whichever way you hid the part (`H`, **Hide selected** or the Model tree): everything is drawn. The hides apply again when you switch x-ray on. In the Radiograph and MRI looks only `hidden` of
the class styles still applies.

## 4.4 Top-bar modes

The five buttons at the top left of the canvas change the whole look in one click.

| Mode | Key | What you see |
| --- | --- | --- |
| **Solid** | `Shift+0` | Everything opaque. X-ray, imaging, peel and behind-only off. A section cut stays. |
| **Ghost** | `Shift+1` | The classic x-ray of this chapter, at factory settings. |
| **Radiograph** | `Shift+2` | A medical x-ray picture: the model as shades of material thickness, the selection as bright bone (6.1). |
| **Glow** | `Shift+3` | The selection gets a soft halo and a bright outline. The context stays ghosted. |
| **Cutaway** | `Shift+4` | A window shaped like the selection is cut through whatever blocks it. Everything else stays solid (5.1). |

**Try it.** Select a duct in the Building. Click each mode in turn. Click a lit mode again: you go to **Solid**, so there
is always one click back to the plain model.

**How it works.** A mode is a preset. A click applies a built-in preset (Solid, Ghost = `coordination`, Radiograph,
Glow = `focus-glow`, Cutaway = `peel-only`). The button lights when the current settings still match that preset. When you
change any setting, the light goes out. At start the bar lights **Ghost**, because that is the factory look.

**Limits and gotchas.** Solid keeps your section planes, box and clearance colours, because a cut is not a transparency.
Use the preset `plain` to reset those too. Applying a mode is one undo step. Solid keeps the transparency that the model
itself has, such as glass. On a phone, the five buttons are icons. The top bar is hidden in packed kiosk pages and in
VR and AR.

## 4.5 Presets and keys 1 to 9

A *mode* is one click on a preset. A *preset* is a saved look: settings only, never a camera position. A view, a keyframe and a share link store more (see chapter 13).

**Try it.**

1. Select a duct in the Building.
2. Press `2`. This is **hide-blockers**: what blocks the focus disappears, and everything else stays solid.
3. Press `1` to return to the factory x-ray (**coordination**).
4. Press `3` (**behind-only**) and `4` (**peelback**). Compare them (5.1).
5. Press `1` again.

Keys `1` to `9` apply the first nine presets. The other five presets are not on a key.

| Key | Preset | Group | What it does |
| --- | --- | --- | --- |
| `1` | coordination | Review | Factory x-ray (the Ghost mode) |
| `2` | hide-blockers | Review | Blockers vanish; the rest solid |
| `3` | behind-only | Cutaway | Removes what is in front of the focus |
| `4` | peelback | Cutaway | A window through what blocks, the rest ghosted |
| `5` | peel-only | Cutaway | The same window, the rest solid (the Cutaway mode) |
| `6` | stacked-floors | Review | Strong fade for the top floor, mild for those below; depth grading on |
| `7` | radiograph | Imaging | Radiograph look (the Radiograph mode) |
| `8` | mri-scan | Imaging | MRI slice with a scan |
| `9` | section-focus | Cutaway | A section box fitted to the selection, with caps |

The others have no key: `presentation` (cinematic effects), `clearance-review`, `plain`, `solid` and `focus-glow`.

**Save your own.** Set the viewer up the way you want. Open the **Presets** tool (or the **Presets** folder in the
Parameters tab) and click **Save current as preset**. Give it a name and one sentence, and choose which groups of settings
to store. The defaults are sightlines, display, far mode, view modes, imaging, section and cinematic. Your presets appear
under **My presets**. You can edit, duplicate (also a built-in, which cannot be edited), delete, export and import them as
a file, and **Share** one as a link. Opening a shared link applies the preset once and does not save it. Your presets live in
the browser.

**How it works.** A preset lists only the settings it changes. Before it applies, it resets the groups it names to the
factory values, so a preset does not stack on the one before. It never changes the model or the selection. It does not
store a camera. Four presets (`behind-only`, `peelback`, `peel-only` and `section-focus`) also move the camera to frame the
selection when applied, and they show nothing useful with nothing selected.

The built-in list holds 14 presets: the nine on keys, and `presentation`, `clearance-review`, `plain`, `solid` and `focus-glow`.

**Limits and gotchas.** The active mark on a preset is a comparison of settings. A setting that changes by itself (a running
animation) clears it. A shared preset runs its actions too, so open links only from people you trust.

## See also

- Chapter 5: cutting and peeling.
- Chapter 6: radiograph, MRI and other looks.
- Chapter 13: views, and the full ladder.
