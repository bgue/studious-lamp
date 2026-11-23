# 7. Model tree and search

## The problem

A real model has thousands of elements and most of them have names like `Basic Wall:Generic - 200mm:312847`. You know what
you want: the pumps on level 2, a door someone mentioned, the setting that makes ghosts fainter. Orbiting and clicking
until you hit it is slow. You need two things: a list that mirrors how the building is organised, and one box that
finds anything by typing a few letters.

## The idea

The **Model tree** is the building as a list. The top level is the storeys, lowest first. Inside a storey are the IFC
classes (walls, slabs, ducts), and inside a class are the elements. A class is the IFC type of the element, such as
`IfcWall`. Elements that belong to no storey sit under a last node called **No storey**. If the model defines systems,
a **Systems** branch is added at the end.

The **search bar** is the other way in. It sits in the top bar. One box searches seven things at once: elements,
commands, presets, views, sets, issues and settings. A radiologist has a light box for the film and a chart for the
patient. The tree is the light box, you walk it. The search bar is the chart, you ask it.

Search also understands conditions. Type `class = 'IfcDuctSegment'` and the box stops searching for text and starts
counting the elements that satisfy the condition. The language of those conditions is taught once, in 8.2.

## 7.1 Browse the model tree

### Try it

1. Open **Sample Projects** and choose **FZK-Haus**. The left sidebar opens on the **Model** tab.
2. Click the small arrow in front of a storey. The classes inside it appear, each with a number: how many elements
   are below it.
3. Open a class, then click an element. It is selected in the 3D view and its data appears in the **Properties** tab
   on the right. Hover a row to see its full name, class and GlobalId in a tooltip. The element is also highlighted in the
   3D view while the pointer is on the row.
4. Click the class row. Every element of that class in that storey is selected. Hold `Shift` and click another class to
   add it.
5. Click the eye icon at the right end of a storey row. Everything on that storey hides, and the eye changes
   to a crossed eye. Click it again to show them.
6. Press `Alt+F`. The cursor jumps to the filter box above the tree. Type `door`. The tree shrinks to the matching
   elements, with every branch open, and a count appears beside the box (`7 matches`, for example). Press `Escape` to clear
   the filter and give the keys back to the page.

> Check: the number of door matches in FZK-Haus is not in the source docs. Run step 6 and replace the example count.

### How it works

The tree is built once per model from the element list. Storeys sort by elevation, classes alphabetically and
elements by name in natural order, so `Wall 2` comes before `Wall 10`. An element with no name shows its GlobalId.
Long names are shortened on screen and shown in full in the tooltip.

Each row has a small coloured dot. For an element it shows the role the x-ray gives it right now: focus, host, near,
far or none (chapters 1 and 4). For storeys and classes the dot is plain.

The filter looks at name, GlobalId and class. While you filter, the tree remembers which branches were open, and puts
them back when you clear the filter. The tree draws only the rows you can see, so a model with 100,000 elements
scrolls without delay.

### Hide, isolate, show

The eye on a row hides or shows everything below that row. A half-dimmed eye on a storey or class means some of its
elements are hidden and some are not. These are your hides. They are separate from the hides that cleanup makes
(chapter 9) and from the ghosting of x-ray, which fades elements but keeps them.

Three keys do the same from the keyboard, on the current selection.

| Key | What it does |
| --- | --- |
| `h` | Hide the selected elements. |
| `Shift+H` | Hide everything that is not selected (isolate the selection). |
| `Alt+H` | Show everything you hid. Pins stay. |

Hidden elements are not drawn, cannot be picked and are removed from the selection.

### Limits and gotchas

- The tree selects and hides. It does not rename, move or delete elements, and it never changes the file.
- An element can appear in two branches (for example under a storey and under a system). Each row is its own row, but
  both select the same element.
- On a phone the tree is an overlay that you open with its rail button (chapter 3.5).
- `[` shows or hides the tree.

## 7.2 The search bar

### Try it

1. Press `/` or `Ctrl+K`. The cursor goes into the search box in the top bar. On a phone, tap the search icon first.
2. Type `wall`. Results appear after a short pause, grouped under headers: **Elements**, **Commands**, **Presets**,
   **Saved views** and so on. The group with the best match is on top.
