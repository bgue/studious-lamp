# V3-FX · forms and permits refusals get their rows in the API error table
kind: ticket · review: lite · branch `p2/v3-fx-errors` · worktree `/home/user/wt/v3p/fx` · base `p2/v3-forms`.
Process: `docs/build-spec/process-v3.md` section 2.

## Goal
`tl_mod_forms.errors` (`FormsError` and its 6 subclasses) and the permits errors in `tl_mod_permits/errors.py` have
no row in `packages/tl-api/src/tl_api/errors.py` `ERROR_TABLE`, so `POST /commands/SubmitForm` answers a refused
form with a 500 (found by V3-F3), and the tl-api "permits error table" test is red on the base.

## Build
1. One `s(<class>, "<code>", <status>)` row per class, in a `# --- forms (P2-FORMS) ---` and a `# --- permits ---`
   block, in the style of the rows around them. Statuses: state and stale-version clashes 409 (as
   `tl_web/pages/forms.py` `_refused` does), rule, answers, template and scope refusals 422. A class whose parent
   already has the right row still gets its own row if a test asks for one (follow `test_api_scaffold_errors.py`).
   Codes unique, not colliding with `HTTP_ERRORS`.
2. A test `packages/tl-api/tests/test_api_forms_errors.py`: every forms and permits error class has its own row; a
   refused `SubmitForm` over the API (the harness in `test_commands.py`) answers 422 with the module's message and
   no answer value in the body; the client re-raises the same class.
3. Wrap the one over-long line `tests/confidentiality/test_forms_sources_walk.py:517` (E501; text unchanged).

## Rules
No other edit in `tl_api` (no auth, routes, app). No change of any error message. No schema change.

## Gate
`uv sync --frozen --all-packages`; ruff and pyright on changed files; `just gate packages/tl-api/tests/test_error_table.py
packages/tl-api/tests/test_api_forms_errors.py packages/tl-api/tests/test_commands.py` plus the failing permits
error-table test (name it). Hold a heavy lock. Report `docs/reports/P2-FORMS/V3-FX.md`, at most 10 lines. Prefix `V3-FX:`.
