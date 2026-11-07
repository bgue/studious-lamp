# P2-SEED-T02 — The materials section of the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: full
Branch: `p2/seed-t02-materials-section`   (from p2/seed)

## Goal
Fill `dev/seed/demo_project/materials.py` (now a stub) so P200 has:
- a company item library of 150+ items (pipe, fittings, flanges, bolts, gaskets, valves, cable, tray, steel, consumables)
  with categories and base units; the project adopts most of them;
- a location tree: project → laydown yards L1–L3 → warehouse → toolcrib → gang boxes (5 levels);
- 40–60 receipts against PO lines (load the PO lines first), 8–12 of them without an MTR (Accept refused for those;
  leave them Received or Inspected), the rest accepted with an MTR file uploaded through `world.upload`;
- 150–250 stock lots over several locations as the result of those receipts;
- 300+ movements of every kind (issue against a cost code, transfer, return, adjust with a reason, dispose), stock never
  negative;
- 150 take-off (MTO) lines from a derived `mto` publication, assigned to IWP-style work package keys or CWP keys that
  exist, with real shortages (required > reserved), and reservations on some.
Read `docs/tickets/P2-SEED/README.md`, `dev/seed/demo_project/engineering.py` (section pattern), and the materials
flows in `dev/accept/P2-I3/S3.py` and `dev/demos/p2_i3_demo.py`. Use only the section's `rng`; no raw SQL writes.
The section runs after `awp` (needs CWP keys for take-off lines); if awp is empty, assign lines to a fixed work
package key and say so in the report.

## Allowed paths
- `dev/seed/demo_project/materials.py`, new data files under `dev/seed/demo_project/data/materials/`
- `tests/tools/test_demo_project_materials.py` (create: `--sections core,engineering,awp,materials` on fresh SQLite;
  asserts the counts above, that some receipts lack an MTR, that at least 20 take-off lines are short, and determinism)
- `docs/reports/P2-SEED/T02.md`

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/tools/test_demo_project_materials.py | tail -20 | tee .gate/summary.txt` ends `gate: PASS`
- `just demo-project /tmp/<x>.db`: paste the summary line for materials in the report
