# P2-X1 — Idempotency key and OpenAPI compatibility gate

Status: in-progress. Plan: `docs/build-spec/12-extension-plan.md` (P2-X1, plan-checked). Live board: `STATE.md`. Branch `p2/x1`.

## Objective
A retry after a timeout never files a second proposal or creates a second record, and a renamed or removed API field fails
`just check` before release. Additive only: no existing event changes, no data migration.

## Demo (`just demo P2-X1`, both adapters)
1. One actor sends one command twice with one `Idempotency-Key`: one event set; the second answer equals the first.
2. The same key with a different body is refused with a fixed message and nothing is written. Two concurrent sends of one key write
   once; the other answers as a replay or a fixed in-progress refusal, never a 500.
3. An agent files a proposal twice with one key (API and MCP): one proposal row.
4. Another actor with the same key value does not see or collide with the first actor's entry.
5. After the actor's clearance drops, a replay returns ids that the viewer filter hides as absent.
6. A removed response field in a scratch `openapi.json` fails `just check`; an added optional field passes.

## Order of work
| ID | What | Tier | Waits for |
|---|---|---|---|
| S1 | Table, setting, helper, replay and mismatch rule at the call sites (gated) | piece | — |
| T04 | OpenAPI diff function in `compat.py` (provided test) | ticket, full | — |
| T01 | `Idempotency-Key` header on command and proposal routes | ticket, full | S1 |
| T03 | MCP write and proposal tools take `idempotency_key` | ticket, full | S1 |
| T02 | Client and remote TUI send a key on retry | ticket, full | T01 |
| T05 | OpenAPI baseline file, `just openapi-baseline`, step in `just check` | ticket, full | T04 |
| T06 | `docs/reference/api-compat.md` deprecation rule | ticket, lite | T04 |
| T07 | Walking tests: five kinds of reader, cross-actor isolation | ticket, full | S1, T01, T03 |
| T08 | Demo driver `dev/demos/P2-X1.sh` | ticket, full | T02, T03, T05 |
| T09 | Runbook `docs/runbooks/api-retries.md`, `AGENTS.md` rows | ticket, lite | T08 |

## Checkpoints
C1 S1 merged. C2 route, client and tool tickets merged. C3 gate and docs merged. C4 demo green, security review SR-X1 closed.

## Approvals
Table `idempotency_key` and setting `idempotency.retention_days`: orchestrator, line in `docs/reports/APPROVALS.md` (relay `95`).
OpenAPI baseline file and its refresh rule: owner (T05; raise before it merges).

## Out of scope and risks
The purge job is deferred (DEFERRED.md); the setting stays and rows are kept. Embedded and CLI paths pass no key. Replay carries ids
only and re-reads through the viewer filter. Heavy test slots are tight: every ticket gate names narrow test paths.
Escalate if the wrap needs a `CommandSpec` or module interface change.
