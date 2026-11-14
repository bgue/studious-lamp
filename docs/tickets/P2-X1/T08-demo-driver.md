# P2-X1-T08 — Demo driver `dev/demos/P2-X1.sh`

Status: ready
Tier: haiku   kind: ticket   review: full
Labels: demo, tests
Depends on: T01, T03, T05, S1, S2, T07 (merged). T02 merges in parallel; the demo does not call the client's retry.
Branch: `p2/x1-t08-demo`   Worktree: `/home/user/wt/x1/t08`

## Goal
`just demo P2-X1` runs the six clauses of `docs/tickets/P2-X1/README.md` ("Demo") on SQLite and Postgres and prints `PASS clause N: ...` after each check, `P2-X1 demo OK on: ...` at the end, and `DEMO FAILED: ...` with exit 1 on a miss.

## Brief references (pasted)
Demo clauses:
1. One actor sends one command twice with one `Idempotency-Key`: one event set; the second answer equals the first.
2. Same key, different body: refused with a fixed message (409 `idempotency_mismatch`), nothing written. Two concurrent sends of one key write once; the other answers as a replay or the fixed in-progress refusal (409 `idempotency_in_progress`), never a 500.
3. An agent files a proposal twice with one key (API and MCP): one proposal row.
4. Another actor with the same key value does not see or collide with the first actor's entry.
5. After the actor's clearance drops, a replay returns ids that the viewer filter hides as absent (404, same text as a missing id).
6. A removed response field in a scratch `openapi.json` fails the compat step of `just check`; an added optional field passes.

## Interfaces
- HTTP: `POST /commands/create_record` with header `Idempotency-Key: K` or body `idempotency_key`; errors `{"error": "idempotency_mismatch"|"idempotency_in_progress"|"invalid_idempotency_key", "message": ...}`.
- MCP: `create_record(..., idempotency_key=...)` and the four other tools in `packages/tl-mcp/src/tl_mcp/write_tools.py`; the agent's filing returns a proposal id; use the same driver pattern as `dev/demos/p2_punch_demo.py` (`mcp_server`, `mcp_call`).
- Agents cannot file `CreateRecord` over HTTP (403 `agent_must_propose`); so clause 3's API half is: the agent's HTTP create is refused, nothing stored; the proposal half runs over MCP twice with one key. If an agent HTTP proposal route with a key exists, use it; do not invent one.
- Compat: `uv run python -m tl_api.openapi --compat` (exit 1 on a break, prints the rule). Paths are module constants: `OPENAPI_PATH` (current) and `BASELINE_PATH`, an absolute value replaces the repo root. Clause 6: in the python helper, write a scratch copy of `docs/reference/openapi.json` with one response-schema property deleted, point `tl_api.openapi.OPENAPI_PATH` (and, if needed, the baseline) at scratch files, call `main(["--compat"])`, expect 1; then a copy with an optional property added, expect 0. Never edit files under `docs/reference/`. Also run the real `--compat` once from the shell: exit 0.
- Clearance drop (clause 5): the pattern in `packages/tl-api/tests/test_idempotency_walk.py` (class moved to `privileged`, no clearance rows).

## Context (read these, nothing else; ≤ 6)
- `dev/demos/P2-PUNCH.sh` (copy the shell skeleton: backends, free port, `tl serve`, helpers, cleanup)
- `dev/demos/p2_punch_demo.py` (copy `World`, `mcp_server`, `mcp_call`, `ok`, `miss`, `check`)
- `packages/tl-api/tests/test_idempotency_walk.py`
- `packages/tl-mcp/tests/test_mcp_idempotency.py`
- `docs/reports/P2-X1/T05.md`, `docs/reports/P2-X1/T07.md` (interfaces and traps)

## Allowed paths
- `dev/demos/P2-X1.sh` (create)
- `dev/demos/p2_x1_demo.py` (create)
- `docs/reports/P2-X1/T08.md`

## Steps
1. Shell: skeleton as P2-PUNCH; people `amy` (record owner, a role that can create records in project P123), `bob` (second actor), `ctl` optional, agent `triage`; users made with `tl admin user add`, sessions with `tl login`. Use `curl` or the helper (`ApiClient` is not used: it would add keys) for raw header sends with the person's session token.
2. Helper modes `clause1 ... clause6` in `p2_x1_demo.py`; the shell prints `PASS clause N` only after the mode returns. Clause 2 concurrency: two threads, one key, one body; assert `{status}` is a subset of {200, 409 in_progress}, never 500, and exactly one record exists after.
3. Print the event count / row count the script counted, not a fixed number.

## Acceptance (the ticket's gate; no unit test)
```
just check
TL_DEMO_BACKENDS=sqlite bash dev/demos/P2-X1.sh
TL_DEMO_BACKENDS=postgres bash dev/demos/P2-X1.sh
```
Expected: six `PASS clause` lines per backend, final `P2-X1 demo OK on: ...`, exit 0, nothing left behind (temp dirs, server, scratch Postgres database).

## Tests to add
None; the demo is the test. Paste the clause lines (not the full output) into the report.

## Report requirements
Standard report; the six PASS lines per backend; any clause half that could not be shown and why.

## Escalation triggers
- An agent HTTP proposal route with a key is missing and clause 3's API half cannot be shown: report, show the MCP half, stop.
- A clause shows a real defect (a 500, a duplicate row, a leaked id): do not weaken the check; stop and report.
- Anything outside Allowed paths needs a change.
