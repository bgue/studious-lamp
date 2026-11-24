# 11. Penetrations

## The problem

Every duct, pipe and cable tray that crosses a wall or a slab needs a hole. If the hole is missing, someone cuts it on
site, through reinforcement, at the wrong place. If the hole is too small, the duct does not fit. Finding all
crossings by orbiting the model takes days on a real building. And the answer you need is a list: which crossings,
on which storey, in what host, with or without an opening.

## The idea

A **penetration** is a place where a service element (MEP: a duct, a pipe, a tray) passes through a structural
**host**: a slab, wall, beam, column, footing or roof. The viewer finds every such crossing, and for each one asks:
does the host have an **opening** there?

An opening is a hole the designer put in the model, an `IfcOpeningElement`. It is not drawn, but its box is known.
The viewer compares the place where the element crosses with the boxes of the openings of that host.

The result is a table, one row per crossing. It is a candidate list for review, not a verdict. The viewer cannot know
what the designer meant, only what the model says.

## 11.1 The penetration schedule

### Try it

1. Open **Sample Projects** and choose **Synthetic 5k**. It is a synthetic 5,000-element building with services.
2. Open the **Penetrations** tool in the tool strip. A wide drawer opens and analyses once.
3. Read the summary counts at the top. Under them are filter chips for status, storey and host class.
4. Click a column header to sort. Use the filter chips to narrow the list by status, storey or host class.
5. Click a row. The MEP element is selected, the camera flies to the crossing, and a marker pulses there. `Ctrl` or
   `Shift` click selects several rows.
6. Look at the markers in the model. Red means no opening. Green means an opening. Grey means the model has no opening
   data. The `markers` option turns them on and off.
7. Press **Export CSV** to save the filtered rows.

On Synthetic 5k every crossing shows as `opening` with a gap of 10 mm. That is by construction: the sample was built with an
opening 10 mm larger than each overlap. It shows you what a clean result looks like. On a real model you will see
`none`.

### What the columns say

| Column | Meaning |
| --- | --- |
| `#` | row number |
| MEP element, host | the two elements that cross |
| storey | the storey of the host, or of the element if the host has none |
| location | the centre of the box where the two overlap |
| orientation | vertical (at least 75 degrees from horizontal), horizontal (at most 15) or inclined |
| size | the two smaller extents of the element's box, in mm |
| host thickness | the smallest extent of the host's box |
| opening status | `opening`, `none` or `unknown` |
| gap | the smallest clearance between the element and the opening, in mm |

**Opening status**

- `opening`: an opening of that host contains the location, or the element is hosted by that host by a filler relation.
- `none`: the model has opening data, and none of this host's openings contains the location. A host with no openings
  counts as none.
- `unknown`: the model has no opening data at all. This happens with older converted files and with `.glb` files.

**Gap** is how much room is left around the element inside the opening, in mm. Half of the difference between the opening
and the element, in the two directions across the run. A negative number means the opening is smaller than the element.
It is empty when the element is hosted only by relation.

### How it works

The viewer takes the MEP elements: either all elements in the focus classes (`scope` = `focus classes`) or the current
focus only (`focus only`). It takes the hosts: every context class whose name contains slab, wall, beam, column, footing
or roof. It finds candidate pairs by sweeping the bounding boxes. Then it checks the real meshes. If the surfaces cross,
or one contains the other, it is a penetration. A duct that runs beside a wall, where the boxes overlap but the meshes do
not, is not.

The orientation comes from the direction of the element's long axis, found from 48 points sampled on its surface. The
size is read from the box, so it is approximate for inclined runs.

Opening boxes come from `relations.openings` in the model data. Both readers, the converter and the in-browser IFC
reader, produce them, and a test compares both.

### Choices and settings

- `scope`: `focus classes` (all MEP) or `focus only` (the current focus).
- `markers`: show or hide the markers.
- **Analyse** runs it again, for example after you changed the scope.
- **Export CSV**: the filtered rows, with ids, classes, names, storey, orientation, sizes, thickness, status, gap and the
  location in m. Cells that start with `=`, `+`, `-` or `@` get a leading apostrophe so a spreadsheet does not run them.
- The drawer lists at most 500 rows. Filter or export for the rest.
- The settings are in the parameters document (19.1), but not in share links.

### Limits and gotchas

- Every overlapping pair is listed. An element that ends inside a host, or touches it for a short distance, appears too.
  Read the list as a set of candidates.
- A host that has openings in the IFC but whose data lacks the opening boxes reads `unknown`. Reconvert the file with the
  current converter, or open the IFC file in the browser.
- Size and gap are approximate for inclined runs.
- Sample models `building` and `plumbing` have no opening relations. Synthetic 5k and Debris demo have synthetic ones.

## 11.2 Raise findings as issues

A schedule nobody acts on is wasted. The drawer has an **Issues** block with **Raise issues from results**. It makes one
issue per row, titled like `Penetration: Duct-12 through Wall-3`. Each issue holds both GlobalIds, a view with the camera
on the crossing, and a drawing tied to the pair. It takes the selected rows, or the filtered rows when none are selected.

Raising again only adds new pairs. A pair that the new analysis no longer reports gets the note `Not found in latest run`,
and **Close n not found** closes them. Above 200 new rows the viewer asks, and offers the 200 worst, the ones with no
opening first. The rules for these issues, including how pairs are matched between runs, are in chapter 15.3.

The drawer has a second button, labelled **Create BCF topics**. It also makes one issue for each selected or filtered row, but it is the older route: it does not match pairs between runs, so raising twice makes duplicates. Its label still uses the old word "topic". Use **Raise issues from results**. To send issues to another tool, export them as BCF (chapter 17).

## See also

- 10.2 Clearance: distances to context, for elements that do not cross.
- 15.3 Issues from checks.
- 17 BCF.
