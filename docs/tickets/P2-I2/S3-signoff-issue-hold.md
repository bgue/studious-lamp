# P2-I2-S3 — IWP sign-off, issue and hold commands

Status: ready (dispatch r3; does not depend on constraints or S4)
Tier: builder
Kind: piece
Review: full
Labels: core, access, security
Depends on: S1, S2 (merged)
Branch: `p2/i2-s3-signoff-issue`
Worktree: `/home/user/wt/i2-s3` (from `p2/i2` head)
Gate: the signer-role check is permission code: orchestrator review before merge (P2-Q10), APPROVALS line at merge.

## Goal
After this piece an IWP in Ready is signed off by two distinct signers who hold a role in `awp.release.signoff_roles`, issued to a foreman, and put on hold and released.
Everything is in `tl_mod_awp` (handlers, projectors, commands, names, actions); the commands are `controller`-word, `by_module` workflow moves, with no `roles` guard in any workflow.

## Brief references (pasted; `field-work-packaging.md` lines 38-58 and P2-Q2 are authoritative)
| Command | Word (new in `schema/settings/access-words.yaml`; this piece adds three) | Effect |
|---|---|---|
| `SignOffIwp` {iwp, record_hash} | `awp.iwp.signoff` = controller | state Ready; the actor holds one of the roles in setting `awp.release.signoff_roles` (project scope; admin holds all); not already a signer of this hash; `record_hash` equals the current one; appends `IWP.SignedOff` {by, role, record_hash}; no state move; projector appends `{by, role, at, record_hash}` to `signoffs_json` (<= 4) |
| `IssueIwp` {iwp, foreman?, record_hash} | `awp.iwp.issue` = controller | state Ready; two distinct signers hold a sign-off for the current hash; the issuer holds the word; foreman `user:<name>` (existing account, default the IWP's `foreman`, required one way or the other); appends `IWP.Issued` {by, foreman}, sets the IWP `foreman`, moves `issue` (Ready -> Issued) |
| `HoldIwp` {iwp, reason} | `awp.iwp.hold` = controller | states Ready, Issued, In progress; reason 1..300 chars; appends `IWP.Held` {by, reason}, moves `hold` (-> On hold) |
| `ReleaseHold` {iwp, reason?} | `awp.iwp.hold` | state On hold; appends `IWP.HoldReleased`, moves `release_hold` (-> Constraint check; no prior-state memory, D5) |
Record hash: the sha256 of the canonical content of the IWP at sign-off (discipline, cwp, planned dates, foreman, estimated hours, crew text, the sorted scope ids, the sorted pinned document
link ids with pin codes). Copy the pattern of `record_hash(cwp, allocations)` in `handlers/cwp.py:435` and the release flow at `:466` (the CWP's one-signer release); expose `iwp_record_hash(conn, iwp_id)` so
a person (or `tl awp iwp show`) reads the hash to sign. A change to any hashed field after a sign-off changes the hash, so earlier signatures no longer count (the projector keeps them, `IssueIwp` counts only
those equal to the current hash). Frozen fields at Ready already hold (S2), so only a return to Constraint check (`unready`) can change the hash.
`awp.release.allow_unknown_checks` and the readiness result: `IssueIwp` and `SignOffIwp` read the last `cur_awp_readiness` row; refused (fixed code `not_ready`) when absent or `ready` false; an `unknown` check
refuses unless the setting is true (S4 supplies the projection; the read is plain SQL on `cur_awp_readiness`/`cur_awp_readiness_check`, absence is `not_ready`). Roles: find how the module-role table is read
(`tl_core.auth.module_roles`); the actor's roles in the project are compared with the setting; the failure message is fixed and names no role list. Missing-expected links (permit) do not block (P2-Q8 A): reported
in `guards_evaluated` as the CWP release does.
Rules: a signer cannot sign twice for one hash; the issuer may be a signer; every refusal is a fixed `IwpRuleError`-style code (see S2's `errors.py`; new subclasses get `tl_api/errors.py` rows with the CWP row pattern).
Actions rules: `RULES` rows with word per row equal to the command word; `IWP` generic allow-list unchanged. Agents never run these commands (not proposable).

## Interfaces (open these)
`handlers/{cwp,iwp}.py`, `projectors/iwp.py`, `commands.py`, `actions.py`, `names.py`, `errors.py`, `common.py` (`move`, `append`, `setting_value`), `schema/modules/awp/{iwp,iwp_events}.yaml`,
`schema/fixtures/workflows/awp-iwp.yaml` (transitions `issue`, `hold`, `release_hold`), `docs/reports/P2-I2/S2.md`, `schema/settings/access-words.yaml`.

## Context (<= 10 files)
The files above; `packages/tl-core/src/tl_core/auth/module_roles.py`.

## Allowed paths
- `packages/tl-modules/awp/**` (new `handlers/signoff.py`; not `readiness/**`, `worker.py`, `targets.py`, `rollup.py`, `pyproject.toml`; `module.py`/`names.py`/`commands.py`/`actions.py` edits for these four commands only)
- `schema/settings/access-words.yaml` (three words: `awp.iwp.signoff`, `awp.iwp.issue`, `awp.iwp.hold`, all controller)
- `packages/tl-api/src/tl_api/errors.py` (rows), `docs/reference/openapi.json` (regenerated), consequential pins: command counts, controller sets, access-word count, agent-refused counts (union form, each listed)
- `dev/accept/P2-I2/S3.py` (create), `docs/reports/P2-I2/S3.md` (create)
Not allowed: any other `schema/**`, generated files (a gap is Blocked), `tl_core`, other modules, `AWP_COMMANDS` registration in `tl_api` (C2 glue), new pytest (S5).
Note: C1 runs beside this piece and deletes the awp constraint code; expect a trivial merge of `commands.py`, `module.py` and `names.py`. Add your rows at the end of each list to keep it trivial.

## Acceptance (run once each; one package per gate; `NODE_OPTIONS=--max-old-space-size=6144` for check)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/S3.py
just gate packages/tl-modules/awp/tests tests/services/test_modules.py
just gate packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_api_document_controller.py packages/tl-api/tests/test_api_proposals.py
just gate packages/tl-core/tests/auth/test_access_words.py
```
`S3.py` (SQLite tmp db, accounts `viewer`, `user`, `controller`, two signers with the role, one without; <= 70 lines, helpers in a sibling module): `user` refused every command; a controller
without the role refused sign-off; first signer ok, same signer twice refused, second distinct signer ok; wrong hash refused; sign-off on a not-Ready IWP refused; not ready (no projection row, or ready false) refused;
issue with one signer refused, with two ok (Issued, foreman set, `permit to work` reported missing in `guards_evaluated`, not blocking); after a change of a hashed field through `unready` the old signatures
do not count; hold from Ready, Issued, In progress; release returns to Constraint check; every refusal text has no cell text; `RULES` word per row equals command word; rebuild equals incremental. Final `S3 ok`.
The script writes the readiness rows directly (S4 is not merged yet) with a helper; say so in the report.

## Guards for S5 (name file:line; run no mutants here)
Role check; distinct signers; hash equality and the hash content list; two-signature rule at issue; not-ready refusal; `unknown` setting; hold states; word per row.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; pins; acceptance output (<= 5 lines per command); guards file:line; learnings.

## Commit
`P2-I2-S3: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the module-role table cannot answer "role in project" for an actor; the readiness tables lack a column the check needs; an access word beyond the three is needed; a workflow transition name differs from the above.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
