# 8. Selection sets and the query language

## The problem

You select all external walls of level 2 with a dozen clicks. Then the meeting ends, you close the page, and next week
the model has a new version and you must do it again. Or a colleague asks for "all fire-rated walls over 2 m3" and you
have no way to say that to the viewer except by clicking.

## The idea

A **set** is a named group of elements. There are two kinds.

A **static set** is a list. You select some elements, give the list a name, and it remembers exactly those elements.
It is a photograph.

A **criteria set** is a rule. You write a condition, such as `class = 'IfcWall' and storey = 'Level 2'`, and the
viewer finds the elements that satisfy it. It finds them again every time the model loads, so it follows the model. It is
a standing order, "bring me every external wall", not a list of the walls it brought last time.

A condition like that is a **query**. The query language is a small part of the SQL `WHERE` clause. You do not need to
know SQL. The viewer treats the model as one big table with a row per element. The columns are things like class, name,
storey and every property. A query describes which rows you want.

This chapter teaches that language once. The search bar (7.3), criteria sets, 4D trade and zone queries (chapter 25),
animation scripts (chapter 23) and the issue checks all use the same language. Other chapters point here.

## 8.1 Save the selection as a static set

### Try it

1. Open **Sample Projects** and choose **FZK-Haus**.
2. Select a few elements: click one, then `Shift`+click others (or use the rectangle select of chapter 3.2).
3. In the left sidebar open the **Sets** tab and press **Save selection as…**. Type a name, for example `Test walls`,
   and confirm.
4. A new line appears: the name, a count and two small buttons, **+** and **⋯**.
5. Press `Escape` to clear the selection. Click the name of the set. The elements are selected again and the camera
   frames them. `Shift`+click the name adds them to what is already selected. The **+** button does the same.
6. Open **⋯**. For a static set you see **Update from selection**, **Rename**, **Duplicate** and **Delete**. Delete
   asks you to click twice.

### How it works

A static set stores GlobalIds, not internal numbers. A GlobalId is the stable identity every IFC element carries.
Because of that a set survives a new conversion of the same file, and it works on the next version of the model if the
elements kept their ids. If a count reads `n/m`, then `m - n` members of the set are not in the loaded model.

Sets are kept per model, in the browser's own storage on your computer. They are not in the IFC file. Chapter 19.4
lists what is saved where.

The **Filter sets** box above the list shows the sets whose name or query contains your text. The keyboard works
too: Up and Down move between sets, Left and Right move between the name, **+** and **⋯**, Enter or Space acts.

### Limits and gotchas

- A static set is only as good as your memory of what it should contain. If the model grows, it does not.
- Sets belong to the browser and the model name. Another computer needs the export file (8.3).

## 8.2 The query language

Everything in this section works in the search bar (after `where`), in the criteria editor, in the Properties
context menu and in 4D, scripts and checks. Examples use the sample models, but every part is the same on yours.

### Try it: a criteria set

1. In the **Sets** tab press **New criteria set**. A small editor opens.
2. Type the name `External walls`.
3. In the first row choose the field `class`, the operator `=` and the value `IfcWall`. The value box suggests the
   values the model really has, most frequent first.
4. Add more rows if you need them, and join them with **Match all** or **Match any**. As you edit, the
   **Query** box shows the text the rows write, for example `class = 'IfcWall'`.
5. Look at the live line under the editor. It says `n matches of N elements`. If you made a mistake it shows the error
   and puts a caret under the place.
6. Press **Preview**. The matches are selected and framed, nothing is saved yet.
7. Press **Save**. The set appears in the list with a funnel icon.
8. Open **⋯**. A criteria set has **Re-evaluate now** and **Edit criteria…** instead of **Update from selection**.
   `Ctrl+Enter` in the Query box also saves.

### The shape of a query

A query is one or more **conditions** joined by `AND`, `OR` and `NOT`. A condition compares a **column** with a
**value**.

```
class = 'IfcWall'
```

