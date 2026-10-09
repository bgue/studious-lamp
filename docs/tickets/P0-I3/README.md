# Increment plan — P0-I3 Links, numbering, workflow; palette, link picker, trace

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §7 (7.1 reference model, 7.2 create, 7.3 maintain, 7.4 surface, 7.5 follow), §8 (workflow engine, numbering service), §3 (cross-scope links), §10.2, §10.6 sketches 3 (palette), 4 (link picker), 12 (links tab, reference tray)
Branch: `p0/i3` (trunk `claude/wizardly-allen-m2v96s`; P0-I2 is merged into it and into this branch)

## Objective
Records can be linked, numbered and moved through a workflow. A link is its own ledger stream with a lifecycle (suggested, active, stale,
broken, retracted; never deleted), resolvable from both ends in `cur_links`; keys come from pattern-driven numbering allocated in the same
transaction as `Record.Created`; a declarative workflow engine allows a transition only when its guards pass (psets, links, expected links,
roles), emits `Workflow.Transitioned`, and updates `status`. The TUI gains the command palette, the link picker, the Links tab with the
reference tray and back/forward history, the trace view, and the workflow action menu with guard-failure display. Out of scope: contractual
workflows and clocks (human gate, M10), real roles and permissions (auth), electronic signatures, link health checks that run on a schedule,
external references (`ExternalRef` records), offline reserved ranges (stub only).

## Demo
`just demo P0-I3` (a script, `dev/demos/P0-I3.sh`, on a temporary ledger):
```
tl init
tl record create --project P123 --title "NCR 1"             # key P123-REC-0001 from the pattern
tl record create --project P123 --title "Supporting record"  # key P123-REC-0002
tl wf transition --project P123 P123-REC-0001 submit         # Draft -> Review
tl wf transition --project P123 P123-REC-0001 approve        # BLOCKED: missing expected link "supporting record"
(headless TUI pilot)  open P123-REC-0001, press l, search "0002", Enter   # link by key in the picker
tl wf transition --project P123 P123-REC-0001 approve        # allowed; Workflow.Transitioned in tl events tail
```

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | LinkML for `cur_links`, `cur_link_counts`, `cur_numbering`, `cur_workflow_state`; `tl:expects_link` documented; fixtures for workflows, expected links, numbering | `schema/**` (human gate) | Orchestrator | built |
| S2 | Link lifecycle rules (`links/lifecycle.py`, 62 tests), error types, vocabulary, loader, expected-link stubs and provided tests | Link state rules are subtle; interfaces and test scaffolds | Orchestrator | built |
| T05 | Numbering pattern parser (`numbering/pattern.py`) | Needed by the allocator at once; reference was written to verify the ticket | Reviewer | built (49 tests) |
| T06 | Numbering allocator, counters projection, key-less `CreateRecord`, `tl record create --segment` | Numbering allocator is supervisor-authored by rule (concurrency) | Orchestrator | built (21 service tests, 1 property test, mutation-checked) |
| T09 | Workflow engine: guard evaluation, `TransitionWorkflow`, `workflow_status`, `Workflow.Transitioned`, `WorkflowProjector` | Workflow engine evaluation is supervisor-authored by rule | Orchestrator | built (23 service tests, two mutations caught) |
| T00 | Atomic edit command (`EditRecord`: record fields plus pset batches in one unit of work) | Command handler semantics; filed by P0-I2 workstream B | Orchestrator or human (core command) | built (12 service tests, 3 TUI tests changed, 2 added) |
| — | `ClientInterface` additions and embedded client for links, search, workflow, key detection; `FakeClient` additions | Shared TUI contract | Reviewer | round 2 |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Relation vocabulary (`links/vocabulary.py`) | H | S2 | merged | pass, 1 round |
| T02 | Link commands: suggest, add, accept, decline, repin, verify, flag, retract, stale-by-revision (`services/links.py`) | H | T01, T03 | merged | pass, 1 round |
| T02b | `tl link` CLI (add, suggest, accept, decline, repin, verify, flag, retract, list); `trace` is added by the supervisor after T14a | H | T02, T03b | ready (batch 4) | |
| T03 | `LinkProjector`: `cur_links`, `cur_link_counts` | H | S2 | merged | pass, 1 round |
| T03b | Link read queries: `links_of` (both directions, labels), counts, `search_linkable` | H | T01, T03 | merged | pass, 1 round |
| T04 | Expected links: `tl:expects_link` loader and missing list | H | S1 | merged | pass, 1 round; supervisor fixed self-link count and empty file (D19) |
| T05 | Numbering pattern parser | S | — | built | |
| T06 | Numbering allocator | S | T05 | built | |
| T07 | Key detection: find keys in text, resolve to records (suggestion chips) | H | T05 | merged | pass, 1 round |
| T08 | Workflow definition loader and registry | H | S2 | merged | pass, 1 round |
| T09 | Workflow engine | S | T04, T08 | built (23 tests, mutation-checked) | |
| T10 | `tl wf show|transition` CLI | H | T09 | merged | pass, 1 round |
| T11 | Command palette widget | H | ClientInterface | merged | pass, 1 round |
| T12 | Link picker modal | H | T02, ClientInterface | merged | escalated once (D24); supervisor fix |
| T13 | Links tab (row actions, expected-but-missing) | H | T03b | merged | pass, 1 round |
| T13b | Reference tray screen (tick, remove, link ticked to the open record) | H | T13 | ready (batch 4) | |
| — | Back/forward history, reference tray state, prompt modal, app wiring, record-view tabs and badges | S | — | built (supervisor) | |
| T14a | Trace query: n-hop tree over `cur_links` (`services/link_trace.py`) | H | T03 | ready (batch 4) | |
| T14 | Trace view widget and tab | H | T14a (the fake client stands in until it merges) | ready (batch 4) | |
| T15 | Workflow action menu (`w`) and guard-failure display | H | T09 | merged | pass, 1 round |
| T16 | Snapshot tests, demo script, report | S/H | all | last | |
| T00 | Atomic edit command | S | T09 | built | | |

