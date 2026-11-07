# P2-SEED-T06 — Constraint seeds on IWPs and CWPs (STAGED, do not dispatch)

Status: staged
Needs: trunk with core.Constraint (ADR-0024, now on branch p2/i2, not yet on the trunk), and wave 2 (IWP, scope, constraint
commands) merged to the trunk. Dispatch only after p2/seed has merged that trunk and `core.Constraint` is in the schema.
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: T01 (awp section), wave 2 on the trunk
Branch: `p2/seed-t06-constraints`   (from p2/seed after the trunk merge)

## Goal
Add a `constraints` section (or an extension of `awp.py`) that raises core constraints on the demo project through the real
constraint commands: about 40 constraints on 15+ IWPs and 10+ CWPs; kinds mixed (material, engineering, permit, access,
predecessor); states mixed (open, released, overdue by the 2026-11-06 clock, waived); some blocking a work package's
readiness so the readiness words differ across packages. Register it in `SECTIONS` with `core.Constraint` as the needed type,
so it is skipped with one line on a trunk without the type.

## Context (read at dispatch; the supervisor completes this list and the interfaces once the trunk has them)
- `dev/seed/demo_project/awp.py`, `registry.py`, `rng.py`; `docs/adr/0024-*.md`; the constraint command models and the awp
  readiness read model on the trunk (names not yet known on this branch)

## Allowed paths
- `dev/seed/demo_project/constraints.py` (create), `dev/seed/demo_project/__init__.py` (one registry line)
- `tests/tools/test_demo_project_constraints.py` (create: counts, states, readiness words differ, determinism)
- `docs/reports/P2-SEED/T06.md`

## Acceptance (to be confirmed at dispatch)
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/tools/test_demo_project_constraints.py tests/tools/test_demo_project.py | tail -20 | tee .gate/summary.txt` ends `gate: PASS`

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
