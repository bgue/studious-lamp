# Selection sets and criteria queries

The **Sets** tab of the left sidebar keeps named groups of elements per model. A set is either

- **static**: an explicit list of elements, saved from the current selection; or
- **criteria** (funnel icon): a query such as `class = 'IfcWall' AND "Pset_WallCommon.IsExternal" = TRUE`. Its members
  are found again when the model loads, when you apply the set and when you pick **Re-evaluate now**, so the set follows
  changes to the model.

The query language is a small subset of the SQL `WHERE` clause, run by a tokenizer, a recursive-descent parser and a
compiled predicate in `web/src/query/` (no SQLite or wasm: a 1 MB engine would double the single-file viewer). A query over
100,000 elements runs in about 20 ms.

## Using the Sets tab

- **Save selection as…** stores the selection under the typed name (static set).
- **New criteria set** opens the editor (below).
- **Export** / **Import**: JSON file `xray-sets/1` (same names are replaced on import).
- **Filter sets**: shows the sets whose name or query contains the text; Down arrow moves into the list, Escape clears.
- Each set is one line: name, element count, **+** and **⋯**.
  - Click the name: select the set and frame it (Shift+click adds to the selection).
  - **+** adds the set to the selection.
  - **⋯** opens a menu: **Update from selection** (static) or **Re-evaluate now** (criteria), **Rename**,
    **Edit criteria…** (criteria), **Duplicate**, **Delete** (click twice to confirm).
  - A count `n/m` means `m - n` members of the set are not in the loaded model.
- Keyboard: Up/Down/Home/End move between sets (Up from the first set returns to the filter box), Left/Right move
  between the name, **+** and **⋯**, Enter or Space activates, Enter or Space on **⋯** opens the menu, arrow keys move in
  the menu, Escape closes it and returns to **⋯**. The Delete key opens the menu of the focused set.

The list is a plain scrolling list of one-line rows with `content-visibility: auto`; 250 sets lay out in about 2 ms.

## Criteria editor

- **Name** of the set.
- **Rows**: field (with suggestions from the columns present in the model, with counts), operator
  (`=`, `≠`, `<`, `<=`, `>`, `>=`, `LIKE`, `NOT LIKE`, `IN`, `NOT IN`, `IS NULL`, `IS NOT NULL`) and value (suggestions are
  the distinct values of the field, most frequent first). **Match all / any** joins the rows with `AND` / `OR`.
  The rows write the query text; numbers and `TRUE`/`FALSE` stay unquoted when the column holds numbers or booleans.
- **Query** box: the text itself, for anything the rows cannot express (parentheses, `NOT`, `BETWEEN`, comparisons
  between two columns). While the text is not a flat AND or OR of simple conditions, the rows are greyed out.
  Ctrl+Enter saves.
- The live line below shows `n matches of N elements`, or the error with its position and a caret under it, and warns
  about columns that no element has (they read as NULL, which is usually a typo).
- **Preview** selects and frames the matches without saving. **Save** stores the set (or the changes).

## Properties context menu

Right-click any row of the properties footer (Class, Name, Storey, Material, GlobalId and every property of the
**Properties** list), or use the **⋯** button that shows on hover (always on touch screens):

| Item | Query |
| --- | --- |
| Select all with this value | `"Pset_WallCommon.IsExternal" = TRUE`, `class = 'IfcWall'`, `storey IS NULL` for "No storey" |
| Add to selection all with this value | same, added to the selection |
| Select all with this property | `"Pset_WallCommon.FireRating" IS NOT NULL` (properties, Name, Storey, Material) |
| Copy value | the value as shown |
| Save as criteria set… | opens the criteria editor with the query and a suggested name |

Selections go through `app.selectIds`, as for the tree and the sets. Bucket, alpha and the other x-ray rows only offer
**Copy value**.

## Query language

```
query     := or
or        := and ( OR and )*
and       := not ( AND not )*
not       := NOT not | primary
primary   := ( or ) | operand [ tail ]
tail      := cmpOp operand | [NOT] LIKE operand | [NOT] IN ( operand, ... )
           | [NOT] BETWEEN operand AND operand | IS [NOT] NULL
operand   := column | 'text' | number | -number | TRUE | FALSE | NULL
cmpOp     := = | == | != | <> | < | <= | > | >=
```