Haiku-ability (`01-tiers.md` §6) for batch 1: each ticket touches two source or test files plus its report, ships a provided test file and a
precise specification, avoids every row of the supervisor-authored table (T03 and T08 only map events and files onto the rules the
supervisor wrote in `lifecycle.py` and `definition.py`; the engine, the allocator and the permission-like role guard are the supervisor's),
and changes no public interface (the stubs are final). Each was verified by running the provided test, `ruff` and `pyright` against a scratch
reference implementation before dispatch (kept in the supervisor's scratch area as the takeover path).

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| D1 | One `cur_links` row per link; the inverse is derived from the relation vocabulary, not stored. Both ends read the same row (`from_id` for outbound, `to_id` for inbound), indexed on both | One source of truth; no pair of rows to keep consistent. "Both directions resolvable" is a query, `links_of` (T03b) |
| D2 | A link is its own stream `core.Link` (stream id = `link_id`), scope = scope of the `from` record; the target must be in the same scope or in `company` (brief 3). Links to voided records are refused | Brief 3 rules; per-link optimistic concurrency |
| D3 | Link provenance (`manual`, `key_detected`, …) is called `source` in event payloads and `cur_links`, and `link_source` on commands, because `Command.source` is the origin of the call (`cli`, `tui`) | Name clash in the frozen `Command` contract |
| D4 | A declined suggestion becomes `retracted` with `declined = true`; `SuggestLink` for the same (from, to, relation) then raises `SuggestionDeclinedError` ("declines are remembered"); a manual `AddLink` is still allowed. At most one live link (not retracted) per (from, to, relation) | Brief 7.3. The status list has no `declined` value, so the flag carries it |
| D5 | Link counts live in `cur_link_counts` (a generated table), not as columns on `cur_core_record` (the plan said "on `cur_core_record`") | The golden DDL for `cur_core_record` equals build spec 03 §9; adding columns would change a frozen contract. The counts table joins, sorts and filters the same |
| D6 | Only an `active` link satisfies an expected link; `suggested`, `stale`, `broken` do not. The record at the other end must exist and not be voided | A stale pin or a broken reference needs attention before the guard passes |
| D7 | Pins: `pin` is a revision label or null (floating). `Link.Repinned` sets it and returns a stale link to active; the stale-by-revision API is a command (`MarkPinsStale`, T02) that flags active pinned links whose pin differs from the revision just issued. Revisions become real with documents (P1); nothing calls it yet | Brief 7.3 |
| D8 | Counters are ledger streams `numbering:<scope>:<pattern>:<prefix>` projected to `cur_numbering`; the allocation event is appended in the creating transaction. Gap-free (default) means a number is only allocated inside the transaction that creates the record it names; a pattern with `gap_free: false` may also be allocated standalone (bulk use) and then can leave gaps. Reserved ranges: a pattern's `reserved` list is skipped by the allocator; handing ranges out (`reserve_range`) is a stub that raises `NotAvailableError` | Q7 is open in the brief; this is the smallest reading that makes the option testable. Flagged for orchestrator review |
| D9 | Numbering config is a YAML file (`schema/fixtures/numbering/patterns.yaml`, under `TL_SCHEMA_DIR`); `{project}` comes from the scope, `{type}` from the pattern's `type_code`, other fields from `CreateRecord.numbering`. Field values are letters and digits only (so keys can be read back and detected). A hand-typed key that equals the next number is skipped, not an error | Settings become ledgered in P0-I8; until then a file |
| D10 | Workflow definitions: `schema/fixtures/workflows/*.yaml`; expected links: LinkML-shaped files in `schema/fixtures/links/*.yaml` read as plain YAML; both found through `TL_SCHEMA_DIR`. Hand-written pydantic models, not generated from LinkML (a discriminated union of guards does not generate cleanly) | Same directory convention as the schema packages; the schema registry reads only top-level `*.yaml`, so subdirectories are safe |
| D11 | A record whose `status` is null is in the workflow's `initial_state`; creation does not emit a transition. `Workflow.Transitioned` goes on the record's own stream, so the record's `version` advances; `WorkflowProjector` updates `status`, `version`, `last_seq`, `updated_at`, `conformance`, and `cur_workflow_state` (workflow, version, state, `entered_at`, transition, actor) | `state_entered_at` is not a column of `cur_core_record` (same reason as D5) |
| D12 | Roles are a stub: `TransitionWorkflow.actor_roles` is a list given by the caller; the `roles` guard passes when it intersects `any_of`. Nothing verifies the list until auth exists | Brief 8 (auth is a human gate); recorded here and in the package README |
| D13 | The `expected_links` guard checks the record type's expectations whose `by_state` equals the target state; the `conformance` guard evaluates the record against the effective schema in the target state | Brief 7.1 and 6.3 |
| D14 | T05 was built by the supervisor instead of dispatched | The allocator needed it at once |
| D15 | `pyyaml` added to `tl-core` dependencies (already in the lock through `tl-schema`) | Core reads YAML definitions |
| D16 | Voiding a record does not yet flag its links stale (brief 7.3 health check) | Needs a rule hook in the void handler; follow-up |
| D17 | Overflow past the declared width (`P1-REC-10000` for `{seq:4}`) is allowed and sorts lexically before `9999`; `Pattern.parse` accepts only the canonical spelling (no `P1-REC-00012`). Gap-free holds only if a failure leaves the `with open_uow` block (an exception swallowed inside commits the number) | Orchestrator review of the allocator |
| D18 | A `broken` link has no direct route back to `active`: flag it `stale`, then repin, or retract | Brief 7.3 makes `broken` a health-check outcome; the check does not exist yet |
| D19 | Reviewed T03 and T04 judgement calls confirmed: the counts upsert rewrites `scope` from the record; a self-link (which the commands refuse) refreshes counts once more and counts once under `direction: either`; an empty expected-links file declares nothing; a duplicate state name is reported once per repeated occurrence | Batch 1 review |
| D20 | TUI keys: `Ctrl+P` and `:` palette; `l` link; `R` add to the reference tray; `F4` open the tray (a modal, not a panel); `w` workflow menu; `t` trace tab; `Alt+Left/Right` history; `1`-`5` record-view tabs; `Ctrl+T` ticks a record in the picker (`Space` types a space in the search box). App-level keys are ignored under a modal. Textual's built-in palette is disabled | Brief keys that exist in the sketches, adapted to what a text box allows |
| D21 | The reference tray is session state in `TlApp` (not saved between sessions in Phase 0). `OpenRecord(follow=True)` extends the back/forward trail; opening from the grid, `[` `]` or a new record starts a new trail; the header breadcrumb shows the trail | Brief 7.2/7.5; persistence needs a user store |
| D22 | Link counts and the state-entered time reach the record view through `ClientInterface.link_counts` and `workflow_status` (joins in the services), shown as header badges (`since <time>`, `N links`, `N stale`, `N suggested`). A grid column for link counts waits for the query language (P0-I4), which needs sorting and filtering on them | Orchestrator ruling on D5/D11 |
| D23 | `NewRecordForm` takes a blank key and lets the numbering service allocate it | Brief 8 |
| D24 | T12 review: Textual delivers `Select.Changed` after a programmatic change, so a reentrancy flag cannot tell the picker's own change from the user's; the picker now stores the relation it chose (`_auto_relation`) and treats a `Changed` with another value as the user's. The defect was in the ticket text, so the supervisor fixed it and added a test with a second record type | Review of T12 |
| D25 | T00 built by the supervisor as a composition of the existing handlers (`services/edit.py`): `EditRecord` carries field `changes` and `pset_edits`; the parts run in order in one unit of work with one `expected_version`, chained versions and one correlation id; a part that changes nothing is skipped and an edit that changes nothing raises `NoChangesError`. `ClientInterface.edit_record`, the embedded and fake clients and `save_record_edits` use it, so a form save is all or nothing (the edit form no longer reports a partial save). The idempotency key is still ignored | P0-I2 decision B16 follow-up |

## Order of work (relay rounds)
| Round | Ticket batch | Supervisor work in the same turn |
|---|---|---|
| 1 | T01, T03, T04, T08 | Plan; schema; lifecycle; T05, T06; stubs, provided tests, fixtures; trunk merge |
| 2 | T02, T03b, T07, T10 | Merge batch 1; T09 engine and `WorkflowProjector`; `ClientInterface` additions, fake and embedded client; review fixes |
| 3 | T11, T12, T13, T15 (TUI) | Merge batch 2; TUI wiring, stubs, provided tests; key map; snapshots for the new tabs |
| 4 | T13b, T14a, T14, T02b | Merge batch 3; T00 atomic edit (built before dispatch, D25) |
| 5 | T16 | Merge batch 4; demo, docs, report |

## Risks and escalation triggers
- Numbering semantics (D8) is a reading of an open question (Q7). If the orchestrator rules differently, `numbering/config.py` and the allocator change; the stream design does not.
- `schema/**` changes: S1 (core LinkML) and the three fixture directories are listed under SCHEMA_APPROVALS.
- A change to a frozen `03` §7 contract (`Command`, `CommandResult`, `UnitOfWork`): `CreateRecord` gained the optional field `numbering` (additive); stop with BLOCKED for anything else.
- Postgres: the new projectors use portable SQL and the allocator relies on the ledger's expected-version check instead of a lock; none of it is executed on Postgres until P0-I5.
- `ClientInterface` growth touches every TUI test double; additions are made once, in round 2, before TUI tickets are cut.

## Blocked / Decision
(none)
