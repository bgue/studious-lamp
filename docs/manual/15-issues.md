# 15. Issues

## 15.0 The problem

A clash is found on Monday. On Wednesday three people believe someone else has dealt with it. On Friday it is still there. A
picture of the clash, even a good one with a red cloud on it, does not fix this. Nobody owns a picture. What is missing is a
name next to the problem, a state ("open", "resolved"), a date and a place to talk.

## 15.1 When something needs an owner: make an issue from a view

**The idea.** An **issue** is a problem someone must act on. It has a status, a priority, an assignee, a due date, comments and
a history. It does not hold the picture itself. It *points at* one or more views (chapter 13). A view says "look here". An
issue says "and someone must do something about it".

This split has a use. A view can exist alone, with no owner, as a bookmark or a note. An issue is always made *from* a view, so
it always has a place to look at. Several issues can sit on several views. One view belongs to at most one issue.

Two quick ways to start:

- On a view: **Make issue** (in the row menu **⋯** or in the view detail).
- In the **Issues** tab: **New issue**. It captures the current view first, saves it in the Views list, and then opens the
  dialog.

**Try it.** Use the **FZK-Haus** sample. Do 14.1 first, so that a view with drawings exists.

1. Open the **Views** tab. Click the row of your view with drawings. Its detail opens.
2. In the detail, a list beside the button **Make issue** offers **New issue** and **Add to: <issue>** for each issue that already
   exists. Leave **New issue** chosen and click **Make issue**.
3. The viewer restores the view, makes the issue from the view's title and note with status **Open**, and takes a snapshot.
   The view's row now has the tag `Issue`, and its detail says `In issue: <title>` with **Open issue**.
4. Open the **Issues** tab. Your issue is in the list with status, priority, the number of views, comments and assignee. The
   status bar shows `1 open issues`.
5. Click the issue. Its detail opens in the same column, and the first view comes back (camera, selection, hides, colours, cut
   planes). **Clear** undoes what applying the view changed. `‹ Issues` goes back to the list.
6. Back in the Views tab, click **In an issue** to list the views that issues point at.

Now try the other direction: select a different element, then in the Issues tab click **New issue**. The dialog is headed
**New issue**. Fill **Title** and **Description**. Pick **Type**,
**Status** and **Priority**. Add **Labels** and **Assigned to**. **Author** is remembered. Two options sit below:
**Attach a snapshot of the current view**, on by default, and **Click the model to place the pin (else: middle of the
selection)**. Click **Create issue**. You get a second issue with its own view.

> Picture (issues-tab): the Issues tab with two issues. The first is open with its snapshot, the drawing burned in, and the views block under it.

## 15.2 Status, priority, assignee, due date, comments, history

An issue's detail has, from top to bottom:

- A snapshot with the drawings burned in.
- **Status** and **Priority** lists. Statuses are **Open**, **In Progress**, **Resolved** and **Closed**. Priorities are
  **Low**, **Normal**, **High** and **Critical**. A BCF file you opened may add its own words, and they show too.
- **Assignee** and **Due date**.
- **The views of the issue**: one row per view with a thumbnail and the buttons **Apply**, **Clear**, **Edit drawings** and
  **Open in Views**. Where a view is tied to the model, the **3D · Plan · Section** switch sits under it (13.3).
- **Add current view**: saves what you see now as a view and adds it to this issue. Use it when the problem looks different
  from another side.
- **Place pin** and **Remove pin**. A pin is a numbered marker on the model. Click **Place pin**, then click the model. The
  number belongs to the issue, and it never changes when other issues are removed or the list is filtered. Behind geometry the
  pin fades and gets a dashed rim. Off screen it becomes a marker at the edge of the view.
- The **comments** with **Add comment**. The author is the name in the **Author** box, which the viewer remembers.
- **History**: created, each comment, last change.
- **Export BCF 2.1**, **Export BCF 3.0** and **Delete issue** (chapter 17).

**List and search.** The list has a search box and the chips **All**, **Open** and **Closed**, each with a count. Search
matches title, description, assignee, labels and comment text. The top-bar search also finds issues (every word must match; a
title hit ranks above a description hit, which ranks above a comment hit) and finds views by name in a section of their own.
`Enter` opens the issue and brings its view back.

**Status bar.** `N open issues` counts the issues of the loaded model that are not resolved, closed, done, solved, completed,
rejected, cancelled, fixed or verified. Click it to open the Issues tab on the **Open** chip.

**On a phone.** The Issues tab is a bottom sheet. It steps aside while you draw and returns on **Done**. The cross closes it.

**Other models.** Every issue belongs to the model it was made on. Issues of another model are hidden under **Other models
(n)** below the list, with **Open**, **Move to this model** (the issue and its views) and **Delete issue**. If the model is a
newer revision of the same file name, the issue is listed with the tag `revised model`, and drawings that can no longer sit on
their elements are flagged as detached (14.2).

## 15.3 Issues from checks: penetrations and clearance, deduplicated

