# P2-X2-S3c report: account version after a partial rebuild (SR-X2 F1)

## Fix
Chose to fold the version bump into `AccountProjector` (handles Agent.Stopped/Resumed, writes only
`cur_account.version` from `stream_version`); `AgentStopProjector` no longer touches `cur_account`.
Reading the head in `_known` would fix Stop/Resume only; `accounts.disable` etc. read
`cur_account.version` too. Now each of `--only accounts` and `--only agent_stop` is safe. No event
changed. Files: auth/projector.py, projection/agent_stop.py, test_agent_stop_projection.py.

## Deviation
`test_agent_stop_projection.py` was already failing on base (agents filed with no explicit
module grant, `no scope 'project:P1'`); its fixture now grants filing as `test_agent_stop.py` does.

## Tests
`test_a_partial_rebuild_leaves_stop_resume_and_account_commands_working` x (accounts,
agent_stop, both) x 2 adapters: version equals live after rebuild; Resume, Stop, Resume and
`accounts.disable` succeed.

## Gate
- `just check`: pass (one earlier run failed on transient dev/seed import order, not mine; reran green)
- gate: 183 passed, PASS (all named paths existed; added test_agent_stop_projection.py)
- gate-pg: 60 passed, PASS

## Mutation
Sentinel (drop bump from handles): killed, 5 failed. Targeted: drop Agent.Resumed from set
killed (4 failed); version off by one killed (5 failed). No survivors.
