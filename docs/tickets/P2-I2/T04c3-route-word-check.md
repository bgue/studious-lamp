# P2-I2-T04c3 — Constraint routes check the access word like the embedded client (security)

Status: ready (T04c1, T04c2 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: api, security, access
Depends on: T04c1
Branch: `p2/i2-t04c3-route-word-check`
Worktree: harness-created under `/home/user/wt/i2/t04c3` (from `p2/i2` head)

## Goal
T04c1's `Reader = Depends(guard(VIEW_WORD))` runs the route-action hook, which does not read the module access-word table: over the API a person with a role but without `core.constraint.view` is served, while the embedded client (`require_word`, `tl_tui/embedded.py` ~1815) and the CLI (`constraint_read.require_view`) refuse. Make the three constraint routes check the word through the same path, before any read, and fix review note F3.

## Findings copied in (T04c1 review; do not reopen)
- HI (orch 9): word missing on the API. Fix: in `routes/constraints.py` replace `Reader` by a dependency that keeps `guard(VIEW_WORD)` (authentication and agent rules) and then runs `tl_core.auth.module_roles.require_word(conn, holder_for_principal(principal), scope=f"project:{project}", module=ACCESS_MODULE, word=normalise_word(VIEW_WORD), what=VIEW_WORD)` on a read connection (`ctx.backend(False)`), mapping `ForbiddenError` to the API's existing 403. `ACCESS_MODULE` is the constant the CLI uses (`tl_cli/constraint_read.py` imports it; import it from where it lives, not from tl_cli). The principal is the one `guard` resolved: if `auth.py` has no public way to get it, add one small helper in `auth.py` (<= 15 lines) that `guard` itself uses; do not duplicate `_principal`.
- F3 LO: `_ANY_KEY_SQL` gets `LIMIT 1` (a key is unique per type, not per scope).
- Order: the word check runs before any lookup, so a refused caller learns nothing, not even a 404 vs 200 difference for a key.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/constraints.py` (all), `packages/tl-api/src/tl_api/auth.py` lines 100-170, `packages/tl-api/src/tl_api/commands.py` lines 335-350 (the holder pattern), `packages/tl-core/src/tl_core/auth/module_roles.py` lines 400-440, `packages/tl-cli/src/tl_cli/constraint_read.py` lines 1-65, `docs/reports/P2-I2/T04c1.md`

## Allowed paths
- `packages/tl-api/src/tl_api/routes/constraints.py`, `packages/tl-api/src/tl_api/auth.py` (helper only, as above)
- `packages/tl-api/tests/test_constraint_route_word.py` (create); consequential pins (union form, listed)
- `dev/accept/P2-I2/T04c3.py` (create), `docs/reports/P2-I2/T04c3.md` (create)

## Tests to add (`test_constraint_route_word.py`)
Walking cases, one per route (list, groups, detail) and per reader kind:
1. role without the word -> 403 before any read (assert no constraint read ran: patch `list_constraints` / `get_constraint` / `review_groups` to raise, the 403 still comes; for detail also an unknown key answers 403, not 404).
2. role with the word, low clearance: hidden subject's constraint 404 as unknown; total does not count it.
3. role with the word, high clearance: served.
4. agent actor with the word: unchanged from T04c1 (read allowed per the pinned table).
5. a key shared by a constraint and another record type in one scope: subject lookup returns the right id (F3).
Reuse the fixtures of `tests/test_api_awp.py` or T04c1's acceptance script for seeding; do not invent a new app factory.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04c3.py
just gate packages/tl-api/tests/test_constraint_route_word.py packages/tl-api/tests/test_auth_review.py packages/tl-api/tests/test_api_awp.py
```
`T04c3.py`: three readers (no role, role without word, role with word) against the three routes: 403 / 403 / 200 each; final `T04c3 ok`.

## Report requirements
Standard report, <= 60 lines, deviations first, pins listed. Commit subjects `P2-I2-T04c3: ...`; trailer as in the other tickets. No model names in committed files.

## Escalation triggers
- Stop (*Blocked*) if the check needs a change to the access-word table, a role, or `holds_word`; or if more than ~40 lines change outside tests.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
