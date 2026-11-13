# Search bar

One box that finds things in the model and in the viewer, and runs criteria queries. It lives in the top bar
(`#xray-topbar-search`, made by the top bar plugin). On a page without a top bar it sits in a small fixed box at the top
centre of `#stage`. Code: `src/ui/awesomeBar.ts` (DOM and keys), `src/plugins/awesomeBar.ts` (mount, indexing, the focus action),
`src/search/*` (matching, index, sources, query mode).

## Use

Press `/` or `Ctrl+K` (`Meta+K`), type, move with Up and Down, press Enter. Escape clears the box and gives the keys back to
the page. Results appear as you type (30 ms debounce) in one list with section headers; the section whose best row ranks
highest comes first.

| Section | What matches | Enter does |
| --- | --- | --- |
| Elements | name, IFC class, GlobalId, storey, material and property values | selects the element and frames it |
| Commands | every registered action (`src/input/actions.ts`), with its keys | runs the action |
| Presets | `window.__xrayPresets` | applies the preset |
| Saved views | `window.__xrayViews` | restores the view |
| Selection sets | the sets of the model (`src/selectionSets.ts`), static and criteria | selects the set and frames it |
| Issues and sketches | issues (BCF topics) and sketches of the loaded model, by title, note or description and comment text, the row says which field matched ([issues.md](issues.md)) | opens the Issues tab on it and brings its view back |
| Settings | every named control of the parameter panel: label, folder path, help text | opens its folders and the dock, scrolls to the control and flashes it |

- **Shift+Enter** adds an element, a set or the query result to the selection instead of replacing it (the camera stays).
- **Several words** all have to match: `duct level 2`. A word matches as a prefix, a word start, a substring or, for letters
  only, an abbreviation (`rdct` finds `Rectangular Duct`). Matched letters are highlighted. A match inside a GlobalId,
  material or property value shows that value under the row.
- **Caps.** Elements: 50 rows, then `N more…` (Enter or a click shows up to 200). Other sections: 5 to 8 rows.
- **`>` prefix.** `>hide` searches commands and settings only, like the old palette.
- **Hover preview.** The element row under the pointer or the arrow keys is highlighted in the 3D view
  (`renderer.setHoverHighlight`, the hover card hook) and cleared when the list closes.
- **Recent items.** Focus the empty box to see the last 8 things you used, newest first (`localStorage` `xray.search.recent`,
  keys such as `e:<GlobalId>`, `a:<action id>`, `p:<preset id>`, `v:<view id>`, `s:<set name>`, `i:<issue or sketch>:<id>`, `g:<folder>/<label>`).
  Items that no longer exist are skipped.

## Query mode

Input that starts with `where ` or `?`, or that looks like a condition (a column and `=`, `!=`, `<>`, `<`, `<=`, `>`, `>=`, or
`LIKE`, `IN (`, `IS NULL`, `BETWEEN` after a column), runs through the criteria query engine (`src/query`, the grammar of
[sets-query.md](sets-query.md)):

```
where class = 'IfcDuctSegment' and storey like '%1%'
? volume > 0.5
name not like '%door%'
```

The list shows one row, `N elements match`, with the top classes, and the footer repeats the count. Enter selects them all
(Shift+Enter adds). The count is live: it runs on every key. An error from the engine is shown inline in a red note
(`Expected a value after "=", found the end of the query. Check the text around character 8.`). A column no element has reads
as empty and is named in a note. With `where` or `?` only the query is shown; a bare expression that fails to parse also
searches as text below the note, so a name with an `=` in it still works.

## Quantity summaries

A text that starts with `count`, `sum`, `avg`, `min` or `max` gives a quantity summary instead of a list of elements. The
condition is the criteria language above, so `where` works the same way; the code is `src/query/aggregate.ts` (parsing and
arithmetic), `src/search/quantityMode.ts` (console report, script API), `src/ui/quantityHud.ts` (the card).

```
count where class like 'IfcWall%'
sum netsidearea where class like 'IfcWall%'
sum length, count where class = 'IfcPipeSegment' by storey
avg length, max length where class = 'IfcBeam'
sum volume by class
```

