# P2-REL-S2 — Real server mode: bind policy, prod environment, plain-http refusal

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core, api, tui, security
Depends on: trunk
Branch: `p2/rel-s2-server-mode`   (from claude/wizardly-allen-m2v96s)
Wave 2: no
Human gate: yes (authentication and server connection path; AGENTS.md "Never write auth ... from a Haiku ticket")

## Goal
A deployer can run `tl serve` for real accounts on a non-loopback address behind a TLS proxy, and it refuses unsafe
combinations by itself. The TUI refuses to send a password over plain http to a non-loopback host. Today
`packages/tl-api/src/tl_api/settings.py` `check_bind` refuses every non-loopback bind without `--insecure-dev` and says
"the Phase 0 API has no real authentication"; ADR-0009 made that false. Read ADR-0009 sections 4, 6, 9 and 14
(`grep -n` the headings, do not read the whole file) first.

## Requirements (security rows Sec-1 to Sec-4 of the plan)
1. `tl_core.auth.env`: add `prod_like(env) -> bool`: true when `TL_ENV` is set (non-empty after strip, lower-cased) and not in
   `DEV_TOKEN_ENVS | DEMO_ENVS` (so `prod`, `production`, `staging`, anything else); unset is false (fails closed as today).
2. `check_bind(host, *, insecure_dev, env=None)`: loopback always allowed. A non-loopback host is allowed when
   `insecure_dev` (unchanged, logs a warning per request as today) **or** `prod_like(env)`. Otherwise refuse with a message
   that tells the truth: bind loopback behind a TLS proxy, or set `TL_ENV` to a production name; no mention of Phase 0.
3. Start-up checks, in `tl_api.main` before the server listens, only when `prod_like` and the host is not loopback:
   (a) the dev token file is not read and any `TL_TOKENS` or `--tokens` value is ignored with one log line (not an error);
   (b) an enabled `demo` account stops the start (the server already refuses with the demo enabled; keep that and add the test);
   (c) `TL_OBJECT_SECRET` must be set (else exit with a message; the dev secret is public, `TL_ENV=dev` only);
   (d) one log line `serving on <host>:<port> behind TLS proxy: <yes|no>`: `yes` when `TL_TRUSTED_PROXY_HEADER` is set. No refusal; a
   deployer may terminate TLS elsewhere, the line makes the choice visible.
4. `tl tui` and `tl-tui` (`tl_tui.main.make_app`, `sign_in_first`, `plain_http_warning`): a `--remote` or `TL_REMOTE` of scheme
   `http` to a non-loopback host is refused with `error: ...` and exit 2 before any prompt, unless `TL_ALLOW_PLAIN_HTTP=1`
   (then the existing warning line stays). `https://` always passes. The refusal text names the host, never a token or password.
5. A dev or agent token (`TL_TOKEN`, `--token`) against a prod-like server: only a real, unexpired agent token is honoured;
   a token from the dev file is not. Prove it with a test rather than changing `tl_api.auth` unless the test fails.
6. Tests (all new, no network, no Postgres needed): `packages/tl-api/tests/test_server_mode.py` (bind x env x demo matrix,
   start-up checks, token ignored), `packages/tl-tui/tests/test_remote_policy.py` (plain-http refusal and override, loopback
   and `localhost` and `[::1]` allowed, https allowed, no secret in the text), `packages/tl-cli/tests/test_serve_prod.py`
   (`tl serve --help` shows the rule in one line; `tl serve --host 0.0.0.0` with `TL_ENV` unset exits 2 with the new text).
   Sec-3: a test captures stdout and stderr of a TUI remote sign-in against the in-process app (use the existing
   `RemoteAuthenticator` tests as the pattern) and asserts the session token string is in neither.
7. Update `tl serve`'s docstring and `packages/tl-api/README.md` (one paragraph: the two bind rules and the proxy duty).
   The long text goes in the runbook (T06), not here.

## Constraints
- No schema change. Interface lines for the orchestrator: `check_bind` gains `env`; `tl_core.auth.env.prod_like` new;
  `TL_ALLOW_PLAIN_HTTP` new environment variable. All additive. No password or token in any log, error or test output.
- Do not add TLS to the server, a new auth route or a new dependency. Do not touch the web package.

## Allowed paths
- `packages/tl-core/src/tl_core/auth/env.py`, `packages/tl-core/tests/auth/test_env.py` (extend)
- `packages/tl-api/src/tl_api/settings.py`, `packages/tl-api/src/tl_api/main.py`, `packages/tl-api/README.md`, `packages/tl-api/tests/test_server_mode.py`
- `packages/tl-cli/src/tl_cli/serve.py`, `packages/tl-cli/tests/test_serve_prod.py`
- `packages/tl-tui/src/tl_tui/main.py`, `packages/tl-tui/tests/test_remote_policy.py`
- consequential pins (AGENTS rule 12): existing tests that assert the old bind message; list them in the report
- `docs/reports/P2-REL/S2.md` (create)

## Acceptance (run once each)
```
just check
just gate packages/tl-core/tests/auth packages/tl-api/tests packages/tl-tui/tests packages/tl-cli/tests
```
Expected: `gate: PASS`. If the whole of those directories does not fit the box, run the named files plus the existing auth,
settings and sign-in tests of each package and say which.
Mutation (3 lines): sentinel plus at most 5 mutants: `prod_like` true for unset; `check_bind` allows any host; demo-account
check dropped; plain-http check dropped; dev-token file read in prod. Each must be killed.

## Report requirements
Standard report ≤ 60 lines; the truth table of Sec-1 as the test pins it; the pins you changed; mutation lines.

## Escalation triggers
- The dev token file is read somewhere other than `tl_api.auth` (list it, stop).
- The demo-account refusal is not where ADR-0009 section 9 says; stop and ask.
- Any need to change an access word, a route or a schema.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
