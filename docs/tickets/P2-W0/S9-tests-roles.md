# P2-W0-S9 (TA) — Tests for module roles (RM-S1 to RM-S4), access words, and the pins they moved

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: tests, auth, security
Depends on: RM-S1, RM-S2, RM-S3, RM-S4, RM-S3-L (T07), W0-B1 (all merged on `p2/w0`)
Branch: `p2/w0-s9-tests-roles`

## Goal
Every test file the roles specs named exists and passes, the old-text pins that the merged work broke are updated, the six RM-S3
snapshots are regenerated, and the four sites that now answer `no item` before `forbidden` are seeded with real records. This piece
writes tests and test support only; it never edits `src`, `schema/**` or `dev/accept/**`. A test that shows a defect in source is
reported under *Blocked* with the test id (no source fix, no skip, no xfail; AGENTS.md "Never").

Do not discuss the commit trailer in the report; no model names anywhere in committed files.

## Owner policy (read first)
Tests run **once**, at the end, by the orchestrator over the whole suite. You write them and run **only your own new or changed
files**, one part at a time: `just gate <file> [<file>...]` (one pytest session, log in `.gate/`), saving the summary with
`| tee .gate/summary.txt`. Never `just test`, never a directory-level or whole-suite gate, never `gate-pg` (the orchestrator does it).
Parity tests you add carry the `parity` marker and are written, not run on Postgres. Never delete `/tmp/pytest-of-root`, never `pkill`.
Run `just check` once at the end.

## Brief references
- Specs: `docs/build-spec/specs/roles-mvp.md` §2 table, §3 grants, §4 resolver (precedence 1 to 7), §5 seams, §9 rows S1 to S4 and T1,
  mutation guards below it; `docs/build-spec/specs/wave0.md` §2 (access words, company grants).
- Reports (the guard sites and the pins are there): `docs/reports/P2-W0/{RM-S1,RM-S2,RM-S3,RM-S4,RM-S3-L,W0-B1}.md`.
- Oracles: the acceptance scripts `dev/accept/P2-W0/{RM-S1,RM-S2,RM-S3,RM-S4}.py` already compute expectations from
  `schema/settings/module-roles.yaml` and `access-words.yaml`; reuse their approach, not their code. Fixture pattern:
  `tests/auth/authworld.py`, `tests/auth/conftest.py`.

## Test files to write (verified paths; none exists yet unless marked)
Order of work; commit after each group so a stop leaves a clean tree.
1. `packages/tl-core/tests/auth/` (**new directory**, the only new one; files `test_module_role_table.py`, `test_module_roles_resolve.py`
   (precedence 1 to 7, company scope), `test_module_grants.py` (checks, idempotence, revoke of an old-table grant stays possible,
   grant events hidden from `/events` for non-admins), `test_company_grants.py` (accepted for `company_roles` true, `NoCompanyRolesError`
   otherwise, read at scope `company` only), `test_access_words.py` (22 words load; unknown table word and duplicate word raise
   `AccessWordError`; `table_word`; every word of `m3-wbs-cwp.md` §3 and `m4-materials.md` §3 present)). Add a `parity`-marked projection
   test for `cur_account_module_role` next to `tests/auth/test_projection_parity.py`'s pattern (file `tests/auth/test_module_role_projection_parity.py`).
2. `packages/tl-api/tests/test_api_module_roles.py` (every module command x viewer, user, superuser, admin, agent x two projects equals the
   table; plain user with no grant on project B refused there), `packages/tl-core/tests/test_actions_scoped.py`,
   `tests/services/test_module_role_seams.py` (runner, proposal accept AND rule D14, `require_generic`, cross-scope refusal per module),
   a `command_words == API_COMMANDS` equality test per module (put them in `test_module_role_seams.py`), a `command_index()` fine-word
   test (a stand-in module with `awp.cwp.release` gives `controller`, `awp.view` gives `read`).
3. `packages/tl-api/tests/test_api_admin_module_roles.py` (five routes in `RM-S3.md` "Routes and actions", errors `unknown_role`,
   `unknown_module`, `no_such_grant`, `no_company_roles`; `/auth/me/roles` principal binding), `packages/tl-cli/tests/test_cli_admin_roles.py`
   (grant, ls, effective, revoke through `CliRunner`; plain user refused), `packages/tl-tui/tests/test_client_module_roles.py`,
   `packages/tl-tui/tests/test_module_roles_log.py` (3 rows, revoke refusal in the status line, 80 and 170 column snapshots, plain walk entry).
4. `packages/tl-cli/tests/test_cli_module_words.py` and `packages/tl-tui/tests/test_embedded_module_words.py`: call the finder of
   `dev/tools/gate_sweep.py` (`find_calls`, `find_helper_calls`): zero ungated calls in `tl_cli` and in `embedded.py`; load the module by
   path with `importlib` (it is not a package).
5. T07 lows (`RM-S3-L.md`): in `packages/tl-tui/tests/test_admin_text.py` (exists) pin `effective_line` of a view with no roles = `—`
   (`EMPTY`), `effective_page` summary `"<n> of <m> modules"` (and empty summary with no views; note `1 of 1 modules` is the accepted text);
   in `test_admin_screen.py` or `test_plain_walk.py` the `is_admin` default False for an app object without the attribute.

