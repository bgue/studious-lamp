# P2-I2-S5 — Tests piece: pytest for C1, C2, S3, S4, T06a1-3, twins, targeted mutants (STAGED)

Status: staged (dispatch when T04d, T04e1, T04e2, T04g and T04c1 are merged; runs beside T10b)
Tier: builder
Kind: piece
Review: full
Labels: tests, core, confidentiality
Depends on: C1, C2, S3, S4, T06a1, T06a2, T06a3, T04a, T04a2 merged; T04c1 for the route twin
Branch: `p2/i2-s5-tests`
Worktree: harness-created (from `p2/i2` head)

## Goal
The owner policy deferred pytest to this piece: every acceptance script left by the pieces becomes durable pytest in the owning package, plus the twin tests and at most 5 targeted mutants. No production code changes; if a test finds a bug,
report it (`4`), do not fix it.

## Scope (read each report first: `docs/reports/P2-I2/{C1,C2,S3,S4,T06a1,T06a2,T06a3}.md`, then the matching `dev/accept/P2-I2/<id>.py`)
1. C1 (`packages/tl-core/tests/`): schema and workflow (opt-in transitions on CWP and IWP, phase `ready`), the words, event types.
2. C2 (`packages/tl-core/tests/constraints/`, create): numbering, due_at as given, the four commands (viewer refused x4), module sources, `phase_not_gated`, suppress/exists, links (resolves, targets, blocks), `cleared_at` refusal, guard on IWP `ready` and CWP
   `start_execution`, keys-only guard message, five-reader walk, no-target twin, history filter, rebuild equals incremental. Use the guard locations in the C2 report ("Guards for S5").
3. S3 (`packages/tl-modules/awp/tests/`): sign-off and issue access words, signer role, distinct signers, wrong record hash, hold and release, permit expectation reported missing and not blocking.
4. S4 (`packages/tl-modules/awp/tests/readiness/`): job claim and settle, nine checks and `n_a` counts, `ready` true/false/unknown, Constraint check <-> Ready moves, guard refusal recorded as the `constraints_cleared` detail, check-sourced constraints raise and clear,
   event-to-IWP mapping (`work_package_id`, else `evaluate_now`), `IWP.Ready` only when the state after the move is Ready (S4 review F2), bounded `resolve_via`.
   S4 F3 note (carry as a test or a recorded gap): the raw requeue `UPDATE` in S4's job code bypasses the job service; add a test that pins the observable behaviour (one queued run per IWP, lease respected) and say in the report whether the raw UPDATE should become a service call.
5. T06a1/2/3: `documents_current` (current, stale pin, floating, none), `rfis_answered`, resolver filtered by link ids (bounded statements, no 1000 cap).
6. D22/D26 twin, one test: the whole `CheckResult` of `documents_current` for a hidden pinned document equals byte for byte the `CheckResult` for a missing one; and (S4 review F1) the engine drops refs it cannot resolve for the viewer, so no hidden id or key appears
   in any read. Whole-event hiding of IWP readiness events is the ADR-0016 scanned-stream rule (per-viewer redaction deferred on the trunk): assert that rule, do not expect per-viewer redaction.
7. T04c1 route twin (when merged): the route body of a hidden pinned document equals the body of a missing one; five-reader walk of every new route, extending `packages/tl-api/tests/test_confidentiality_walk.py` in union form.

## Mutants (run by you in your worktree, reported in 3 lines)
One sentinel plus at most 5 targeted, each must make a named test fail: (a) C2 subject join dropped (`_where` hidden condition), (b) C2 `phase_not_gated` check, (c) S3 distinct-signer check, (d) S3 record-hash comparison, (e) S4 `constraints_cleared` open-count condition.
Revert each; the tree must end clean.

## Allowed paths
- `packages/tl-core/tests/**`, `packages/tl-modules/awp/tests/**`, `packages/tl-modules/documents/tests/**`, `packages/tl-modules/correspondence/tests/**`, `packages/tl-api/tests/test_confidentiality_walk.py` and new `packages/tl-api/tests/test_iwp_constraint_routes.py`
- `docs/reports/P2-I2/S5.md` (create). Nothing under any `src/`.

## Acceptance
Gate one package at a time (the whole 4-part gate OOMs on 16 GB): `just gate packages/tl-core/tests/constraints`, `just gate packages/tl-modules/awp/tests`, `just gate packages/tl-modules/documents/tests packages/tl-modules/correspondence/tests`,
`just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_iwp_constraint_routes.py`; `just check`. Tests are dialect-neutral (no `group_concat`), pass ruff, never reuse a real module name for a stand-in.

## Report requirements
Builder return <= 15 lines; report <= 60 lines: tests per area, the mutant table (mutant, test that killed it), the F3 verdict, any bug found. Commit subjects `P2-I2-S5: ...`; trailer as the harness requires plus `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation
- Stop with `4` if a test needs a production change; report the file and line.
