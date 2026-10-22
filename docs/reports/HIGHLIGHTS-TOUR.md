# Highlights: the everyday screens

Eight screenshots of the screens people use most: the RFI log, an RFI, the correspondence log, a letter and the document log. They are generated: `just tour highlights` (`uv run python dev/tour/highlights.py`) builds a small made-up project (four RFIs in different states, a few letters, three documents, the company standards loaded), drives the real terminal UI headless and writes the SVG files under `tour/highlights/`. The clock is frozen, so a second run changes no file. The full tours are [PHASE-0-TOUR](PHASE-0-TOUR.md) and [PHASE-1-TOUR](PHASE-1-TOUR.md); the layout rules these screens follow are in the `tui-layout` skill.

Each screen reads the same way: where you are, which record, what state, then the detail in named sections. The identity line (`number · subject`) and the state come first; every other value is a `Label  value` line; an empty value reads `—`; the ids and keys the system uses inside are shown only to an admin who switches technical details on (Ctrl+D).

## 01 RFI log, wide

![Ctrl+G: the RFI log at 170 columns](tour/highlights/01-rfi-log-wide.svg)

The list shows the number, the subject and the state first, then the fields people scan by (discipline, date needed). A column that is the same in every row, such as the kind (always "Request for information"), is left out until two kinds appear. The selected RFI sits to the right: its question, the key facts, the clocks and the start of the timeline.

## 02 RFI log, stacked

![The same log at 100 columns](tour/highlights/02-rfi-log-stacked.svg)

On a narrower terminal the same record panel moves below the list. Only the subject is shortened (with `…`) to fit; the rest of the record is a key away (Enter).

## 03 An RFI's Details

![Enter on the RFI: Details](tour/highlights/03-rfi-details.svg)

Enter opens the record. The Details tab reads top to bottom: the question in full, the proposed solution, the key facts, the response clocks, the status timeline (oldest first, with who and why), the files and when the record was made. Extended properties are on the Properties tab, not here.

## 04 The RFI's Files tab

![6: the Files tab](tour/highlights/04-rfi-files.svg)

Key `6` lists the attachments with their kind, size and, for a PDF, the page count; Enter or `v` opens the selected file in the system viewer.

## 05 The correspondence log

![F5: the correspondence register](tour/highlights/05-correspondence-log.svg)

The register lists every letter, email and register item with number, subject and state first. The selected letter shows its message, who it is with and which dates matter, the reply clock and the timeline. It is shown at 200 columns because the register has eight columns.

## 06 A letter's Details

![Enter on a letter: Details](tour/highlights/06-letter-details.svg)

The letter's record leads with the message, then the key facts, the people, the dates, the response clock, the timeline and the files. The delivery state and other plumbing are technical details.

## 07 The document log

![F7: the document log](tour/highlights/07-document-log.svg)

Documents list the number, title and state first, then the current revision, type and discipline. The panel shows the key facts, the revisions (the current one marked), the files of the current revision and the links, with a stale link marked `!`.

## 08 The document preview line

![The preview line of a PDF where images are not shown](tour/highlights/08-document-preview-line.svg)

Under Files the panel gives the file's kind, size and page count; in a terminal that can show images it draws page 1 instead (the tour's terminal cannot, like the tests). `v` opens the file.
