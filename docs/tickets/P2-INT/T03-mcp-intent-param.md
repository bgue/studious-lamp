# P2-INT-T03 — MCP `intent` parameter on write and propose tools

Status: staged (release after S2 merged)
Tier: haiku
Review: full
Labels: mcp
Depends on: S2 merged
Branch: `p2/int-t03-mcp-intent-param`

## Goal
An agent can give the reason with a write or a proposal. After this ticket every hand-written write and propose tool has an optional `intent` object parameter, passed into the command it builds; a proposal stores it the S2 way (Created event column). An agent intent grants no authority.

## Brief references (pasted)
> ADR-0025 d6: "An agent supplies an intent exactly as a person does. For an agent proposal the intent is part of the stored command; ... An intent never grants authority." d4: validation is the server's one function; the tool does not re-check beyond JSON type.
> ADR-0027 F9: a proposal's intent goes in the Created event's `intent` column, not the payload; `evidence` is deferred (the parameter schema has no `evidence`).

## Interfaces
Tool parameter (JSON schema, shared constant `INTENT_PARAM` in `tl_mcp/intent_param.py`, create): an object with the four optional keys and the ADR limits as `maxLength`/`maxItems` (documentation for the agent; the server enforces). Each `*_impl` gains `intent: dict | None = None` and passes `intent=intent` into the command model (`Command.intent` accepts a dict).

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/write_tools.py` (`create_record_impl`, `register_write_tools`), `awp_tools.py`, `correspondence_tools.py`, `derivation_tools.py` (the `propose_*_impl` pattern), `packages/tl-mcp/src/tl_mcp/materials_tools.py` if present
- `docs/tickets/P2-INT/S2-intent-boundary.md` (Interfaces and Proposal path)
may explore: the closed `MCP_ACTIONS` list (no new action: no new tool).

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/intent_param.py` (create), the tool modules listed in Context (parameter and pass-through lines only), `packages/tl-mcp/tests/test_intent_param.py` (create), `docs/reports/P2-INT/T03.md` (create)
Consequential pins (rule 12): tool-schema snapshots that break only for the new parameter are updated and listed. No new tool, no new action, no schema.

## Acceptance
```
just check
just gate packages/tl-mcp/tests
```

## Tests to add
`test_intent_param.py`: a write tool and a propose tool with an intent store it (read back the Created event column and the appended event column); a bad intent returns the fixed `intent_invalid` text; an agent intent does not change an access refusal.

## Report requirements
Standard plus the list of tools changed and pins updated.

## Escalation triggers
- Stop and report *Blocked* if a tool builds its command without the dispatcher path S2 listed as carrying the intent, or if more than the modules in Context need edits.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
