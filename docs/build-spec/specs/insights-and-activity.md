# Spec: the Activity and Insights record tabs

Status: design v0.1 (proposed), 2026-11-07. Owner request: `OWNER-2026-11-07-insights.md` (parts A and C).
Part B (providers, router, storage, telemetry) is `docs/adr/0028-insight-providers-routing-telemetry.md`.
Nothing here is built. Each element says what the code has (Have), what is missing (Gap) and what to build (Build).
Checked against trunk, plus `p2/i2` for constraints (ADR-0024), readiness and intent (ADR-0025).

## A0. Two tabs, kept apart, and the keys they take
| Tab | Looks | Key | Replaces |
|---|---|---|---|
| Activity | Back: what happened | `4` and `h` (as today) | History |
| Insights | Forward: what could happen next | **`9`**, and `I` in a log (open at Checks) | new |

Record tab keys today: `1` Details, `2` Properties, `3` Links, `4` History, `5` Trace, `6` Files, `T` Thread
(`record_view.py` bindings). Taken by specs: `7` Locations (drawings panel), `8` Graph (graph-views). So `9` is the next
free key. Log toggles follow the capital-letter pattern (`L` locations, `G` graph, `I` insights). The keymap and
`OWN_KEYS` tests check every key; nothing else may take 7, 8 or 9.

## A1. Activity: the past only
| Owner ask | Have | Gap | Build |
|---|---|---|---|
| Replace History, keep a "Revisions only" view | `RecordView` History tab, `record_text.history_columns/cells`, `ClientInterface.history`, `GET /records/{id}/history`, `queries.record_history` (own stream, viewer-filtered) | One stream only | `Revisions only` = today's list, same rows |
| Every event: edits, moves, links, files, thread posts | Edits and moves are on the record's stream. Threads are the stream `thread:<id>`; links and files have their own streams; `outbox_events` has one row per event with an indexed `subject_id` | No read joins these | `queries.record_activity` merges the streams (A1.2) |
| Proposals filed, accepted, rejected, by whom | `cur_proposals` (agent, `created_at`, `decided_by`, `decided_at`, reason); `Proposal.*` events | No column says which record a proposal is about | Side table `cur_proposal_subjects` (proposal, record): a projection rebuilt from the ledger, using the id scan `confidentiality.names_hidden_record` already does |
| Constraints raised and cleared | ADR-0024 events carry `subject_id` (wave 2, not on trunk) | Reads need the subject | Read through `cur_core_constraint.subject_id` after wave 2; before it, no rows |
| Readiness evaluations | `IWP.ReadinessEvaluated` is on the IWP's own stream (wave 2) | The payload lists every check | One line: "Readiness checked: 5 of 7 ready" |
| Intent "why" as a column | ADR-0025 (proposed): `intent` column on `events` | Not built; lands after wave 2 | `why` shown when set; the column drops out while no row has one |
| Related activity, marked | `links_of`, link relations | No read of linked records' events | A1.3 |
| Hidden absent | `filter_events`, `is_hidden` | Needs tests on the new read | Twin and walking tests (C3) |
| Doorway to "show in graph" and intent chains | Graph tab `8`, `G` (graph-views) | Not built | Nothing now; Enter on a row opens the record |