- A **column** is a field of the element: `class`, `storey`, a property.
- A **value** is text in single quotes (`'IfcWall'`), a number (`2.4`, `-1`), or one of the words `TRUE`, `FALSE`,
  `NULL`.
- A single quote inside text is doubled: `'it''s'`.
- Keywords ignore case: `and`, `AND` and `And` are the same.

Combine conditions:

```
class = 'IfcWall' AND storey = 'Level 2'
class = 'IfcWall' OR class = 'IfcSlab'
NOT class = 'IfcColumn'
```

`AND` binds tighter than `OR`, and `NOT` binds tighter than `AND`. Use brackets when in doubt:

```
(class = 'IfcWall' OR class = 'IfcSlab') AND storey = 'Level 2'
```

Without the brackets that would mean "every wall, plus the slabs on level 2".

### Comparisons

| Write | Means |
| --- | --- |
| `=` or `==` | equal |
| `!=` or `<>` | not equal |
| `<` `<=` `>` `>=` | smaller, at most, larger, at least |
| `LIKE 'text%'` | matches a pattern (below) |
| `NOT LIKE` | does not match the pattern |
| `IN ('a', 'b')` | equals any of the listed values |
| `NOT IN (...)` | equals none of them |
| `BETWEEN a AND b` | from a to b, both ends included |
| `IS NULL` | has no value |
| `IS NOT NULL` | has a value |

**LIKE** matches text against a pattern. `%` stands for any run of characters, including none. `_` stands for exactly
one character. The pattern must match the whole text, not just a part of it, so `name LIKE 'door'` finds only the name
`door`, and `name LIKE '%door%'` finds every name that contains it. To mean a literal `%` or `_`, put a backslash before
it.

**IN** is a short way to write several `OR`s: `class IN ('IfcWall', 'IfcWallStandardCase')`.

**BETWEEN** includes both ends: `sizeY BETWEEN 2.4 AND 3.2`.

A column on its own is a test for TRUE. `"Pset_WallCommon.IsExternal"` means the same as
`"Pset_WallCommon.IsExternal" = TRUE`.

### Columns

| Column | What it holds |
| --- | --- |
| `class` (also `ifcClass`) | the IFC class, such as `IfcWall` |
| `name`, `material` | the text, or NULL when empty |
| `storey` | the storey name, or NULL when the element has none |
| `storeyElevation` (also `elevation`) | the storey elevation in m |
| `globalId`, `id` | the IFC GlobalId; the viewer's own element number |
| `xMin` `yMin` `zMin` `xMax` `yMax` `zMax` | the bounding box, in m, viewer axes (y is up) |
| `sizeX` `sizeY` `sizeZ` | the size of the bounding box in m (`sizeY` is the height) |
| `volume` | the volume of the bounding box in m3, not the volume of the element |
| any property | `"Pset_WallCommon.IsExternal"`, `"BaseQuantities.NetVolume"`, `"Attr.ObjectType"` |

The core column names ignore case. A property is named `PropertySet.Property`. A property name with a space, or a name
that is also a keyword, goes in double quotes: `"Pset_WallCommon.Fire Rating"`, `"not"`. A dotted name without spaces
may stay bare: `Pset_WallCommon.IsExternal`. Property keys match exactly first and then without regard to case. 
You do not have to remember any of these. In the criteria editor, the field box suggests the columns that the model has,
with counts. In the Properties tab, right-click a row and the viewer writes the query for you (below).

Single quotes are for values. Double quotes are for column names. `'storey'` is the word storey, `"storey"` is the column.

### Missing values (NULL)

A missing property, an empty name and "no storey" are all NULL. NULL is not zero and not an empty string. It means
"nothing is known".

A comparison with NULL is neither true nor false. It is unknown, and an element is selected only when the query is
definitely true. The surprise is this:

```
"Pset_WallCommon.IsExternal" != TRUE
```

does not find walls that have no such property, because for them the answer is unknown. To include them write

