# P2-I4A-S5 — Close the DONE-gate failures (whole suite on `p2/i4a` @ head)

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: tests, integration, webhooks, confidentiality
Branch: `p2/i4a-s5-done-fixes`
Worktree: harness-created under `/home/user/wt/i4a/s5` (from `p2/i4a` head)

## Goal
`just gate` (the whole suite, 4 parts) is green on this branch. The orchestrator's run on `p2/i4a` gave the failures
below. Most are registries the new `requisitions` module must join; fix each at its root, never by skipping,
deselecting or weakening a test. The P2-I5 close fixed the same kind of webhook failure for awp (see
`tests/webhooks/scenario.py` MODULE_STREAMS on branch `p2/i5`, commit b964bcfe, for the pattern).

1. **Part 1, collection (5 errors).** `packages/tl-api/tests/test_{activity_intent,activity_walk,checks_walk,intent_walk,note_need_walk}.py`
   do `from test_confidentiality_walk import PASSWORD, MAY_READ, Seed`. When tl-api and tl-mcp tests land in one pytest
   session, the bare name resolves to `packages/tl-mcp/tests/test_confidentiality_walk.py`. The new requisitions test
   directory shifted the part split, which exposed this. Make the import unambiguous (for example a helper module with a
   unique name in tl-api tests that both import, or load by path as other tests do); the walk files keep their checks.
2. **Twin walk (4 failures).** `tests/confidentiality/test_twin_walk.py`: `get_requisition: add values for the argument 'key'`.
   Add the requisition tools' argument values to the walk's table (and any other new requisition tool the walk names).
3. **Webhook catalog (2 failures).** `tests/contract/test_webhook_catalog_contract.py` and
   `tests/parity/test_webhooks_parity.py[sqlite]`: the scenario does not deliver the requisition and work-order event
   types. Add their streams to `tests/webhooks/scenario.py` MODULE_STREAMS (opener + followers in a valid order).
4. **Module role seams (2 failures).** `tests/services/test_module_role_seams.py`: the API table, the index and the
   require-generic walk must include `requisitions`.
5. **Modules offline (2 failures).** `tests/services/test_modules_offline.py`: counts (`10 == 9`) and the module list.
   Update the pinned lists for the new module, after checking the module really declares only draft-only types if the
   test asks that.
6. **Webhook dispatcher (1 failure).** `tests/webhooks/test_dispatcher.py::test_replay_between_times_uses_the_recorded_time`
   (`assert 0 == 1`). Find whether a requisition event lacks a recorded/valid time the replay needs; fix the root cause.
   If it is not caused by this increment (it fails on the trunk too: check with `git stash`-free means, e.g. a scratch
   worktree of `claude/wizardly-allen-m2v96s`), say so in the report and leave it.
7. **Part 2 died with exit 137 (memory).** After the above, run the whole gate; if a part is killed again, rerun that
   part's paths alone with `just gate <paths>` and report both.

## Context (read these, nothing else up front)
- The failing test files above; `tests/webhooks/scenario.py`; `docs/reports/P2-I4A/S1.md`, `S2.md` (event names)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/module.py`

## Allowed paths
- `tests/**`, `packages/tl-api/tests/**`, `packages/tl-mcp/tests/**`
- `docs/reports/P2-I4A/S5.md`
- Not `schema/`, not `packages/*/src/**` unless item 6 proves a source bug; then stop and write it under Blocked.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate
```
At most one heavy pytest session at a time (another session shares the box).

## Report requirements
Builder return <= 15 lines; report <= 60 lines, one line per item with the root cause. Commit subjects
`P2-I4A-S5: ...`; trailer is the attribution lines your harness requires then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(builder writes here)

## Decision
(orchestrator writes here)
