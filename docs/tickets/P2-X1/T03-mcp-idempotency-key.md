# P2-X1-T03 — MCP write tools take an optional `idempotency_key`

Status: ready (dispatch r2; S1 merged on `p2/x1` @77e9b51)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp
Depends on: S1 (merged)
Branch: `p2/x1-t03-mcp-idempotency-key`
Worktree: `/home/user/wt/x1/t03`

## Goal
The four record-proposing tools in `write_tools.py` (`create_record`, `update_psets`, `link_records`, `transition_workflow`) and
`propose_setting_change` accept an optional `idempotency_key` and set it on the command they submit. `proposals.propose` (S1) then
answers a retry with the first proposal. The module tools in other files (punch, requisition, awp, ...) are a later ticket (T03b); do
not touch them. `post_feed` takes no key.

## Brief references (pasted)
- `proposals.submit(factory, tool=, agent=, command=, summary=)` -> `propose` calls `idempotency.check(conn, agent, command.idempotency_key,
  "propose", {"tool", "summary", "command"})`; on a replay it returns the first proposal's view, writes nothing, counts nothing
  against the daily budget's new rows. A bad key raises `InvalidIdempotencyKeyError`; reuse with another body `IdempotencyMismatch`.
- `Command.idempotency_key: str | None = None`, validated: printable ASCII without space, 1..128 (`tl_core.services.commands`).
- MCP errors are mapped by `guarded` (`tl_mcp/errors.py`). Check whether it maps `ServiceError` subclasses generically; if it needs a
  row for the three S1 errors, add that row in `tl_mcp/errors.py` (allowed, one table, <= 6 lines) and say so.
- A refused key text never contains the key.

## Interfaces (verbatim)
```python
# write_tools.py: add one alias beside Summary/ExpectedVersion and use it as the last parameter of each tool and each *_impl
IdempotencyKey = Annotated[
    str | None,
    Field(min_length=1, max_length=128, pattern=r"^[\x21-\x7e]+$",
          description="Optional. Retrying with the same key (same arguments) returns the first proposal instead of filing another."),
]
# *_impl example: create_record_impl(ctx, *, scope, ..., intent: Intent | None = None, idempotency_key: str | None = None)
#   command = CreateRecord(actor=ctx.actor, ..., intent=intent, idempotency_key=idempotency_key)
```
The four command classes (`CreateRecord`, `SetPsetValues`, `AddLink`, `TransitionWorkflow`) and `ChangeSetting` all derive from `Command`.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/write_tools.py`
- `packages/tl-mcp/src/tl_mcp/errors.py`
- `packages/tl-mcp/tests/test_mcp_write_tools.py` (helpers `propose_create`, `env`)
- `packages/tl-mcp/tests/test_mcp_setting_proposals.py` (style only)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/write_tools.py`
- `packages/tl-mcp/src/tl_mcp/errors.py` (only if the check above says a row is missing)
- `packages/tl-mcp/tests/test_mcp_idempotency.py` (new)
- Consequential pins (AGENTS rule): a tool-schema snapshot or count test that breaks only because the five tools now list one more
  optional parameter; list each in the report.

## Acceptance
```
just check
just gate packages/tl-mcp/tests/test_mcp_idempotency.py packages/tl-mcp/tests/test_mcp_write_tools.py packages/tl-mcp/tests/test_mcp_setting_proposals.py
```
Expected: pass. Name only these files; if a pin elsewhere breaks, run that one file too.

## Tests to add (`test_mcp_idempotency.py`)
- `create_record` twice with one key and the same arguments: one proposal row, both results carry the same proposal id.
- Same key, other title: refused with the mismatch text, still one proposal.
- Same key for another actor/agent: separate proposal (no collision).
- No key: two calls, two proposals (unchanged).
- Bad key (129 chars, a space): refused before anything is stored; the error text does not contain the key.
- One more tool of the five (`update_psets`) with a key replays.
- The tool's input schema lists `idempotency_key` as optional on all five tools and not on `post_feed`.

## Report requirements
Standard report; list the pins changed and whether `errors.py` was touched.

## Escalation triggers
- Stop if the replay answer differs in shape from a first answer (ProposalResult must be the same type).
- Stop if any file outside Allowed paths needs a non-pin change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
