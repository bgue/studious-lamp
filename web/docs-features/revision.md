# Revision walk

A second version of a model arrives. The revision walk compares it with the first, carries over what you already decided, and takes you through only what changed.

Words: **base** is the earlier model, **head** is the one on screen now.

## Starting

1. Load the first model, classify it, review it. The viewer keeps a small snapshot of it in this browser after each classify run and each commit. The snapshot is geometry numbers, names, properties and results. It holds no geometry and no pictures.
2. Load the second model. If it looks like a revision, a banner says so: `This looks like a revision of <name> (saved <date>, <n> reviewed)`. The test is the same file name, a share of the same element ids (30 % or more), or a similar name and the same mix of classes.
3. Click **Review changes**. Nothing is carried over before you click. **Not a revision** hides the banner. **Compare with…** lets you pick any stored model, or an IFC file that is read without being shown (it has no decisions, so you get the differences and the report only).

The palette actions are `Revision: review changes (walk)` (`Shift+V`), `Revision: compare with an earlier model…` and `Revision: export the report`.

## What carries over

| Element | Result | Your earlier decision | In the walk |
|---|---|---|---|
| Unchanged | copied as it is | carried to the new model | not visited |
| Changed, classification not affected | copied as a suggestion | not carried | visited |
| Changed, classification affected | classified again; the earlier result is the suggestion | not carried | visited |
| Rematched (new GlobalId, same shape) | as above | carried after you accept the match | visited |
| New | classified now | none | visited |
| Deleted | none | stays in the earlier log | visited |

Only loaded properties are compared (attributes, common property sets, base quantities). A different classification schema carries nothing: you still get the differences and the report.

## The panel

One card per change: progress, the title with a badge (new, deleted, changed, rematched), the **what changed** table (`moved 8 mm north-east`, `area -12 %, volume -9 %`, property keys with before and after, at most 8 then `n more`), the earlier decision beside the new proposal, the issues and sketches attached, and the buttons. Alike changes (same kind, class, storey, flags and, for moves, the same vector to 1 mm) are one item: `A` switches between all of them and one.

In the view the new element is selected and framed. The earlier shape is a red ghost, a new element has a green frame, the head element of a change an amber frame. `G` cycles both, head only, base only. When the earlier model is no longer in the page, the ghost comes from meshes stored with the review, else it is the earlier bounding box.

| Key | Action |
|---|---|
| `Enter`, `Y` | Accept. A changed element takes the earlier classification when it is not affected or the proposal equals it, else the new proposal. A deleted one is acknowledged. |
| `2` | Accept with the other classification |
| `E` | Edit the classification, then accept |
| `R` | Reject: this change is wrong (a deletion: should not be gone; a new element: should not be here; a match: not the same element) |
| `N`, right arrow | Skip. `Shift+N` skips the rest of the item |
| `?` | Mark the decision unsure |
| left arrow, `[`, `]` | Back, step inside an item |
| `A`, `U`, `G`, `B`, `Esc` | All or one, undo, ghost, bulk, close |

Accepting creates a normal pending change of the review log, so commit, undo, revert and export all apply. **Commit** writes the pending changes as one commit, carries the earlier decisions of accepted matches, moves their issues and sketches to the new GlobalId, and applies your choice for the attachments of deleted elements: **Keep, flagged** (default: a comment `element deleted in <model>`), **Re-attach to the selected element**, or **Resolve issues**. Nothing is deleted.

**Reject** always writes a report row. It never opens an issue by itself. The button **Raise issue** does, with the element GlobalIds as components.

## Bulk, filters, report

`B` (or **More** on a phone) lists rules with their count: placement-only moves up to `10` mm, property-only changes that do not affect the classification, rematches with a score of `0.95` or more, deletions with nothing attached, new elements classified by a rule and not needing review, everything in the current filter. Point at a rule to select its elements. A rule is one undo step. The millimetre and score boxes are editable.

**Filters** limit the walk by kind, change, storey, class, undecided, unsure, skipped, with issues or sketches, and moves of at least some millimetres. **Report** exports `revision-<base>-to-<head>.csv` (one row per changed element with the verdict, the classification used, who decided and when) and `…-summary.md`. The names of reviewers are in this file, as in the review log export, because you exported it.

## Phone

Up to 640 px wide, or with a touch screen, the panel is a bottom sheet of 45 % of the height. Drag the handle to 85 %. Accept, Reject, Skip and More are in a fixed grid. The table is a row of chips that open when tapped. Swipe left to skip, right to go back. Bulk rules and filters are under **More**. No key is needed.

## Reload and resume

The session is saved 500 ms after each decision, skip or step, and when the page is hidden. Skips are kept. Reload, open the second file again and the banner says `Resume revision review of <name> (123 of 410 decided)`. Resume keeps the stored differences, puts the cursor back, proposes again what you accepted and did not commit, and classifies only new or affected elements that have no result. Without browser storage the walk is kept for this page only, and the panel says so.

## Storage and privacy

IndexedDB database `xray-revisions`: snapshots (3 per file name, 300 MB in all, oldest first; a snapshot of an open review is kept), sessions, and the ghost meshes (up to 64 MB). Nothing is in the settings, a preset, a view, a link or a packed page. The reviewer name stays in this browser as in the review walk.

## Saving into the IFC

`revisionStatusMap(session, headGlobalIds)` (`src/revision/status.ts`) gives the Save IFC plan its `extra.revision`: `new`, `changed`, `rematched` or `unchanged` for each element of the new model, and the name of the base for `RevisionBaseline`. `window.__xrayRevision.status()` returns it. Deleted elements are not in the new file, so they are in the report only.

## Scripting

`window.__xrayRevision`: `candidates()`, `snapshots()`, `start(baseKey)`, `resume()`, `state()`, `decide(key, verdict)`, `bulk(ruleId)`, `report()`, `items()`, `commit(note)`, `status()`, `snapshotNow()`, and `walk` (`open`, `close`, `state`, `goto`).

Code: `src/revision/` (pure core and `controller.ts`, `ghost.ts`, `attachHost.ts`, `capture.ts`, `card.ts`, `status.ts`), `src/plugins/revision.ts` (banner, actions), `src/plugins/revisionWalk.ts` (panel), `src/ui/panelHost.ts` (where the panel sits). Design: `docs/design/ifc-save-and-revision.md`. Smoke test: `bench/smoke-ifc-save-revision.mjs`.
