# Right sidebar

A tabbed column at the right edge of the window that mirrors the model tree on the left: a collapse chevron, a 28 px rail when
folded, the state kept in `localStorage`. It is the element `#dock` (`src/ui/rightSidebar.ts`, `src/plugins/rightSidebar.ts`).

| Tab | Holds | Moved from |
| --- | --- | --- |
| **Properties** | The properties of the selected element: GlobalId (with **Copy GlobalId**), class, name, storey, material, x-ray state, and the collapsible list of every property set and quantity, with the `⋯` menu and the right-click menu (select all with this value, copy, save as criteria set) | the foot of the left sidebar |
| **Classification** | The classify panel (provider, settings, results, calibration, schema), the **selected element** card with Accept, Change and Unsure, and the **review walk** ([classify.md](classify.md)) | the Classify drawer of the tool strip |
| **Revision** (only while a revision walk is open) | The revision walk ([revision.md](revision.md)): it is added when the walk opens, at 420 px, and taken away when the walk closes | a floating panel at the bottom left |
| **Script** | The animation script editor: code with line numbers, live errors, Run / Pause / Stop, examples, saved scripts per model, `.xrayanim` export and import ([animation-script.md](animation-script.md)). Added at 420 px, order 40 | (new) |
| **Parameters** | The lil-gui "X-ray parameters" panel with all its folders | a floating panel in the same column (it was already docked at the right) |

The left sidebar keeps Model, Sets, Views and Issues and gives the freed height to them.

## Behaviour

- **Fold.** The chevron at the top left of the column, the key `]` (action `panel.right`) or a click on the vertical label of the rail. The state is
  `localStorage["xray.dock"] = {"collapsed": bool, "tab": id}`; `index.html` applies it before the first paint. A phone starts folded.
- **Width.** 300 px; the Classification tab asks for 420 px while it is shown (its tables and the walk need it). The column is not draggable (the left one is not either).
- **Tabs** scroll sideways when there are more than fit. A stored tab that no feature registered falls back to Properties.
- **Properties** follow the selection (the first selected element; "+ N more selected" for a multi-selection) and refresh four times a second. The hover card and the `all properties in sidebar` and `property filter` settings of the Hover info folder
  ([hover-info.md](hover-info.md)) drive the list.
- **Parameters.** Search (`/`) and the command palette (`Ctrl+Shift+K`) open the Parameters tab when they jump to a control. The lil-gui panel keeps its own title bar (it opens and closes the folder list).
- **Classification.** `tool.classify`, the strip button, `window.__xrayToolbar.open('classify')` and `boot.openTool: "classify"` open the tab.

## Phone (360 px)

The column is a **bottom sheet** with the same tabs: folded it is the 28 px rail at the right edge (below the top bar); open it rises from the bottom edge, above the status bar,
58 % of the height at most (440 px), with rounded top corners. The left sidebar, the Issues sheet and this sheet are **never open together**: opening one folds the others (the
automatic fold is not stored, so the wide-screen choice survives). The sheet is registered with the overlay (`ov.reserve('right-sidebar')`), so labels, markers, the gizmo and the
drawing toolbar keep clear of it; on a wide screen the column sits beside the canvas and the overlay's edge insets already count it (`#dock` is one of the edge chrome elements).

## Adding a tab (the integration point)

```ts
import { addRightSidebarTab } from '../plugins/rightSidebar';      // or window.__xrayRightSidebar.addTab(spec)

const tab = addRightSidebarTab({
  id: 'revision',                 // unique; an existing id returns the existing handle
  label: 'Revision',              // the text of the tab button
  order: 40,                      // optional sort key; built-in: Properties 10, Classification 20, Parameters 30; default 100
  width: 360,                     // optional preferred width in px while shown (default 300)
  title: 'Confirm the revision',  // optional tooltip
  helpKey: 'Right sidebar/Revision tab', // optional data-help-key of the button
  mount(pane, ctx) {              // runs once, on the first show; `pane` is an empty flex-column <div>
    pane.append(myContent());
    ctx.onVisible((on) => { if (on) refresh(); });   // shown or hidden (also when the sidebar folds or opens)
    ctx.setBadge('3');            // a short mark on the tab button; '' removes it
    return () => cleanup();       // optional: runs when the tab is removed
  },
});
tab.show();      // open the sidebar when folded and switch to the tab
tab.visible();   // the sidebar is open on this tab
tab.setBadge('3');
tab.remove();    // take the tab away
```

`addRightSidebarTab` works before the sidebar is built (plugins install in order; the spec is queued) and after. Types: `RightTabSpec`, `RightTabHandle`, `RightTabContext` in `src/ui/rightSidebar.ts`
(the contract is documented at the top of that file).

## Scripting

`window.__xrayRightSidebar`: `addTab(spec)`, `open(id)` (expands and switches; false for an unknown id), `close()`, `toggle()`, `tabs()` (ids in order) and `state()`
(`{ collapsed, tab, phone }`). Actions: `panel.right` (key `]`), `panel.left` (key `[`).

## Tests

`bench/smoke-right-sidebar.mjs` (SMOKE_PORT) covers the tabs, the properties following the selection, the Classification tab opened by `tool.classify` with the selected element's result, the Parameters tab, the persisted fold,
the phone sheet, the `addTab` API and the console. It writes `bench/right-sidebar.png` and `bench/right-sidebar-phone.png`. `bench/smoke-dock.mjs` checks the fold and the layout.
