# P2-X2-S3c: account version after a partial projection rebuild (SR-X2 F1)

## Why
`AgentStopProjector` bumped `cur_account.version` on Agent.Stopped/Resumed (account stream
events). `rebuild --only accounts` replays only Account.* events, so the version fell below the
stream head and StopAgent, ResumeAgent and account commands failed with a concurrency error;
`--only agent_stop` rolled it back the other way.

## Fix (no event changes)
Move the bump into `AccountProjector` (it now also handles Agent.Stopped/Resumed, writing only
`cur_account.version`); `AgentStopProjector` writes only `cur_agent_stop`. Chosen over reading the
head from the ledger in `_known` because account commands (accounts.disable etc.) also read
`cur_account.version`; fixing only `_known` would leave them broken. Each projector now owns its
table, and either rebuilds alone correctly.

## Allowed paths
- packages/tl-core/src/tl_core/auth/projector.py
- packages/tl-core/src/tl_core/projection/agent_stop.py
- packages/tl-core/tests/test_agent_stop_projection.py
- docs/tickets/P2-X2/S3c-stop-version.md, docs/reports/P2-X2/S3c.md

## Interface
`STREAM_BUMP_EVENT_TYPES` in auth/projector.py; `AccountProjector.handles` grows by it.

## Tests
`test_a_partial_rebuild_leaves_stop_resume_and_account_commands_working` (--only accounts,
agent_stop, both): version equals live, then Resume/Stop/Resume and accounts.disable succeed;
both adapters via the `db` fixture. Existing agent_stop tests stay green.

## Gate
`just check`; `just gate` on test_agent_stop.py, tests/auth, test_agent_stop_projection.py,
tests/services/test_proposals.py, cli and api agent_stop tests; `just gate-pg` on test_agent_stop*.py.
