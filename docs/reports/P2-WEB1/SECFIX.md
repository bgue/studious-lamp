# P2-WEB1-SECFIX: the three findings of the WEB1 security review

Deviations: (1) `run_command(guard=True)` is the default (fail closed); the JSON endpoint passes
`guard=False` (orchestrator decision). (2) Consequential edits outside the first allowed list: tests in
`packages/tl-web/tests/` beyond the two named (sign-in posts; `test_a_refusal_of_run_command_is_shown...`),
`packages/tl-api/tests/test_run_command.py` (spy test passes `guard=False`; new default/off test), and
`packages/tl-api/src/tl_api/ratelimit.py` (`NOT_A_FAILURE_KEY`, see F1; app.py needed no change).
## F1 login CSRF (MD)
`csrf.verify_origin` (new dependency) is on `POST /web/sign-in`: when `csrf.origin_matches` is false the
answer is the 403 `csrf_refused` of `csrf.verify` (same bytes), before `auth_routes.sign_in`, so no
lockout count, no audit, no Set-Cookie. No token is needed for sign-in. Tests: `conftest.World.sign_in`
and the other sign-in posts send the server Origin; `test_web_auth.py` (foreign Origin, `null`, foreign
Referer, other port, neither header: 403, no Set-Cookie, CSP present, same body as sign-out's refusal, a
wrong password is also 403 not 401; the own Origin or own Referer gives 303); `test_web_csrf.py` walk
runs `check_origin_only` on the exempt route (token not required, origin required).
The refusal sets scope key `ratelimit.NOT_A_FAILURE_KEY`, so `RateLimitMiddleware` does not count it (no
password was checked); test: 10 foreign-origin posts leave a `SourceLimiter(3)` open, real failures trip it.

## F2 web /do skipped the endpoint guard (LO)
Not a true move: the JSON guard runs before the body is read, so moving the calls would reorder API
refusals. The two calls (authorizer, then `ctx.authorize`) live once in `run_command`, on by default
(`guard=True`); the JSON endpoint passes `guard=False` (its guard dependency ran). API behaviour unchanged.
Test `test_a_refusing_authorizer_stops_the_web_action_like_the_endpoint_guard[authorizer|hook]`: the
refusal is `! <text>` 403, no event, state unchanged, the asked action/path is `command.SubmitTechnical`,
the JSON endpoint is refused too, and the request passes once the refuser is gone. Side effect: a user
without the controller word is now refused by the authorizer before the module role check (other text).

## F3 rate limit on web sign-in (LO)
`test_failed_web_sign_ins_share_the_json_routes_count_and_answer_429`: `SourceLimiter(3)` (new optional
`World.make_app(limiter)`); web 401, JSON 401, web 401, then the right password is 429 with `Retry-After`
and the CSP, no cookie; `/auth/sign-in` is 429 too; a fresh app/limiter signs in.

## Demo
`dev/demos/P2-WEB1.sh` `sign_in` sends the Origin. `just demo P2-WEB1`: sqlite and postgres, 5/5.

## Runs
`just check` clean. `just gate` (tl-web, test_commands, test_auth_review, test_run_command): PASS, 512 passed.
`just demo P2-WEB1`: sqlite and postgres, 5/5. Mutation: sentinel (drop `verify_origin`) killed; 6/6
killed (guard off in web, no hook call, no authorizer call, no-op `verify_origin`, origin 403 counted,
`guard` default False).
