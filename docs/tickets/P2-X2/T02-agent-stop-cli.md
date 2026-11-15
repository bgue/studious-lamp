# P2-X2-T02 — `tl agent stop`, `resume`, `stopped`

Status: ready
Tier: haiku
kind: ticket
review: full
Labels: cli
Depends on: S3 (merged @a03515d2)
Branch: `p2/x2-t02-agent-stop-cli`
Worktree: `/home/user/wt/x2/t02`

## Goal
A `tl agent` group for the signed-in admin: stop an agent, resume it, list the stopped agents with the held count. Each command is one call into
`tl_core.services.agent_stop`, run through `require_admin`, as `tl admin roles grant` runs `GrantModuleRole`.

## Brief references (pasted)
> P2-X2 T02: `tl agent stop`, `resume`, `stopped` (CLI `require_admin`). Demo 4-5: `tl agent stop` refuses new filings and shows pending ones as held; `tl agent resume` lifts
> both. 140/141: the held count is taken after the viewer filter; a hidden record is neither named nor counted. An agent never runs these (ADR-0009).

## Interfaces (verbatim from `tl_core/services/agent_stop.py`)
```python
class StopAgent(_AgentStopCommand):   # scope: str = COMPANY; agent: str (max 200, "agent:<name>")
    reason: str | None = Field(default=None, max_length=MAX_REASON)   # 200
class ResumeAgent(_AgentStopCommand): ...
class AgentStopResult(CommandResult):  # changed: bool = True
class StoppedAgent(BaseModel):
    agent: str; stopped_at: str | None; stopped_by: str | None; reason: str | None; held: int
def handle_stop_agent(uow, cmd: StopAgent) -> AgentStopResult
def handle_resume_agent(uow, cmd: ResumeAgent) -> AgentStopResult
def list_stopped(conn, viewer: confidentiality.Viewer, *, limit: int = 200) -> list[StoppedAgent]
```
Refusals are service errors (`ForbiddenError`, `AccountNotFoundError`); `session.service_errors()` turns them into `error: ...` and exit 1.
Pattern: `tl_cli/admin_roles.py` (`require_admin(ctx.obj)`, `backend_of(ctx)`, `service_errors()`, `fail`; `--json` flag on `ls`); viewer via
`confidentiality.current_viewer()` as in `tl_cli/awp_export.py`. Registration pattern: `main.py` line 205-206 (`admin.app.add_typer(...)`) and line 148 (`app.add_typer(proposal.app, name="proposal")`).

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/services/agent_stop.py` (signatures; abridged above)
- `packages/tl-cli/src/tl_cli/admin_roles.py`
- `packages/tl-cli/src/tl_cli/awp_export.py` (lines 40-60 only)
- `packages/tl-cli/tests/test_cli_admin_roles.py`
- `packages/tl-cli/tests/auth_support.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/agent_stop.py` (create; `app = typer.Typer(help=..., no_args_is_help=True)`)
- `packages/tl-cli/src/tl_cli/main.py` (one import and one `app.add_typer(agent_stop.app, name="agent")`)
- `packages/tl-cli/tests/test_cli_agent_stop.py` (create)
- `docs/reports/P2-X2/T02.md` (create)
Consequential pins (a test that lists every `tl` command group, if one breaks): update it in this ticket and list it in the report.

## Steps
1. `tl agent stop NAME [--reason TEXT]`: NAME is the agent's username (a leading `agent:` is accepted); the command's `agent` is `agent:<name>`, `source="cli"`, `actor=admin.actor`.
   Prints `stopped agent:<name>` or `already stopped: agent:<name>` (when `changed` is false).
2. `tl agent resume NAME`: prints `resumed agent:<name>` or `not stopped: agent:<name>`.
3. `tl agent stopped [--json]`: one line per agent `agent  since <stopped_at>  by <stopped_by>  held <n>  <reason>`; `none stopped` when empty; `--json` prints the list of `StoppedAgent` dicts.
   Read-only backend, `confidentiality.current_viewer()`. No decision, no filtering of your own.
4. All three call `require_admin(ctx.obj)` first; no password or token appears in any output.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-cli/tests/test_cli_agent_stop.py packages/tl-cli/tests/test_cli_admin_roles.py packages/tl-cli/tests/test_cli_admin_commands.py
```
Expected: all pass; `just check` clean.

## Tests to add
`test_cli_agent_stop.py` (as `test_cli_admin_roles.py`: temp SQLite ledger, `root` signed in, a plain user, an agent account that has filed one proposal): stop prints the line and a second
stop prints `already stopped`; resume likewise; `stopped` lists it with `held 1` and `--json` equals the text; a signed-in plain user is refused by all three (exit 1, `forbidden`) and the
ledger gains no event; no session is refused; an unknown name and a never-filed agent give the same `error:` text; a pending proposal carrying a hidden record is not counted in `held`
(held 0 for the admin without clearance).

## Report requirements
Standard report plus: output of both commands (<= 5 lines each).

## Escalation triggers
Stop and write *Blocked* if the agent account cannot be found by username through `find_account` for an agent kind; if a command needs logic beyond one service call.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
