# 9. Cleaning a messy model

## The problem

Exports from design tools carry rubbish. A bolt floats in mid-air. A 3 cm offcut sits in a ceiling void. A marker
object lies 300 m from the building and makes "zoom to fit" show a speck. Two identical beams sit in the same place and
flicker. You cannot see the building, and the rubbish costs memory. You also cannot delete anything: the file is not yours
to change.

## The idea

**Cleanup** finds elements that look like debris and hides them. It never deletes. It makes a list of suspects by
rules, shows them to you, and only then hides them. It remembers which elements it hid, so one button gives them back.

Think of it as a clinical filter, not surgery. You describe what you consider debris in numbers. The viewer applies your
description and shows the result. You change the numbers until the result is right.

There are five kinds of suspect.

| Kind | What it catches |
| --- | --- |
| **Floating** | elements that touch nothing connected to the main structure, and are small |
| **Tiny** | elements whose largest side is below a limit (50 mm by default), connected or not |
| **Distant strays** | elements far from the rest of the model, such as geo-reference markers |
| **Duplicates** | elements of the same class and shape in the same place (they z-fight) |
| **Degenerate** | elements with no triangles, impossible bounds or a class that is not physical (spaces, annotations, grids) |

Three class toggles are a blunt extra: `proxies` (generic IfcBuildingElementProxy), `furniture` and
`accessories and fasteners`.

## 9.1 Find, preview, hide, restore

### Try it

1. Open **Sample Projects** and choose **Debris demo**. It is a 400-element model that holds 31 pieces of rubbish
   added, all named `Debris …` and kept in a set called **Debris** (chapter 8).
2. Open the **Cleanup** tool in the tool strip, or the **Model cleanup** folder in the **Parameters** tab. Both show the
   same rules. The drawer has the short buttons **Preview**, **Hide** and **Restore**. The folder has the full set, named as below.
3. Leave the defaults. Press **Preview matches**. The matches turn magenta. When there are fewer than 50, the camera
   frames them.
4. Some matches sit inside walls and are hidden behind them. Press **Select matches** to select them. Selected elements
   are always visible.
5. Compare with the set: open the **Sets** tab and click **Debris**. The two selections are nearly the same. The cluster
   of three touching 12 cm boxes is missing from the cleanup matches. They touch each other, so they do not count as
   "floating".
6. Change the floating `mode` to `small clusters`. The preview is cancelled when you change a rule. Press **Preview matches**
   again. The cluster is now in.
7. Press **Hide matches**. The debris disappears from the view.
8. Hide one wall yourself with `h`. Then press **Restore cleanup**. The debris returns. The wall stays hidden: cleanup gives
   back only what it hid.
9. Press **Export report** if you want a record. You get a JSON file with each element, its class and the reason.

### What the rules mean

**Floating.** Two elements touch when the gap between their bounding boxes is at most `contact tolerance` (10 mm by
default). Chains of touching elements form groups. The group with the largest total bounding volume is the main
structure. The viewer counts volume and not the number of pieces, so thousands of small pipe parts cannot outrank the slabs
and walls. The main structure never matches. Everything else that is smaller than the `threshold` matches.

- `size metric` is how "small" is measured: `largest dimension` (default, 0.5 m), `bounds volume`, `mesh volume` or
  `triangle count`.
- `mode` is `single elements` (only elements that touch nothing) or `small clusters` (whole groups smaller than the
  threshold).
- `precise contacts` also checks the real surfaces, not only the boxes. It drops diagonal elements whose boxes overlap
  but whose surfaces do not.

**Tiny.** The largest bounding side is below `max size`. Connected or not.

**Distant strays.** The viewer finds the middle of the model and the typical distance from it. An element whose centre is
more than `distance factor` times that distance away (6 by default) matches. Two limits narrow it down. `min gap` requires
the element to be at least that far outside the main model. `max size` stops a large misplaced part, such as a whole
second building, from being hidden as rubbish. Set either to 0 to turn it off.

**Duplicates.** Same class, same triangle count, bounds within 2 mm. The lowest id stays and the others match.

