# P2-SEED-T01 — The awp section of the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: full
Branch: `p2/seed-t01-awp-section`   (from p2/seed)

## Goal
Fill `dev/seed/demo_project/awp.py` (now a stub) so the demo project P200 has, on the README's project calendar:
- a WBS of about 100 nodes over 4–5 levels (project → area 100–600 → discipline → system → sub-system), cost codes on
  leaf nodes only;
- 12 CWAs over the six areas, a path of construction v1, then a resequence giving v2 with a reason;
- 40–60 CWPs across areas and disciplines, allocated to WBS leaves (allocations sum to 100% per CWP), in mixed states
  (some Planned, many Released for IWP development, a few Closed), with budget hours;
- 8–12 EWP and PWP references, two of them constraint sources, linked to CWPs.
Read `docs/tickets/P2-SEED/README.md` (project, areas, people), `dev/seed/demo_project/engineering.py` (the section
pattern: `build(world, rng)`, `world.on(day)`, `world.run(handler, Command, ..., by=username)`), and the awp commands
the P2-I1 demo uses (`dev/demos/p2_i1_demo.py`, `packages/tl-modules/awp/tests/awp_world.py`). Use only the section's
`rng`; no clock; no raw SQL writes. Loads (`tl load`) may be used through their Python API if the demo does so.

## Allowed paths
- `dev/seed/demo_project/awp.py`, new data files under `dev/seed/demo_project/data/awp/`
- `tests/tools/test_demo_project_awp.py` (create: runs the generator with `--sections core,engineering,awp` on a fresh
  SQLite ledger and asserts the counts above and that two runs give the same CWP keys)
- `docs/reports/P2-SEED/T01.md`

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/tools/test_demo_project_awp.py | tail -20 | tee .gate/summary.txt` ends `gate: PASS`
- `just demo-project /tmp/<x>.db`: paste the summary line for awp in the report
