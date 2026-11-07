# P2-WEB1-S1 — Web foundation: `tl-web` package, cookie sessions, CSRF, headers, vendored scripts

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: auth, security, api, web
Depends on: RM-S2 (merged on trunk)
Branch: `p2/web1-s1-foundation`
Approver (auth path): the human gate list covers "Auth, permissions" (`04-gates.md` §2): the piece stops at the PR; the orchestrator does not approve it. The web stays off in production (`TL_WEB`) until the C4 security review.

## Goal
After this piece a person can sign in at `/web/sign-in`, hold a cookie session, sign out, and every `/web` answer carries the
security headers; unsafe `/web` requests are CSRF-checked; htmx and pdf.js are vendored with a hash manifest. There is no
log page yet (`GET /web/` redirects to `/web/p/{TL_PROJECT}/rfis`, which 404s until S4; `TL_PROJECT` is read from the environment as `tl_tui/main.py` does, and unset is a 404 page). The JSON API is unchanged: it never reads the cookie.

## Brief references
`docs/build-spec/specs/web-client-i1.md` **§2, §3, §4, §5** read in full; they are the interface. Deltas and pins (this file wins):
1. **Module layout.** Create `packages/tl-web/` (`pyproject.toml` name `tl-web`; dependencies `tl-api`, `tl-tui`, `jinja2`, `python-multipart`;
   hatchling like `tl-api`), `src/tl_web/{__init__,app,session,csrf}.py`, `templates/{base,sign_in,not_found}.html`,
   `static/{tl.css,tl.js}`, `static/vendor/`. Root `pyproject.toml`: `tl-web = { workspace = true }` under `[tool.uv.sources]` and
   `packages/tl-web/tests` in `testpaths` (the glob already makes it a member). Run `uv lock` once; `uv.lock` is committed.
   `tl_web` imports no `tl_tui` module yet (S4 adds `present.py`); the dependency is declared now so `uv.lock` changes once.
2. **Mount.** `tl_web.app.mount(app: FastAPI) -> None`. `tl_api.app.create_app` calls it (lazy import) when `TL_WEB` is `on`; unset means
   `on` for `TL_ENV` dev, test, ci and `off` otherwise. `TL_WEB=on` with `tl_web` not importable is a start-up error; unset-and-default-on with
   it missing is silent. The switch is a small pure function in `tl_api/settings.py` (`web_enabled(env: Mapping[str,str]) -> bool`).
   All `/web` routes use `include_in_schema=False`: `docs/reference/openapi.json` must not change.