3. Press the Down arrow. The first element row is highlighted in the 3D view while it is the active row.
4. Press `Enter`. The element is selected and the camera frames it.
5. Open the box again, type `rdct`. It finds `Rectangular Duct`: letters can be an abbreviation of the start of
   each word. Matched letters are highlighted.
6. Type `duct level 2`. All three words must match, in any order. A word can match the start of a name, the start of
   a word inside it, or any part of it.
7. Type `>hide` and press `Enter`. The `>` limits the search to commands and settings, so you see only what the
   keyboard could do.
8. Type `fire` and look under **Settings** (or any other term from the parameter panel). `Enter` opens the right
   folder in the **Parameters** tab, scrolls to the control and flashes it.

### What each section does

| Section | What matches | Enter does |
| --- | --- | --- |
| Elements | name, class, GlobalId, storey, material, property values | selects the element and frames it |
| Commands | every action, with its keys | runs the action |
| Presets | the presets (chapter 4.5) | applies the preset |
| Saved views | the views of this model | restores the view |
| Selection sets | the sets of this model (chapter 8) | selects the set and frames it |
| Issues and sketches | issues and drawn views, by title, note or comment | opens the **Issues** tab on it |
| Settings | every named control of the parameter panel | opens it and flashes it |

> Check: the last section is labelled "Issues and sketches" in `web/docs-features/search.md`. After the views-and-issues
> change lands, replace the label with the one on screen.

`Shift+Enter` adds to the selection instead of replacing it, and leaves the camera alone. Elements show up to 50
rows and then `N more…`. Another `Enter` or a click on that row shows up to 200. Other sections show 5 to 8 rows.

Focus the empty box and it lists the last 8 things you used, newest first. This list is kept in the browser. Items that
no longer exist are skipped.

### How it works

When a model opens, the viewer reads every element's name, class, GlobalId, storey, material and property values into one
text index. A query looks up its rarest word in that index and scores only the rows that contain it. On a synthetic
100,000-element model the index took about 0.2 s to build and a query 1 to 15 ms. Up to 20,000 elements the index is
ready at once. A larger model is indexed in the background, and the footer says `Indexing the model` until it is done.

### Limits and gotchas

- One letter matches only the start of a name or class.
- The search finds only what is loaded in the current model.
- In kiosk pages and in AR/VR the bar is hidden. `/` and `Ctrl+K` then do what they did before: focus the tree filter and
  open the command palette.
- The full-screen command palette is still there on `Ctrl+Shift+K`. It lists every action and every button of the
  parameter panel.

## 7.3 Conditions typed into search

### Try it

1. Press `/` and type `where class like 'IfcWall%'`.
2. The list is replaced by one row: `N elements match`, with the top classes. The footer repeats the count. It updates
   as you type.
3. Add ` and storey like '%1%'`. The count drops.
4. Press `Enter`. All the matching elements are selected. `Shift+Enter` adds them to the selection.
5. Break the query on purpose: `where class =`. A red note says what is wrong and where, for example `Expected a value
   after "=", found the end of the query.`
6. Try `count where class like 'IfcWall%'`. You get a number, not a list: a quantity summary. Chapter 8.2 explains
   these.

### How it works

Search decides that your text is a condition in one of three ways. It starts with `where ` or `?`. It starts with
`count`, `sum`, `avg`, `min` or `max`. Or it looks like one: a column name followed by `=`, `!=`, `<>`, `<`, `<=`, `>`,
`>=`, `LIKE`, `IN (`, `IS NULL` or `BETWEEN`. In the last case a failed parse falls back to plain text search, so a
name that contains an `=` still works. With `where` or `?` you only get the query.

A column that no element has reads as empty, and the box names it in a note. That is nearly always a typo.

### Limits and gotchas

- Search does not save a query. To keep one, make a criteria set (8.2). The properties context menu (8.2) can write
  the query for you.
- Everything in this section, the words and the signs, is the language of chapter 8.2. Learn it there once.

## See also

- 8.2 The query language, and how to keep a query as a set.
- 3.3 Select, hover cards and the Properties tab.
- 4.3 Pins, hides and class styles: how hides interact with x-ray.