```
"Pset_WallCommon.IsExternal" != TRUE OR "Pset_WallCommon.IsExternal" IS NULL
```

`x = NULL` never matches. Use `IS NULL`. `NOT IN` with a NULL in the list matches nothing.

### Text, numbers and case

- Text comparison ignores case: `class = 'ifcwall'` finds `IfcWall`.
- Two numbers compare as numbers. A number and a text that looks like a number compare as numbers too: `'0.24' = 0.24`.
  Two texts compare as text.
- A yes/no property can be compared with `TRUE` and `FALSE`, or with the text `true`, `false`, `yes`, `no`.

### Worked examples

```
class IN ('IfcWall', 'IfcWallStandardCase') AND "Pset_WallCommon.IsExternal"
"BaseQuantities.NetVolume" > 2 AND storey = 'Erdgeschoss'
name LIKE 'Riser%' OR "Attr.ObjectType" LIKE '%duct%'
sizeY BETWEEN 2.4 AND 3.2 AND NOT class = 'IfcColumn'
"Pset_WallCommon.FireRating" IS NULL AND class LIKE 'IfcWall%'
```

The last one is a quality check: every wall that has no fire rating.

### Errors

When a query does not parse, the message names the character where it went wrong, for example `Expected ")" to
close the "(" at character 23, found the end of the query`. If you use a keyword as a column name the message
says to put it in double quotes. A column that no element has is not an error: it reads as NULL, and the editor warns
you in a note, because that is nearly always a misspelling.

### Counting and adding up

A query that starts with `count`, `sum`, `avg`, `min` or `max` does not select elements. It gives you a number. Type it in
the search bar (7.3).

```
count where class like 'IfcWall%'
sum netsidearea where class like 'IfcWall%'
sum length, count where class = 'IfcPipeSegment' by storey
avg length, max length where class = 'IfcBeam'
sum volume by class
```

| Part | Meaning |
| --- | --- |
| `count` | how many elements |
| `sum`, `avg`, `min`, `max` plus a quantity | total, mean, smallest, largest. `sum of length` and `sum(length)` also work |
| `a, b` or `a and b` | several numbers at once |
| `where <condition>` | optional: the query language above. Without it the summary covers every element that is not hidden. With it, every matching element, hidden or not |
| `by <column>` | optional: one subtotal per storey, class, material or property (`by storey`, `by class`, `by Pset_WallCommon.FireRating`). `level` means `storey` |

A quantity is named loosely. The viewer looks it up on each element on its own, so `length` reads the beam length on a
beam and the wall length on a wall. Useful names are `length`, `width`, `height`, `depth`, `thickness`, `perimeter`,
`area`, `volume` and `weight`. You can also type the last part of a property (`netsidearea`), several words (`net side area`)
or the full key (`Qto_WallBaseQuantities.NetVolume`).

The answer appears under the search box (for example `42 pipe segments, sum of length 318.4 m`) and, with `by`, the top
three groups. `Enter` selects the elements and frames them. `Shift+Enter` leaves the selection alone. A small card under the bar repeats the answer, stays
while the pointer is on it, and fades after about 6 s. A click on it copies the text.

**What if an element has no value?** Values must be numbers. An element whose property is missing or not a number is
skipped, and is counted and listed in the console with the reason. For some quantities the viewer then makes an
**estimate** from the shape of the element, and the total says how many: `(6 est.)`.

| Quantity | Estimate | Not available when |
| --- | --- | --- |
| `volume` | the volume of the mesh | the mesh is not a closed solid |
| `length` | the longest side of the bounding box | the element has no geometry |
| `height` | the vertical size of the bounding box | the element has no geometry |
| `area` | half the surface of the mesh | the element is not a closed thin plate |

A slanted pipe reads short by this box method, and a thick plate reads a few percent high. Treat estimates as a check,
not as a quantity take-off. Other quantities have no estimate. A property that is present but not numeric is never
estimated.

