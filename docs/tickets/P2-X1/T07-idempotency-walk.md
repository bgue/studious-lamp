# P2-X1-T07 — Walking tests: replay as five kinds of reader, cross-actor isolation, Q3

Status: ready (dispatch r3)
Tier: haiku
Kind: ticket
Review: full
Labels: tests, api, mcp
Depends on: S1, T01, T03 (merged)
Branch: `p2/x1-t07-idempotency-walk`
Worktree: `/home/user/wt/x1/t07`

## Goal
Tests only. They pin that a replay never shows a reader more than a first answer would, that keys never cross actors, and they settle
open question Q3. A red Q3 test is a finding, not something to fix here.

## Brief references (pasted)
- AGENTS.md: a new route, tool or feed that can carry record text needs a walking test as five kinds of reader. The five kinds are
  those of `packages/tl-api/tests/test_confidentiality_walk.py` (reuse its `Seed`, `seed`, `hidden_markers`, `harness` helpers by import
  or copy, whichever the file allows; copy helpers into the new file if they are not importable).
- Replay carries ids only and re-reads through the viewer filter (S1). After the actor's clearance drops, a replay of a command whose
  record is now hidden returns ids that the viewer filter hides as absent (status and text as for a record that never existed).
- Keys are per actor: the same key value from another actor neither replays nor collides.
- Q3 (T03 author): `proposals.submit` (tl_core/services/proposals.py:725) runs `_check_proposal`, then the daily budget check, then
  `precheck`, and only then `propose`, which holds the idempotency replay. A keyed retry may therefore be refused instead of replayed.
  Required cases (MCP, `create_record` tool, harness in `packages/tl-mcp/tests/mcp_harness.py`, style of `test_mcp_idempotency.py`):
  (a) an agent files with key K, reaches its daily cap (set the budget as `test_mcp_write_tools.py` does; read it for how), retries K:
      expect the first answer replayed, no error. (b) an agent files with key K, then the target record is moved or voided so `precheck`
      would now refuse, retries K: expect the first answer replayed. Write the expected behaviour; if it fails, keep the test failing
      NOT marked xfail or skipped: this is the one allowed red, listed in the report as Q3 RED with the error text. Do not edit src.

## Context (read these, at most 6)
- `packages/tl-api/tests/test_confidentiality_walk.py` (lines 1-130 only)
- `packages/tl-api/tests/test_idempotency_header.py` (harness use)
- `packages/tl-mcp/tests/test_mcp_idempotency.py`
- `packages/tl-mcp/tests/mcp_harness.py` (skim)
- `packages/tl-core/src/tl_core/services/proposals.py` (lines 459-545 and 725-755)
may explore: `packages/tl-mcp/tests/test_mcp_write_tools.py` (budget setup only)

## Allowed paths
- `packages/tl-api/tests/test_idempotency_walk.py` (new)
- `packages/tl-mcp/tests/test_idempotency_walk.py` (new)

## Acceptance
```
just check
just gate packages/tl-api/tests/test_idempotency_walk.py packages/tl-mcp/tests/test_idempotency_walk.py
```
Expected: pass, except Q3 cases if real (then `gate: FAIL` with only those named). Do not run any wider directory.

## Tests to add
API file (both adapters via the harness):
- For each of five readers: the actor sends CreateRecord with key K; the clearance drops (as the confidentiality walk does it); the same
  actor replays K: the answer contains no marker text the reader may not read, and a GET of a returned id that is now hidden answers
  exactly as for an id that never existed.
- Another actor sends K with the same body: its own record, ids differ, no 409.
- Another actor sends K with a different body: no 409 either.
MCP file:
- Cross-agent isolation (same key, two agents): two proposals.
- Q3 case (a) and Q3 case (b) above.

## Report requirements
First line: `Q3 GREEN` or `Q3 RED <case> <error text>`. List the test names.

## Escalation triggers
- Stop if a replay body contains text of a hidden record (write it under Blocked, as a security finding, with the test that shows it).
- Stop if reusing the walk helpers needs an edit outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment (orchestrator, 2026-11-14, after attempt 1)
- Q3 is fixed by S2 (merged into this branch). The two Q3 tests must now pass unchanged; if either is still red, stop and report.
- Answer 1 (five-reader walk): use option (a), a confidential extension record type via `use_modules`, as in `packages/tl-core/tests/test_idempotency.py`. Drop the actor's clearance after the first filing; the replay must return ids the viewer filter hides as absent (same answer as a missing record), for each of the five kinds of reader.
- Answer 2 (cross-actor isolation): the second actor uses the same idempotency key value with a body whose record key differs (for example `REC-OTHER`). Expected: the second actor's command runs and creates its own record; no 409 mismatch, no replay of the first actor's result. The duplicate record-key rule is not idempotency and is not tested here.

## Amendment 2 (orchestrator, 2026-11-14, after attempt 2)
- Q3 (b-voided) red is a real core finding: the body hash includes `expected_version`, which the MCP tools resolve server-side at call time (`write_tools.py` ~201, ~271), so a retry after the target changed looks like a different request. Decision: `expected_version` is concurrency control, not request content. Added allowed paths: `packages/tl-core/src/tl_core/services/idempotency.py` (add `"expected_version"` to `EXCLUDED` and update the `body_hash` docstring; nothing else) and `packages/tl-core/tests/test_idempotency.py` (one test: same body with a different `expected_version` hashes equal; a different field still differs). The voided test must then pass unchanged.
- Answer 1 revised (five-reader API walk): `CreateRecord` refuses extension types. Use a module record type the API test worlds already create through `/commands` and read at a restricted class: see `packages/tl-api/tests/test_activity_walk.py` and `test_api_awp_progress.py` for the pattern (an awp IWP or another confidential-class module record). Lower the reader after the first keyed call; the replay must show the record as absent for each of the five readers. If no such type works through `/commands`, write the five-reader walk at the MCP layer in the MCP test file and say so in the report.

## Decision (orchestrator, 2026-11-14, after attempt 3)
`body_hash` also strips the `EXCLUDED` keys from a nested `command` dict, because the proposal hash wraps the command (`{"tool", "summary", "command"}`); the top-level exclusion alone left `command.expected_version` in. Made by the orchestrator at 9d903fcf with a test; claim, lookup and record all hash through this one function.
