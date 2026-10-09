# Workstream plan — P0-I2 workstream B: TUI shell, grid, record view, forms

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §4, §10.1–§10.4, §10.6 (sketches 1, 2, 11), §6.3
Branch: `p0/i2b` (integration branch `p0/i2`; trunk `claude/wizardly-allen-m2v96s`)
Fanout plan: `docs/tickets/P0-I2/FANOUT.md`. Counterpart: workstream A (`p0/i2a`).

## Objective
A Textual shell in embedded mode: header, nav tree, main area, context panel, footer; a virtualised data grid; a record
view with Details, Psets and History tabs; and generated forms that save pset values through `SetPsetValues`. Everything
reads and writes through `ClientInterface`; no screen holds business logic. Until workstream A merges, the screens run
against `FakeClient` (`packages/tl-tui/tests/fakes.py`), which reproduces the §6.3 `valve_data` example. After A merges,
the demo uses the embedded client over the real pset services.

## Demo
`just demo P0-I2` (`dev/demos/P0-I2.sh`, written after workstream A merges): load the `co.acme.engineering@3.2.0` and
`x.P123@1.4.0` fixtures, print `tl schema hash P123`, create a record, set `valve_data.size_in` and
`valve_data.x.fat_witness_by` through the same client the TUI uses, and show the conformance warning for the missing
advisory property. The TUI itself is exercised by `just test-tui` (snapshot tests) and started with `just tui`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| T11 | `EmbeddedClient` over `tl_core` services; `tl_core.services.queries` additions (`get_record_by_id`, `record_history`, `record_type`/`limit`/`offset` on `list_records`); `errors.py`, `messages.py`, `paths.py`, `text.py`; `FakeClient` and test helpers | Interface implementation that every screen depends on | Orchestrator (REVIEW-SUPERVISOR-PIECES) | built, `73bb88c` and following |
| T13 | `RecordGrid` core: paging, virtualised rendering, cursor, sort, multi-select, TSV, mouse | Plan marks "S core" | Orchestrator | built |
| T12 skeleton | `TlApp` (layout, F2/F3/F6, narrow-mode overlays, message routing), `MainArea`, `app.tcss`, `main.py`, stubs with final interfaces | The layout and routing are the shared structure all widget tickets plug into | Orchestrator | built |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T11 | Embedded `ClientInterface`, fakes | S | — | merged (supervisor-built) | |
| T12 | Header and footer widgets | H | T11 | merged | Review pass on attempt 2 (attempt 1 committed its report file). Follow-up by supervisor: `footer_lines` when the count is wider than the footer |
| T12b | Nav tree and context panel | H | T11 | merged | Review pass. Follow-ups by supervisor: `NavTree.KEY_HINTS`, `conformance_mark(None)`. Split from the plan's T12 (shell) so each ticket stays under 400 lines |
| T13 | Data grid core | S | T11 | merged (supervisor-built) | |
| T13b | Grid column chooser and copy as TSV | H | T13 | merged | Review pass; the error status on a failed `form_metadata` is accepted. The plan's "H polish" half of T13 |
| T14 | Record view: header, Details, History | H | T11, T12 skeleton | merged | Review pass, no findings |
| T15 | Psets tab: layer-grouped rendering with enforcement markers (sketch 2) | H | T14 (fake metadata; WS-A T05 not needed to build) | ready | |
| T16a | Form field editors generated from `FieldMeta` (inline validation) | H | T11 | ready | Split from the plan's T16 so it can run beside T15 |
| T16b | Form assembly: edit mode in the Psets tab, Save to `SetPsetValues` grouped by (pset, layer), new-record form | H/S | T15, T16a | draft | Second half of the plan's T16 |
| T17 | Snapshot tests; key map `n e Ctrl+S Esc [ ]` | H | T16b | draft | |
| T18 | `just tui`, demo, report | S | T17, WS-A merged | draft | Taken by the supervisor (demo and report are supervisor deliverables) |

