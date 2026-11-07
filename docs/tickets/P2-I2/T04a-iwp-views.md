# P2-I2-T04a — IWP and scope read views (awp)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: S2, S3 (merged)
Branch: `p2/i2-t04a-iwp-views`
Worktree: `/home/user/wt/t04a` (from `p2/i2` head)

## Goal
`tl_mod_awp.iwp_views` gives the API, CLI, MCP and screens one read layer over IWPs and their scope: a list with filters, one IWP by number, and the scope items of an IWP. Nothing writes; nothing checks an
access word (entry points do). Constraint reads are T04a2 (core). Readiness reads come with S4's tables (T04c1).

## Brief references (pasted)
> Pattern: `packages/tl-modules/awp/src/tl_mod_awp/views.py` (`_cwp_rows`, `cwp_detail`): pydantic row models, `text()` SQL joined to `cur_core_record r`, `not_hidden("r.id")` before `ORDER BY ... LIMIT`,
> `r.voided = False`, a number is `r.key`, a reference to another record is named only when `hidden_among` lets it through.
> Tables: `cur_awp_iwp i` (id, scope, discipline, cwp_id, planned_start, planned_finish, foreman, estimated_hours, crew_text, signoffs_json, last_seq), `cur_awp_scope_item s` (id, scope, commodity, description, qty,
> uom, est_hours, cwp_id, last_seq). IWP state is `cur_workflow_state.state` by `record_id`, default `Draft` (`names.IWP_DRAFT`; see `facts.py` `_IWP_SQL`). Scope membership: `cur_links` rows `relation = 'belongs_to'`,
> `source = 'rule'`, `status = 'active'`, from the scope item (`from_id`) to the IWP (`to_id`) (`names.SCOPE_RELATION`; `facts.py` `_SCOPE_SQL` reads both directions; tags are in scope too, type `TAG_TYPE`).
> Pins: `cur_links` rows from the IWP with `pin IS NOT NULL`, `status = 'active'`.
> Sign-offs: `projectors.iwp.signoff_rows(i.signoffs_json)` gives dicts (pass them through as stored, do not reshape).
> Constraint counts: `tl_core.constraints.queries.count_constraints(conn, scope, subject_id=<id>, state=<s>)` for `Open` and `Assigned`; it applies the viewer join itself.
> Hidden looks like missing: a hidden IWP is absent from the list and `iwp_detail` returns `None`; counts and totals never include it; the scope list of a hidden IWP is `None` (not `[]`).

## Interfaces (to create; signatures fixed)
```python
# packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py
class IwpRow(BaseModel):  # id, number (r.key), title, state, discipline, planned_start, planned_finish, foreman, estimated_hours (Decimal | None), cwp_number (str | None; None when the CWP is hidden or unset), scope_count (int)
class IwpDetail(IwpRow):  # + crew_text, signoffs (list[dict[str, Any]]), pin_count (int), open_constraints (int: Open + Assigned), scope_by_type (dict[str, int])
class ScopeRow(BaseModel):  # id, number (r.key or None for a tag), type, commodity, description, qty, uom, est_hours (Decimal | None)
def iwp_list(conn, scope, *, state=None, discipline=None, foreman=None, limit=200) -> list[IwpRow]: ...  # by number; limit clamped 1..500
def iwp_detail(conn, scope, number) -> IwpDetail | None: ...
def iwp_scope(conn, scope, number, *, limit=500) -> list[ScopeRow] | None: ...  # by type, key; None when the IWP is absent or hidden
```

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` (lines 200-275 and 404-465 only)
- `packages/tl-modules/awp/src/tl_mod_awp/facts.py`, `names.py` (lines 100-140)
- `packages/tl-core/src/tl_core/constraints/queries.py` (signatures only), `docs/reports/P2-I2/S2.md`
- `dev/accept/P2-I2/S2.py` and `packages/tl-modules/awp/tests/s2_checks.py` (for a seeded ledger)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` (create)
- `dev/accept/P2-I2/T04a.py` (create; helper in `dev/accept/P2-I2/t04a_checks.py` if over 70 lines)
- `docs/reports/P2-I2/T04a.md` (create)
Not here: `views.py`, any other file, new pytest (S5), schema, routes, CLI.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04a.py
just gate packages/tl-modules/awp/tests
```
`T04a.py` (SQLite temp ledger built like `S2.py`; one `PASS <check>` per line; final `T04a ok`): list returns the seed's 3 IWPs by number; each filter narrows (`state`, `discipline`, `foreman`);
detail shows `scope_count` 40 for the seed IWP with 40 items, `pin_count` 2, `open_constraints` matching the seed's constraints; `scope_by_type` sums to `scope_count`; `iwp_scope` lists the items; unknown number gives `None`;
as a viewer below the class of a restricted record (see how `c2_checks.py` makes one hidden subject) a hidden IWP is absent from `iwp_list`, `None` from `iwp_detail` and `iwp_scope`, and the answer for it equals
the answer for an id that never existed; a hidden CWP gives `cwp_number` `None`; statement count of `iwp_list` is the same for 3 and for 30 IWPs (no per-row query: count with a `before_cursor_execute` listener).

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T04a: ...`; the commit trailer is the attribution lines your harness requires followed by
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if an IWP has no readable way to a hidden-aware CWP number without widening the viewer filter, or if the seed ledger lacks something the acceptance needs.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
