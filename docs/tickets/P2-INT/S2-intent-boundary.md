# P2-INT-S2 — Intent at the command boundary: validation, carrier, API reads, proposals, confidentiality walk

Status: ready (starts after S1 merged)
Tier: sonnet
Kind: piece
Review: full
Labels: core, api, security
Depends on: S1 merged
Branch: `p2/int-s2-intent-boundary`  (from p2/int at the state commit after S1; check `git rev-list --left-right --count p2/int...HEAD` is `0 0`)
Approver: orchestrator, with an APPROVALS line. Sec row: intent references (hidden = unknown; no leak through error, count, key or timing of resolution).

## Goal
An intent is accepted, checked, stored and returned. After this piece: `check_intent(command)` (the one S1 function) validates sizes and references for the actor
and normalises; the one dispatcher sets a ContextVar that `append_in` of both adapters reads, so no handler changes; the API envelope accepts `intent`; event, history
and trace reads return it with unreadable references shown as "not available"; an agent proposal stores the intent in the `Proposal.Created` event's `intent`
column (not the payload) and accepting runs the command with it; the confidentiality walk covers it. The temporary S1 refusal and its test are removed.

## Brief references
> ADR-0025 d4 (validation: limits; each reference resolves like a link end for the actor; unknown and hidden give the same code `intent_reference_unknown` and
> fixed message; ids stored, keys resolved at write time; `toward.state` must be a workflow state of the target when it has one, else `condition`; `next.command` a registered
> command name, not permission-checked; bad intent refuses the whole command, `intent_invalid`), d5 (visible exactly when the event is; unreadable reference inside a visible event
> shown as "not available", no key, title or differing count; `why` never filtered by words), d6 (agent proposal: intent part of the stored command, actor = accepting person, agent named as today; an intent grants no authority), d7 (reads).
> Answers F3 (ContextVar like effective time; `append_in` reads it), F14 (normalise `{}`/all-null to None), ADR-0027 F9 (proposal intent in the Created column, `evidence` deferred, an unreadable evidence id is Phase 3).
> AGENTS.md never-list: class filter on every read; a new route or feed that can carry record text needs a five-reader walking test.

## Interfaces
```python
# tl_core/intent.py (S1 file; this piece replaces the body of check_intent and adds the rest)
def validate_intent(conn, command, *, viewer) -> Intent | None   # sizes (why 500, next <=5, text 200, condition 200, goal_ref ^[a-z0-9_-]{1,64}$, canonical <=4000 bytes), refs, states, command names; {} -> None
def check_intent(command, conn, viewer) -> Command               # returns the command with the validated, id-resolved intent (or None); raises IntentInvalid / IntentReferenceUnknown
class IntentReferenceUnknown(ValueError): code = "intent_reference_unknown"   # message fixed: "intent reference not found"
def intent_scope(intent: Intent | None) -> ContextManager[None]  # sets _INTENT ContextVar (like util.effective_time); nesting restores; None clears
def current_intent() -> Intent | None
def redact_intent(conn, intent: Intent | None, viewer) -> IntentView | None   # refs the viewer cannot read -> text "not available"
# Adapters' append_in: NewEvent.intent if set, else current_intent(); the same value goes to the column and to event_hash.
# API: the command body gains optional `intent`; Event read models (event, history, trace) gain `intent: IntentView | None = None`.
```
The carrier is set ONLY by `run_command` (`tl_api/commands.py:312`, inside the same `with effective_time(...)` line) and by the proposal accept path in `tl_api/routes/proposals.py` (the sites that already
use `effective_time`; `grep -rn "effective_time(" packages/*/src` lists them). Entries that call handlers without these (simulator, rule and integration runners, jobs, CLI embedded paths that bypass `run_command`)
keep writing NULL intent; list each in the report, do not extend them. A proposal's `Proposal.Created` and `Proposal.Accepted` events themselves carry no ContextVar intent except the Created one set explicitly.

