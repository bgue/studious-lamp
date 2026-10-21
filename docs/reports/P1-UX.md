# P1-UX report: usability increment before Phase 2

Status: done except S5 (final polish, in flight; its line below is filled at merge)
Branch `p1/ux` (@ed025b8 at writing). Plan `docs/tickets/P1-UX/README.md`, scope `SCOPE.md`, board and decisions D1-D46 `STATE.md`.

## Objective (owner, 2026-10-21)
The Phase 1 register screens are lists with a fixed summary panel. They never show property sets, cannot open the
full record, and show technical detail a mainstream AEC user should not see. Fix that in the TUI. No new domain
behaviour, no change to commands, events or stored data.

## What shipped (SCOPE clauses)
| # | Clause | Result |
|---|---|---|
| 1 | One record screen | Enter on a row of every register opens `RecordScreen` (Details, Properties, Links, History, Thread); Esc returns to the same row. Documents, tags, correspondence, inbox, clocks, RFI log, commercial, schedules, review queue, schema packages, grid. Details per type from typed views (`tl_tui/details/`); `GET /schema/forms` takes an optional `record_id` so class-bound sets show |
| 2 | Plain language | One helper (`tl_tui/display.py`) for type, code-list, domain, property and set labels with units; ids, hashes, versions, internal keys, clock and calendar ids, `svc:` actors and rule markers are hidden. Every screen was converted (T01-T13, T06b, T08b-c, T09a-e) |
| 3 | Technical toggle | `Ctrl+D` (palette "Technical details", help screen), admin-only, per viewer, off at start, not remembered; a plain user gets one line: "Technical details are for admins" |
| 4 | Property sets | `document_data`, `rfi_data`, `correspondence_data` added to the fixture standard `co.acme.engineering@3.2.0` (additive, in place); labels, units, one required and one code-list property each; owner approval in APPROVALS.md; demo ledgers carry values |
| 5 | Tour re-shot | `just tour-all`: phase 0 27 shots, phase 1 74 shots; second run changes no file; new section 23 in `PHASE-1-TOUR.md`; the tour now fails on any plain shot that carries technical text |

## Decisions worth knowing
- Toggle is `Ctrl+D` and admin-only (D7, D5). It steps aside inside text inputs (D18). The refusal lives in `DisplayMode.toggle` (D19).
- Adoption of the new sets is mandatory for project scopes, and `required_in_states: Issued` makes missing values at most a warning, never nonconformant (D12). A Draft stays clean; an Issued document without `originator` reads `conformance: warning`.
- The commercial `Status` column is dropped in both modes; it duplicated `State` (D26).
- Plain names replace codes: snapshots read `Snapshot 3` (technical `CODE#3`, D29); schedule phases and relationship types are words (D37); P6 codes read as words; layers read `Company`, `Project P123`, `User` (D19, D39).
- Admin tools stay plain by default (D13): token ids, setting seq numbers, `svc:` actors and digest lines are technical-only. Setting keys, the workbench Version column and the Property, Lint and Diff tabs stay visible because admins work with them.
- Grid `Ver` column shows only in technical mode (D39). Agents read `name ⚙` in plain (D31).
- Record screen is a modal over the register, not a new route (D1, D2).

## Gates
| Gate | Result |
|---|---|
| `just check` at DONE | `<<fill>>` |
| `just gate` whole suite | `<<fill>>` |
| `just gate-pg` touched dirs  | `<<fill>>` |
| tl-tui suite at S4 | 1304 passed |
| `just demo P1-UX` (S4) | 4/4 clauses on SQLite and Postgres (about 15 min; the walk is 7 of them) |
| `just tour-all` x2 (S4) | exit 0, no `LEAK`, second run identical; 27 + 74 shots |
| S5 final polish | `<<fill>>` |

## Security
Nine reviews, stronger tier, range `4b2cda0..aca2ec5`.
- Record screen: hidden = missing on every route, byte-identical bodies, same timing class. LO `record_id` had no length cap: fixed `09461d6` (`max_length=64`). LO "reload after reclassification" accepted per ADR-0016 section 6.
- Property sets: no read or write path added. LO `confidentiality_note` wording could suggest it restricts access: fixed `09461d6` (it now says it does not change who can read the document).
- The findings listed are all LO. The S4 review (leak check in the tour) raised F1 and F2, both placed in S5.

## Deviations
- S2 regenerated `docs/reference/openapi.json` (new optional `record_id` query).
- S3 seed values for the new sets are written by the demo and tour (`tl pset set`), not by the fixture; the P0-I2 demo count was fixed on trunk (`fix/p0-i2-demo-count`).
- S4 edited `schema_review_screen.py` (outside its paths): the tour check found `co.acme.engineering@4.0.0` in a refusal line.
- Rule 12 consequential pins (listed per report): publish preview header (T11), five done-lines in `test_schema_review_screen.py` (S4), grid column tests (T08c), 12 snapshots (T11b).
- Several tickets merged as lite review before D32 (tl-tui is always full): T05, T09e.

## Follow-ups
1. Properties tab shows code-list codes and a raw `{currency}` unit; the schema workbench shows `user:demo`; `SERVICE_PATTERN` stops at a hyphen; tour check lacks the walk's `key_hits`; no review-queue row in the demo. All five are S5.
2. Enricher panel property lines run name into value when the name has 10+ characters (`disciplinetext`); pre-existing, both modes (T09a). No ticket.
3. `setting_form.py` still says `at project:P123` in plain mode (T09b); workbench key hints omit Enter (T09d); `schedule_detail_lines(technical=)` unused (T06); record screen does not reload the register after an edit (F5 does).
4. `CALENDAR_REF_PATTERN` matches a numeric e-mail domain (`amy@123.example.com`): a false positive in the leak finder, never a leak (T00).
5. `KNOWN_LEAKS` in the plain walk is empty. Server-written text (`FeedItem.summary`, card text) was not audited for ids (T13).
6. Question for the owner: the TUI and API keep hidden = missing in the same timing class (reviewed). The future web client (Phase 5) will read the same routes; do you want its review to include a timing probe, or is the TUI/API result enough?

## Process notes
- Cost: most tickets ran a block, decide, respawn, regate, review loop of 20-50 minutes, because Allowed paths were narrow and a consequential pin or a missing gate path stopped the author. Owner request ended it: skill rule 12 (pins updated in the ticket and listed, size by coherence, one pass, orchestrator fixes trivia, builders run only what is named), trunk `5a05125`.
- T11/T12 splits (D40) and then S4 replacing T11c, T12 and T12b (D45) showed a coherent piece beats three narrow tickets.
- Every tl-tui ticket is `review: full` (D32).

## Showcase
`docs/reports/PHASE-1-TOUR.md` section 23, "Plain language and the record screen", shots `23a`-`23g`: the record screen opened from each register with its Properties tab, and the technical toggle off and on (`23f` is the unchecked technical shot). Run `just demo P1-UX` for the four clauses live.
