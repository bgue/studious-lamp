# P2-WEB1-SECFIX: the three findings of the WEB1 security review

Deviations: (1) `run_command` gained a keyword `guard: bool = False` (see F2). (2) four existing tests
outside the named two files were edited because sign-in now needs the Origin: `test_web_headers.py`,
`test_web_demo_clauses.py`, `test_web_auth.py` (more calls than the two named lines), and
`test_web_actions.py::test_a_refusal_of_run_command_is_shown_as_it_is` (the authorizer now refuses
first, so its expected text comes from `run_command(..., guard=True)`). All under `packages/tl-web/tests/**`.

## F1 login CSRF (MD)
`csrf.verify_origin` (new dependency) is on `POST /web/sign-in`: when `csrf.origin_matches` is false the
answer is the 403 `csrf_refused` of `csrf.verify` (same bytes), before `auth_routes.sign_in`, so no
lockout count, no audit, no Set-Cookie. No token is needed for sign-in. Tests: `conftest.World.sign_in`
and the other sign-in posts send the server Origin; `test_web_auth.py` (foreign Origin, `null`, foreign
Referer, other port, neither header: 403, no Set-Cookie, CSP present, same body as sign-out's refusal, a
wrong password is also 403 not 401; the own Origin or own Referer gives 303); `test_web_csrf.py` walk
runs `check_origin_only` on the exempt route (token not required, origin required).
Note: the 403 is counted by `RateLimitMiddleware` (403 is in `FAILURE_STATUSES`), as any 403 from that route.

## F2 web /do skipped the endpoint guard (LO)
Chosen: not a true move. The JSON guard is a dependency that runs before the body is read, so moving the
calls into `run_command` unconditionally would reorder API refusals and break
`test_run_command.py::test_the_admin_authorizer_is_asked...` (outside allowed paths). Instead the two
calls (`ctx.authorizer.authorize(principal, action_for(spec), path)`, then `ctx.authorize(actor, ...)`)
live once in `run_command` behind `guard=True`; `actions._run` passes it; the JSON endpoint leaves it off
(its guard dependency ran). API behaviour is unchanged. The default is False so the existing callers keep
their meaning; flipping it to True (and the endpoint passing False) is a one-line change plus that one
spy test if the reviewer prefers fail-closed by default.
Test `test_a_refusing_authorizer_stops_the_web_action_like_the_endpoint_guard[authorizer|hook]`: the
refusal is `! <text>` 403, no event, state unchanged, the asked action/path is
`command.SubmitTechnical` on the request path, the JSON endpoint is refused too, and the request passes
once the refuser is removed. Side effect seen: a user without the controller word is now refused by the
authorizer (`control.command.X needs the controller access word...`) before the module role check.

## F3 rate limit on web sign-in (LO)
`test_failed_web_sign_ins_share_the_json_routes_count_and_answer_429`: `SourceLimiter(3)` (new optional
`World.make_app(limiter)`); web 401, JSON 401, web 401, then the right password is 429 with `Retry-After`
and the CSP, no cookie; `/auth/sign-in` is 429 too; a fresh app/limiter signs in.

## Demo
`dev/demos/P2-WEB1.sh` `sign_in` sends `Origin: $TL_DEMO_URL`. `just demo P2-WEB1`: sqlite and postgres, 5/5.

## Runs
`just check` clean (NODE_OPTIONS=--max-old-space-size=6144). `just gate packages/tl-web
packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_auth_review.py`: PASS, 498 passed.
Also `packages/tl-api/tests/test_run_command.py`: 11 passed.
Mutation: sentinel (drop `verify_origin` dependency) killed; 4/4 killed: `guard=False` in actions, drop
the hook call, drop the authorizer call, `verify_origin` made a no-op (csrf walk).
