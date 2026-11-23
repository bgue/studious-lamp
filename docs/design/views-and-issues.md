# Views and Issues: two nouns

Status: implemented in this branch. Replaces the three nouns saved view, sketch and issue.

## Model

- **View**: a captured moment (camera, section, selection, hides, isolate, explode, params snapshot, preset, thumbnail). A view MAY carry **drawings** (clouds, arrows, text, callouts, shapes, pen; attached to the model in 3D or view-locked). A page of a PDF sheet is a view too: its drawings are the sheet's drawings.
- **Issue** (a BCF topic): status, priority, assignee, due date, comments, history. It points at one or more views (its viewpoints). An issue is made FROM a view. BCF is only the exchange format.
- The UI says "view" and "drawings". It never says "sketch" or "markup" (exceptions: reading and writing older files, the glossary, the file format names).

## Storage: two stores, one list

Nothing is moved. The two stores stay, the Views tab presents them as one list.

| Old | Where it lives | New |
| --- | --- | --- |
| saved view | localStorage `xray.views.<model>`, `xray-views/1` | a view |
| sketch (markup set) | IndexedDB `xray-work`, `xray-markup-set/1` | the drawings of a view; a loose one is a view of its own |
| sheet sketch | sheets store | a view "on a sheet" |
| BCF viewpoint with `sketchId` | BCF topic | a view of the issue |

- A saved view gets one optional field, `drawings: <markup set id>`. It names the set that holds the drawings of the view (the set may hold none yet: it also backs a view that sits in an issue). Absent or dangling (the set is gone, another model): a plain view.
- `buildEntries` (`src/views/unified.ts`, pure) merges the saved views and the sets of the loaded model into one list of **entries**:
  1. every saved view, in its order (its set, if any, is folded into it);
  2. every set that no saved view claims (a **legacy sketch**, a sketch made from an opened BCF file, a sketch raised from a check): a view built from the sketch's own capture (`set.view`, `set.thumb`);
  3. sheet sets, flagged `sheet`.
  An entry knows its drawings count, the issue it is in (from the topics: `viewpoint.sketchId` is the truth, as before) and its filters: **All**, **With drawings**, **On sheets**, **In an issue**.
- A legacy sketch is not converted when the model loads. Nothing is written until the person acts on it. A sketch has no saved view, so it has no number, no reorder grip and no "Duplicate"; all the other actions work on the set directly.

## Migration

- Old files read as before: `xray-views/1` without `drawings`, `xray-markup-set/1`, BCF files, the work store. Older readers ignore `drawings`.
- Legacy sketches show up in the Views tab at the next start. Their comments and status (pre-issue data) keep the banner: "N views have comments or a status. Make issues of them?", which makes issues as before.
- The share link of a view and the `views` params section carry no `drawings` link (set ids mean nothing in another browser). The views JSON export keeps it; a dangling link reads as a plain view.

## What each control becomes

| Before | Now |
| --- | --- |
| Issues tab, segment `Issues` | Issues tab (no segments), issues only |
| Issues tab, segment `Sketches` | Views tab, filter `With drawings` |
| Issues tab, segment `Sheets` | Views tab, filter `On sheets` |
| New sketch | **Draw on this view** (row menu and detail of a view; the toolbar of the current view when none is selected) |
| Add current view as sketch (in an issue) | **Add current view** (issue detail): saves the current view into the issue |
| Raise as issue | **Make issue** (row menu, view detail): chooser `New issue` / `Add to: <issue>` |
| New issue (topic dialog) | **New issue** (Issues tab): captures the current view first, then the dialog |
| Save view (Views tab) | unchanged |
| Edit drawing | Edit drawings |
| Open sketch (issue detail) | Open in Views |
| Issue of a sketch: "Viewpoint of the issue" | "In issue: <title>" with Open issue |
| `Sketches` group in search | views are found by name and note; issues as before |
| Key `K` | opens the Views tab on `With drawings` |

## Scripting

`window.__xrayViews` gains `entries(filter?)`, `withDrawings()`, `drawOn(id)`, `makeIssue(id, { topic? })`, `filter`/`setFilter`, `open(filter?)`. `__xrayIssues`, `__xrayMarkup`, `__xrayBcf`, `__xraySheets` keep every method; `__xrayIssues.open('sketches' | 'sheets')` opens the Views tab on the matching filter, `newSketch` is `drawOn` of the current view.

## Left as it is

- Fly-through keyframes point at saved views; drawings are not drawn during playback.
- Viewpoints of an issue that have no set (a script created them, no drawing layer yet) show in the issue detail only, not in the Views list; "Edit drawings" gives them a set, then they list.
