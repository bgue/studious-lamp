# P1-UX2: the log standard, actions, the RFI record and document preview (scope)

Owner request, 2026-10-21, after P1-UX: "Our logs should tell us where we are (RFI Log), what record we're on
(RFI-0328: Conflict in piling/utilities at AZ203), and what actions to take. Our RFI record should have not only its
metadata but the usual narrative information of question and answer, status updates, and list of attached files.
Our document log should provide a click to preview or a file preview of the first page of the file if it's a PDF."
Owner decisions the same day: PDF preview = open in the system viewer plus a page-1 thumbnail where the terminal
can show images; layout = list on top, details below, details to the right on wide terminals (about 160+ columns).

TUI only, built on P1-UX (display helper, plain/technical mode, RecordScreen, details registry). Process: skill
rule 12 (consequential pins, pieces sized by area, one pass, run only what is named).

## 1. One log standard, built once
A shared log screen used by every log: document register, tag register, correspondence (register, triage inbox,
clocks), RFI log, commercial register, evidence, schedule screens that list records, review queue, integration
registry, schema workbench list. Layout, top to bottom:
- **Breadcrumb**, always current: `P123 › RFI Log › P123-RFI-0328: Conflict in piling/utilities at AZ203`
  (project, log name, highlighted record number and title; the record part is empty when nothing is selected).
- **List** (DataTable), plain labels in every cell (no raw codes: `Structural`, `Isometric`, `Piping`).
- **Selected record panel** below the list; on terminals ≥ 160 columns the panel sits to the right of the list.
  The switch happens on resize.
- **Actions bar**: only the actions the viewer may take on the highlighted record in its current state, each with
  its key, e.g. `[a] Answer  [c] Close  [e] Escalate  [Enter] Open record`. Nothing is shown that would be refused.
- **Keys row**: navigation and filters only (`/ filter`, `o open only`, `F5 reload`, `Esc back`).
- A count/summary line stays where each log has one today.
The standard is written down in packages/tl-tui/README.md ("Log screens") and every log uses the shared screen.

## 2. Actions from the server, never guessed by the screen
A read-only query "which actions may this viewer take on record X now" answered by the module that owns the record
type (state machine + role and class rules already in the commands), exposed through the client interface
(embedded and remote) and an additive API route. An action in the bar runs the existing command (with the same
confirmation and forms the CLI uses, e.g. the answer text for Answer); a refusal from the command is shown in the
status line. Hidden records: the query for a record the viewer may not read answers exactly like a missing record
(ADR-0016). CLI, MCP and existing API output unchanged.
First record types with actions: RFIs (and the other technical items), commercial notices, correspondence items,
documents/revisions (issue, supersede, void, transmittal where the viewer may), tags (where any exist).

## 3. The RFI record
The record screen for an RFI (and the other technical items) gets:
- **Narrative** first: subject, question, proposed solution, answer (with who answered and when), raiser's and
  answerer's cost/schedule view, escalation. Long text wraps; nothing truncated silently.
- **Status timeline**: every state change with date, person (plain name) and note, oldest first, from the record's
  events (Raised → Issued → Answered → Closed, re-opened, escalated), plus the clocks with their outcome.
- **Files**: the attachments and linked documents of the item, each with name, type, size and pages (PDFs), with
  the same open/preview as the document log.
Correspondence items get the same narrative/timeline/files where the data exists.

## 4. Document preview
In the document log and on a document's record screen:
- **Open**: a key (`v`, or Enter on the file line) opens the current revision's file in the system viewer; in
  remote mode it is downloaded to a temporary file first. The file is fetched through the existing file routes, so
  confidentiality and hashing are unchanged.
- **Thumbnail**: where the terminal can show images (kitty, iTerm2, WezTerm, Windows Terminal/sixel), the panel
  shows page 1 of a PDF as a picture; elsewhere it shows page count, size and title. Rendering uses pypdfium2
  (Apache-2.0 / BSD-3; PDFium BSD-3) and a permissive terminal-image library; both pass `dev/tools/check_licences.py`
  or the piece stops (stop condition: copyleft). Rendering is bounded (page 1 only, size and time caps, no
  network), runs off the UI thread, and is cached by content hash.
- Tests use the text fallback; a deterministic snapshot of the thumbnail is not required.

## 5. Tour and demo
`just demo P1-UX2` (SQLite and Postgres): the breadcrumb follows the highlighted row; the actions bar of an RFI
shows Answer to an answerer and not to a plain reader, and Answer from the bar answers it; the RFI record shows
narrative, timeline and files; the document log opens a PDF (to a temp file, checked by hash) and shows its
page-count fallback. Tours regenerated with the tour leak check; a new PHASE-1-TOUR section shows the log standard,
the RFI record and the document preview fallback.

## Constraints
- No change to command semantics, events or stored data. The allowed-actions query is additive.
- Security review at DONE, one reviewer per item: the allowed-actions query (no leak, no action offered that the
  command would refuse for authorization reasons), the open/preview path (no path traversal, temp files private and
  cleaned, PDF rendering bounded against hostile files).
- New dependencies: pypdfium2 and the image library, owner-approved by the preview decision; record in APPROVALS.
