# P2-REL refresh, 2026-11-09

The release branch was brought up to date with the trunk (wave 2 close, P2-INS, P2-INT, seed T06, outside review) at merge 1f28ed07.
- Conflicts: `docs/build-spec/DEFERRED.md` (both sides kept); `docs/reference/openapi.json` was regenerated with `python -m tl_api.openapi`.
- `just check` passed. Gates: tl-api 1641 passed, tl-tui 2015 passed, tl-cli 1261 passed, `tests/auth` plus `tl-schema` resources 247 passed.
- tl-api needed four runs by file group: `test_commands.py` grows to about 4 GB resident and the one-session run was killed (exit 137) under the shared memory limit. It passes alone (238).
- `just release-build`: 21 wheels, `check_wheels` OK. The starter was rebuilt; its `events` table has the `intent` column and the current `tl` opens it.
- `just release-smoke dist/release-0.1.0`: install, try-it, real-server and session-file steps all `ok`, `smoke: PASS`.
- Prod refuses an enabled `demo` account: `test_auth_review.py::test_startup_refuses_demo_when_the_environment_is_not_dev_demo_or_test[prod]` and `test_server_mode.py::test_an_enabled_demo_account_stops_a_prod_start`.
