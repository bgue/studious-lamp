# P2-X2-T01 — API routes and ApiClient methods for stop, resume, list stopped

Status: ready
Tier: haiku
kind: ticket
review: full
Labels: api
Depends on: S3 (merged @a03515d2)
Branch: `p2/x2-t01-agent-stop-routes`
Worktree: `/home/user/wt/x2/t01`

## Goal
Three named admin routes and three `ApiClient` methods over the merged S3 services: stop an agent, resume it, list the stopped agents with the
held count. Thin: one `tl_core.services.agent_stop` call per route. No new logic, no new exception class.

## Brief references (pasted)
> P2-X2 T01: API routes and `ApiClient` methods for stop, resume, list stopped. Demo 4-6: an admin stops an agent, new filings are refused, pending ones show as held;
> the held count and the stopped list name no hidden record and count none (140, 141). AGENTS.md: a new route is denied for agents until someone allows it; the viewer
> filter runs before any count.

## Interfaces (verbatim from `tl_core/services/agent_stop.py`)
```python
class StopAgent(_AgentStopCommand):   # scope: str = COMPANY; agent: str (max 200, "agent:<name>")
    reason: str | None = Field(default=None, max_length=MAX_REASON)   # 200
class ResumeAgent(_AgentStopCommand): ...
class AgentStopResult(CommandResult):  # changed: bool = True (false: already in that state, nothing written)
class StoppedAgent(BaseModel):
    agent: str; stopped_at: str | None; stopped_by: str | None; reason: str | None; held: int
def handle_stop_agent(uow: UnitOfWork, cmd: StopAgent) -> AgentStopResult
def handle_resume_agent(uow: UnitOfWork, cmd: ResumeAgent) -> AgentStopResult
def list_stopped(conn: Connection, viewer: confidentiality.Viewer, *, limit: int = 200) -> list[StoppedAgent]
```
Refusals (already mapped, do not add rows): `ForbiddenError` (not an admin person), `AccountNotFoundError` (unknown agent, one text).
Pattern to copy: `routes/admin.py` `grant_role` (command built with `actor=actor, source="api"`, `with ctx.backend() as uow`) and its list route
(`ctx.backend(True)`); viewer via `confidentiality.current_viewer()` as in `routes/awp_progress.py`; client style in `client/admin.py`.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/services/agent_stop.py` (signatures; abridged above)
- `packages/tl-api/src/tl_api/routes/admin.py` (lines 1-60 and 288-345)
- `packages/tl-api/src/tl_api/client/admin.py`
- `packages/tl-api/tests/test_api_admin_module_roles.py` (the `Cast` fixture and parity harness)
- `packages/tl-api/tests/test_auth_review.py` (lines 360-395 only)
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/agent_stop.py` (create)
- `packages/tl-api/src/tl_api/app.py` (import and the `for module in (...)` tuple: one line each)
- `packages/tl-api/src/tl_api/client/agent_stop.py` (create; class `AgentStopApi(ApiClientBase)`)
- `packages/tl-api/src/tl_api/client/__init__.py` (import and base list: one line each)
- `docs/reference/openapi.json` (regenerated, additive)
- `packages/tl-api/tests/test_api_agent_stop.py`, `packages/tl-api/tests/test_client_agent_stop.py` (create)
- `packages/tl-api/tests/test_auth_review.py` (consequential pin: add the three actions to `AGENT_MAY_NOT`, with a comment `P2-X2 T01`; list in the report)
- `docs/reports/P2-X2/T01.md` (create)

## Steps
1. Routes, guard actions `admin.agents.stop`, `admin.agents.resume`, `admin.agents.list` (the guard makes them admin-only; agents are denied):
   `POST /admin/agents/stop` body `{agent, reason?}` (extra forbidden) -> `AgentStopResult`, operation_id `admin_stop_agent`;
   `POST /admin/agents/resume` body `{agent}` -> `AgentStopResult`, `admin_resume_agent`;
   `GET /admin/agents/stopped` (query `limit` 1..500, default 200) -> `list[StoppedAgent]`, `admin_list_stopped_agents`, read through `confidentiality.current_viewer()`.
2. Register the router in `app.py`; run `uv run python -m tl_api.openapi` to refresh `docs/reference/openapi.json`. Never run `--baseline`.
3. Client: `stop_agent(agent, reason=None)`, `resume_agent(agent)`, `list_stopped_agents(limit=200)`; ids go through `quote` where in a path (none here).
4. Add the three actions to `AGENT_MAY_NOT` in `test_auth_review.py`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-api/tests/test_api_agent_stop.py packages/tl-api/tests/test_client_agent_stop.py packages/tl-api/tests/test_auth_review.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_openapi.py packages/tl-api/tests/test_openapi_baseline.py packages/tl-api/tests/test_client_admin.py
```
Expected: all pass; `just check` clean (openapi `--compat` additive).

## Tests to add
`test_api_agent_stop.py` (parity harness, as `test_api_admin_module_roles.py`): admin stops then the second stop answers `changed: false`; resume likewise; a plain user, a
document controller and an agent token get 403 on all three; unknown agent and a never-filed agent get the same 404 body; an agent filing is refused after stop and files after resume.
List: a stopped agent with a pending proposal that carries a record the reader may not read is listed with `held` excluding it (equal to a world without that proposal), for
five readers (admin without clearance, user, controller, lowest, full clearance; copy the walk shape of `test_confidentiality_walk.py`, one agent, one hidden record).
`test_client_agent_stop.py`: the three methods round-trip through `ApiClient` and raise `ForbiddenError` / `AccountNotFoundError` as the admin client does.

## Report requirements
Standard report plus: the `AGENT_MAY_NOT` pin; output of the two commands (<= 5 lines each).

## Escalation triggers
Stop and write *Blocked* if a route needs a new exception class or `errors.py` row; if `list_stopped` needs a change; if the five-reader walk cannot be built from the existing helpers.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
