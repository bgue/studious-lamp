---
name: tui-layout
description: Layout rules for Throughline's terminal screens (logs, record screens, detail panels, forms) - information hierarchy, grouping, property:value lines, column choice, sections, empty values, width behaviour. Load it before designing, building or reviewing any TUI screen or panel, and when a ticket changes what a screen shows. Applies on top of the "Log screens" and "Plain and technical display" standards in packages/tl-tui/README.md.
---

# TUI layout

A screen is read in two passes: a glance that must answer *where am I, what is this, what state is it in, what can I
do*, and a second pass for detail. Design for the glance first. Everything below follows from four principles.

1. **Hierarchy.** One thing is most important on each screen; it is first, and it looks first. Identity
   (number and subject) outranks state, state outranks dates and people, those outrank extended properties.
2. **Grouping.** Things that belong together sit together, under a name, and apart from other groups (proximity and
   common region). A reader should never have to work out where one topic ends and the next begins.
3. **Consistency.** The same kind of information is in the same place, with the same label and the same format, on
   every screen. A person learns the layout once.
4. **Progressive disclosure.** Show what most people need on most visits; put the rest one key away (a tab, a
   section toggle, technical mode). The list shows enough to choose; the panel enough to decide; the record screen
   everything.

## Identity: the only implicit fields

- The **number and subject/title** form the heading of a panel or record screen, on one line: `P123-RFI-0328 ·
  Conflict in piling/utilities at AZ203`. They carry no label because the heading position names them.
- The **state** follows directly, as a short badge-like phrase (`Awaiting response`), optionally with the time in
  that state (`since 2026-10-13`). It is the second thing read.
- Nothing else is implicit. Every other value is a `Label: value` line.

## Property lines

- Format: `Label` left, value right, one property per line, labels in plain words with an initial capital, no
  trailing colon inside an aligned table (`Needed by      2026-10-23`), or `Label: value` where lines are not aligned.
  Within one section, align the values on one column (the longest label plus two spaces, capped at 24 characters;
  longer labels wrap their value to the next line, indented).
- Values in the reader's words: labels from code lists, people by name, dates as `YYYY-MM-DD` (with the weekday where
  a day matters), money with its currency (`12 500 USD`), durations with units (`10 calendar days`).
- **Empty values**: in a section that always shows the same fields, show `—` so the shape stays stable and absence is
  visible (`Answered by   —`). In an open-ended list (attachments, links), omit empty rows and show one line saying
  so (`No files`). Never show `-`, `None`, `null` or a blank value with a label.
- **Long text** (a question, an answer, a letter body) is a section of its own: a heading line, then the text wrapped
  to the panel width, never truncated silently. If it must be cut in a panel, cut at a word and end with `… (Enter
  for all)`.

## Sections

A panel or a Details tab is a stack of named sections. Each section has a heading line in the screen's heading
style (bold, muted colour, title case, e.g. `Question`, `Status`, `Dates`, `People`, `Files`), its lines below, and
**one blank line** before the next heading. No rules of `─` between sections unless the panel is very dense; the blank
line and the heading do the work.

Order sections by what the reader needs first. For a record of a correspondence-like type (RFI, letter, notice):
1. Heading (number · subject) and state line
2. The narrative (question, proposed solution, answer, or letter summary)
3. Key facts: discipline, needed by, raised, answered, who with, cost/schedule impact
4. Status timeline (oldest first; date, person, event, short note)
5. Files and links (counts in the heading: `Files (2)`)
Documents: heading and state; current revision; revisions; files; links (stale ones marked).

**Metadata tiers.** Keep three tiers apart:
- *Everyday metadata* (dates, people, discipline, due, impact): in the panel and the Details tab, as property lines.
- *Extended properties* (property sets, company and project schemas): only on the Properties tab, grouped by set,
  with the set's label as the section heading. Never mixed into Details.
- *Technical details* (ids, versions, hashes, internal keys): only in technical mode (Ctrl+D, admins).

## Logs (lists)

- **Columns** in this order: identifier (Number), Subject/Title, State, then the two or three fields people sort or
  scan by (Discipline, Needed by, Days, With, Due). Subject is never further right than the third column.
- **Drop a column whose value does not vary** in the rows shown (e.g. `Kind` when every row is `Request for
  information`): show it only when two or more values are present. A constant belongs in the log's name.
- **No duplicate columns** (State and Status saying the same thing) and no column that only a technical reader
  understands.
- Widths: identifiers and dates fixed; Subject takes the remaining width and is the only column that shortens (with
  `…`); numbers right-aligned with tabular digits.
- Sorting and filters are named in the keys row, not as columns.

## Screen frame

Top to bottom, always: breadcrumb (`Project › Log › Number: subject`), filter, list, panel, actions bar (only
offered actions, `[key] Verb`), keys row (navigation and filters), status line. Wide terminals (≥ 160 columns) put
the panel right of the list; narrow ones below. The panel and the record screen use the same sections in the same
order; the panel shows sections 1–3 and the first lines of 4–5, the record screen shows all.

## Colour and emphasis

Colour means something or it is not used: state (green done, amber waiting, red overdue/refused), stale links,
warnings. Bold for headings and the identity line only. Dim for labels and secondary text. Never colour as
decoration; everything must read in monochrome.

## Checklist (run it on every screen a ticket touches)

- The glance answers: where, which record, what state, what next.
- Identity line first; every other value is `Label: value`; no unlabeled stray values.
- Sections named, ordered by need, separated by one blank line; long text in its own section.
- Everyday metadata, extended properties and technical details are on separate tiers.
- Log columns: Number, Subject, State first; no constant or duplicate columns.
- Empty values shown as `—` in fixed sections, omitted with a one-line note in open lists.
- Same labels and order as the other screens of the same record type.
- Works at 80 and at 170 columns; nothing important truncated without `…` and a way to see it whole.