## Old-text pins and unaudited tests to fix (by reading the report, then running the file)
| Where | Old text or assumption | Source of the change |
|---|---|---|
| `packages/tl-cli/tests/test_cli_controller_gates.py` | keys `P123-RC-1` and `--number P123-TRN-0001` were **assumed**; refusal text now the module word; no-session actor now `error: forbidden` | RM-S4 "Pins updated" |
| `packages/tl-cli/tests/test_cli_corr.py::SITES` (line ~209) and the `comm` loop in `test_cli_domains.py` (~197) | made-up ids `P123-COR-0001`, `P123-EW-0001`, party `ACME`, clause `CT-1` answer `no item`/`no party` before `forbidden` (ADR-0016 order). **Q7: seed real records** (create them as `dora`/`ada` in a fixture, use their numbers), keep the refusal assertions; add the gate-before-lookup case for `class grant`/`class withdraw` with an unknown number answering `forbidden` for a plain user | RM-S4 attempt 3, Q7 |
| `packages/tl-cli/tests/xercli_support.py::GATE`, `test_cli_xer.py` | module-word text | RM-S4 |
| `packages/tl-tui/tests/test_embedded_{actions,derivation,controller_gate}.py` | refusal text | RM-S4 |
| `packages/tl-api/tests/test_commands.py::test_a_command_with_no_body_is_a_422_not_a_500`, `test_api_document_controller.py::test_taking_the_role_away_closes_the_commands_at_once` | predicted by RM-S2 deviation 2 | RM-S2 |
| `tests/auth/test_authorizer_and_seed.py`, `packages/tl-sim/tests/` (28 files) | **Q6 unaudited**: run both once; fix only by reading `RM-S2.md` D1 to D4 (controller commands need the module word; dev ledger actor holds `user`) | RM-S2 |
| `packages/tl-tui/tests/test_plain_walk.py`, keymap pin | `m` is a VIEW_KEY; `AGENT_MAY_NOT` line | RM-S3 |
| An account-less actor on Postgres ledger | now refused on gated `user` commands (SQLite dev/test/ci fallback only, D2); a Postgres-run test relying on it gets a session | RM-S4 |

## Snapshots (regenerate only these; list each in the report)
RM-S3 changed `AdminScreen.KEY_HINTS` (`m module roles`). Expected, and the only ones you may regenerate with
`uv run pytest <node id> --snapshot-update` (one run per file, then review the SVG diff shows only the hint line):
`test_admin_screen.py::test_the_accounts_snapshot_120x40`, `::test_the_accounts_snapshot_80x24`, `::test_the_agent_tokens_snapshot_120x40`;
`test_account_forms.py::test_the_add_form_snapshot_120x40`, `::test_the_password_form_with_an_error_snapshot_80x24`,
`::test_the_token_shown_once_snapshot_120x40` (only if they actually differ). Any other snapshot that differs is **not** explained by a
merged ticket: do not regenerate it; list it under *Blocked*. The new `test_module_roles_log.py` snapshots are new files (allowed).

## Mutants (sentinel + at most 5, in your own worktree, each killed by your own new file; restore after each; 3-line report)
Sentinel: make `require_command_access` a no-op. Then: precedence 4 over 6 swapped (`module_roles.py effective_roles`); agent capped roles
removed (`roles &= frozenset(table.agent_roles)`); unknown word accepted in `parse_role_table`; `scope == COMPANY` branch ignores grants;
`_make_endpoint` access check removed (`commands.py:330`). Guard sites by name: `RM-S1.md` "Mutation guard sites", `RM-S2.md` "Seam
list", `RM-S3.md`/`RM-S4.md` "Guard sites for TA". Run the one killing file per mutant with `just gate <file>`.

## Context (read these; the rest by `grep`)
`docs/build-spec/specs/roles-mvp.md` (§2 to §5, §9), the six reports above, `tests/auth/authworld.py`, `schema/settings/module-roles.yaml`,
`schema/settings/access-words.yaml`, `dev/tools/gate_sweep.py` (finder names only). may explore: the existing test file next to each new one for house style.

## Allowed paths
Create or change only: the test files and support files named above; `packages/tl-tui/tests/__snapshots__/**` for the listed snapshots;
`docs/reports/P2-W0/S9.md` (create). Everything else read-only (`src/**`, `schema/**`, `dev/**`, `docs/reference/**`).

## Acceptance
```
just check
just gate <each new or changed test file>      # once per group; all PASS; summaries in .gate/
```
Expected: every new file passes; no existing file you did not touch is run. Report counts per group and the 3-line mutation result.

## Report requirements (<= 60 lines; deviations first)
Files written (path, test count); pins fixed (table row, old to new); snapshots regenerated (ids) and any that differed unexplained;
Q6 and Q7 outcomes; defects found in source (test id, *Blocked*); mutation lines; commands with <= 5 decisive output lines each.

## Escalation triggers
- A test shows a source defect, or a pin cannot be fixed without changing source or `dev/accept`.
- A snapshot differs and no merged ticket explains it.
- More than 3 of the unaudited sim tests fail for one reason (stop, name the reason).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
