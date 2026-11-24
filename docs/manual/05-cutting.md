# 5. Cutting and peeling (one clipping system)

Ghosting shows you what is behind a wall, but a ghost is still a veil. Sometimes you want to see the thing clearly, as if
the wall were not there. Or you want to see a room in section, the way an architect draws it. Or you want to lift a
building apart, floor by floor, to show how it is stacked.

Three kinds of tools do this. *Peeling* removes what is in front of the part you selected, in a window around it. A
*section* cuts the whole model with a box or a plane. *Exploding* slides the parts apart without cutting anything. The
section and every other place that sets a cut use one set of cut planes (5.4). Peeling is separate: it follows your
selection, not planes.

## 5.1 Behind-only and partial peelback

Both tools need a selection, because they work on the focus (chapter 1). With nothing selected, or with x-ray off, they do
nothing.

**Behind-only** (key `B`). The viewer imagines a flat plane square to your view, through the nearest point of the focus.
Everything on the camera side of that plane is the *front*. It is cut away, or ghosted, or cut and capped (the cut shows
a flat hatched colour so a solid looks sectioned). Everything behind the plane is drawn fully solid. `Shift+B` cycles the
three treatments: `cut`, `ghost`, `cut + cap`. The plane follows your camera as you orbit. Choose `locked` for `orientation`
to freeze it, or `horizontal` for a plan cut: the plane sits at the top of the focus and everything above it goes.

**Partial peelback** (key `P`). The viewer cuts a window through whatever is in front of the focus. The window has the shape
of the focus and widens toward you, like a funnel, so the wall around the window stays in place. Big slabs are split, not
hidden whole: part is removed and the rest stays. `Alt+=` makes the window 25 % larger, and `Alt+-` makes it 25 % smaller.
The setting `outside` says what the rest looks like: `x-ray` (peel plus ghosts, the default) or `solid` (peel only, everything
outside the window solid).

**Try it.**

1. Open **FZK-Haus**. Click a window in an outside wall. Orbit to look at it from outside.
2. Press `P`. A window opens in what hides the selected window, and you see the room behind it. The rest of the model is
   ghosted. Press `Alt+=` once or twice to widen the opening.
3. Click **Cutaway** in the top bar, or press `Shift+4`. The wall is solid around the opening: this is peeling with
   `outside` set to `solid`, and it frames the selection for you.
4. Press `Shift+1` to go back to the plain x-ray, then press `B`. A plane cuts everything in front of the window, and
   the room behind is solid. Press `Shift+B` to try the other treatments. Press `B` again to switch it off.

> Picture: FZK-Haus from outside with a window selected, in three states: ghosted, peeled with solid surroundings, and
> behind-only with cap.

**How it works.** The decision is made for each pixel, not for each element, so a slab can be half removed. For the peel,
the viewer draws the focus into a small hidden picture, then spreads each focus pixel outward to find, for every other
pixel, the nearest focus pixel and its depth. A pixel is cut when it lies in front of that depth and close enough to the
focus in the picture. The distance allowed grows with the gap between the pixel and the focus. This is why the window
widens toward you. Revealed back faces are painted flat in the `cap colour`, so a solid wall appears cut.

**Choices.**

- Behind-only: `offset (m)` (default 0.2; a positive value keeps a margin of solid around the focus), `front alpha` (0.12,
  used by `ghost`), `apply to` (`all context` or `occluders only`), `keep x-ray behind`.
- Peelback: `radius (m)` (0.4), `slope` (0.6, how fast the window widens), `feather (m)` (0.08, the soft edge), `rim band`
  (an accent band on the edge of the window), `animate` (the window grows over 0.5 s).

All are in the **View modes** folder of the Parameters tab, and in the **View modes** tool. Both modes can be on together.
The peel wins inside its window.

**Limits and gotchas.**

- A click goes through what a cut removes, so you do not select things you cannot see. For the peel this is an
  approximation at the rim, a few pixels off.
- A focus that runs deep along your view (a duct pointing away from you) cuts with the depth of its nearest part.
- If your graphics card has no float render targets, the peel falls back to a coarser method with up to 16 ellipses. The
  window is then less exact.
- Caps are painted only on closed solids (5.2).

## 5.2 Section box and section plane

A section cuts the whole model with a box (six sides) or a plane (one side). Unlike peeling, it does not care what is
selected.

**Try it.**

1. In FZK-Haus, select any element, then press `Shift+C`. A section box fits around the selection
   with a margin of 0.5 m and switches on. Everything outside the box is cut away.
2. Six round handles appear on the box faces. Drag one: that face moves along its axis. A readout shows the face position
   and the size of the box. A face stops 5 cm before the opposite one.
3. In the view cube's **section strip**, click **Y**. A plane square to the vertical axis cuts the model through the
   centre of the selection: a plan cut. Click **Y** again to remove it. **X** and **Z** cut the other two ways.
4. Click **Flip** to keep the other side. Click **Caps** to turn the hatched caps on or off.
5. Drag the arrow on the plane to push or pull it. A readout shows the offset in metres. Drag a ring to tilt the plane in
   steps of 15 degrees (hold `Shift` for free tilting).
6. Click **Clear** to remove everything.

**The strip.**