| Part | Meaning |
| --- | --- |
| `count` | The number of elements. |
| `sum`, `avg`, `min`, `max` + quantity | The total, mean, smallest or largest value of a quantity. `of` and brackets are allowed: `sum of length`, `sum(length)`. |
| `a, b` or `a and b` | Several aggregates at once: `sum length, count`. |
| `where <condition>` | Optional. Without it the summary covers every visible element (not hidden). With it, every matching element, hidden or not, as a plain query selects. |
| `by <column>` | Optional. Subtotals per storey, class, material or any column or property: `by storey`, `by class`, `by Pset_WallCommon.FireRating`. `level` means `storey`. |

A `?` in front is ignored. `sum banana` (a word that names nothing in the model) stays a plain text search; with `where`,
`by` or a comma it is a summary and an unknown quantity is an error.

**Quantity names.** The quantity is a column or property key, ignoring case and punctuation, and it is looked up per element,
so `length` reads `Qto_BeamBaseQuantities.Length` on a beam and `BaseQuantities.Length` on a wall. Aliases (first match wins
per element): `length` Length; `width`; `height`; `depth`; `thickness` Width or Depth; `perimeter`; `area` NetArea, GrossArea,
NetSideArea, GrossSideArea, NetFootprintArea ...; `volume` NetVolume, then GrossVolume; `weight` NetWeight, GrossWeight.
The last part of a key (`netsidearea`), a part of it (`sidearea`) and the whole key
(`Qto_WallBaseQuantities.NetVolume`) work too, and words join: `net side area`. Core numeric columns work (`sizeY`).
Keys on the samples:

| Sample | Quantity keys |
| --- | --- |
| fzk-haus (82) | `BaseQuantities.` Length (14), Width (34), Height (29), Perimeter (20), GrossArea (15), NetArea (4), GrossSideArea (13), NetSideArea (13), GrossVolume (18), NetVolume (18), CrossSectionArea, OuterSurfaceArea |
| synth5k (5000) | `Qto_BeamBaseQuantities.` and `Qto_ColumnBaseQuantities.` Length, NetVolume, CrossSectionArea; `Qto_DuctSegmentBaseQuantities.` Length, CrossSectionArea; `Qto_PipeSegmentBaseQuantities.Length`; `Qto_SlabBaseQuantities.` Length, Width, Depth, NetArea, NetVolume; `Qto_WallBaseQuantities.` Length, Height, Width, NetVolume |
| building (26) | `Qto_BeamBaseQuantities.` Length, NetVolume, CrossSectionArea; `Qto_SlabBaseQuantities.` Depth, NetArea, NetVolume; `Qto_WallBaseQuantities.` Length, Width, NetSideArea, NetVolume |

**Values.** A value must parse as a number (a number, or text that is only a number). Others are skipped, counted, and listed
with the reason on the console (`not a number ("tall")`, `yes/no value`, `not finite`).

**Estimates.** An element with no property for the quantity gets a geometric estimate when one exists, and the total says how
many (`(6 est.)`):

| Quantity | Estimate | None when |
| --- | --- | --- |
| `volume` | the mesh volume (signed tetrahedron sum) | the mesh is not a closed solid (the flags of `closedMesh.ts`) |
| `length` | the longest axis of the axis-aligned bounds | the element has no geometry |
| `height` | the vertical size of the bounds | the element has no geometry |
| `area` | the mesh surface divided by 2 | the element is not a closed thin plate (thinnest bounds side at most 0.3 of the middle one and 0.6 m) |

The plate estimate includes the narrow edge faces, so it reads a few percent high on a thick plate; the box estimate for a
slanted pipe reads low. Other quantities have no estimate. A present but non-numeric value is never estimated.

**Units.** Values are in the unit of the model (`SceneModel.units`, metres for every loader today) and shown as `m`, `m²`,
`m³` and `kg`. Rounding: 3 decimals below 1, 2 below 10, 1 below 1000, none from 1000, trailing zeros dropped
(`318.4 m`, `2 310 m`, `0.125 m³`).

**While typing** the query row shows the answer line, for example `13 wall standard cases` and, under it, the top groups.
**Enter** selects the elements (as a plain query does), frames them, writes the details to the console and shows the card.
**Shift+Enter** does the last two without changing the selection.

**Console.** One collapsed `console.groupCollapsed` per run, headed `[X-ray] <text> → <answer> (<ms>)`, holding a line per
aggregate, `console.table` of the elements (GlobalId, Name, Class, Storey, the `by` group, then the value and its source
property or `estimated` per quantity; the first 500), a subtotal table per group when `by` is used, and a table of the skipped
elements with the reason for each (the first 200).

