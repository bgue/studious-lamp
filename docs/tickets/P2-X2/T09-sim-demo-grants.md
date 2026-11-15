# P2-X2 T09 — Sim and demo agents get an explicit grant (S1 fallout)

kind: ticket
branch: p2/x2-t09-sim-demo-grants
worktree: /home/user/wt/x2/t09
base: p2/x2@6e70ffa4

## Why
S1 (filing check): an agent files only under an explicit module `user` grant on the scope; a derived account role does not
count. Agents with no account or no grant are now refused as `no scope '<scope>'`.

## Goal
1. tl-sim: the test suite (`packages/tl-sim/tests/suite.py`) makes `sim-assistant` an agent account and grants it `user` on
   the sim project through `GrantModuleRole` by an admin account. The assistant still only proposes; the approver decides.
2. Demos (`dev/demos/*`): run each that files as an agent on SQLite; where it fails on `no scope`, grant the agent in the
   demo setup (admin `GrantModuleRole` or `tl admin roles grant`). No clause is weakened. P2-I2 `awp.worker.run` is not ours.
3. `dev/accept/P2-I2/T09b.py` `action words` (`len(IWP_MCP_ACTIONS)==5`): decide by reading whether X2 changed the count; fix
   the pin only if it did.

## Allowed paths
- `packages/tl-sim/tests/**`, `packages/tl-sim/src/**` (setup only)
- `dev/demos/**`, `dev/accept/P2-I2/T09b.py`
- `docs/reports/P2-X2/T09.md`

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; `just gate packages/tl-sim/tests`; demo results in the report.