3. **Cookie fill, one place.** `AuthenticationMiddleware` (`tl_api/auth.py`): only when the path starts with `/web/` and there is no
   `Authorization` header, the bearer token is the `tl_session` cookie value. Open paths: `/web/sign-in` and `/web/static/`. Unauthenticated: `GET`
   under `/web/` is a 303 to `/web/sign-in`, any other method 401 (JSON error body as the middleware's own). **Pin (security, beyond the spec text):**
   a cookie that resolves to an agent principal is refused (401, no redirect loop: clear nothing, a plain 401 page) because agents have no web session.
   The cookie is never read for any other path. The principal and the ADR-0016 viewer are set exactly as for a bearer token.
4. **Sign-in.** `POST /web/sign-in` (form `username`, `password`; body limit 16 KiB via `BODY_LIMITS` like `/auth/`) calls the same function the
   JSON `POST /auth/sign-in` calls (find it in `tl_api/routes/auth.py`; do not copy its logic; lockout, audit, timing and error text unchanged).
   Success: `Set-Cookie: tl_session=<token>; HttpOnly; SameSite=Strict; Path=/web; Max-Age=43200` plus `Secure` unless the host is loopback **and**
   `TL_ENV` is dev, test or ci (pure function `cookie_flags(host, env)` in `session.py`); 303 to `/web/`. Failure: the form again, status as the JSON route
   gives, its error text, username re-shown (escaped), password never echoed, logged or put in a redirect. A new token every sign-in (no fixation).
   `POST /web/sign-out` (CSRF-checked) calls the same sign-out the JSON route calls, expires the cookie, 303 to `/web/sign-in`.
5. **CSRF.** `csrf.py`: `csrf_token(session_token: str, secret: bytes) -> str` = `base64url(HMAC-SHA256(secret, b"csrf|" + sha256(session_token).hexdigest()))`
   (no padding); `verify(request, ...)` as a FastAPI dependency for every non-GET `/web` route except sign-in: header `X-CSRF-Token` or form field `csrf`,
   `hmac.compare_digest`, and `Origin` (else `Referer`) equal to `TL_WEB_ORIGIN` if set, else the request's own scheme and host; missing or foreign: 403
   `{"error": "csrf_refused"}`. `TL_WEB_SECRET` (>= 32 bytes) is required when `TL_ENV` is not dev, test or ci and a short one stops start-up; in dev/test/ci one is
   generated per process. Templates expose the token as `<meta name="csrf-token">` and a hidden `csrf` field in the sign-out form.
6. **Headers** on every answer under `/web` (including 303, 401, 404, static, errors): the exact CSP, `X-Content-Type-Options`, `Referrer-Policy`,
   `Cache-Control: no-store` of spec §5; a handler that already set `Cache-Control` (later pieces: `private`) is not overridden. Pure ASGI middleware limited to
   `/web` paths (not `BaseHTTPMiddleware`). No inline script or style anywhere; htmx is configured from a `<meta name="htmx-config">` tag.
7. **Vendored files.** `static/vendor/VENDORED.toml` is the manifest (format below, also pasted in T06). Vendor `htmx.min.js` of htmx 2.0.4 and, of `pdfjs-dist`
   4.10.38, `build/pdf.min.mjs` and `build/pdf.worker.min.mjs`, plus each upstream LICENSE file, from the npm tarballs
   (`https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.4.tgz`, `https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.10.38.tgz`; use the proxy-configured `curl`).
   Record the licence the upstream LICENSE file actually says (SPDX id); it must be permissive (MIT, BSD, 0BSD, Apache-2.0, ISC) or the piece **stops** (95 line).
   Serve `.mjs` as `text/javascript` (check the served `Content-Type`; add the mimetype if the platform lacks it).
   `static/tl.js` and `static/pdfview.js` are not written here (S4, T05); `tl.js` is an empty module with a header comment.
```toml
[[file]]
path = "htmx/htmx.min.js"        # relative to the directory holding VENDORED.toml
name = "htmx"
version = "2.0.4"
licence = "<SPDX id from the upstream LICENSE>"
url = "https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.4.tgz"
sha256 = "<hex sha256 of the file as vendored>"
```

## Interfaces (existing; read, do not redesign)
- `tl_api/auth.py`: `bearer_token(headers)`, `AuthenticationMiddleware(app, resolver)`, `BODY_LIMITS`, `Resolver.resolve(token) -> Principal | None`, `current_principal`.
- `tl_api/routes/auth.py`: the JSON sign-in/sign-out handlers (reuse their service call).
- `tl_api/app.py`: `create_app(...)`, the middleware stack at lines ~247-262 (the headers middleware goes outside the authentication middleware so a 303/401 from it is also covered).

## Context (<= 10 files)
- `docs/build-spec/specs/web-client-i1.md` §2-§5; `docs/adr/0009-authentication.md` (sessions)
- `packages/tl-api/src/tl_api/{auth,app,settings}.py`, `tl_api/routes/auth.py`; `packages/tl-api/tests/test_auth.py` (TestClient pattern)
- `dev/accept/P2-WEB1/` is new; style of `dev/accept/P2-W0/RM-S2.py` (lines 1-110: temp SQLite ledger, `TL_ENV=test`, one `PASS <check>` per check)
may explore: `tests/auth/authworld.py`

## Allowed paths
- `packages/tl-web/**` (create; no tests directory content beyond an empty `tests/` with `.gitkeep`)
- `packages/tl-api/src/tl_api/{auth,app,settings}.py` (modify: cookie fill, mount call, `web_enabled`, `BODY_LIMITS` row only)
- `pyproject.toml` (root: sources line, testpaths), `uv.lock`
- `dev/accept/P2-WEB1/S1.py` (create), `docs/reports/P2-WEB1/S1.md` (create)
Not allowed: `docs/reference/openapi.json` (must not change), any `routes/*`, `commands.py`, `tl_tui/**`, `schema/**`, any other package.

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-WEB1/S1.py
```
`dev/accept/P2-WEB1/S1.py` (SQLite temp ledger, TestClient, `TL_ENV=test`, exit 0, one `PASS <check>` per check; expected values from the spec text, not from the code under test):
(a) sign-in: 303 to `/web/`, cookie has `HttpOnly`, `SameSite=Strict`, `Path=/web`, no `Secure` on loopback in test; `cookie_flags` adds `Secure` for a non-loopback host and for env `prod`;
(b) wrong password: same status and error text as `POST /auth/sign-in`, password absent from body and headers; escaped username (`<script>` shows as `&lt;script&gt;`);
(c) the cookie token on a JSON path (a bearer-only GET and `POST /commands/...`) is 401, the same token as a bearer header is 200; the cookie is ignored on `/web`-prefixed look-alikes (`/webx/`);
(d) unauthenticated `GET /web/` 303 to `/web/sign-in`, unauthenticated `POST /web/sign-out` 401; agent token in the cookie is 401;
(e) CSRF on `POST /web/sign-out`: no token 403 `csrf_refused`; wrong token 403; token of another session 403; right token with foreign `Origin` 403; no `Origin` and no `Referer` 403; right token and own origin 303; `TL_WEB_ORIGIN` honoured; `Referer` accepted when `Origin` is absent;
(f) a short `TL_WEB_SECRET` with `TL_ENV=prod` stops start-up; none in dev works; `TL_WEB` unset: on in test, off for `prod`; `TL_WEB=off` gives 404 on `/web/`;
(g) CSP string equals the spec's byte for byte on 200, 303, 401, 403, 404 and a static file; `Cache-Control: no-store` on pages; no `<script>` without `src` and no `style=`/`<style>` in the sign-in page;
(h) sign-out: cookie expired, old token then 401 as a bearer;
(i) body over 16 KiB to `/web/sign-in` is 413 (or the status the `/auth/` limit gives);
(j) `openapi.json` is unchanged (`uv run python -m tl_api.openapi` leaves a clean `git diff`);
(k) manifest: every file's sha256 equals the manifest, every licence passes `dev/tools/check_licences.py`'s `term_ok`, htmx is 2.0.4, pdfjs-dist is >= 4.2.67, `.mjs` served as `text/javascript`;
(l) importing `tl_web` does not put `textual` in `sys.modules`.

## Mutation guards (you run them, own worktree, 1 sentinel + <= 5 targeted, report in 3 lines)
Sentinel: baseline green. Targets: cookie fill applied to every path (c red); `compare_digest` replaced by a pass (e red); origin check removed (e red);
agent-by-cookie allowed (d red); CSP header dropped on the 303 path (g red).

## Tests for the end run (S5 writes them; this piece writes none)
`packages/tl-web/tests/{test_web_auth,test_web_csrf,test_web_headers}.py`, `packages/tl-api/tests/test_api_cookie_refused.py`. List in the report the
function names S5 should call (`cookie_flags`, `csrf_token`, `web_enabled`) and the seam lines (file:line) of the cookie fill and the CSRF dependency.

## Report requirements
Standard piece report (<= 60 lines): deviations first; licences found for htmx and pdf.js (SPDX as read); seam list; acceptance output (<= 5 lines per command);
mutation result in 3 lines; no discussion of the commit trailer; no model names in any committed file.

## Escalation triggers
- *Blocked* if: the vendored files cannot be fetched; a vendored licence is not permissive; the JSON sign-in service call cannot be reused without editing `routes/auth.py`;
  `openapi.json` changes; any test outside this piece breaks (name it).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
