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
  keys such as `e:<GlobalId>`, `a:<action id>`, `p:<preset id>`, `v:<view id>`, `s:<set name>`, `g:<folder>/<label>`).
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

`window.__xraySearch` has `bar` (the `AwesomeBar`), `sources`, `state()` (open, query, active row, rows, notes, footer) and
`indexReady()`. `bar.setQuery(text)` runs a search. Smoke test: `node bench/smoke-search.mjs` (port 5662).
