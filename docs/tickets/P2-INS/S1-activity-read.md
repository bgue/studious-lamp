# P2-INS-S1 — Activity read: `record_activity`, route, `ClientInterface.activity`, both clients, walking test (INS-A1)

Status: ready (hold until the orchestrator dispatches; base `p2/wave2-close`)
Tier: builder
Kind: piece
Review: full
Labels: core, api, tui, tests
Depends on: wave 2 close (on the base). Intent "why" is NOT on the base (ADR-0025 slice not landed): `why` is `None` on every row and the column drops out in the screen
Branch: `p2/ins-s1-activity-read`
Worktree: `/home/user/wt/ins-s1` (from `p2/ins` head)
Approver (interface): orchestrator, one APPROVALS line with S2 (`ClientInterface.activity`, route `GET /records/{id}/activity`). No schema change in this piece.

## Goal
After this piece one read answers "what happened around this record": its own events, its thread, link and file events, the
proposals that name it, the constraints raised on it, readiness evaluations, and (marked related, one hop) causal events of linked records.
Every row passes the viewer filter at every hop. The read writes nothing. There is no `cur_proposal_subjects` (plan check F5).

## Brief references (pasted; spec `docs/build-spec/specs/insights-and-activity.md` A1, plan check answers F3 F5 F6 F8 F12 win)
- Hidden looks like missing: a hidden or unknown record answers the same 404 body as `GET /records/{id}/history` today; embedded and fake clients return an empty page for both.
- Own events, from `outbox_events` (one row per event; indexed `scope`, `subject_id`; NOT indexed on `stream_id`), newest first, paged by `seq` (`before_seq`, `limit` default 120, max 200):
  1. rows with `subject_id = <record id>` (the record stream, its files, constraints raised on it if their subject is the record, readiness events of an IWP; the builder reports which `subject_id` the thread, file and constraint events carry and uses `stream_id`/`related_ids` only where subject is not the record);
  2. thread events: stream `thread:<record id>`;
  3. link events where the record is the `to` end: ids from `cur_links` (`to_id = :id`, newest `updated_at`, at most 200 links per call), then `outbox_events WHERE subject_id IN (<from ids>) AND stream_id IN (<link ids>)` so the `subject_id` index serves it; links with `from_id = :id` are already in (1);
  4. proposals: accepted ones through `cur_proposals.result_stream_id = :id`; pending and rejected ones through a scope-bounded match on the stored command (`scope = :scope AND CAST(command AS TEXT) LIKE '%<id>%'`, at most 50, dialect-neutral SQL, no table scan outside the scope), then their `Proposal.*` events by `subject_id = <proposal id>`; `filter_events` runs on them (the proposal stream is already in `SCANNED_STREAM_TYPES`).
- `revisions_only=True`: the record's own stream only, the same events in the same order as `queries.record_history` (assert equality in the test). `related=False`: no related rows.
- Related rows (default on, one hop, plan Q1): far-end records over `cur_links` with `status = 'active'` and relation in `blocks, blocked_by, targets, targeted_by, resolves, resolved_by` (read each name as the schema spells it), at most 100 far ends; event types only `Workflow.Transitioned`, `Technical.Answered`, `Correspondence.Responded`, `ResponseClock.Met`, `Constraint.Cleared`, `Proposal.Accepted`; at most 30 related rows per page. The far end is dropped when either end of the link is hidden (`confidentiality.not_hidden_each` on both ends, in SQL, before any event is read) and the linked record's events go through `filter_events` again. Dropped means no row, no gap and no count.
- Filter before LIMIT, then refill: select candidates by `seq` desc, `filter_events`, repeat until `limit + 1` visible rows or no candidates, at most 5 rounds and 1000 candidates scanned per call. When the cap stops a call, return what was found and a cursor; that is the only case where a page may differ from its twin and the twin test stays under the cap.
- Statement count: a call issues at most N SQL statements however many rows it returns; the builder measures N on the walking test data (500 own events, 40 links, 20 proposals) and pins it with a SQLAlchemy `before_cursor_execute` counter, and pins that doubling the rows does not change N.
- Reads are not logged: no INSERT, UPDATE or DELETE statement and no telemetry (the counter test lists statement verbs).