- Precedence, low to high: `OR`, `AND`, `NOT`, comparison. Keywords ignore case.
- Strings in single quotes (`'it''s'`), column names in double quotes (`"Pset_WallCommon.Fire Rating"`); a dotted name
  without spaces may stay bare (`Pset_WallCommon.IsExternal`). A keyword used as a column needs quotes (`"not"`).
- A column alone is a test for TRUE: `"Pset_WallCommon.IsExternal"` means `... = TRUE`.

### Columns

| Column | Value |
| --- | --- |
| `class` (also `ifcClass`) | IFC class |
| `name`, `material` | NULL when empty |
| `storey`, `storeyElevation` (also `elevation`) | storey name and elevation in m; NULL without a storey |
| `globalId`, `id` | IFC GlobalId, viewer element index |
| `xMin` `yMin` `zMin` `xMax` `yMax` `zMax` (also `minX` ...) | bounds in viewer coordinates, m (y is up) |
| `sizeX` `sizeY` `sizeZ`, `volume` | bounds size in m (`sizeY` is the height), bounding-box volume in m3 |
| any property key | `"Attr.ObjectType"`, `"Pset_WallCommon.IsExternal"`, `"BaseQuantities.NetVolume"` ... |

Core column names ignore case; property keys match exactly first and then ignoring case. Properties are those of the
sidecar (`ElementRecord.props`, at most 24 per element, see [hover-info.md](hover-info.md)).

### Semantics

- **NULL**: a missing property, an empty name or material and "no storey" are NULL. SQL three-valued logic applies: a
  comparison with NULL is UNKNOWN, `NOT UNKNOWN` is UNKNOWN, and a row matches only when the query is TRUE. So
  `"Pset_WallCommon.IsExternal" != TRUE` skips elements without the property; write
  `... != TRUE OR "Pset_WallCommon.IsExternal" IS NULL` to include them. `x = NULL` never matches; use `IS NULL`.
- **Types**: two numbers compare as numbers; a number and a numeric string compare as numbers (`'0.24' = 0.24`); two
  strings compare as text. Booleans compare as 0/1 with numbers and as `true`/`false` (also `yes`/`no`) with strings.
- **Case**: string comparison ignores case (`class = 'ifcwall'` finds `IfcWall`).
- **LIKE**: `%` any run of characters, `_` one character, anchored, ignores case; `\%` and `\_` are literal.
- `BETWEEN a AND b` is inclusive. `IN` with a NULL member follows SQL (`x NOT IN ('a', NULL)` matches nothing).
- Errors name the character position: `Expected ")" to close the "(" at character 23, found the end of the query (at
  character 38)`.

Examples:

```sql
class IN ('IfcWall', 'IfcWallStandardCase') AND "Pset_WallCommon.IsExternal"
"BaseQuantities.NetVolume" > 2 AND storey = 'Erdgeschoss'
name LIKE 'Riser%' OR "Attr.ObjectType" LIKE '%duct%'
sizeY BETWEEN 2.4 AND 3.2 AND NOT class = 'IfcColumn'
"Pset_WallCommon.FireRating" IS NULL AND class LIKE 'IfcWall%'
```

## Storage

`localStorage` key `xray.sets.<model>`, JSON `{ "version": 1, "sets": [...] }`, unchanged for static sets
(`{ "name", "globalIds" }`). A criteria set adds `"kind": "criteria"` and `"query"`; its `globalIds` hold the members of
the last evaluation, so older viewers and the cinematic tour still read it as a static set. Export files (`xray-sets/1`)
and the `selectionSets` section of the params document carry the same objects. A hand-written criteria set may leave
out `globalIds`. Sets are stored by GlobalId, so they survive a reconversion of the IFC file.

## Code

- `web/src/query/lexer.ts`, `parser.ts`, `compile.ts`: tokens, AST, predicate (`QueryError` has `pos`).
- `web/src/query/table.ts`: the virtual flat row per element (`ModelTable`, columns, distinct values).
- `web/src/query/index.ts`: `runQuery(model, text)`, quoting helpers, rows-to-text and text-to-rows for the builder.
- `web/src/selectionSets.ts`: storage, `kind`/`query`, list operations.
- `web/src/ui/setsView.ts`, `criteriaEditor.ts`, `popupMenu.ts`, `propsView.ts`; wiring in `web/src/plugins/sidebar.ts`.
- Tests: `web/tests/query-engine.test.ts`, `web/tests/selection-sets-criteria.test.ts`.
