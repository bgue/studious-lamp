# P2-X2 — Agent scope: filing check, queue cap, stop switch

Status: done. Plan: `docs/build-spec/12-extension-plan.md` (P2-X2, 9 items, no plan check). Live board: `STATE.md`. Branch `p2/x2`.

## Objective
An agent in the pilot files only where it may propose, cannot flood a project queue, and an admin can stop one agent and hold what
it filed. Additive only: new event types and a setting; no existing event changes, no data migration.

## Demo (`just demo P2-X2`, both adapters)
1. An agent without the module `user` word on the scope files: refused, the same as a scope that does not exist.
2. With the word it files; accept still needs the command's own word. A pilot agent lacking the grant is refused until an admin runs `GrantModuleRole`.
3. A project pending-queue cap (setting) is reached: the next filing is refused with a fixed text that shows no counts.
4. `tl agent stop`: new filings refused, pending ones show as held, accept refused.
5. `tl agent resume` lifts both; ledger shows `Agent.Stopped` then `Agent.Resumed`.
6. Held count and stopped list, read as five kinds of reader, name no hidden record and count none.

## Order of work (checkpoints: C1 S1, C2 S2+S3, C3 surfaces and tests, C4 demo green)
| ID | What | Tier | Waits for |
|---|---|---|---|
| S1 | Filing check in `proposals.submit` (word on scope, hidden equals missing) | piece | seams (committed) |
| S3 | Stop switch: events, projection, admin commands, checks (schema: gated) | piece | seams |
| S2 | Project queue cap, fixed refusal text (gated setting) | piece | S1 merged |
| T01 | API routes and `ApiClient` for stop, resume, list stopped | ticket, full | S3 |
| T02 | `tl agent stop`, `resume`, `stopped` | ticket, full | S3 |
| T03 | Accounts screen: stopped flag and held count | ticket, full | T01 |
| T04 | Walking tests, `AGENT_MAY_NOT` rows | ticket, full | S1, S2, S3, T03 |
| T05 | Demo driver `dev/demos/P2-X2.sh` | ticket, full | T02, T04 |
| T06 | Runbook `accounts-and-access.md` with the grant checklist | ticket, lite | T05 |

## Seams (committed in round 1, so S1 and S3 have disjoint paths)
`services/agent_scope.py` (S1 fills `check_filing`; S2 adds the cap) and `services/agent_stop.py` (S3 fills). `proposals.py` calls
them: replay, `check_filing`, `require_not_stopped`, budget, precheck; accept calls `require_not_stopped`. Later pieces do not edit `proposals.py` wiring except S2 (cap line).

## Risks and escalation
Existing tests that file as an agent without a grant: S1 pins them with a fixture grant. I6 scenario agents are granted before I6 T04. Escalate: a core command needs a module word at filing (Q1); a stop check needed outside `proposals.py`.
