# Increment plan — P1-UX2 The log standard, actions, the RFI record and document preview

Status: in-progress
Supervisor session: 2026-10-21 (round 1)
Brief sections: §10 (TUI), §9 M10 (Technical / RFI), §8 (documents), §20 (files); ADR-0016 (confidentiality), ADR-0010 addendum
Branch: `p1/ux2` (trunk `claude/wizardly-allen-m2v96s`). Scope and owner request: `SCOPE.md`. Live board: `STATE.md`.

## Objective
Every log in the TUI tells the user where they are (breadcrumb `P123 › RFI Log › P123-RFI-0328: Conflict in
piling/utilities at AZ203`), shows the selected record in a panel (below, or right at 160+ columns), and lists the
actions this viewer may take on it now, asked of the server and never guessed by the screen. The RFI record carries the
question and answer, a status timeline and its files. The document log opens a file in the system viewer and shows a
page-1 thumbnail where the terminal can. TUI only; no change to command semantics, events or stored data. Built on
P1-UX (display helper, record screen, details registry).

## Demo (SCOPE §5; `just demo P1-UX2`, SQLite and Postgres)
| # | Clause |
|---|---|
| 1 | The breadcrumb follows the highlighted row of the RFI log (and of the document log). |
| 2 | The actions bar of an RFI shows Answer to an answerer and not to a plain reader; Answer from the bar answers the RFI. |
| 3 | The RFI record shows narrative (question, answer), status timeline and files. |
| 4 | The document log opens a PDF (to a temp file, checked by hash) and shows its page-count fallback (text-only terminal). |
Tours regenerated with the leak check (`just tour-all` twice, no LEAK, second run identical); new PHASE-1-TOUR section
shows the log standard, the RFI record and the preview fallback.

## Supervisor-tier pieces (builder, `review: full`, `kind: piece`)
| # | Piece | Area | Depends | Spec |
|---|---|---|---|---|
| S1 | Allowed-actions query (module hook, core, API route, both clients) and file access on the client interface | tl-core, modules, tl-api, tl-tui client | none | `S1-allowed-actions.md` |
| S2 | Shared `LogScreen` and the "Log screens" standard | tl-tui widget, README | none | `S2-log-screen.md` |
| S3 | Move every log except documents to `LogScreen`, wire actions, remaining code labels | tl-tui widgets, text modules | S1, S2 | `S3-migrate-logs.md` |
| S4 | Documents: log move, open in viewer, thumbnail, Files tab for any record | tl-tui widgets, `preview/`, dependencies | S1, S2, T01, T02 | `S4-document-preview.md` |
| S5 | RFI record: narrative, status timeline, clocks (technical items; correspondence where data exists) | tl-tui details | none (Files tab is S4's) | `S5-rfi-record.md` |
| S6 | Demo, tours, tour section, README and runbook | dev, docs | S3, S4, S5 | `S6-demo-tours.md` |

## Tickets (Haiku, isolated pure functions with a provided test)
| ID | Title | Depends | Review | Status |
|---|---|---|---|---|
| T01 | `image_protocol(env)`: which inline-image protocol the terminal speaks | none | full | ready |
| T02 | `file_text`: `human_size`, `file_kind`, `file_line` | none | full | ready |
Both are tl-tui work, so `review: full` (orchestrator instruction r1; D32 of P1-UX).

## Waves (3 heavy slots; a ticket workflow is one slot)
| Wave | Items | Why this set |
|---|---|---|
| 1 | S1, S2, workflow {T01, T02} | No dependency; paths disjoint (S1 client files vs S2 new widget and README). |
| 2 | S3, S4, S5 | After S1, S2, T01, T02 merged. S3 owns every log except documents; S4 owns documents, `preview/`, `record_view.py`, `record_screen.py`; S5 owns `details/technical.py` and friends. Paths disjoint. |
| 3 | S6 | After S3, S4, S5 merged. Demo, tours, docs. |
Then the orchestrator runs the whole gate, parity on touched directories, the demo, and the security reviews (below).

## Decisions
- D1 The seam is an additive `ModuleSpec.actions` hook (per record type, `(conn, record_id, holds) -> list[ActionOffer]`);
  the core asks it only after the visibility check; `holds(level)` is the same decision the API authorizer makes.
  `docs/adr/0010-module-record-storage.md` gets an addendum written by S1. Why: the module owns state and role rules.
- D2 Presentation (key letter, form, confirmation) stays in the TUI, keyed by command name; the server returns
  `command` and a plain `label`. A table in the TUI maps command to key and form.
- D3 Haiku tickets only for T01/T02 (isolated pure functions, provided tests); everything that visits many screens is a piece (rule 12). All tl-tui work is `review: full`.
- D4 Preview rendering runs in a child process with a timeout and size caps (a hostile PDF can crash the native
  library; a thread cannot contain that). Cached by content hash in a private directory.
- D5 Owner decisions 2026-10-21 (APPROVALS b57c20b): open in system viewer plus page-1 thumbnail; pypdfium2 plus
  textual-image (permissive; `dev/tools/check_licences.py` gates; copyleft = stop); layout top/bottom, right panel at
  160+ columns.
- D6 Code labels (`Structural`, `Isometric`, `Piping` ...) come from the effective schema's code lists. A raw code in a
  cell is fixed in `labels_load`/`display` or reported. `schema/**` is never edited by these pieces (stop and list).

## Security (Sec rows; one fresh reviewer per row at DONE, range `b57c20b..<head>`)
| Row | What to prove |
|---|---|
| Sec1 allowed-actions query | A hidden record answers byte-identical to a missing one on route, client and embedded call; the answer carries no record text; an agent is offered nothing; no action is offered that the command would refuse on authorization (role or class) grounds, and every refused-on-state action is withheld (table test over states x roles); route listed in the five-reader walk. |
| Sec2 open and preview path | Temp files and directories are private (0700/0600) and removed on close/exit; file name never builds a path outside the temp dir; downloaded bytes match the stored sha256 before opening; viewer launched with an argument list (no shell), name never starting with `-`; rendering is page 1 only, size/pixel/time/memory capped, in a child process, no network; cache keyed by sha256 in a private dir with a size cap; a hidden record's file answers like a missing one; remote mode goes through the existing file routes only. |

## Risks and escalation triggers
- S1 touches several packages (core hook, two modules, API, tl-tui client): additive and owner-scoped (D1); an
  interface another workstream consumes must still not break, so existing OpenAPI output changes only by the new route.
- S3 is the largest piece (seven screens). If it fails twice, split by area (re-spec in the next round); do not retry whole.
- Snapshot churn: S3 and S4 regenerate snapshots; a generated-file conflict at merge is regenerated (Code 131).
- Dependencies need network at install; the proxy reached PyPI in round 1 (`uv pip install --dry-run` resolved
  pypdfium2 5.14.0, textual-image 0.14.2, pillow 13.0.0). `uv.lock` change is S4's.
- Terminal image support cannot be tested; tests use the text fallback (SCOPE §4).
- A copyleft finding in `check_licences.py` stops S4 (stop condition).
- Escalate: any need to edit `schema/**`, change a command's semantics, or change an event.

## Blocked / Decision
(none)