**Degenerate.** No triangles, bounds that are not numbers, a side below 0.1 mm, or a class that is not a physical
thing.

Each match has a reason in plain words, such as `floating lone element, no contacts: largest dimension 0.300 m < 0.500 m`.
The report lists it.

### Units

Each threshold names its unit in its label. A `length unit` list at the top of the folder switches the whole folder
between `mm`, `cm` and `m`. The numbers convert for display. The rules are always stored in metres. The unit is a
personal preference and is not part of the rules.

### How it works

Cleanup measures bounding boxes first, which is fast. Twenty thousand boxes take about 0.2 s. It reads the mesh only
when a rule asks for it, such as `precise contacts` or `mesh volume`.

Hiding goes into the same list as your own hides (the eye icon and `h`, chapter 7.1), with a note of who hid what.
That note is what lets **Restore cleanup** undo only its own work. Hidden elements are ignored by picking and by the
x-ray, and they are removed from the selection.

### Choices and settings

- **Apply on load** runs the rules and hides the matches every time the model loads. Use it for a model you always clean
  the same way.
- Rules are stored per model in the browser, and they are part of the parameters document (chapter 19.1). The match list
  is not.
- The palette has `cleanup.preview`, `cleanup.hide` and `cleanup.restore`, without default keys.

### Limits and gotchas

- Boxes are treated as solid. An element inside the box of a large curved element counts as touching it, unless
  `precise contacts` is on.
- A preview paints over the colour of the element. Clearance colouring (chapter 10.2) uses the same paint, so switch one
  off before the other.
- Changing any rule, hiding the matches, or changing the model cancels the preview.
- Judge the first result by eye. A floating threshold of 0.5 m also catches small parts that are meant to be there. Look
  at the preview before you hide.

## 9.2 Nothing is deleted, and saving a lighter copy

Cleanup changes what you see. It does not change the model in memory and it does not change the file. Close the page and
the hides are gone, unless you saved the rules, **Apply on load** is on, or you saved a view (chapter 13), which stores
hides.

To get the result out of the viewer you have two ways.

**Save cleaned IFC.** The command `Save cleaned copy…` writes a new IFC file without the elements that cleanup hid, with
relations repaired. Chapter 19.3 describes it.

**Simplify and save a glb.** The **Simplify** folder inside **Model cleanup** makes the model lighter before saving it
as a `.glb` file. Every tool has **Preview**, which shows what it would change and the triangles before and after, and
**Apply**, which stages the change.

| Tool | What it does |
| --- | --- |
| Decimate mesh | reduces the triangles of each element, never moving a corner and never growing the bounding box |
| Small details | removes elements below a size or volume, optionally only fasteners and accessories |
| Hidden interior | removes elements that no ray from outside can reach. One open ray is enough to keep an element |
| Instances | stores one mesh for elements with the same shape and colour, even if moved or turned |
| Weld and clean | joins coincident vertices and drops zero-area triangles and repeated faces |

**Save cleaned model** opens a summary: the elements removed (with the rule), simplified and instanced, the triangles
before and after, and an estimated size. `strip property data` leaves names and properties out. **Save .glb** downloads
`cleaned-<model>.glb`, and **Open the saved file to check** opens it in the viewer. **Undo simplification** forgets staged
changes. A running preview shows `Working: n of m` and stops with **Cancel run**.

The `.glb` has one node per element, named by GlobalId, so selection and hover work when you reopen it. A glb cannot hold
storeys, relations or full property sets, so its tree is grouped by class only.

### Limits and gotchas

- Simplification shows in the saved file, not in the live view. Removals do hide in the view.
- Run **Instances** after the other tools. Copies that were decimated differently do not match.
- Mirrored copies are not instanced.
- Hidden interior is conservative on purpose, and windows, spaces and openings never block a ray.
- Writing the simplified meshes back into the IFC is experimental. It is off unless the page address has `?experimental=simplifiedIfc`. This manual does not cover it.

## See also

- 7.1 The tree and your own hides.
- 8 Sets: the **Debris** set in the demo, and queries that find the same things (`sizeY < 0.05`).
- 19.3 Save cleaned IFC.
