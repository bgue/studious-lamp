# P2-I2-T10a — Simulator `IwpDesk` and the `iwp_planner` actor

Status: ready (r10; T09a, T04e1, T04e2, S2, C2 merged; commands exist on the API)
Tier: haiku
Kind: ticket
Review: lite
Labels: sim
Depends on: S2, C2, T04e1, T04e2 (merged)
Branch: `p2/i2-t10a-sim-iwp`
Worktree: harness-created under `/home/user/wt/i2/t10a` (from `p2/i2` head)

## Goal
A simulated person builds IWPs and works their constraints through the API: creates an IWP, makes scope items and adds them, starts development, raises a manual constraint now and then and clears the ones raised earlier. Pattern: `actors/crew.py` (a person, identity `user:sim-<name>`) and `actors/document_registrar.py` (desk Protocol on `HttpSimClient`, `Recorder` method, `FakeClient` twin). Q6 A: simulated people do `user` acts only; sign-off and issue are operators' (`Scenario.operators`), not this actor's.

## Design (fixed; decision D40)
The plan row says "workface_planner"; that name is the P2-I1 agent (CWP proposals, `actors/workface_planner.py`) and stays untouched. This actor is a person and is named `iwp_planner`.
```python
# tl_sim/client.py: ApiLike gains list_iwps(project, *, state=None, limit=200) -> list[IwpRow] and
#   list_constraints(project, *, subject=None, state=None, limit=200) -> ConstraintList (both exist on tl_api IwpApi; import the types as client.py imports its other views).
# @runtime_checkable class IwpDesk(Protocol):
#   def iwps(self) -> list[dict[str, Any]]                       # {id, number, state}, by number
#   def create_iwp(self, discipline: str, title: str) -> dict    # {id, key, title}
#   def create_scope_item(self, commodity, description, qty, uom, est_hours) -> dict   # {id, key, title}
#   def add_scope(self, iwp_id: str, item_ids: list[str]) -> dict
#   def start_development(self, iwp_id: str) -> dict
#   def raise_constraint(self, subject_id: str, category: str, description: str) -> dict  # {id, key, title}
#   def open_constraints(self) -> list[dict]                     # rows in state Open or Assigned: {id, key, subject_id}, by key
#   def clear_constraint(self, constraint_id: str, reason: str) -> dict
# HttpSimClient implements it. Commands go through self._api.correspondence_command(NAME, Model(**self._common(), ...))
#   (it is the generic POST /commands/<Name>; say so in the report). self._clock.tick() before each write, as the other desks do.
#   Names/models: CreateIwp, CreateScopeItem, AddIwpScope (tl_mod_awp.commands), StartIwpDevelopment, RaiseConstraint(phase="ready",
#   severity="blocking", source_kind default), ClearConstraint (tl_core.constraints.commands). Ids in, ids out (stream_id, key from CommandResult).
#   `title` in each made-dict is read back with self._api.get_record_by_id(id)["title"].
# actors/base.py Recorder: create_iwp(...) -> Rec, create_scope_item(...) -> Rec, add_scope(...), start_development(...), raise_constraint(...) -> Rec,
#   clear_constraint(...); each calls the desk (client not an IwpDesk -> ProposeUnavailableError, as _document_desk does for its desk),
#   and notes gt.RECORD_CREATED {"title", "record_type", "voided": False} for the IWP ("awp.IWP"), the scope item ("awp.ScopeItem") and the constraint ("core.Constraint").
#   Scope add, start and clear are not noted (no intent fits; sim_assert for them is I6, say so in the report).
# actors/iwp_planner.py: class IwpPlanner(BaseActor); name = "iwp_planner"; identity default user:sim-iwp_planner.
#   TEMPLATES = (("PIP","Spool set"), ("PIP","Valve install"), ("CIV","Footings"), ("ELE","Cable pull"))
#   ITEMS = (("PIPE-SPOOL","Pipe spool","1","EA","12"), ("VALVE","Valve","1","EA","6"), ("SUPPORT","Pipe support","4","EA","3"))
#   CATEGORIES = ("materials","engineering","permit","labour")
#   act(), exactly this draw order:
#     1. n = draw(params.iwps_per_day, ctx.rng)
#     2. for each of n: discipline, title = ctx.rng.choice(TEMPLATES); iwp = rec.create_iwp(discipline, f"{title} {existing + i + 1}");
#        for _ in range(params.scope_items): commodity, desc, qty, uom, hours = ctx.rng.choice(ITEMS); rec.create_scope_item(...);
#        rec.add_scope(iwp, items in creation order); rec.start_development(iwp)
#     3. roll = ctx.rng.random() (always); if roll < params.constraint_rate and an IWP exists (iwps() non-empty, last one by number):
#        category = ctx.rng.choice(CATEGORIES); rec.raise_constraint(iwp.id, category, f"{category} needed for {iwp.number}")
#     4. clear: open = desk.open_constraints() (read BEFORE step 3 so a new one is not cleared the day it is raised); take the first
#        min(params.clears_per_day, len(open)) in key order; rec.clear_constraint(id, "cleared by planner")
#   existing = len(desk.iwps()) read once before step 2 (SimContext has no day number). Docstring in the style of crew.py (numbered steps).
# scenario.py: IwpPlannerParams(Strict): iwps_per_day: Count = 1; scope_items: int = Field(default=6, ge=1, le=40);
#   constraint_rate: float = Field(default=0.5, ge=0, le=1); clears_per_day: int = Field(default=1, ge=0, le=5).
#   ActorsConfig.iwp_planner: IwpPlannerParams | None = None (off unless named: needs a CWP-less awp project); ACTOR_NAMES inserts "iwp_planner" after "workface_planner".
#   ROLE_NAMES is NOT changed (I6). orchestrator.all_identities(): people = (*ROLE_NAMES, "approver", "iwp_planner").
# actors/registry.py: "iwp_planner": IwpPlanner
# testing.py: FakeWorld gains iwp_rows, scope_rows, constraint_rows (lists of dicts, default []); FakeClient implements IwpDesk over them
#   (keys f"{project}-IWP-{n:04d}" style is fine; record rows appended to record_rows with record_type awp.IWP / awp.ScopeItem / core.Constraint so sim_assert-style checks see them;
#   clear_constraint sets state "Cleared"; open_constraints returns Open ones) and writes the same events its siblings write.
```
Consequential pins (rule 12): the provided-identities list in `test_orchestrator.py`, the `enabled()` order pins in `test_scenario.py` and `ACTOR_NAMES` pins: update them as the union (append `user:sim-iwp_planner`, insert the name) and list them in the report.

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/actors/crew.py`, `actors/document_registrar.py`, `actors/base.py` lines 190-260 (desk lookup, `register_document`), `actors/registry.py`
- `packages/tl-sim/src/tl_sim/client.py` lines 60-130 (Protocols) and 228-300, 395-415 (`HttpSimClient`, a desk method)
- `packages/tl-sim/src/tl_sim/testing.py` (FakeWorld init, `FakeClient.register_document`), `scenario.py` lines 100-200, `orchestrator.py` lines 85-92
- `packages/tl-modules/awp/src/tl_mod_awp/commands.py` lines 516-560, 586-635 (field names); `packages/tl-core/src/tl_core/constraints/commands.py` lines 86-160
- `packages/tl-sim/tests/test_actor_document_registrar.py` lines 1-60 (the test pattern)
may explore: `packages/tl-api/src/tl_api/client/iwp.py` (read method signatures only)

## Allowed paths
- `packages/tl-sim/src/tl_sim/client.py`, `testing.py`, `scenario.py`, `orchestrator.py`, `actors/base.py`, `actors/registry.py` (edit, additive only); `packages/tl-sim/src/tl_sim/actors/iwp_planner.py` (create)
- `packages/tl-sim/tests/test_iwp_planner.py` (create); `packages/tl-sim/tests/test_orchestrator.py`, `test_scenario.py` (consequential pins only)
- `dev/accept/P2-I2/T10a.py` (create), `docs/reports/P2-I2/T10a.md` (create)
- Size check (§6): 7 source files (one new), about 300 lines with tests; no schema, dependency or change outside tl-sim.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I2/T10a.py
just gate packages/tl-sim
```
`T10a.py` on `FakeWorld`, actors stepped with `make_context(...)` as in the registrar test, seed 1, `iwps_per_day=2`, `scope_items=3`, `constraint_rate=1.0`, `clears_per_day=1`, two days: `PASS built` (day 1: 2 IWPs, 6 scope items, each IWP in state In development with 3 scope links; ground truth has 2 + 6 + 1 `record.created` notes), `PASS raised` (one constraint, subject the last IWP, category from CATEGORIES, state Open), `PASS cleared` (day 2: the day-1 constraint is Cleared and the day-2 one is Open), `PASS same seed` (two worlds, identical keys and titles), `PASS off by default` (`actors.enabled()` lacks `iwp_planner`; named, it follows `workface_planner`; `ROLE_NAMES` unchanged), `PASS registry`, `PASS identities` (`all_identities()` ends with `user:sim-iwp_planner` before the assistant). Ends `T10a ok`.
`test_iwp_planner.py`: the same cases as pytest, plus one `HttpSimClient` test with a recording stub `ApiLike` pinning the command names and bodies (`CreateIwp`, `CreateScopeItem`, `AddIwpScope`, `StartIwpDevelopment`, `RaiseConstraint` with `phase="ready"` and `severity="blocking"`, `ClearConstraint`).

## Report requirements
`docs/reports/P2-I2/T10a.md` <= 60 lines; deviations first; the consequential-pin list; say plainly that scope add, start and clear have no ground-truth intent (I6). Subject `P2-I2-T10a: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a command is refused for a `user:sim-*` token (an access word or a missing role: say which), if `ApiLike` cannot gain the two reads without a change outside Allowed paths, or if a pin outside the list above breaks.

## Blocked
(implementer writes here)

## Decision
D40 (r10): person actor `iwp_planner`, not an extension of the agent `workface_planner`; identity added to `all_identities()`.
