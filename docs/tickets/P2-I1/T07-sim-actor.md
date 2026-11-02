# P2-I1-T07 — Simulator `AwpDesk` and the `workface_planner` actor

Status: draft (r8: design fixed, three facts to settle at r9 before dispatch; T06 and T03b merged)
Tier: haiku
Review: lite
Labels: sim
Depends on: T06, T03b (merged)
Branch: `p2/i1-t07-sim`
Worktree: `/home/user/wt/i1/t07` (from `p2/i1` head)

## Goal
A simulated workface planner proposes CWPs from a small template list; a simulated person (the existing `approver` actor) accepts them. Pattern: the tag clerk (`actors/tag_clerk.py`, `TagDesk` in `client.py`, `FakeClient` in `testing.py`) and the assistant/approver pair (`rec.propose`, `rec.pending`, `rec.decide`). The planner holds the `user` word only: it never creates a CWP directly (`propose_cwp`, T06, files a pending proposal).

## Design (fixed)
```python
# tl_sim/client.py : @runtime_checkable class AwpDesk(Protocol): the reads an awp planner needs on top of SimClient
#   def areas(self) -> list[str]: ...      # CWA codes of the current path steps (MCP path_of_construction, field steps[].cwa)
#   def cwps(self) -> list[dict[str, Any]]: ...   # MCP list_cwps (number, title, cwa, state)
#  HttpSimClient implements both through self._mcp.call_tool; FakeClient (testing.py) answers from the FakeWorld (no new record type: a list on the world)
# tl_sim/actors/workface_planner.py : class WorkfacePlanner(BaseActor); TEMPLATES = a tuple of (discipline, title, budget_hours) of 4 entries
#   act(): areas = desk.areas(); draw n = draw(params.cwps_per_day, ctx.rng); for each: template = ctx.rng.choice(TEMPLATES), area = ctx.rng.choice(areas);
#   rec.propose("propose_cwp", {"project": <code from ctx.scope>, "discipline": d, "title": f"{title} {area}", "cwa_code": area, "budget_hours": h}); nothing when areas is empty
# tl_sim/scenario.py : WorkfacePlannerParams(cwps_per_day: Count = 1); ActorsConfig.workface_planner: ... | None = None (off unless named); ROLE_NAMES / ACTOR_NAMES gain "workface_planner" before "assistant"
# tl_sim/actors/registry.py : "workface_planner": WorkfacePlanner
```
Ground truth: `rec.propose` already notes `PROPOSAL_CREATED`; the accepted CWP's ground truth is a T11/phase follow-up (say so in the report).

## To settle at r9 before dispatch (supervisor)
1. Where the awp data lives for a sim run: `sim-<run>` has no CWA or path. Decide: the acceptance adds a CWA and a path to the run's project with the module handlers before the run, or a scenario `setup` hook (a core sim change; then this becomes a piece).
2. Whether `FakeClient.propose` and `accept_proposal` learn `propose_cwp` (needed for unit tests, `packages/tl-sim/tests/test_workface_planner.py`, T11) or the actor test uses a stub desk.
3. Whether `ROLE_NAMES` growing changes `test_scenario.py` pins and the provisioned identities (consequential pins, rule 12).
Allowed paths, acceptance (`uv run python dev/accept/P2-I1/T07.py`: 3 CWPs proposed, accepted by the approver, `list_cwps` +3 on a project with awp areas) and the 5-file size check are written at r9 once 1-3 are answered.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