## Proposal path
`services/proposals.py` (~line 470, the `uow.append` of `PROPOSAL_CREATED`): `stored.model_dump(mode="json", exclude={"intent"})` into `payload["command"]`; `NewEvent(intent=<validated intent>)`. The accept path re-reads the intent from the Created event
(`ledger.read_stream(proposal_id)` version 1, `.intent`; the proposal projection is NOT changed: no schema) and runs the command inside `intent_scope(...)`. A proposal listed to a viewer shows the intent through `redact_intent`. Test: payload has no `intent` key; accept events carry the same intent; actor is the accepting person, agent named.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/intent.py` (S1), `util.py` (`effective_time` precedent), `services/commands.py`, `services/proposals.py` (create/accept, ~lines 440-560 and the accept runner), `confidentiality.py` (Viewer, `hidden_row_ids`, link-end visibility helper used by `links`)
- `packages/tl-core/src/tl_core/links/` (how a link end is resolved and hidden: reuse that function for a reference), the workflow state lookup used by `Workflow.Transitioned` handlers, `command_index()` / `command_table()` (registered command names)
- `packages/tl-api/src/tl_api/commands.py` (`run_command`, `_make_endpoint`, the body build ~line 243-282), `routes/events.py`, `routes/records.py` (history, trace reads), `routes/proposals.py`
- `packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-mcp/tests/test_confidentiality_walk.py` (pattern, `MIN_ROUTES`), `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py` / `postgres/ledger.py` (`append_in`)
may explore: `docs/reference/` openapi regeneration recipe, the five-reader fixture helper in the walk tests.

## Allowed paths
- `packages/tl-core/src/tl_core/intent.py`, `services/proposals.py`, `ledger/types.py` (view model only if needed), `util.py` only if the carrier lives there (prefer `intent.py`)
- `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py`, `postgres/ledger.py` (the `current_intent()` read, 2 lines each)
- `packages/tl-api/src/tl_api/commands.py`, `routes/events.py`, `routes/records.py`, `routes/proposals.py`, `models` files that define the event read models, `docs/reference/openapi.json` (regenerate), `docs/reference/` event envelope page (one field)
- `packages/tl-core/tests/`, `packages/tl-api/tests/`, `packages/tl-mcp/tests/test_confidentiality_walk.py` (rows only), `packages/tl-api/tests/test_command_refuses_intent_until_s2.py` (delete)
- `dev/accept/P2-INT/S2.py` (create), `docs/reports/P2-INT/S2.md` (create)
Consequential pins (rule 12): openapi, route/model-list and event-envelope snapshots that break only for the new field are updated and listed. No schema/** change, no module handler change, no projection table change, no migration.

## Acceptance (once; named paths only)
```
just check
just gate packages/tl-core/tests packages/tl-api/tests packages/tl-mcp/tests packages/tl-adapters/tests
just gate-pg packages/tl-adapters/tests packages/tl-api/tests
uv run python dev/accept/P2-INT/S2.py --keep .accept/p2-int.db
```

## Tests to add
- `packages/tl-core/tests/test_intent_validation.py`: each limit at the bound and one over; control characters and NUL; `{}`, `{"why":null}`, `{"next":[]}` -> None; `toward` state vs condition; unknown `next.command`; keys resolved to ids and stored as ids; key rename does not break a stored reference.
- `packages/tl-core/tests/test_intent_carrier.py`: ContextVar nesting, thread and task copy, `append_in` stores and hashes the carrier value; an explicit `NewEvent.intent` wins; no carrier -> NULL and the old hash.
- `packages/tl-api/tests/test_intent_commands.py`: end to end on two commands of different modules with no handler change; `intent_invalid` and `intent_reference_unknown` HTTP codes; the whole command refused, nothing appended; an intent changes no access decision (same command with and without gives the same 403).
- `packages/tl-api/tests/test_intent_proposals.py`: the Proposal path above.
- **Walk, five kinds of reader** (`packages/tl-api/tests/test_intent_walk.py`, plus rows in the existing two walks): (a) hidden record id and unknown id as `toward.target` and `next.target` give byte-identical status, body and timing class; (b) an event on a hidden stream is absent with its intent (history, trace, events list, count); (c) a visible event with an intent referencing a restricted record shows "not available", never key, title or count difference; (d) `why` containing a hidden record's key is shown unchanged; (e) lake and webhook thin payload leave intent out for non-internal records (S1 lake test re-run with a real command).
- `dev/accept/P2-INT/S2.py`: demo clauses 1, 4, 5, 6, 7 on one scratch database.

## Mutants (builder, own worktree, 3 lines)
Sentinel plus at most 5: unknown and hidden give different codes; `redact_intent` skipped on history; carrier not cleared after the block; proposal payload keeps `intent`; `{}` stored as text.

## Report requirements
Standard (≤ 60 lines) plus: the entry points that bypass the dispatcher (named), consequential pins, any `evidence` hook left out (deferred by ADR-0027 F9). Candidate learning: the carrier rule for envelope fields.

## Escalation triggers
- Stop if a reference check needs a new read path that does not use the viewer filter, if a handler or schema must change, or if the proposal projection needs a column.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
