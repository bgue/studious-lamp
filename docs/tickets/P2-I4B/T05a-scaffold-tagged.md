# P2-I4B-T05a — Readiness check `scaffold_tagged`

Status: ready (provided test and interface stub committed on `p2/i4b`; dispatch now)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: S1 (merged, C1)
Branch: `p2/i4b-t05a-scaffold-tagged`
Worktree: `/home/user/wt/i4b/t05a` (from `p2/i4b` head)

## Goal
The readiness check `scaffold_tagged` (frozen contract `docs/build-spec/phase2-contracts-draft.md` §1) answers for one IWP whether every scaffold it `requires` stands, is tagged green and is in date. It is found through the entry point
group `throughline.readiness_checks`, so the readiness job lists it beside the others. (T05b, the labour check, follows; it replaces the awp placeholder of that name and is a separate ticket.)

## Brief references (pasted)
> Answer (decision D9a of this increment): `n_a` (detail `NO_SCAFFOLD`) when the IWP has no live `requires` link to a scaffold; else, per required scaffold: **good** = state `Inspected` or `In Use`, `tag = 'green'`, and not overdue (`next_due_on` is NULL or `next_due_on >= today.isoformat()`: the due day itself is in date). `ok` when every one is good, detail `f"{good}/{total} required scaffolds tagged green and in date"`; else `blocked`, same detail, `resolve_via` = a `RecordRef(record_id, SCAFFOLD, key)` for each scaffold that is not good, by key, at most `MAX_RESOLVE_VIA`. `count_ok = good`, `count_total = total` in both. A scaffold in `Modify` or `Dismantle`, a yellow or red tag, no tag, or not yet erected is not good. Detail text is fixed words and counts; no note, no subject, no path.
> Read (one statement, no viewer: a job runs it, `resolve_via` carries keys only and the engine repeats the id in the key slot): `SELECT cr.id, cr.key, COALESCE(cr.status, 'Requested') AS state, s.tag, s.next_due_on FROM cur_links l JOIN cur_core_record cr ON cr.id = l.to_id JOIN cur_scaffold_scaffold s ON s.id = cr.id WHERE l.scope = :scope AND l.from_id = :iwp AND l.relation = 'requires' AND l.status <> 'retracted' AND cr.type = :type AND cr.voided = :no ORDER BY cr.key, cr.id` (use `names.SCAFFOLD`, `names.SCAFFOLD_TABLE`, `names.REQUIRES`, `names.REQUESTED`; the same link filter is `_REQUIRING_SQL` in `handlers/scaffold.py`).
> Any exception while reading is `unknown` with the fixed `UNKNOWN` text, never raised (pattern: `evaluate` in `tl_mod_materials/readiness.py`). `today` is the job's clock; the check never reads another.
> `watches` is `{SCAFFOLD}` (already in the stub). Entry point line in `packages/tl-modules/scaffold/pyproject.toml`: `[project.entry-points."throughline.readiness_checks"]` `scaffold_tagged = "tl_mod_scaffold.readiness:scaffold_tagged"`.

## Interfaces (in the tree as a stub: constants, class and factory are final; fill `evaluate`, change no name)
`packages/tl-modules/scaffold/src/tl_mod_scaffold/readiness.py` (read it first).

## Context (read these, nothing else)
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/{readiness.py, names.py}`, `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (the pattern: `_result`, `try/except`)
- the provided test `docs/tickets/P2-I4B/provided/T05a_test_scaffold_tagged.py` (do not edit it); `packages/tl-core/src/tl_core/readiness/types.py` (`CheckResult`, bounds)
may explore: `packages/tl-core/src/tl_core/readiness/harness.py` (what the contract proves)

## Allowed paths
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/readiness.py` (the body and private helpers)
- `packages/tl-modules/scaffold/pyproject.toml` (the one entry-point block above; no dependency change)
- `packages/tl-modules/scaffold/tests/test_scaffold_tagged.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I4B/T05a.md` (create)
- Consequential pins (rule 12; list each in the report): every test, script or demo that asserts the exact set of loaded check names breaks only because `scaffold_tagged` is now loaded. Find them with `grep -rn '"permits_planned"' packages dev tests --include=*.py`; add `"scaffold_tagged"` to each exact-set assertion (as a union, change nothing else). Known: `packages/tl-core/tests/test_readiness_registry.py:~56`, `dev/demos/p2_w0_demo.py:~318`, `dev/accept/P2-W0/W0-B1.py:~138`; check `packages/tl-modules/awp/tests/readiness/test_readiness_engine.py`, `packages/tl-api/tests/test_iwp_constraint_routes.py`, `dev/accept/P2-I2/T06a2.py` and any other hit.

## Acceptance
```
uv sync --all-packages
cp docs/tickets/P2-I4B/provided/T05a_test_scaffold_tagged.py packages/tl-modules/scaffold/tests/test_scaffold_tagged.py
just check
just gate packages/tl-modules/scaffold/tests/test_scaffold_tagged.py packages/tl-core/tests/test_readiness_registry.py packages/tl-modules/awp/tests/readiness packages/tl-api/tests/test_iwp_constraint_routes.py
cmp docs/tickets/P2-I4B/provided/T05a_test_scaffold_tagged.py packages/tl-modules/scaffold/tests/test_scaffold_tagged.py
```
Expected: the 11 provided tests pass (also once under `just gate-pg packages/tl-modules/scaffold/tests/test_scaffold_tagged.py`), the pinned files still pass, `cmp` silent.

## Tests to add
The provided test (copied): found by name with its watches; `n_a` and the contract for a package that requires nothing (another package's scaffold does not count); green `Inspected` and `In Use` are `ok` with the contract; one good, one erecting, one not yet designed gives `blocked 1/3` with the two refs and their keys; yellow, red and modified block and a new green tag clears them; a scaffold being dismantled blocks; the due day is in date, the day after is not; a retracted link is ignored; a failed read is `unknown` with the fixed text; one statement.

## Escalation triggers
- Another exact-set pin that needs more than adding the name; a column the SQL needs is missing; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; the pins updated listed. Commit subjects `P2-I4B-T05a: ...`; trailer lines as your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-15)
The statement-count test counted the SQLite adapter's `BEGIN DEFERRED` (emitted through `before_cursor_execute`) as a read.
Its listener now ignores BEGIN, COMMIT and ROLLBACK; the bound stays at one read statement. The provided copy is updated
to the same bytes; both paths are allowed for that.
