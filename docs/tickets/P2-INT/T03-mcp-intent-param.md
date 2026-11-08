# P2-INT-T03 — MCP `intent` parameter on write and propose tools

Status: ready (S2 merged at 0fc06f1)
Tier: haiku
Review: full
Labels: mcp
Depends on: S2 merged
Branch: `p2/int-t03-mcp-intent-param`

## Goal
An agent can give the reason with a write or a proposal. After this ticket every propose tool has an optional `intent` object parameter, passed into the command it builds; the proposal stores it the S2 way (Created event column). An agent intent grants no authority.

## Brief references (pasted)
> ADR-0025 d6: "An agent supplies an intent exactly as a person does. For an agent proposal the intent is part of the stored command; ... An intent never grants authority." d4: validation is the server's one function; the tool does not re-check beyond JSON type.
> ADR-0027 F9: a proposal's intent goes in the Created event's `intent` column, not the payload; `evidence` is deferred (the parameter schema has no `evidence`).

## Interfaces
Checked at r3 against S2: every MCP write tool is a propose tool (12 `submit` calls in 8 modules, each ends in `proposals.submit(..., command=command)`). `submit` runs the S2 check and stores the intent in the Created event's `intent` column, payload without it (S2 `services/proposals.py`). So the work is parameter plus pass-through only.
```python
# tl_mcp/intent_param.py (create)
IntentParam = Annotated[Intent | None, Field(description="Why you propose this: why (<= 500 chars), next (<= 5 items: {command,target} or {text}), toward ({target,state} or {target,condition}), goal_ref. Recorded with the event; it grants no authority.")]   # Intent from tl_core.intent; no `evidence` key (ADR-0027 F9)
```
Each tool function gains `intent: IntentParam = None`, its `*_impl` gains `intent: Intent | None = None`, and the command it builds gets `intent=intent`. Tools (grep `proposals.submit(` in each file): write_tools.py (create_record, update_psets, link_records, transition_workflow, propose_setting_change), awp_tools (propose_cwp), correspondence_tools (propose_triage), derivation_tools (start_extraction, propose_import), iwp_tools (propose_iwp_scope), materials_tools (propose_reservation), schedule_tools (propose_publish_schedule_snapshot), thread_tools (propose_dispatch). A tool whose `*_impl` also serves a non-propose caller keeps the default `None`.
No new tool, no new action, no schema. The `MCP_ACTIONS` list is untouched.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/write_tools.py` (`create_record_impl`, `create_record`: the pattern) and one other tool module
- `packages/tl-mcp/tests/test_mcp_write_tools.py` (harness use), `tl_core/intent.py` (`Intent`), `docs/reports/P2-INT/S2.md`
may explore: `packages/tl-api/tests/test_intent_proposals.py` (reads the Created column back).

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/intent_param.py` (create), the 8 tool modules named above (parameter and pass-through lines only), `packages/tl-mcp/tests/test_intent_param.py` (create), `docs/reports/P2-INT/T03.md` (create)
Consequential pins (rule 12): tool-schema snapshots or tool-list tests that break only for the new parameter are updated and listed.

## Acceptance
```
just check
just gate packages/tl-mcp/tests
```

## Tests to add
`test_intent_param.py`: `create_record` and one module tool with an intent store it in the Created event column (payload has no `intent` key); accepting by a person appends events with the same intent; a bad intent returns the `intent_invalid` text and leaves no proposal; a hidden and an unknown `toward` target give the same text; an agent intent does not change an access refusal; every tool listed above has an `intent` parameter in its schema (one parametrised test).

## Report requirements
Standard plus the list of tools changed and pins updated.

## Escalation triggers
- Stop and report *Blocked* if a tool does not go through `proposals.submit`, or if a module outside Allowed paths needs edits.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
