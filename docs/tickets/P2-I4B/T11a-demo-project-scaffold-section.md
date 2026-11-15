# P2-I4B-T11a — Demo project section: scaffolds on P200

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: S1, T09a (merged)
Branch: `p2/i4b-t11a-seed-scaffold`
Worktree: `/home/user/wt/i4b/t11a` (from `p2/i4b` head)

## Goal
The demo project generator gains a section `scaffold`: scaffolds built through the real commands from the project's Approved scaffold requisitions, in several states, so the register, the record screen and the tour have data. No `requires` links to IWPs (readiness of every P200 IWP must not move).

## Brief references (pasted)
> Owner rule 2026-11-14: screenshots of new modules go into the tour as they land. P200 has 4 scaffold requisitions (`dev/seed/demo_project/requisitions.py` KINDS positions 20-23; their final states are `FINAL[20:24]`) and no scaffold records.

## Interfaces (verbatim from repo at the branch point)
Pattern: `dev/seed/demo_project/quality.py` (a `build(world, rng)` that runs one command per step as a roster person on a day via `world.on(day)`, ends with `register("quality", build, needs=("quality.PunchItem",))`).
Commands (`tl_mod_scaffold.commands`, handlers in `tl_mod_scaffold.handlers`, names in `names.py`): `RegisterScaffold(request_id, title, location_text)`, `DesignScaffold(scaffold)`, `ErectScaffold(scaffold)`, `InspectScaffold(scaffold, result)` (`conditional` or `fail`), `TagScaffoldGreen(scaffold)` (controller word), `ReleaseScaffold(scaffold)`. Command order and states: `dev/accept/P2-I4B/S1.py` `check_lifecycle`.
Section: `build(world, rng)`: for each Approved scaffold requisition (in order; read them with the requisitions views or SQL on `cur_requisitions_scaffold_request`, as `tl_mod_scaffold` does) one `RegisterScaffold` by `lhartmann`, then by position: 1st Designed; 2nd Erecting; 3rd In Use (tagged green by `mokafor`, released); 4th Modify (green, released, then `InspectScaffold` fail). With fewer approved requests, the first ones; with none, a one-line note `scaffold: no approved scaffold requisitions`. Days: from `BASE` of the requisitions section onward, never after `TODAY`. `register("scaffold", build, needs=("scaffold.Scaffold", "requisitions.LaborRequisition"))` (check the real type name in `schema/modules/scaffold/`).

## Context (read these, nothing else)
- `dev/seed/demo_project/quality.py`, `world.py` (`World.on`, `run`, `actor_of`), `registry.py`
- `dev/seed/demo_project/requisitions.py` (top 100 lines only)
- `dev/accept/P2-I4B/S1.py` (`check_lifecycle`, `fresh`)
- `tests/tools/test_demo_project_quality.py` (shape for the section test), `tests/tools/test_demo_project.py` (pinned section lists)
may explore: `packages/tl-modules/scaffold/src/tl_mod_scaffold/handlers/scaffold.py` (handler names only)

## Allowed paths
- `dev/seed/demo_project/scaffold.py` (create); `dev/seed/demo_project/__init__.py` or the one place the sections are imported (one line; find it with grep `quality` in `dev/seed/demo_project/`)
- `tests/tools/test_demo_project_scaffold.py` (create)
- consequential pins (union form, listed): `tests/tools/test_demo_project*.py` lists of sections or counts of record types
- `docs/reports/P2-I4B/T11a.md` (create)

## Acceptance
```
just check
just gate tests/tools/test_demo_project_scaffold.py tests/tools/test_demo_project.py
```
Expected: pass. The tools gate is slow: run in the background with a long timeout. Also run once: `uv run python -m dev.seed.demo_project --db /tmp/x-scaffold.db --sections core,engineering,awp,constraints,requisitions,scaffold` and paste the summary line (remove the file after).

## Tests to add
`test_demo_project_scaffold.py` (child-process runs as in the quality test): the section builds N scaffolds for N approved requests, one per request, states Designed, Erecting, In Use, Modify in that order, tags green on the In Use one and red on the Modify one; the same seed twice gives the same ledger hash; a run without `scaffold` leaves every other type's count unchanged; a run without requisitions gives the one-line note.

## Report requirements
Standard report; paste the state counts of the built scaffolds.

## Escalation triggers
- Stop if a scaffold command refuses a roster person (access words): write which word and who.
- Stop if any other section's counts change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1
Orchestrator rulings after the first attempt was blocked:
- `"scaffold"` is added to `ORDER` in `dev/seed/demo_project/registry.py` right after `"requisitions"` (allowed).
- `needs=("scaffold.Scaffold", "requisitions.ScaffoldRequest")` (the type the requisitions section registers).
- Actors: `lhartmann` (project engineer, `user` role) registers, designs, erects, releases and inspects; `mokafor` (administrator, holds the controller word) tags green. Section runs through commands only, deterministic, no `requires` links.
- Fact found: of the 4 scaffold requisitions of P200 only 1 is Approved (`FINAL[20:24]` = Approved, Cancelled, Requested, Rejected), so the demo holds 1 scaffold (Designed). The In Use and Modify paths are coded but not reached in P200 data.
