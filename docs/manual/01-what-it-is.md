# 1. What the viewer is and the x-ray idea in one page

You open a building model to check a duct run above a ceiling. What you see is walls, slabs and beams. The duct is behind
them. You can hide the walls one by one, but then you lose the room around the duct, and an hour later you have forgotten
what you hid. You want the structure to get out of the way for a moment and come back when you look elsewhere.

This viewer does that. It opens building models (IFC and glb files) in your browser. When you select a part, it makes the
things that block your view of that part faint, and leaves everything else solid. Around that idea it has tools to cut,
measure, check, annotate and present. This chapter explains the idea and how the program is delivered. The other chapters
build on it.

## 1.1 Focus, context, occluder

A radiologist sees a bone on an x-ray picture because the flesh around it is made faint, not removed. The flesh is still
there, so the bone keeps its place in the body. The viewer does the same with a building.

Three words carry the idea. You will meet them in every chapter.

- **Focus** is what you care about right now: the part you select, plus the parts connected to it. If you select one
  duct segment, the focus is the whole connected duct run (the viewer follows the ports and the system the segment belongs
  to). The viewer draws the focus solid and, by default, in front of everything.
- **Context** is what may ghost: slabs, walls, beams, columns, footings, stairs and roofs, on the focus storey and one
  storey above and below.
- **Occluder** is a context part that stands between your eye and the focus, or that touches the focus. Only occluders
  change how solid they look. A column on the far side of the building, out of your way, stays as it is.

So here is why a wall ghosts when you select a duct: the duct is the focus, the wall is context, and the wall blocks your
line of sight to the duct, so it becomes an occluder and fades.

**How the viewer decides how much.** It does not guess. It measures.

1. It spreads sample points over the surface of the focus. The default is 64 points per focus part, and at most 500 in
   total.
2. From each point it draws a straight line to the camera. These lines are the *sightlines*.
3. For each occluder it counts how many sightlines it crosses and divides by the number of lines. That share is the
   *occlusion*, between 0 and 1.
4. The more of the focus an occluder hides, the more it fades.

A slab that crosses 3 of every 4 sightlines (occlusion 0.75) fades to an opacity of about 0.24, where 1 is solid and 0 is
invisible. A beam that crosses none keeps its normal look. The test is repeated after each camera move, so the picture
follows you as you orbit. The change is eased in small steps, so nothing pops.

**Proximity.** Not every context part is equal. The viewer sorts each one into a bucket.

| Bucket | What it is | How it ghosts |
| --- | --- | --- |
| Focus | The selection and its connected run | Never. Solid. |
| Host | Context that crosses or contains the focus, such as the slab a duct passes through | Strongest (weight 1) |
| Near | Context within a buffer around the focus, not a host | Weaker the further away it is |
| Far | All other context | Only if it blocks the view, and less than the others |

The buffer starts at 0.30 m and grows with the size of the focus part, up to 1.50 m. A thick duct reaches further than a
thin pipe. A far part that blocks your view still ghosts in this viewer (the original research report ghosted only host
and near parts). A far wall that blocks the whole focus settles at an opacity of about 0.40. You can turn that off
(see 4.2).

> Picture: the Building model with one duct selected. The duct is solid; the slab above it and one wall are faint with
> visible outlines; the rest of the building is solid.

**Words used in this manual.** A *view* is a captured moment: camera, what is shown, hidden, cut and selected. A *preset* is
a saved look (settings only). A *mode* is one of the five looks in the top bar: Solid, Ghost, Radiograph, Glow and
Cutaway. A *set* is a named group of elements. A *query* is a condition such as `class = 'IfcWall' and storey = 'Level 2'`.
An *issue* is a problem someone must act on. Appendix E has the full glossary.

## 1.2 What runs where

The viewer is a web page. It runs in your browser, on your computer. There is no server that holds your model. You can
get it in three forms.

| Form | What it is | When to use it |
| --- | --- | --- |
| Single file | `xray-viewer.html`: one file with the program, the sample models and the IFC reader inside. Open it by double-click. | Trying the viewer, sending it to a colleague, working offline |
| Served app | The program run from its source with a local web server (`npm run dev`). | Development, large models, the sample "Synthetic 5k" |
| Packed page | A single HTML file made with the `xray-pack` tool. It holds one model and a starting state. | Handing a finished model to someone who needs nothing else (see chapter 30) |

**Nothing is uploaded.** Your IFC file is read inside your browser, by a background worker. The single file makes no
network request. Two kinds of feature reach out, and only when you turn them on yourself: the map under the model sends
the project location to a tile server (see 6.2), and some of the decision models in the classifier use a download or an
endpoint you name (see chapter 18).

A packed page contains your model. Treat it like the model file itself. A share link holds settings, not the model (see
chapter 29).

Use Chromium, Edge or Chrome. Firefox and Safari were not available for testing, so they are untested.

## 1.3 Who reads which part

You do not need to read the manual in order. Pick your route.

| You are | Read first | Then |
| --- | --- | --- |
| **Coordinator or site engineer** [C] | Chapters 2 to 6 (look and cut), 7 to 8 (find), 10 to 11 (check) | 13 to 17 (views and issues), 20 (revisions) |
| **4D planner** [P] | Chapters 2 to 3 and 8, then 24 | 25 to 28 (4D), 21 to 22 (films), 32 |
| **Integrator or developer** [D] | Chapters 2, 3 and 35 | 30 (packed pages), 32 to 34 (command line, agent skill, data) |
| **Presenter** | Chapters 4 to 6 | 13, 21 to 23 |

Sections tagged [C], [P] or [D] are for that reader only. Untagged sections are for everyone.

Part I (chapters 1 to 3) is the base. Part II (4 to 6) is the core of the viewer: seeing through the model. If you read
only one more chapter after this one, read chapter 4.

## See also

- Chapter 2: get a model on screen.
- Chapter 4: use the idea of this chapter and tune it.
- Appendix E: glossary.