| Button | What it does |
| --- | --- |
| X, Y, Z | A plane square to that axis (Y is vertical), through the selection or the model. Click again to remove. `Alt+C` toggles the plane. |
| Box | Fit the box to the selection (else the model) and switch it on (`Shift+C`). `C` toggles the box. |
| Flip | Keep the other side of the plane. |
| Caps | Hatched caps on cut closed solids. |
| Clear | Remove box, plane and any plane set by an issue's view. |

The **Section** tool in the tool strip adds numeric fields for the box minimum and maximum, which you can type into.
**Fit box to model** fits the whole model. `margin (m)` changes the margin, and changing it refits.

**How it works.** Each cut is tested per pixel in every drawing step, so a wall that crosses the plane is cut exactly and
the outlines of the cut part are not drawn. A cut face has no real surface. When you look into a cut solid, you see its back
faces, and the viewer paints those flat in the cap colour with a light hatch. That is what makes it look like a section.

**Limits and gotchas.**

- Caps work only on *closed solids*. At load, the viewer checks each element: if every edge is shared by two faces it
  counts as closed. A single-sided pane or sheet (some glass) is open, and shows its back faces shaded like any other face.
  A badly joined solid with hundreds of loose edges also counts as open.
- A ghosted element is cut without a cap, because ghosts do not draw back faces.
- The box is aligned with the viewer's axes. It cannot be turned.
- The handles are drawn without a depth test. A handle behind the model is still visible.
- Up to 8 planes at one time (a box uses 6, a plane 1, one is spare).
- A click skips what a plane removes, so you do not select cut-away parts.

## 5.3 Exploded storeys

Exploding moves parts apart, without cutting any of them. It is a good way to show how floors stack.

**Try it.**

1. Open **Synthetic 5k** (needs the served app) or a model with several storeys. In the Model tree (chapter 7), select
   several storeys, or press `Ctrl+A` to select everything visible.
2. In the **Parameters** tab, open the **Cinematic** folder, then **Exploded view**. Set `Mode` to `storeys`.
3. Click **Explode**. The floors slide apart vertically, with `Storey gap (m)` (default 3 m) between neighbours. The middle
   storey stays in place. Click **Explode** again and they slide back.

The `explode` list says which parts move. `auto` explodes the selection when you selected more than one element, and
otherwise the parts that block a single selected element. `selection`, `occluders` and `both` are explicit. `Mode` is
`radial` (the default: parts burst outward from the middle), `storeys` (floors lifted apart) or `radial+storeys`. `Radial
factor`, `Min push (m)` and `Duration (ms)` shape the move.

**How it works.** The move is only a displacement applied when drawing. The model itself does not change.

**Limits and gotchas.** Picking stays at the unexploded positions. A click on an exploded part selects what lies at its
original place, so a pick next to a cut of an exploded part can differ from what you see. A change of the selection
collapses the explosion. A view can remember that the model was exploded.

## 5.4 One clipping system

The section box, the section plane, the plane strip on the view cube, the views that belong to issues, and the Plan and
Section switch of a view all do the same thing: they put cut planes into one list in the renderer. Whatever you start,
you get the same cut, the same hatched caps, and the same `Clear` button.

| Where it starts | Which planes | When |
| --- | --- | --- |
| Section tool and view cube strip | Box (6 planes), plane (1) | You switch them on |
| An issue's view (in a BCF file, a viewpoint) | Whatever planes it carries | You apply the view. It clips and caps. Creating an issue captures the current planes, a box counting as six. |
| **3D · Plan · Section** switch on a view with drawings attached to the model | Plan: one horizontal cut at the storey level + 1.2 m. Section: one vertical cut through the middle of the target | You press **Plan** or **Section** |
| A view | Its section settings, and the planes of an applied issue view | You restore the view |

The Plan and Section switch looks straight down (Plan, north at the top) or straight at the cut (Section) in the viewer's
approximate orthographic projection. When you leave **3D**, the viewer remembers the section you had and puts it back when
you press **3D** again.

**What this means for you.**

- **Who is in charge.** The section tool sends planes only when you change one of its settings. If something else sets
  planes (an issue's view, the Plan switch), the tool steps back and takes over again only when you change a section
  setting. This stops two tools fighting over the same plane.
- **The Clear button is honest.** While an issue's planes are in force, **Clear** turns amber and says how many planes it
  removes, and the X, Y, Z, Box and Flip buttons are not lit. The section settings are not what the view shows.
- **Behind-only and peelback are separate.** They are not planes. They work together with planes, and the cuts add up.
- **Undo.** A change of planes that stays still for 0.4 s is one undo step. Applying an issue's view with a camera move is
  one step, and so is the Plan or Section switch.

The **3D · Plan · Section** switch appears in the detail of a view, in the detail of an issue's view and in the drawing toolbar. It appears only when the view has drawings that are attached to the model (14.2). A view with only view-locked drawings has no switch. Chapter 13 describes it from the view's side.

**Limits and gotchas.** Up to 8 planes at one time. While an issue's planes are applied, they replace the section tool's own
planes until you change a section setting. The Map under the model is not cut by section planes: it is the ground the model stands on.

## See also

- Chapter 4: ghosting and presets (`behind-only`, `peelback`, `peel-only`, `section-focus` are presets 3, 4, 5 and 9).
- Chapter 13: views, and Plan and Section of a view.
- Chapter 17: exchanging issues, where cut planes travel.