## Interfaces (verbatim shape; put the models in `tl_core/insights/types.py`, which S2 also uses; S2 creates no model in it before this merges, so write only these)
```python
ActivityKind = Literal["change", "move", "link", "file", "post", "proposal", "constraint", "check"]

class ActivityRow(BaseModel):
    event: Event                      # the ledger event (A2 reuses record_text.event_label and event_summary)
    kind: ActivityKind                # from the event type prefix; unknown types are "change"
    related: bool = False             # true for a row of a linked record
    from_id: str | None = None        # the linked record's id when related
    from_key: str | None = None       # its display key (never given for a hidden record: such rows do not exist)
    why: str | None = None            # None until ADR-0025
    decided_by: str | None = None     # proposal rows: the person who accepted or rejected
    note: str | None = None           # readiness rows: "5 of 7 ready"; None otherwise

class ActivityPage(BaseModel):
    rows: list[ActivityRow]           # newest first
    next_before_seq: int | None       # None when nothing older remains

# tl_core.insights.activity
def record_activity(uow: UnitOfWork, record_id: str, *, revisions_only: bool = False,
                    related: bool = True, before_seq: int | None = None, limit: int = 120) -> ActivityPage: ...
# ClientInterface (client.py, after `history`), embedded.py (after `history`), remote.py, tl_api.client (new file client/activity.py), FakeClient (after history)
def activity(self, record_id: str, *, revisions_only: bool = False, related: bool = True,
             before_seq: int | None = None, limit: int = 120) -> ActivityPage: ...
# route (new file tl_api/routes/activity.py, one registration line in app.py): GET /records/{record_id}/activity
#   query revisions_only, related, before_seq, limit (ge=1, le=200); `guard("record.read")` like history; 404 `record_not_found` when hidden or unknown
```
Keep `history` and its route unchanged (A3 still uses `history` for nothing, but MCP and the API do).

## Context (<= 10 files)
`tl_core/services/queries.py` (`record_history`); `tl_core/confidentiality.py` (`filter_events`, `hidden_event_streams`, `not_hidden_each`, `SCANNED_STREAM_TYPES`); `schema/core/outbox.yaml`, `schema/core/links.yaml`, `schema/core/proposals.yaml`; `tl_api/routes/records.py`; `tl_tui/client.py`, `embedded.py` (`history`), `tests/fakes.py`; `packages/tl-api/tests/test_confidentiality_walk.py` (the five readers); `docs/adr/0028` plan check F5, F6, F12.

## Allowed paths
- `packages/tl-core/src/tl_core/insights/__init__.py`, `types.py`, `activity.py` (create); `packages/tl-core/tests/insights/test_activity.py` (create)
- `packages/tl-api/src/tl_api/routes/activity.py` (create), `app.py` (one registration line), `packages/tl-api/src/tl_api/client/activity.py` (create) and the one line that mixes it into `ApiClient`
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py`, `remote.py` (the `activity` method only, placed next to `history`), `packages/tl-tui/tests/fakes.py` (`FakeClient.activity`: rows built from its `history`)
- walking test `packages/tl-api/tests/test_activity_walk.py` (create): five readers x visible, hidden, missing id on the route; hidden equals missing (status and body); the statement-count and no-write tests (both adapters through the existing parity fixture)
- `dev/accept/P2-INS/S1.py` (create), `docs/reports/P2-INS/S1.md` (create)
- consequential pins (rule 12): route lists, OpenAPI snapshot, client-method lists, `ClientInterface` conformance tests; each listed
Not allowed: `schema/**`, `tl_core/confidentiality.py`, any TUI screen or widget, `record_view.py`, MCP tools (no tool: Authorization is closed for agents; the route is denied to agent tokens by the existing default, prove it in the walk).

## Acceptance (run once each)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-INS/S1.py
just gate packages/tl-core/tests/insights packages/tl-api/tests/test_activity_walk.py packages/tl-tui/tests/test_client_conformance.py
just gate-pg packages/tl-core/tests/insights packages/tl-api/tests/test_activity_walk.py
```
`S1.py` (SQLite tmp db, <= 70 lines, final `S1 ok`): a record with edits, a move, a link (as `from` and as `to`), a file, a thread post, an agent proposal accepted and one rejected, a raised and cleared constraint: every kind appears once, newest first; `revisions_only` equals `record_history`; a related RFI answered shows once with `from_key`, and vanishes when the link is to a hidden record.

## Guards for the review and the one sentinel mutant plus at most 5 (name file:line in the report; run no sweep)
The hidden-record 404 and empty page; `filter_events` before LIMIT and refill; the far-end `not_hidden_each` on both link ends; the related event-type allow-list; the per-page caps (links 200, far ends 100, related rows 30, proposals 50, candidates 1000); the cursor (`before_seq` strict); `revisions_only` branch.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; the `subject_id` each event kind carries; the measured statement count N; the relation and event names as the schema spells them; pins; guards file:line; learnings. Builder return <= 15 lines.

## Commit
`P2-INS-S1: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the outbox cannot be read for a link or thread event without a new index or a schema change (report the query and its plan); `Event` cannot be rebuilt from an outbox row plus the ledger without a new ledger read function outside `tl_core`; the proposal match needs a dialect-specific operator; the statement count grows with rows.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