Haiku-ability (`01-tiers.md` §6): T12, T12b, T13b and T14 each read at most six files, depend only on interfaces already
on `p0/i2b`, ship with a supervisor-provided test file (stored under `provided/*.py.txt`, L-P0-I1-8), stay under about 400
lines across at most three files, avoid every Sonnet-authored row, avoid `schema/**` and dependencies, and are verifiable
from the diff plus `just check` and the test commands. Each provided test was confirmed satisfiable by a scratch reference
implementation, which was then discarded.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| B1 | `tl_core.services.queries` gains `get_record_by_id`, `record_history`, and optional `record_type`, `limit`, `offset` on `list_records` (all additive, defaults keep old behaviour) | `ClientInterface` needs them and no service existed; screens may not run SQL or read the ledger. `OFFSET` without `LIMIT` uses the portable maximum `LIMIT`; negative `limit` or `offset` raise `ValueError` |
| B2 | `tl-tui` declares `tl-schema` and `tl-adapters` as dependencies; only `embedded.py` and `main.py` import `tl_adapters` | `tl_tui` already imports `tl_schema.forms` (the contract); `just tui` needs `open_uow` |
| B3 | Screens read pset values by dotted path with `tl_tui.paths.pset_value`, which accepts nested dicts and flat dotted keys | The stored shape of `psets_json` is workstream A's decision; the TUI must not break on either form. Writes use `FieldMeta.path` minus `psets.<group>.` as the key (`x.` prefix kept) and group by `(pset, layer)` |
| B4 | (Superseded by B7.) Grid sort was client-side over loaded rows; a sort first loaded every page (cap 50,000) | `list_records` has no sort parameter and the contract is frozen; fine for Phase 0 sizes, revisit with the query language (P0-I4) |
| B5 | The shell is built by the supervisor; header/footer, nav/context, column chooser and record view are tickets against stubs with final interfaces | Keeps layout and message routing consistent, and lets four tickets run with disjoint paths |
| B6 | `test-tui` runs every test in `packages/tl-tui` (behaviour and snapshots) | Snapshots live beside the behaviour tests; one command |
| B7 | Grid sort is server-side. `order_by: list[tuple[str, "asc"\|"desc"]] \| None` is added to `tl_core.services.queries.list_records` (allow-list `key, title, status, type, created_at, updated_at, version`; unknown column, bad direction, negative limit or offset raise `ValueError`; empty values last; `id` breaks ties) and, as an additive keyword, to `ClientInterface.list_records`, `EmbeddedClient` and `FakeClient`. **Orchestrator-approved contract change** (supersedes B4). Sorting on pset columns waits for the query language (P0-I4): the grid shows "Sort on pset columns arrives with the query language". Columns outside the allow-list (conformance, description) say "Sorting by X is not available" | Review of the first grid: `_load_all` froze the UI for 2.7 s at 20k rows and truncated at the cap with a wrong order |
| B8 | End loads further pages in a Textual thread worker with progress in the footer, up to 5,000 rows, and then shows "Capped at 5,000 rows; narrow the list to see more". Late worker results are dropped (generation counter). Scrolling still pages one page at a time with no cap | Brief §15 (under 150 ms to 100k rows) cannot hold if the UI thread loads everything |
| B9 | Ctrl+A selects the loaded rows only and says "N loaded rows selected; more not loaded" when more exist | Same reason; honest about what is selected |
| B10 | Shift+Up/Down extends the selection add-only (it never removes a row on the way back) | Acceptable per review; Space toggles a row off |
| B11 | TSV and `y` export raw values (`6.0`, `nonconformant`, ISO timestamps, `true`), not display symbols; header uses the column labels | A pasted spreadsheet should hold data, not decoration |
| B12 | A failed page fetch posts an error status and leaves `exhausted` false (and a failed reload leaves the rows untouched); the next cursor move retries | The list must not look complete after an error |

### §15 performance gap
The brief's target (under 150 ms to 100k rows, §15) is met for the first page and for server-side sort (one `LIMIT` query).
It is not met for "load everything": End is capped at 5,000 rows and Ctrl+A selects loaded rows only. Real windowed paging
by row range, and filters, arrive with the query language in P0-I4.

## Order of work (relay rounds)
| Round | Ticket batch | Supervisor work in the same turn |
|---|---|---|
| 1 | T12, T12b, T13b, T14 | Plan, T11, T13 core, shell skeleton, provided tests |
| 2 | (merge round 1) T15 against the fake, then "ready for A" | Merge, integration commit wiring |
| 3 | T16, T17 after A merges | Merge A, swap fake for embedded client where applicable, T18, report |

## Risks and escalation triggers
- Textual API drift (the installed version is newer than the build spec assumed): tickets paste the exact names they use.
- Snapshot flakiness: sizes pinned at 120x40 and 80x24; no clock, no random values on screen.
- The `psets_json` shape and `form_metadata` field paths come from workstream A; a mismatch is a contract question for the orchestrator.
- `uv.lock` changed (new `tl-tui` dependencies); workstream A may also change it. Resolve with `uv lock` at integration.

## Blocked / Decision
(none)
