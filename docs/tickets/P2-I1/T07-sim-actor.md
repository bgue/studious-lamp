# P2-I1-T07 — Simulator `AwpDesk` and the `workface_planner` actor

Status: ready (r9: the three facts are settled, D43-D45; needs T06 and T03b, both merged)
Tier: haiku
Review: lite
Labels: sim
Depends on: T06, T03b (merged)
Branch: `p2/i1-t07-sim`
Worktree: `/home/user/wt/i1/t07` (from `p2/i1` head)

## Goal
A simulated workface planner proposes CWPs from a small template list; the existing `approver` actor accepts them. Pattern: `actors/assistant.py` (an agent that proposes over MCP) and `actors/approver.py`. The planner is an AGENT, not a person: only `agent:sim-assistant` has an MCP caller (`HttpConnector._mcp_for`), and `propose_cwp` is an MCP tool. It never creates a CWP: the tool files a pending proposal and the approver (the `user` word) accepts it.

## Design (fixed; decisions D43-D45)
```python
# tl_sim/client.py : @runtime_checkable class AwpDesk(Protocol): def areas(self) -> list[str]: ...
#   CWA codes of the current path steps, in path order. HttpSimClient.areas(): self._mcp.call_tool("path_of_construction", {"project": self._project}) ->
#   the structured answer is the PathView as a dict (steps[].cwa); if it is wrapped as {"result": ...} unwrap it; a null/empty path -> []. No MCP caller -> raise McpUnavailableError as `propose` does.
# tl_sim/testing.py : FakeWorld gains area_codes: list[str] (default []) and cwp_rows: list[dict] (default []).
#   FakeClient.areas() -> list(self.world.area_codes).
#   FakeClient.propose("propose_cwp", args): ProposalRefusedError when args["cwa_code"] not in world.area_codes; otherwise the proposal row's command = dict(args).
#   FakeClient.accept_proposal for tool "propose_cwp": append {"number": f"{project}-CWP-{discipline}-{n:04d}", "title", "cwa", "state": "Draft"} to world.cwp_rows (n = len+1) before the Proposal.Accepted event.
# tl_sim/actors/workface_planner.py : class WorkfacePlanner(BaseActor); name = "workface_planner"; self.identity = ASSISTANT (as Assistant does); TEMPLATES = 4 entries (discipline, title, budget_hours as str), e.g. ("CIV","Footings","320"),("MEC","Pipe spools","180"),("ELE","Cable pull","240"),("INS","Loop checks","96")
#   act(): n = draw(params.cwps_per_day, ctx.rng); stop if n == 0; desk = ctx.client, areas = desk.areas() (client not an AwpDesk -> ProposeUnavailableError); stop if no areas;
#   for each of n: discipline, title, hours = ctx.rng.choice(TEMPLATES); area = ctx.rng.choice(areas);
#   rec.propose("propose_cwp", {"project": ctx.scope.removeprefix("project:"), "discipline": d, "title": f"{title} {area}", "cwa_code": area, "budget_hours": h})
#   Draw order is exactly this (template, then area, per CWP). Docstring in the style of assistant.py: numbered steps.
# tl_sim/scenario.py : WorkfacePlannerParams(Strict): cwps_per_day: Count = 1; ActorsConfig.workface_planner: WorkfacePlannerParams | None = None (off unless named: needs CWAs and a path);
#   ACTOR_NAMES = (*ROLE_NAMES, "assistant", "workface_planner", "approver"). ROLE_NAMES is NOT changed (D45).
# tl_sim/actors/registry.py : "workface_planner": WorkfacePlanner
```
Ground truth: `rec.propose` already notes `PROPOSAL_CREATED` (agent = the assistant identity); the accepted CWP's own ground truth is a phase follow-up (say so in the report).
D43: the sim project has no awp data and none is added by the sim: a run is prepared by hand with `tl awp cwa define` and `tl awp path define --project sim-<run>` as an operator (precedent: `dev/seed/scenarios/schedule-weeks.yaml` header, `operators:`). No `setup` hook, no core sim change. T08 does this in the demo.
D44: `FakeClient`/`FakeWorld` learn `propose_cwp` (above) so unit tests (T11) and this acceptance run the real actor pair.
D45: the planner is an agent sharing `ASSISTANT`, so `all_identities()`, the provisioned list in `test_orchestrator.py` and the `enabled()` pin in `test_scenario.py` do not change (the planner is off by default). Both agent actors share the agent's daily proposal budget (500 by default).

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/actors/assistant.py`, `actors/approver.py`, `actors/registry.py`, `scenario.py` lines 15-40 and 160-200
- `packages/tl-sim/src/tl_sim/client.py` lines 95-135 and 225-240 (Protocols, `HttpSimClient` init), `testing.py` lines 58-70, 190-260, 625-720 and 765-790
- `packages/tl-sim/tests/test_actor_assistant_approver.py` lines 1-50 (the pattern for the script), `packages/tl-mcp/src/tl_mcp/awp_tools.py` lines 85-125 and 185-225 (argument names)

## Allowed paths
- `packages/tl-sim/src/tl_sim/client.py`, `testing.py`, `scenario.py`, `actors/registry.py` (edit, additive only); `packages/tl-sim/src/tl_sim/actors/workface_planner.py` (create)
- `dev/accept/P2-I1/T07.py` (create), `docs/reports/P2-I1/T07.md` (create)
- Size check (§6): 5 source files (one new), about 220 lines with the script; no schema, dependency or public-interface change outside the sim package.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T07.py                         # no pytest
```
`T07.py` (on `FakeWorld` with `area_codes = ["A1","A2","A3"]`; actors stepped with `make_context(..., propose=True)` as in the pattern test; both actors with `cwps_per_day=3`, seed 1): `PASS proposed` (the planner makes 3 `propose_cwp` proposals, status pending, `world.cwp_rows` still empty, ground truth has 3 `PROPOSAL_CREATED`); `PASS accepted` (the approver with `accept_rate=1.0` accepts all 3; `len(world.cwp_rows) == 3`; each `cwa` is one of the areas; titles end with their area); `PASS no areas` (empty `area_codes`: the planner proposes nothing); `PASS refused` (a `cwa_code` outside the areas: `ProposalRefusedError`); `PASS same seed` (two worlds, same seed: identical titles); `PASS off by default` (`Scenario.model_validate({"scenario": "t", "seed": 1, "start": date(2026, 11, 2), ...})`.actors.enabled()` lacks `workface_planner`; with `{"workface_planner": {}, "assistant": {}, "approver": {}}` it lists them in the order assistant, workface_planner, approver, and `ROLE_NAMES` is unchanged); `PASS registry` (`build_actor("workface_planner", params)` is a `WorkfacePlanner`). Ends `T07 ok`.

## Tests to add
none (T11: `packages/tl-sim/tests/test_workface_planner.py`).

## Report requirements
`docs/reports/P2-I1/T07.md` <= 60 lines; deviations first; say how `path_of_construction` answered through `call_tool` if it could be seen (unwrapped or not). Subject `P2-I1-T07: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if `FakeClient` cannot take `propose_cwp` without a change outside Allowed paths, or if a pinned test in `packages/tl-sim/tests` would break (list which; do not edit it).

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
