# 20. Comparing a new model version

The architect sends version 2 of the model on Thursday. You spent two weeks classifying and reviewing version 1. Most of the
8,000 elements did not change, yet nothing tells you which did. Starting over wastes the two weeks. Trusting version 2
blindly risks that a duct moved 30 mm into a beam and nobody saw it.

## 20.1 Start a revision walk

### The idea

A **revision walk** compares two versions of a model and takes you through only what changed. The **base** is the earlier model.
The **head** is the one on screen now. Elements that did not change keep your earlier decisions. Changed, new and deleted
elements come to you one at a time, with what changed written out.

Think of marking an exam paper a second time after the student corrected it. You do not re-read every answer. You look at the
lines that are different, and you keep your earlier ticks on the rest.

### Try it

The **Sample Projects** list has no pair of versions, but the source repository has one. Version 1 is `models/AC20-FZK-Haus.ifc`.
Version 2 is `web/tests/fixtures/ifc/fzk-v2.ifc`. It was made from version 1: a few elements moved, one turned, 4 deleted,
3 added, and 6 given new GlobalIds. `fzk-v2.truth.json` next to it lists every change. The viewer file and the packed pages do not
include version 2, so you need a checkout of the repository. For your own model, export two versions from your authoring tool.

1. Open version 1 with **Open IFC or glb file**. Classify it and review it (chapter 18). The viewer keeps a small snapshot in this browser after each classify
   run and each commit. The snapshot holds numbers, names, properties and results. It holds no geometry and no pictures.
2. Open version 2 the same way.
3. If it looks like a revision, a banner says: `This looks like a revision of <name> (saved <date>, <n> reviewed)`. The test is the same
   file name, 30 % or more of the same element ids, or a similar name with the same mix of classes.
4. Click **Review changes**. Nothing is carried over before you click.
5. If the banner is wrong, click **Not a revision**. If you want another base, click **Compare with...** and pick any stored model.
   You can also pick an IFC file that is read without being shown. It has no decisions, so you get the differences and the report only.

The command palette has the same actions: *Revision: review changes (walk)* (key `Shift+V`), *Revision: compare with an earlier
model...* and *Revision: export the report*.

### How it works

The viewer matches elements of the two versions by GlobalId first. Elements with a new GlobalId but nearly the same shape are
matched as **rematched**, which covers software that rewrites ids on export. For each element it then compares attributes, the
common property sets and base quantities, and the position and size. Only loaded properties are compared.

What happens to each kind of element:

| Element | Its result | Your earlier decision | In the walk |
| --- | --- | --- | --- |
| Unchanged | copied as it is | carried to the new model | not visited |
| Changed, classification not affected | copied as a suggestion | not carried | visited |
| Changed, classification affected | classified again; the earlier result is the suggestion | not carried | visited |
| Rematched (new id, same shape) | as above | carried after you accept the match | visited |
| New | classified now | none | visited |
| Deleted | none | stays in the earlier log | visited |

A different classification schema carries nothing over. You still get the differences and the report.

### Limits and gotchas

- The comparison sees only what the viewer loaded. A property the file has but the loader left out is invisible to it.
- A revision needs the earlier snapshot to be in this browser. If you cleared site data, use **Compare with...** and an IFC file.
- Classify and review version 1 before you open version 2. The walk can carry over only decisions that exist.

## 20.2 Walk only the changes

### The idea

The panel gives you one card per change. You say whether the change is expected and right (accept), wrong (reject), or not yours
to decide yet (skip). Alike changes are grouped: 40 columns that all moved 8 mm north are one item.

### Try it

1. After **Review changes**, a **Revision** tab opens in the right sidebar (it exists only while the walk is open).
2. Read the card: a progress count, a title with a badge (new, deleted, changed, rematched), and a **what changed** table, such
   as `moved 8 mm north-east` or `area -12 %, volume -9 %`, with property names and their before and after values.
   Beside it you see your earlier decision and the new proposal, and any issues and drawings attached to the element.
3. In the view, the new element is selected and framed. The earlier shape is a red ghost. A new element has a green frame, the head
   element of a change an amber one. `G` cycles both, head only, base only.
