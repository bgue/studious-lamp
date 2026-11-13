# Issues and sketches

BCF is the container and the markup drawing engine is the drawing layer. There is one drawing system (clouds, arrows, text, callouts, shapes and pen, attached to the model in 3D or view-locked), and two things are built on it:

- **Sketches** (formerly markup sets): a saved view, its drawings and an optional one-line note. They keep the 2D markup view and the PDF report. They have **no status and no comment thread**.
- **Issues** (BCF topics): status, priority, assignee, due date, comments, history. **An issue's viewpoints are sketches.** Raising a sketch as an issue makes an issue (or adds the sketch to an existing one) whose viewpoint links to the sketch by id, not a copy.

Where: the sidebar tab **Issues** (after Model, Sets and Views) with the switch `Issues · Sketches`; the drawing toolbar floats over the view while a sketch is edited; the status bar says `N open issues`; the top-bar search finds issues and sketches. Scripting: `window.__xrayIssues` (panel, links, search, migration), `window.__xrayBcf` (issues as BCF data), `window.__xrayMarkup` (sketches). Code: `src/issues/` (`link.ts` and `search.ts` pure, `controller.ts`, `ui.ts`), `src/plugins/issues.ts`, `src/markup/toolbar.ts`. See [markup.md](markup.md) for the drawing engine and the PDF, [bcf.md](bcf.md) for the file formats.

## The panel

`Issues` segment: `New issue` (the old topic dialog), `Open BCF`, a search box, the chips `All / Open / Closed` (with counts), and the list of the loaded model's issues with status, priority, number of sketches, comments and assignee. `Other models (n)` lists the issues made on another model, hidden and not drawn, with `Open`, `Move to this model` (the issue and its sketches) and `Delete issue`, as before ([markup.md](markup.md), "Which model an item belongs to"). Clicking an issue opens its detail in the same column and applies the view of its first viewpoint the BCF way (camera, selection, hides, colours, clip planes; `Clear` undoes it); the sketch of the applied viewpoint is drawn next to the active sketch (`MarkupController.companion`), so applying a viewpoint from a script or a link shows its drawing too; `‹ Issues` goes back.

The issue detail: snapshot with the drawing burned in, status and priority lists, assignee, due date, the sketches (one row per viewpoint: `Apply`, `Clear`, `Edit drawing`, `Open sketch`; `Edit drawing` on a viewpoint without a drawing makes its sketch, linked to the issue), `Add current view as sketch`, `Place pin` / `Remove pin`, the comments with `Add comment`, the history (created, each comment, last change), and `Export BCF 2.1` / `Export BCF 3.0` / `Delete issue`.

`Sketches` segment: `New sketch` (saves the current view and starts drawing), `Open file` (a sketch PDF or JSON), a search box (title and note), cards with thumbnails, and `Other models (n)`. The card of a sketch that belongs to an issue says `Issue: <title>`. The sketch detail: thumbnail, title, note, `Raise as issue` (a list picks `New issue` or `Add to: <issue>`), `Edit drawing`, `Restore view`, `Update view`, `Export PDF`, `Export JSON`, page size and picture quality for the PDF, `Delete sketch`, and the list of drawings (number, kind, text, the attachment chip of the selected one). A sketch that belongs to an issue shows `Viewpoint of the issue <title>` with `Open issue`: the link shows from both sides.

Phone (up to 700 px wide): the sidebar collapses and the panel is a **bottom sheet** (like the classification review walk). It steps aside while a sketch is edited and comes back on `Done`; the cross closes it, `N open issues` in the status bar opens it.

## The drawing toolbar

A small floating bar, shown only while a sketch or an issue's viewpoint is edited (`window.__xrayMarkup.editing`; `Edit drawing`, `New sketch` or choosing a tool in a script start it, `Done` ends it). It has all the tools of the markup tool (select, cloud, cloud draw, callout, text, pointer, marker, highlight box, rectangle, ellipse, line, arrow, polyline, polygon, pen), the colours, the line weights, `Fill`, the text of the next callout, `Undo` and `Redo` of the sketch's markup history, `Finish` for a polyline in progress and `Done`. It sits bottom centre inside the edge chrome and moves aside or up where another reserved rect is (the gizmo, legends), through the shared overlay reserve API (`ov.reserve('markup-float', ...)`, `toolbarSpot` in `src/markup/toolbar.ts`); it never covers the gizmo or the top bar, and wraps to fit 390 px.

The global undo stack skips while the toolbar is active (`markupHasKeys` in `src/plugins/undo.ts` checks `editing`). Pointer modes Arrow and Hand keep working: a drawing tool takes the left button, other buttons still orbit and pan. Keys while editing: `Ctrl+Z`, `Ctrl+Shift+Z`, `Delete`, `Escape` (cancel the drawing, then back to select, then deselect).

## Raise as issue, and how the link works

`Raise as issue` (button, `window.__xrayIssues.raise(sketchId, { topic? })`, or `window.__xrayMarkup.toBcf(sketchId)`): the sketch's view is restored, the issue is made from the title and note (status `Open`), the viewpoint captures the camera, selection, hides, colours, clip planes and a snapshot, and the viewpoint gets `sketchId`; the sketch gets `issue: { topic, viewpoint }`. With `topic` the sketch is added to that issue as one more viewpoint.

