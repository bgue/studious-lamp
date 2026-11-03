# P2-I1-T10c — view fields the logs need (allocated, package CWPs, WBS CWPs)

Status: ready
Tier: haiku
Review: full
Labels: api
Depends on: T10, T10b, T03a (merged)
Branch: `p2/i1-t10c-fields`
Worktree: `/home/user/wt/i1/t10c` (from `p2/i1` head)

## Goal
Five fields the terminal and web logs show and no view carries (decision D26): `CwpRow.allocated` (register column
`Allocated`), `PackageRow.title` (column `Subject`), `PackageRow.cwps` (package log column `CWPs`, panel `required by 3 CWPs`), `WbsRow.cwp_count` and
`WbsRow.cwps` (WBS panel `Parent 1.2 · 4 CWPs`, section `CWPs`). The routes return the view models as they are, so the API
gains the fields with no route change; `docs/reference/openapi.json` is regenerated. All new fields have defaults so the
clients written in parallel (T03b fake, T06) need no change.

## Brief references (pasted; spec §8)
CWP register column `Allocated` (`✓`/`—`). External packages column `CWPs`. WBS tree panel summary `Parent 1.2 · 4 CWPs ·
4 200 h`; section CWPs (table Number, Subject, %, Hours). Leaf-only allocation: a CWP is allocated to leaf nodes only.

## Interfaces (verbatim; add these, change nothing else)
```python
class WbsCwp(BaseModel):          # new, in views.py
    number: str; title: str; percent: Decimal; hours: Decimal | None   # hours = budget_hours * percent / 100, 2 places, half-even; None without budget
CwpRow:     allocated: bool = False                                    # the CWP has >= 1 allocation to a readable, non-void WBS node
PackageRow: title: str = ""                                               # the package record's title (`cur_core_record.title`, already joined as `r`)
PackageRow: cwps: list[str] = Field(default_factory=list)              # numbers of readable, non-void CWPs with a non-retracted `requires` link to it, sorted
WbsRow:     cwp_count: int = 0                                         # distinct readable, non-void CWPs allocated to the node or any descendant
            cwps: list[WbsCwp] = Field(default_factory=list)           # filled by wbs_detail only, and only for a leaf (its own allocations, by number); [] in wbs_tree
```
Rules: every CWP counted or named passes `not_hidden`/`_hidden` (a hidden CWP is absent, never counted); counts do not change with
`wbs_tree(depth=)`; `cwp_list` stays one query for allocations (no per-row query); `cwp_detail.allocations` is unchanged.
`wbs_detail` loads one node (`n.id = :node`) and `wbs_tree` all of them; both must give the same `cwp_count` for a node (one helper over the allocations and the `parent_id` chain; not a per-node query in the tree).
Tables: `CWP_ALLOCATION_TABLE` (`scope, cwp_id, wbs_node_id, percent`), links `cur_links` (see `cwp_detail` for the `requires` clause).

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` (all)
- `dev/accept/P2-I1/S4.py` lines 404-436 (records a package and links a CWP to it with `AddLink`), `dev/accept/P2-I1/T10b.py` (copy-the-seed pattern)
- `docs/reference/openapi.json` is regenerated, not read
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/views.py`
- `docs/reference/openapi.json` (`uv run python -m tl_api.openapi`; `just check` fails on drift)
- `dev/accept/P2-I1/T10c.py` (create), `docs/reports/P2-I1/T10c.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T10c.py --db .accept/p2-i1.db
uv run python dev/accept/P2-I1/T10.py --db .accept/p2-i1.db
uv run python dev/accept/P2-I1/T03a.py
just gate packages/tl-api/tests/test_openapi.py packages/tl-api/tests/test_confidentiality_walk.py
```
`T10c.py` (copy the seed to a temp file; no pytest) prints `PASS <check>` for: every `cwp_list` row has `allocated == bool(cwp_detail(..).allocations)`
(the seed has allocated and unallocated CWPs); on the copy, one EWP recorded and linked from two CWPs: `package_list` gives `title` and
`cwps` of both, sorted, and each `cwp_detail.packages` agrees; after retracting one link `cwps` has one; a leaf node's `cwps` equals
the CWPs whose detail allocates to it, with `percent`; a parent's `cwp_count` equals the distinct CWPs over its leaves (a CWP on two
leaves counts once) and is the same for `wbs_tree(depth=1)`; with `views._hidden` patched to hide one CWP id it vanishes from
`allocated` count, `cwps`, `cwp_count`. Ends `T10c ok`.

## Tests to add
none (T11 adds the cases to `test_views.py`).

## Report requirements
`docs/reports/P2-I1/T10c.md` <= 60 lines, <= 5 decisive output lines per command; deviations first; consequential pins listed
(rule 12). Subject `P2-I1-T10c: ...`; no model names; commit trailer = the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if a field needs a schema or projector change, a second query per row, or a change to a route.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
