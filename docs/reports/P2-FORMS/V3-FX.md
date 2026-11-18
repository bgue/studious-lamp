# V3-FX report: deviations first
Deviations: `tl_api/errors.py` also sends FormTemplateError/FormAnswersError rule texts as body `issues` and rebuilds them on the client (no message changed). No edit to test_error_table.py. QR rows added per coordinator (qr_scope 422, qr_rule 422, qr_state 409, `# --- qr ---`).
Branch `p2/v3-fx-errors`, code and report commits on top of fc0dd88e; not pushed, not merged.
Changed: `packages/tl-api/src/tl_api/errors.py` (forms, permits and qr rows); new `packages/tl-api/tests/test_api_forms_errors.py` (2 tests); `tests/confidentiality/test_forms_sources_walk.py` (line 517 wrapped, text unchanged).
Gate: `just gate` on test_error_table, test_api_forms_errors, test_commands, test_api_scaffold_errors, test_auth_roles (under tl-heavy lock): 699 passed, 0 failed.
ruff check, ruff format --check, pyright on errors.py: clean, 0 errors.
Learnings: the test_error_table own-row test also covered the QR classes, which the spec did not name.