### A1.1 What one Activity row holds
| Field | Source | Plain text |
|---|---|---|
| When | event `recorded_at` (proposals: the proposal event's time) | `2026-11-07 14:02` |
| Who | `actor`; for a proposal the agent and the person who decided | `Maria Lee`, `Agent: planner`, `Agent: planner, accepted by Maria Lee` |
| Kind | event type prefix: `Record.`, `Pset.`, `Workflow.`, `Link.`, `File.`, thread, `Proposal.`, `Constraint.`, readiness | Change, Move, Link, File, Post, Proposal, Constraint, Check run |
| What | `event_label` and `event_summary`; new types fall back to `humanize` | `Moved to Ready`, `Constraint raised: Permit`, `Proposal accepted` |
| Why | `intent.why`; for a proposal row the intent of its Created event | text or `—`; a hidden record it names reads "not available" |
| From | `—` for the record's own events; the linked record's number for related rows | `↳ P123-RFI-0328` |
Technical mode adds the event type and version, as the History table does today. Order: newest first.

### A1.2 The read: `record_activity`
One core query, one `ClientInterface.activity(record_id, *, revisions_only, related)`, one route `GET /records/{id}/activity`.
1. If the record is hidden, answer `[]` exactly as `record_history` does.
2. Own events: the record stream, `thread:<id>`, link events with this record at either end, file events, the
   proposals in `cur_proposal_subjects`, the constraints whose subject it is.
3. Run `filter_events` over the merged list (hidden streams and events naming hidden records go).
4. Page by `recorded_at` and event id; the TUI asks for 120 rows first (P2-PERF window).
5. Reads are not logged: the query writes nothing, not even telemetry.

### A1.3 Related activity
Only events on a record linked to this one by a relation that carries cause: `blocks`, `blocked_by`, `targets`,
`targeted_by`, `resolves`, `resolved_by`. One hop. Only these kinds: workflow moves, answers and responses, constraint
cleared, proposal accepted. The viewer filter runs at the link (hidden if either end is hidden) and again on the linked
record's events. A hidden linked record leaves no row, no gap and no count. Related rows carry `From`.
Example: the RFI that a constraint targets is answered, and the constraint's record shows "RFI answered" as related.

### A1.4 Filters (keys in the tab; the builder checks them against the keymap test)
`v` Revisions only (the record's own stream and nothing else, byte-identical to today's History), `r` related on or off
(default on), `/` text filter. The tab title shows the active filters. At a narrow width the table drops `Kind`, then
`From`, then shortens `What`, and `Why` last (`layout.DROP_FIRST`).

## A2. Insights: what could happen next
A tab on every record with four subtabs; Left and Right switch them (digit keys are record tabs).
| Subtab | Shows | Now | Later |
|---|---|---|---|
| Checks | Exact findings, always current | Filled (below) | More providers (roadmap 1) |
| Suggestions | Pending items: Accept `y`, Dismiss `x`, confidence High, Medium or Low, source records | "Suggestions are not available yet." | Roadmap 7 |
| Analysis | Asked analyses, running or done, each with sources; `n` asks a new one | "Analyses are not available yet." | Roadmap 11 |
| Ask | A conversation about this record, following the selected row like the drawings panel | "Ask is not available yet." | Roadmap 12 |
Opening one of the three "not available yet" subtabs writes one `unmet` telemetry row (ADR-0028), so demand is counted
from day one. Accepting a suggestion or analysis files a proposal or command whose intent `why` cites it.

### A2.1 Checks: sources, today and after
| Finding | Source | Trunk now | After wave 2 | After the intent slice |
|---|---|---|---|---|
| Readiness (blocked, pending, unknown) | `cur_awp_readiness`, results with `resolve_via` | No | Yes, IWPs | same |
| Open constraints | ADR-0024 `cur_core_constraint` | No | Yes, any record | same |
| Missing expected links | `ClientInterface.expected_links` | Yes | Yes | same |
| Overdue response clocks | correspondence `list_clocks` | Yes | Yes | same |
| Shortages | materials `views` and `reports` | Yes | Yes | same |
| Stale pins, orphaned links | `list_stale_links`, `list_orphaned_links` | Some types | Yes | same |
| "Why this is open" (the intent that raised it) | ADR-0025 `intent.why` on the raising event | No | No | Yes, a line under the finding |
Data health (missing owner, stale draft, orphan link) is roadmap item 1, not part C.
One shape for all: `CheckFinding` {source, subject_id, state word, text, since, severity, `resolve_via` records}. It mirrors
the frozen readiness `CheckResult`, so wrapping readiness is a copy. The list shows only what needs attention, grouped by
source; with none it says "Nothing needs attention." Checks are never labelled as suggestions or as machine output.
**Leak to close in the build:** a readiness result is computed once, with no viewer, and its `detail` text may name
keys. For a viewer the tab keeps the state word and counts (as ADR-0024 does for constraint counts), drops hidden
`resolve_via` records, and replaces `detail` with a fixed line when any were dropped. The orchestrator confirms (Q5).

### A2.2 Attention in logs and panels
| Place | Shows | Build |
|---|---|---|
| Log row | A `!` mark when the record has findings; filter key `n` "Needs attention" | `ClientInterface.attention_counts(record_ids)`, one batched read per window, off the UI thread (P2-PERF); base `LogScreen` gets the column and the key |
| Panel | A line `Needs attention  2 findings` under the summary; `I` opens the record at Insights, Checks | a `layout.Page` row and a `LogAction` |
The marker counts only what the viewer can read, so it is in the twin test.

## A3. Rules for both tabs
- Plain words by default, ids only in technical mode (`display.find_technical` walk). No model type or provider is named.
- Everything is computed for, or filtered for, the viewer. Hidden looks like missing, in retrieval too.
- Nothing acts alone. Accept files a proposal or command with intent `why` citing the sources; the insight's own id is
  never written to the ledger (ADR-0028).
- Shown, dismissed and expired suggestions go to telemetry, never to Activity. Activity shows an accepted one only as
  the proposal or command it filed.

## C. Part C: pieces, sizes, slot
S = builder piece, H = ticket (the sizes the roadmap uses). IDs are working names.
| ID | Piece | Size | Needs | Gate |
|---|---|---|---|---|
| INS-A1 | `record_activity`, route, `ClientInterface.activity`, both clients, `cur_proposal_subjects` | S | wave 2 merged; intent optional | core interface and schema: orchestrator, APPROVALS line |
| INS-A2 | `activity_text.py`: columns, words, why, related mark (pure) | H | A1 contract | none |
| INS-A3 | Activity tab replaces History: filters `v` `r`, keymap, README, `test_plain_walk` | H | A1, A2 | none |
| INS-A4 | Walking and twin tests of tab and route | H | A1 | none |
| INS-B1 | `CheckFinding`, `record_checks`, `attention_counts`, routes, `ClientInterface.checks`, both clients; five sources | S | wave 2 merged | core interface: orchestrator, APPROVALS line |
| INS-B2 | Insights tab: four subtabs, Checks list, three "not available yet" lines | H | B1 | none |
| INS-B3 | Log `!` column and `n` filter in `LogScreen` | H | B1 | none |
| INS-B4 | Panel "Needs attention" line and `I` action | H | B1 | none |
| INS-B5 | Walking and twin tests of Checks and the marker | H | B1 | none |
| INS-T1 | `schema/core/telemetry.yaml`, `tl_core.telemetry.note_need`, retention, parity test, no reader | H | none | schema: orchestrator, APPROVALS line |
| INS-T2 | `ClientInterface.note_need`; the three subtabs write `unmet` | H | B2, T1 | core interface (same line as B1) |
Total: 2 S + 9 H, about 4 weekly points (1 per S, 0.25 per H, the calibration of the other roadmap rows). Cheapest cut:
B3 and B4 (marker and panel line), 2 H.

**Slot (recommended).** Right after the wave 2 merge, in the gap that holds the ADR-0025 slice (plan check F13: after the
wave 2 close, before wave 3), beside the demo generator. A1 and B1 touch `tl-core`, `tl-api`, `tl-tui`; the generator
touches `dev/seed`; the TUI release touches packaging. Order: T1, then A1 and B1 together, then A2 to A4 and B2 to B5,
then T2. One APPROVALS line covers the interface changes (A1, B1, T2), one the T1 schema. ADR-0025's "TUI History display"
ticket folds into A3 (saves 1 H there; Trace display stays). It does not delay wave 2 (starts after it), the generator or
the release (the History tab stays until A3 merges; if Part C misses the release freeze, the release ships History and
Activity follows), or waves 3 and 4. If the slice is at baseline + 9 points, Part C waits one slice.

### C3. Confidentiality, walking and twin tests (A4, B5)
- Walking: for every reader the existing walks use, ask the activity and checks routes for a visible, a hidden and a
  missing id; hidden equals missing (same body).
- Twin, Activity: record X linked to a hidden record H versus X without the link: identical rows, order, counts. The same for
  a constraint whose target is hidden (row stays, no target) against a no-target twin, and a proposal naming H.
- Twin, related: a linked record's events vanish for a viewer who cannot read it, at the link and at the events.
- Twin, Checks: a hidden RFI that a constraint targets, versus none: equal findings and attention counts.
- Intent: a `why` that names a hidden record reads "not available" (ADR-0025 d.5); `why` text is never filtered.
- The tab and routes write nothing (read-only test on both adapters).

## Open owner questions
| # | Question | Default |
|---|---|---|
| Q1 | Related activity on by default? | Yes, marked, one hop |
| Q2 | Should Activity show who looked? | No: reads are not logged |
| Q3 | Insights key `9`, `I` in logs | As written |
| Q4 | Agent activity view (agent-first 3.6) and this tab: one read or two | Two; they share `cur_proposals` only |
| Q5 | Readiness detail for a viewer who cannot read some blockers | Keep state and counts, drop hidden records, fixed text |
The four policy questions (spend, restricted data, Ask transcripts, learning) are in the roadmap entry.

## Plan check (2026-11-07)
All twelve findings are accepted; the answers in ADR-0028 win over this spec. Part C is now the two tabs plus the
telemetry stub: 2 S (A1 Activity read with its walking test; B1 Checks read with the telemetry table, `note_need` and its
walking test) + 4 H (A2 lite; A3, B2 and the twin tests full). The log marker, `!` filter, panel line and
`attention_counts` move to roadmap item 1. There is no `cur_proposal_subjects`. Screen-opened telemetry holds
`record_type` only. Activity pages over `outbox_events`. Keys: `9` for Insights, `!` for the log filter, never `n` or `I`.