4. Press `Enter` or `Y` to accept. Press `R` to reject. Press `N` or the right arrow to skip. `2` accepts with the other
   classification, `E` lets you edit the classification and then accepts, and `?` marks the decision unsure.
5. Press `B`. A list of **bulk rules** shows how many elements each would settle: moves of up to 10 mm that touch only the
   placement, property changes that do not affect the classification, rematches scoring 0.95 or more, deletions with nothing
   attached, new elements settled by a rule. Point at a rule to select its elements. Apply it. A rule is one undo step.
6. When you are done, click **Commit**.

| Key | Action |
| --- | --- |
| `Enter`, `Y` | Accept |
| `2`, `E` | Accept with the other classification, or edit it |
| `R` | Reject: the change is wrong |
| `N`, right arrow; `Shift+N` | Skip; skip the rest of the item |
| left arrow, `[`, `]` | Back; step inside an item |
| `A`, `U`, `G`, `B`, `Esc` | All or one; undo; ghost; bulk; close |

### How it works

Accepting creates an ordinary pending change of the review log from chapter 18, so commit, undo, revert and export all work the
same way. **Commit** writes one commit, carries the earlier decisions of accepted matches, moves the issues and drawings of those
matches to the new GlobalId, and applies your choice for the attachments of deleted elements. The choice is on the card of a
deleted element that has issues or drawings attached (not on the Commit panel), and it is one of:

- **Keep, flagged** (default): a comment `element deleted in <model>` is added.
- **Re-attach to the selected element.**
- **Resolve issues.**

Nothing is deleted from anywhere.

**Reject** always writes a row in the report. It never opens an issue by itself. **Raise issue** does, with the element
GlobalIds as the components of the issue (chapter 15).

**Filters** limit the walk by kind, change, storey, class, undecided, unsure, skipped, with issues or drawings, and by minimum
move in millimetres. The millimetre and score boxes of the bulk rules are editable.

### Limits and gotchas

- If the earlier model is no longer on the page, the red ghost comes from meshes stored with the review (up to 64 MB), else it is
  only the earlier bounding box.
- Bulk rules apply to what is in the current filter. A rule that says "settle everything in the filter" does what it says. Read
  the count before you click.
- Rejecting a deletion records that the element should not be gone. Resolving that with the author is outside the viewer.

## 20.3 Resume, report, phone

### The idea

A revision with 400 changes does not fit in one sitting. The walk must survive a closed laptop, and the result must leave the
viewer in a form others can read.

### Try it

1. Decide a few items, then reload the page.
2. Open version 2 again. The banner says `Resume revision review of <name> (123 of 410 decided)`. Use it to resume.
3. The cursor returns to where you stopped. What you accepted and did not commit is proposed again.
4. In the walk, click **Report** (or use *Revision: export the report*). You get `revision-<base>-to-<head>.csv`, one row per
   changed element with the verdict, the classification used, who decided and when, and `...-summary.md`.
5. On a phone, the walk opens as the **Revision** tab, a bottom sheet. Accept, Reject, Skip and More are in a fixed grid. The
   what-changed table is a row of chips you tap. Swipe left to skip and right to go back. Bulk rules and filters sit under **More**.

### How it works

The session is saved 500 ms after each decision, skip or step, and when the page is hidden. Skips are kept. Resume keeps the
stored differences, puts the cursor back, and classifies only new or affected elements that have no result yet.

It is stored in the browser's database `xray-revisions`: snapshots (3 per file name, 300 MB in all, the oldest dropped first;
a snapshot of an open review is kept), sessions and ghost meshes. It is not in settings, presets, views, links or packed pages.

After a walk, **Save IFC** (see 19.3) can write the result into the new file. Each element of version 2 gets
`RevisionStatus` (new, changed, rematched or unchanged) and `RevisionBaseline` (the name of the base). Deleted elements are not in
the new file, so they appear in the report only.

### Limits and gotchas

- Without browser storage the walk lasts for this page only, and the panel says so.
- The report holds reviewer names, as the review log does, because you exported it. Check who will read it.
- Only three snapshots per file name are kept. A fourth version replaces the oldest.

### See also

Chapter 18 (review log and walk), 19.3 (writing `RevisionStatus` into the IFC), chapter 15 (raising issues).
