# P2-I1-S7 — Reload after compensation recreates the WBS nodes

Status: ready, gated (schema event: human approver under P2-Q10 pattern, orchestrator line in `docs/reports/APPROVALS.md` at merge)
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: S2 S3 T02 (merged)
Branch: `p2/i1-s7-wbs-reload`
Worktree: `/home/user/wt/i1/s7` (from `p2/i1` head)

## Goal
Spec m3-wbs-cwp section 6: "compensate, then reload gives the same tree". Today `WbsTarget.reverse` (targets.py ~449) retires the nodes the run made; the record keys stay taken (`key_taken` counts retired and void records, as core does), so a reload plans `new 0 existing 12`, refuses with "nothing to load", and allocation to the node is refused. A fix inside the target is impossible: no event brings a node back, and a key cannot be reused. Decision (orchestrator, 2026-11-04): compensating an awp load ends the batch and a reload recreates the 12 WBS nodes.

## Design (the builder may refine; report any deviation first)
- New event `WBSNode.Reinstated {reason}` (schema `schema/modules/awp/events.yaml`, projector `projectors/wbs.py` clears `retired`), command `ReinstateWbsNode {node, reason}` (access word `awp.wbs.configure`, superuser, as RetireWbsNode), handler beside `handle_retire_wbs_node` (refuses a node that is not retired; asks a rollup; refuses when the parent is retired). Run `just gen`; commit the output. Add the access-word, catalog and `module.py` registration lines the way `RetireWbsNode` has them.
- `WbsTarget.plan`: a row whose code resolves to a RETIRED node of the same parent code is planned as a row to reinstate, not as `existing`; a retired node with another parent, or a live node, stays `existing`/`M_TAKEN` as now. A reload with the same file plans `new 12`.
- `WbsTarget.apply`: for such a row call the reinstate handler (parents first, as now), then re-map cost codes only when the node's lines differ from the row (`_lines_differ`); `Created` carries the existing stream id, so a second compensation retires them again.
- `WbsTarget.compare` and `reversals` unchanged except they must treat a reinstated node as Active.
- The CWA target has the same shape (`CWA.Retired`); out of scope here, say so in the report. Only the WBS target blocks T08.

## Allowed paths
`schema/modules/awp/**` (events, commands if declared there), generated output by `just gen` only, `packages/tl-modules/awp/src/**`, `packages/tl-modules/awp/tests/**`, `dev/accept/P2-I1/S7.py`, `docs/reports/P2-I1/S7.md`, access-word and registry lines `ReinstateWbsNode` needs (list them in the report).

## Acceptance (run once)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S7.py
just gate packages/tl-modules/awp packages/tl-modules/legacy
```
`S7.py` (SQLite tmp db; `PASS <check>`; final `S7 ok`; <= 50 lines): load `packages/tl-modules/awp/src/tl_mod_awp/samples` WBS file (12 nodes); compensate; all 12 retired; reload plans `new 12` and writes 12 `WBSNode.Reinstated` (no new records); tree equals the first load (codes, parents, positions, lines, retired false); a CWP can allocate to a reinstated leaf; compensate again retires 12; a package allocation blocks the retire as before; Reinstate of an active node refused; hidden-reader check as the other WBS commands (viewer filter before the lookup).

## Guards to mutate (1 sentinel + at most 5)
retired-only reinstate; same-parent check; parent-retired refusal; rollup request; access word.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines; builder return <= 15 lines. Never name a model.
