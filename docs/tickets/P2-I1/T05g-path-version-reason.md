# P2-I1-T05g — PathVersion.reason_code (the reason a path version was made)

Status: ready
Tier: haiku
Review: full
Labels: api
Depends on: T10, T03a (merged)
Branch: `p2/i1-t05g-reason`
Worktree: `/home/user/wt/i1/t05g` (from `p2/i1` head)

## Goal
The path screen (T05c, blocked on this) shows a Reason per version and in its state line ("Re-sequenced 2026-10-29 by A. Ruiz · reason Access"). `PathVersion` has no reason; the reason sits on the steps of that version (`schema/modules/awp/path.yaml` `reason_code`: only the moved step carries it, the others are null). Add one defaulted field and fill it in `path_versions`, which already walks every step of every version: no new query, no route change (the routes return the model as it is); `docs/reference/openapi.json` is regenerated.

## Interfaces (verbatim; add this, change nothing else)
```python
class PathVersion(BaseModel):          # views.py
    ...                                # existing fields unchanged
    reason_code: str | None = None     # PathReason code of the re-sequencing that made this version
```
Rule: version 1 -> `None` (it is the definition). Version n > 1 -> the first non-null `reason_code` among that version's readable steps in position order, else `None`. `path_versions` stays one pass over `_steps(...)`; counts and order unchanged; a step the viewer may not read contributes nothing (a reason on a hidden area's step is not shown).

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` lines 120-165 and 700-790 (`PathStep`, `PathView`, `PathVersion`, `_steps`, `path_versions`)
- `packages/tl-modules/awp/src/tl_mod_awp/handlers/path.py` lines 105-165 (what a move writes)
- `dev/accept/P2-I1/T10b.py` (copy-the-seed pattern), `dev/accept/P2-I1/T04e.py` (CliRunner on a seed copy)
- `docs/reference/openapi.json` is regenerated, not read
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/views.py`
- `docs/reference/openapi.json` (`uv run python -m tl_api.openapi`; `just check` fails on drift; use `git diff --minimal` to review)
- `packages/tl-tui/tests/fakes_awp.py`: in `seed_awp` set `reason_code="Access"` on the version-2 `PathVersion` only (consequential pin, rule 12; list it in the report)
- `dev/accept/P2-I1/T05g.py`, `docs/reports/P2-I1/T05g.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T05g.py --db .accept/p2-i1.db
uv run python dev/accept/P2-I1/T10.py --db .accept/p2-i1.db
```
No pytest. `T05g.py` copies the seed to a temp file and prints `PASS <check>` for: the seed's versions all have `reason_code None` (v1 only); after `MoveCwaInPath` of A3 to position 1 with reason `Access` (command as in `S4.py` line 273, or the `tl awp path` move verb through `CliRunner`) `path_versions` gives v2 with `Access` and v1 with `None`, other fields unchanged (`step_count`, `is_current`, newest first); a second move with reason `Weather` gives v3 `Weather`, v2 still `Access`; with `views._hidden` patched to hide the moved step's area the v2 reason is `None`; version 1 stays `None` even if a step of it carries a reason. Ends `T05g ok`.

## Tests to add
none (T11 adds the cases to `test_views.py`).

## Report requirements
`docs/reports/P2-I1/T05g.md` <= 60 lines, <= 5 decisive output lines per command; deviations first. Subject `P2-I1-T05g: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if the field needs a schema or projector change, a second query, or a route change.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