- **One sketch, at most one issue.** Raising a sketch that already belongs to an issue is refused (`linkSketch` in `src/issues/link.ts`); open that issue instead.
- **Not a copy.** The viewpoint's drawing (`annotations`) is a projection of the sketch, rebuilt by `syncViewpoint` after every sketch change and again before every export. Shape points are fractions of the sketch camera and the viewpoint's snapshot camera is set to that same camera, so they copy over without projecting; clouds are closed, ellipses become polygons and arrows get a head. Elements that the drawing points at join the viewpoint selection (other BCF tools highlight them), as before.
- **Editing updates the issue.** Draw, move, delete, retype, undo or change an attachment: the issue's drawing follows, and `composeSnapshot` and the BCF export burn and serialise the current drawing. `Update view` on a sketch captures the issue viewpoint again from the same live view. While a viewpoint belongs to a sketch the BCF overlay draws no annotations of it (the markup view draws the sketch), so nothing is drawn twice.
- **Removing a sketch that belongs to an issue asks first** (a confirmation box in the panel, `removeSketch(id)` returns `confirm` until called with `confirmed`). The issue keeps the camera view and loses that drawing. Deleting an issue leaves its sketches as loose sketches.
- Links are repaired when topics change (`reconcileLinks`): the viewpoint's `sketchId` is the truth, `set.issue` the mirror.

## BCF import

Opening a BCF file keeps working as before (2.0, 2.1, 3.0; the side file, Lines and Components). Every viewpoint with annotations and a camera that can carry shapes becomes a **sketch linked to its issue** (`sketchFromViewpoint`): the markups are made from the annotations (callout, note, arrow, measurement callout, rectangle, freehand line as pen), numbered in order, the sketch camera is the snapshot camera, the view holds only that camera, and restoring the sketch applies the BCF viewpoint (`fromViewpoint`). A viewpoint whose drawing cannot become markup (a foreign line set without a shape) keeps its drawing as it is, drawn by the BCF overlay, and gets no sketch. The same happens to annotations added through `window.__xrayBcf.addAnnotation` and `addShape` on a viewpoint that has none yet; on a viewpoint that already is a sketch these calls (and `updateAnnotation`, `removeAnnotation`) go through the sketch (`BcfController.linked`), so a script never loses an annotation to the next projection. Until the sketch changes, the drawing of an imported viewpoint stays exactly as the file had it (no relabelling). The session link (`sketchId`, `issue`) is not written to the BCF file; the file stores the derived annotations in the side file, so re-opening an export makes the sketches again.

## Migration of old markup sets

Old sets kept review data on their markups: a comment thread, a resolved status, an assignee, a due date. Sketches have none of these any more, and nothing is lost:

- Sets with comments or a non-default status show a banner in the Sketches segment: **"N sketches have comments or a status. Raise them as issues?"** (singular: "1 sketch has comments or a status. Raise it as an issue?"). `Yes, raise them` converts each set into an issue that links to the sketch (`migrateLegacy`): title of the sketch, the note (or a generated line) as description, status `Open` when any markup was open and `Resolved` otherwise, the first assignee, the earliest due date, and every comment as an issue comment (`"<markup number>. <text>"`, original author and date, oldest first). The comments and status are then removed from the sketch. `Not now` hides the banner for the session.
- Until converted, the legacy comments and status stay in the data and show read-only on the sketch ("Earlier comments and status") and in search.
- Opening an old markup JSON (or a PDF that carries one) works as before and shows the same banner.
- `window.__xrayMarkup.comment` and the status, assignee and due fields of `update` and `add` no longer change a sketch (`comment` returns false); the data of old documents is still read and written.

## Search and status bar

The top-bar search has a section **Issues and sketches** ([search.md](search.md)): title, note or description, and comment text (also the legacy comments of sketches), every word must match, a title hit ranks above a note or description hit above a comment hit; the row says which field matched. Enter opens the tab on the item and brings its view back. `searchIssues` in `src/issues/search.ts` is pure.

The status bar shows `N open issues` (issues of the loaded model whose status is not resolved, closed, done, solved, completed, rejected, cancelled, fixed or verified; `isOpenStatus`). Clicking it opens the tab on the Issues segment with the `Open` chip.

## Keys, commands and ids

`K` (action `markup.toggle`) opens the tab on the Sketches segment. `tool.markup` and `tool.bcf` are kept as aliases (Sketches and Issues segment); `markup.new`, `markup.open`, `markup.pdf`, `markup.json`, `bcf.open`, `bcf.create`, `bcf.export`, `bcf.clear` work as before (the ones that used to need a drawer open the tab first). New: `issues.open`, `issues.sketches`, `issues.edit` (toolbar for the active sketch), `issues.done`. A packaged page whose boot config says `openTool: "bcf"` or `"markup"` (or lists them in `tools`) opens the tab.

## File formats

Additive only. The markup document stays `xray-markup-set/1`: a set may carry `note`, `issue` (`{ topic, viewpoint }`) and `fromViewpoint`; older readers ignore them and old documents read as before (comments, status, assignee, due keep reading and writing). The BCF side file is unchanged. The PDF report and its attached JSON are unchanged (the table still lists legacy status and comments of a set that has them). Names, e-mail addresses and pictures of people stay out of params, share links, saved views, presets and packed pages (the leak test); the author text of sketches and issues lives in the markup JSON and the BCF file only, as before.

## Tests

Unit: `tests/issues-link.test.ts` (linking, projection of the drawing, BCF import into sketches, migration, formats), `tests/issues-search.test.ts`. Smokes (one at a time): `bench/smoke-issues.mjs` (SMOKE_PORT=5710: tab and segments, toolbar, raise and edit, status bar, search, banner, phone; screenshots `bench/issues-panel.png`, `issues-sketch-toolbar.png`, `issues-phone.png`), and the updated `smoke-markup.mjs`, `smoke-bcf.mjs`, `smoke-bcf-markup.mjs`, `smoke-markup-attach.mjs`, `smoke-markup-scope.mjs`.