**Quantity card.** A small translucent card (`backdrop-filter: blur`, light and dark) just under the top-bar search, for
example `42 pipe segments · Σ length 318.4 m (6 est.)`; with `by`, a second line with the top 3 groups and `+N more (console)`.
It stays while the pointer is on it, fades about 6 s after the last result, and goes on Escape or a click (a click also copies
the text). It is a reserved rect of the overlay while shown, so labels keep out of it. On a phone (700 px or less) it spans
the width under the bar. It is hidden in kiosk mode and during XR, like the bar.

Measured: `sum` over 100,000 rows (all numeric) 7 to 9 ms best of 5, 39 ms with a `where` and a `by` over the same rows
(`tests/quantity-summary.test.ts`); 5000-element sample, `sum volume, sum area, sum length` 4 ms.
Smoke test: `node bench/smoke-quantity.mjs` (port 5681).

## Keys and the palette

| Chord | Action | Notes |
| --- | --- | --- |
| `/`, `Ctrl+K`, `Meta+K` | `search.focus` | Focuses the box. On a phone it expands first. |
| `Ctrl+Shift+K`, `Meta+Shift+K` | `palette.open` | The full-screen command palette, kept. It used to be `Ctrl+K`. |
| `Alt+F` | `sidebar.filter` | Focus the model tree filter. It used to be `/`. |

The bar replaces the palette as the main entry point: it lists every command, with its keys, and reaches the panel controls
that the palette only ran or toggled. The old chords moved so the keymap has no conflict; rebind them in `Edit shortcuts`.
When the bar is hidden (kiosk, XR session) `/` and `Ctrl+K` do what they did before (tree filter, palette). Inside the box, `Ctrl+K`
selects the text.

## Index

`ElementIndex` (`src/search/elementIndex.ts`) is built once per model. Up to 20,000 elements it is built at once; larger models
in idle slices (`requestIdleCallback`, about 8 ms each) while the bar is already usable (the footer says `Indexing the model`).
It keeps lower-case copies of the name, class, GlobalId, storey and material per row, and chunk strings of 512 rows with every
field and property value. A query finds the rows that contain its rarest word with `indexOf` over the chunks, scores only
those rows, and keeps the best 200 in a bounded list; if few rows contain the word and it looks like an abbreviation, a second
pass adds subsequence matches on the name or class (a per-row letter mask rejects most rows at once). One letter matches the
start of a name or class only.

Measured on a synthetic 100,000-row model (8 properties per row; `tests/search-index.test.ts`, one run on the dev machine):
index build about 0.15 to 0.2 s; a query 1 to 15 ms (`wall` 7, `duct 5` 7, `level 12 beam` 10, `ifcdoor` 9, `rdct` 4,
an id such as `ref-4999` 8); a WHERE query over the same rows 4 to 9 ms.

## Phone and other modes

At 700 px width or less the bar is a search icon; tapping it expands the box over the full width (8 px margins) and the list
fits the screen. The bar is hidden in kiosk mode (`xray-pack --kiosk`) and while an XR session runs.

## Accessibility

The input has `role="combobox"` with `aria-expanded`, `aria-controls` and `aria-activedescendant`; the list is
`role="listbox"` with `role="option"` rows (`aria-selected`) and `role="presentation"` headers and notes. The footer is a
polite live region.

## Scripting

`window.__xraySearch` has `bar` (the `AwesomeBar`), `sources`, `state()` (open, query, active row, rows, notes, footer),
`indexReady()`, `hud` (the quantity card: `state()`, `showLines()`, `hide()`, `holdMs`) and `summarize(text)`. `bar.setQuery(text)` runs a search.
`summarize("sum length, count where class = 'IfcPipeSegment' by storey")` returns `{ rows, total, aggs, groups, skipped,
skippedCount, estimated, unit, matched, lines, ms }`: one row per element (`id`, `globalId`, `name`, `class`, `storey`, `group`,
`values` and `sources` by quantity), `total` the value of the first aggregate, `groups` with `key`, `count`, `total` and
`aggs`. It throws on a syntax error or an unknown quantity, and does not touch the selection, the console or the card. Smoke tests: `node bench/smoke-search.mjs` (port 5662), `node bench/smoke-quantity.mjs` (port 5681).
