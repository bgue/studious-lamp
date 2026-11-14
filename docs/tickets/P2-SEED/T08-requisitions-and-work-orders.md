# P2-SEED-T08 — Requisitions and work orders in the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: —
Branch: `p2/seed-t08-requisitions`   (from p2/seed; worktree /home/user/wt/seed/p2-seed-t08)

## Goal
Fill `dev/seed/demo_project/requisitions.py` (a stub) so `tl req ls` and `tl wo ls` are full. About 24 requisitions through
`RaiseRequisition` (models in `tl_mod_requisitions/commands.py`, handlers in `handlers/requisitions.py`): 7 labor, 8 material
(lines use item ids of the materials section and its cost codes; when materials is absent, raise only the other kinds and print
one line), 5 general, 4 scaffold; `for_record_id` an existing IWP or CWP, `cost_code_id` a cost code of the awp section.
Raise as `lhartmann`, `cbrooks`, `pnair`; approve, reject and cancel as `mokafor` (the requester may not approve, and the
approver holds the superuser word; an admin holds all). Final states by position: 10 Approved (each opens a work order), 4
Rejected with a reason, 3 Cancelled (one after approval), 7 left Requested. Then drive the work orders (handlers in
`handlers/work_orders.py`): of the ~9 live ones, 3 stay Open, 2 Scheduled, 2 Assigned (`user:cbrooks`, `user:pnair`), 1 Started, 1
Completed with `hours_actual`, plus one more that is Closed (closing moves its requisition to Closed). Pass the version each
command needs by reading it with `world.version(id)`. Every event falls on a day of the project calendar through
`world.on(day)`, between 2026-10-05 and TODAY; need-by dates after TODAY for most, 3 before it (overdue). Only the section's
`rng`; no raw SQL writes; confidentiality as the module default.

## Context (read these, nothing else)
- `dev/seed/demo_project/quality.py` (pattern: `_run`, `FINAL` by position), `world.py`, `registry.py`
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/commands.py` (bodies and commands)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/handlers/work_orders.py` (handler names only)
- `docs/runbooks/requisitions.md`
- `tests/tools/test_demo_project_quality.py` (child-process test pattern)
may explore: `dev/seed/demo_project/materials.py` (how items and cost codes are named)

## Allowed paths
- `dev/seed/demo_project/requisitions.py`
- `tests/tools/test_demo_project_requisitions.py` (create)
- `docs/reports/P2-SEED/T08.md`

## Acceptance
```
just check
just gate tests/tools/test_demo_project_requisitions.py tests/tools/test_demo_project.py
```

## Tests to add
`tests/tools/test_demo_project_requisitions.py`: `--sections core,engineering,awp,materials,requisitions` on fresh SQLite:
counts per kind (7/8/5/4), per state (pin the exact numbers you build; one Cancelled requisition was Approved first and its work order is Cancelled), work orders per state, 3 overdue need-by dates, one Closed work order with a Closed requisition;
deterministic twice (counts and key hash); a run without the section leaves other types' counts unchanged.

## Escalation triggers
- A roster person lacks a word that the seed needs: do not edit `core.py`; stop and name the person and word.
- The module lacks a command the states need (stop; no command is added here).
