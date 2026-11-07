# P2-SEED-T05 — Fixed anchor tags and documents in the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Branch: `p2/seed-t05-anchors`   (from p2/seed)

## Goal
Other fixtures (the drawings and model panel's fake locator, plan check F4) need names that never change with the seed.
In `dev/seed/demo_project/engineering.py` and `documents.py`, always create, besides the generated ones:
- tags `200-V-1027` (a reactor feed valve) and `300-T-101` (a crude tank) with fixed descriptions;
- document `P200-200-PID-4701` (P&ID, 3 sheets, **restricted** confidentiality) and `P200-200-PID-4702` (P&ID with
  revisions A and B, A superseded by B), each with a small PDF rendition;
- export the names as constants in `dev/seed/demo_project/anchors.py` (`ANCHOR_TAGS`, `ANCHOR_DOCUMENTS`).
The generated counts may grow by these few records; the determinism test must still pass.

## Allowed paths
- `dev/seed/demo_project/engineering.py`, `dev/seed/demo_project/documents.py`, `dev/seed/demo_project/anchors.py` (create)
- `tests/tools/test_demo_project_anchors.py` (create: the anchors exist with those properties after a run)
- `docs/reports/P2-SEED/T05.md`

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/tools/test_demo_project_anchors.py tests/tools/test_demo_project.py | tail -20 | tee .gate/summary.txt` ends `gate: PASS`