**The problem.** The penetration check lists 140 places where pipes cross walls with no opening. You do not want to type 140
issues. And on Thursday you run the check again after a fix, and you do not want 140 new ones.

**The idea.** Both the **Penetrations** drawer (chapter 11) and the **Clearance** results (chapter 10) have an **Issues**
block with **Raise issues from results**. Each result becomes one issue. The viewer remembers which result an issue came from,
by the type of the check plus the sorted pair of GlobalIds. A second run raises only the results that have no issue yet.

**What an issue from a check contains.**

- A title such as `Penetration: Duct-12 through Wall-3` or `Clearance 120 mm < 300 mm: Pipe-4 / Beam-9`.
- Type `Clash`, and the labels `clash` and `penetration` or `clearance`.
- A priority from the severity. For penetrations: no opening, or one that is too small, is High. Unknown is Normal. A fitting
  opening is Low. For clearance: touching is High.
- The two elements as the selection. The camera frames the pair, with a pin and a snapshot.
- A view with a drawing tied to the pair: a rectangle around the region. Because it is tied, the issue gets the
  **3D · Plan · Section** switch and a Plan and Section in the report.

**Which rows.** Penetrations: the selected rows, else the filtered rows of the table. Clearance: every clashing or tight pair of
the last run (the clearance colouring must be on, with a focus).

The block shows three counts: new, already raised, and not found in the latest run.

**Results that disappear.** After a fix, a pair may no longer be reported. The viewer never deletes its issue. It adds one
comment, `Not found in latest run`. **Close n not found** then sets the status of those still open to **Closed**. If the pair
comes back, the issue gets `Found again in the latest run`. A pair is only judged "not found" when the run could have found it:
a different focus or scope says nothing about it.

**Batch limit.** Above 200 new results the block asks first: **Raise top 200 by severity**, **Raise all n** or **Cancel**. While
it works it shows `Raising issues d / n` and a **Stop** button.

## 15.4 Reports: PDF and CSV for a meeting

At the bottom of the Issues list, the collapsed block **Export report** has **Page size** (A4 or Letter, portrait) and
**Plan/Section images** (on by default), and two buttons: **PDF report (n)** and **CSV (n)**. The number is how many issues the
report holds. The report follows the list as it is filtered now: the status chip, the search, and the loaded model. Issues of
other models are left out. The cover says which filter it was made with.

**PDF.**

- **Cover**: model and project name, date and author, the filter, counts (total, open, closed, and a bar for each status) and a
  table of issues. Each row links to the issue's page.
- **One page per issue**: title, status, priority, type, assignee, due date, labels, created and changed (with authors),
  description, the views (the snapshot with drawings burned in), the target elements (the first 24, then a count), and the
  comments with author names and dates. A long thread continues on further pages. The footer says `Page n of N`.
- **Plan and Section** beside the snapshot, for an issue whose view is tied to the model. They are rendered on the live canvas
  and then your camera, cut, hides and look are put back. With the option off, nothing is switched.

**CSV.** One file, one row per issue, with a **Comments** column holding every comment as `author (date): text` and a **Comment
count**. A spreadsheet opens one file as it is, and a second file of comments would have to be joined by hand. The file is UTF-8
with a byte order mark so that umlauts read right. Text that starts with `=`, `+`, `-` or `@` gets a leading apostrophe, so a
spreadsheet cannot run it as a formula.

File names are `xray-issues-<model>-<yyyymmdd-hhmm>.pdf` and `.csv`.

The reports carry comment authors on purpose: you export the file to hand it on. Names never go into share links, presets,
parameters or packed pages.

## 15.5 Older files

Drawing sets from before the two-noun change could carry comments, a resolved flag, an assignee and a due date. A view has none
of those now, and nothing is lost. If the loaded model has such sets, the Views tab shows a banner: "N views have comments or a
status. Make issues of them?" **Yes, make issues** makes one issue for each. It takes the view's title, the note as the
description, status **Open** (if any drawing was open) or **Resolved**, the first assignee, the earliest due date, and each comment as an
issue comment with its original author and date. **Not now** hides the banner for the session. Until you convert them, the old
comments show read-only on the view under "Earlier comments and status".

## 15.6 Choices and limits

- **One view, at most one issue.** Making an issue of a view that is already in one is refused. Open that issue, or use **Add
  current view** inside it.
- **Not a copy.** The issue's picture is built from the view. Edit a drawing and the issue follows, in its snapshot and in the
  next export. **Update view** captures the issue's view again.
- **Removing a view that is in an issue asks first.** The issue keeps the camera view and loses the drawings. Deleting an issue
  leaves its views as loose views.
- In the detail you can change status, priority, assignee and due date, and add comments. The detail has no box for the title or the description of an existing issue, so write them well when you make the issue.
- Drawings and issues are kept in this browser, per model. Without IndexedDB (a private window) nothing is kept.

## 15.7 See also

Chapter 13 (views), chapter 14 (drawings), chapter 17 (BCF files), chapters 10 and 11 (the checks that raise issues).
