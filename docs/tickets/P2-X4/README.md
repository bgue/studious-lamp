# P2-X4 — Module-supplied commands, read routes and agent tools

Status: in-progress. Plan: `docs/build-spec/12-extension-plan.md` (P2-X4, plan-checked). Live board: `STATE.md`. Branch `p2/x4`.

## Objective
A new module adds its API commands, read routes, agent tools and CLI group by declaring them on its `ModuleSpec`. No edit to
`tl-api`, `tl-mcp` or `tl-cli` source, no release of those packages. Additive only: no event changes, no migration. Policy accept
(ADR-0029) keys on the command name, so names stay unique across modules and each command can carry a `meta` mapping.

## Demo (`just demo P2-X4`, both adapters)
1. `tl new module` scaffolds a module with one command, one read route and one tool; no other package is edited.
2. After install: a `/commands/<Name>` route, a `tl <module>` group and an MCP tool appear.
3. The command runs through API and CLI; its access word is enforced (refused for a person without it).
4. An agent calls the tool: refused until allowed; after an allow row it files a proposal.
5. The read route and the tool answer a hidden record exactly as a missing one, for the five readers.
6. A module whose hook names a missing object fails with a fixed message; the other modules still load.
7. `openapi.json` gains the routes additively; the X1 compatibility gate passes.

## Order of work
| ID | What | Tier | Waits for |
|---|---|---|---|
| S1 | `ModuleSpec` hooks as lazy refs for every installed module, `ModuleCommand`, load checks, unique names (core interface: gated) | piece | X3 ADR, I6 T03 (both on trunk) |
| S2 | API command table, routers, error rows from `load_modules()`; equality test | piece | S1 |
| S3 | MCP tool registration; module tools closed until allowed; equality test | piece | S1 |
| T01 | CLI groups from the hook: `main.py` loop and equality test | ticket, full | S1 |
| S4 | Conformance: existing walks over `load_modules()`, row-or-exclusion, word check, delegation class check (ADR-0029 dec. 7), registry drift check | piece | S2, S3 |
| T02 | `tl new module` scaffold emits the hooks, an example route and tool | ticket, full | S2, S3, T01 |
| S5 | Fixture module `ext_demo` under `tests/` (was T03; access-worded command plus confidential read: builder piece, D11) | piece | S4 |
| T04 | TUI note and `docs/runbooks/new-module.md` | ticket, lite | T02 |
| T05 | Demo driver `dev/demos/P2-X4.sh` | ticket, full | T02, S5 |
| T06 | `AGENTS.md` rows; module README template | ticket, lite | T05 |

## Checkpoints
C1 S1 merged. C2 S2, S3, T01 merged. C3 S4 and scaffold merged. C4 demo green, SR-X3 closed.

## Approvals
`ModuleSpec` hooks and `ModuleCommand.meta` (core interface, addendum to the module-seam ADR): orchestrator, APPROVALS line before S1 merges.

## Out of scope and risks
TUI hook is later work; screens still import modules by name. X2 is in flight on `p2/x2` (it rewrites `agent_scope.py`, `proposals.py`
wiring, `tl_api/errors.py`): X4 pieces keep off those files. Wave 3 slots are tight: S4 runs alone; at most 2 builders gate at once.
Escalate if a surface cannot be reached by a ref inside the allowed prefixes (see STATE OPEN Q1).
