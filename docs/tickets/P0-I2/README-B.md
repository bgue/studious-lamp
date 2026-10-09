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
| T12 | Header and footer widgets | H | T11 | ready | |
| T12b | Nav tree and context panel | H | T11 | ready | Split from the plan's T12 (shell) so each ticket stays under 400 lines |
| T13 | Data grid core | S | T11 | merged (supervisor-built) | |
| T13b | Grid column chooser and copy as TSV | H | T13 | ready | The plan's "H polish" half of T13 |
| T14 | Record view: header, Details, History | H | T11, T12 skeleton | ready | |
| T15 | Psets tab: layer-grouped rendering with enforcement markers (sketch 2) | H | T14, WS-A T05 | draft | |
| T16 | Generated forms; Save to `SetPsetValues` | H | T15 | draft | |
| T17 | Snapshot tests; key map `n e Ctrl+S Esc [ ]` | H | T16 | draft | |
| T18 | `just tui`, demo, report | S | T17, WS-A merged | draft | Taken by the supervisor (demo and report are supervisor deliverables) |

Haiku-ability (`01-tiers.md` §6): T12, T12b, T13b and T14 each read at most six files, depend only on interfaces already
on `p0/i2b`, ship with a supervisor-provided test file (stored under `provided/*.py.txt`, L-P0-I1-8), stay under about 400
lines across at most three files, avoid every Sonnet-authored row, avoid `schema/**` and dependencies, and are verifiable
from the diff plus `just check` and the test commands. Each provided test was confirmed satisfiable by a scratch reference
implementation, which was then discarded.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| B1 | `tl_core.services.queries` gains `get_record_by_id`, `record_history`, and optional `record_type`, `limit`, `offset` on `list_records` (all additive, defaults keep old behaviour) | `ClientInterface` needs them and no service existed; screens may not run SQL or read the ledger. `OFFSET` without `LIMIT` is sliced in Python to stay dialect neutral |
| B2 | `tl-tui` declares `tl-schema` and `tl-adapters` as dependencies; only `embedded.py` and `main.py` import `tl_adapters` | `tl_tui` already imports `tl_schema.forms` (the contract); `just tui` needs `open_uow` |
| B3 | Screens read pset values by dotted path with `tl_tui.paths.pset_value`, which accepts nested dicts and flat dotted keys | The stored shape of `psets_json` is workstream A's decision; the TUI must not break on either form. Writes use `FieldMeta.path` minus `psets.<group>.` as the key (`x.` prefix kept) and group by `(pset, layer)` |
| B4 | Grid sort is client-side over loaded rows; a sort first loads every page (cap 50,000) | `list_records` has no sort parameter and the contract is frozen; fine for Phase 0 sizes, revisit with the query language (P0-I4) |
| B5 | The shell is built by the supervisor; header/footer, nav/context, column chooser and record view are tickets against stubs with final interfaces | Keeps layout and message routing consistent, and lets four tickets run with disjoint paths |
| B6 | `test-tui` runs every test in `packages/tl-tui` (behaviour and snapshots) | Snapshots live beside the behaviour tests; one command |

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