Values are in the unit of the model, which is metres for every loader today, and shown as `m`, `m²`, `m³`, `kg`.
Small numbers show more decimals (`0.125 m³`), large ones fewer (`2 310 m`).

On a model with no quantity properties, `sum` and `avg` rely on the estimates. FZK-Haus carries `BaseQuantities.*`; Synthetic 5k
and Building carry `Qto_*BaseQuantities.*`.

### Right-click to write a query

Right-click any row of the **Properties** tab (Class, Name, Storey, Material, GlobalId or any property), or use the **⋯**
button that shows on hover. The menu lets you write the query without typing it.

| Item | What it does |
| --- | --- |
| Select all with this value | selects every element with the same value, e.g. `class = 'IfcWall'`. For "No storey" it writes `storey IS NULL` |
| Add to selection all with this value | the same, added to the selection |
| Select all with this property | `"Pset_WallCommon.FireRating" IS NOT NULL` |
| Copy value | copies the value as shown |
| Save as criteria set… | opens the criteria editor with the query and a suggested name |

This is the quickest route: select one fire door, right-click its property, choose **Save as criteria set…**.

### How it works

When you type a query, the viewer splits it into pieces, checks the grammar, and compiles it to a small function. That
function is called for every element's row, and the elements for which it answers "true" are the matches. No database
is involved. A query over 100,000 elements takes about 20 ms, so the count under the editor can update on every
keystroke.

### Limits and gotchas

- Properties are only those the viewer read from the file, at most 24 per element.
- Comparisons between two columns work (`sizeX > sizeZ`), but the row editor can not show them. Write them in the
  Query box.
- The row editor shows only flat `AND` or flat `OR` lists. As soon as the text has brackets, `NOT`, `BETWEEN`, or a
  mix of `AND` and `OR`, the rows are greyed out and you edit the text. Nothing is lost.
- There are no functions (`upper()`), no arithmetic, no joins, and no way to query relations between elements (what is
  hosted by what).
- `volume` is the volume of the bounding box. Use a property such as `"BaseQuantities.NetVolume"` for the real one.
- Bounds are in viewer coordinates (y up, shifted by the model origin), not in IFC project coordinates.

## 8.3 Export, import, and use a set elsewhere

### Try it

1. In the **Sets** tab press **Export**. A JSON file (`xray-sets/1`) downloads.
2. Open the same model in another browser, or on another computer.
3. Press **Import** and choose the file. The sets appear. A set with the same name as one already there replaces it.

### Using a set as a target

A set is a name for a group. Other parts of the viewer accept that name.

| Where | How a set or a query is used |
| --- | --- |
| Search | `Enter` on a row in the **Selection sets** section selects the set (7.2) |
| 4D mapping (chapter 25) | assign a value to a **selection set**, or to a **criteria query** with a live count |
| Animation scripts (chapter 23) | `set "External walls"` names the set. `where class = IfcPump` writes a query in place |
| Parameters document (19.1) | the sets are in the `selectionSets` section |

Scripts write `where` queries a little looser than this chapter: `class = IfcPump` works without quotes, and
`class A, B` means the same as `class IN ('A', 'B')`. The script text is rewritten to the query language and parsed by the
same parser. Chapter 23 lists the differences.

### How it works

A criteria set stores the query and also the GlobalIds it found last time. That is why an older version of the viewer
still sees it as a plain list. When you open the model the viewer runs the query again,
and the list is refreshed. If it finds fewer elements than before, the model changed.

The export file and the `selectionSets` part of the parameters document hold the same data. A hand-written criteria set
may leave out the GlobalIds, and they are filled in on the first evaluation.

### Limits and gotchas

- **Re-evaluate now** is needed only when you edit the model's data while it is open. On load it is automatic.
- Sets belong to the model by name. Opening a file with another name starts with no sets.
- Import replaces sets of the same name without asking.

## See also

- 7.3 Conditions typed into search.
- 25.1 Assign by query or set in 4D.
- 23.2 Queries inside animation scripts.
- 19.4 What is saved where.
