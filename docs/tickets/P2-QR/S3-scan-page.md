# P2-QR-S3 — The scan page `/web/q`, the miss counter, the log filter

kind: piece
review: full
branch: p2/qr-s3-scan-page
worktree: /home/user/wt/qr/s3
Base: `p2/ip-r3` (QR-S2, T04, T06 not required; the card providers are injected in tests). Merge note: **waits for X4 on trunk** (D8) like every merge into `p2/ip`; it edits `tl_web/app.py`, `tl_web/routers.py`, `tl_api/main.py`, which other increments may touch, so merge `p2/ip` before the final gate. Build, gate and review may start now.
Depends on: QR S1, S2 (merged: `tl_mod_qr.resolve.resolve`, `labels.label_fields`, `codes.normalise_code`), the web client (`packages/tl-web`).
Gated: a web route whose miss must equal the sign-in-protected 404; the miss counter; the log filter (APPROVALS line at merge). Labels: web, security.
Read first: `docs/build-spec/specs/qr-workface.md` §3-§5 and §11, `docs/adr/0030-qr-workface-status.md` item 2, learnings L-P2-WEB1-2 and L-P2-WEB1-3 (`grep -n -A6 <id> docs/memory/LEARNINGS.md`).

## Why
S2 resolves a code to a `ScanCard` or `None`. Nothing serves it to a phone. The page must tell a signed-out visitor nothing about a code, tell a signed-in one only what the card says, and make every miss look the same.

## Goal
1. **Routes** in `packages/tl-web/src/tl_web/pages/scan.py` (new; `router = web_router()`; add `"tl_web.pages.scan"` to `PAGE_MODULES` in `tl_web/routers.py` before the catch-all, one line, the only edit there):
   - `GET /web/q` a form to type a code (POST below), `GET /web/q/{code}` the card, `POST /web/q` (typed code, origin check through `csrf.verify_origin`, answers a 303 to `/web/q/<normalised>` only when the code has the valid shape, else the miss page; the code is never in a query string).
   - **Signed out, `/web/q/<anything>` answers the sign-in page before any lookup** (no resolver call, no statement): for every path segment, whether or not a code exists. The page carries a hidden `next` only when the segment matches `[A-Z0-9]{16}` after upper-casing; a malformed segment has no `next`. So two signed-out answers differ only by the echoed `next` the visitor typed itself; the test compares them after blanking that field.
   - **Signed in:** `resolve.resolve(conn, code, viewer, now)` with the request's viewer (`current_viewer()`; never the LOWEST default widened) and `now` read once. A card renders `scan.html`; `None` is the one miss page.
   - **Agents:** `guard("qr.read")` (the action T06 also uses; on no agent list), so an agent token gets the closed guard's 403 before any lookup.
2. **Sign-in return.** `tl_web/app.py` sign-in form and submit accept `next`; the value is used only when it matches `/web/q/[A-Z0-9]{16}` exactly (`re.fullmatch`, no whitespace, no scheme, no `//`), else dropped (303 to the home as today). Tests: `/web/q/ABCDEFGH23456789`, `https://x`, `//x`, `/web/q/abc`, `/web/q/ABCDEFGH23456789/..`, `/web/p/P123/rfis`. The existing sign-in behaviour and its tests do not change otherwise.
3. **The page** `templates/scan.html` (extends `base.html`; phone width; under 30 KB; no script, no third-party resource; tone as a class from `static/tl.css` (CSP forbids inline style): the banner word is always printed, colour is never the only signal; identity (key, title), `as of <UTC time>`, `valid until` when set, up to 8 `label: value` lines, an "Open record" link only when `open_path` is set (it starts with `/web/`)). Autoescape on; the card text is data, never markup.
4. **The miss page** is the web client's one 404 (`not_found.html` through `not_found_page`): the same status, bytes and headers for a malformed code, an unknown one, a revoked one, an expired one, a hidden record, a reader without the view word and a missing provider.
5. **Headers.** Every `/web/q` answer (card, miss, form, sign-in bounce, 429) carries `Referrer-Policy: no-referrer` instead of the app's `same-origin`: change `SECURITY_HEADERS` handling in `tl_web/app.py` so the pure ASGI middleware replaces that one header for paths under `/web/q` (one function, with a test), `Cache-Control: no-store` (already the default), no `Set-Cookie` on a miss.
6. **Miss counter.** A pure in-process counter (new `tl_web/scan_limit.py`, not `tl_api/ratelimit.py`, which counts only failed sign-ins): misses per session token and per client address (`ratelimit.client_key` with the trusted header setting the API already has), sliding window; constants `MISS_LIMIT_SESSION = 10`, `MISS_LIMIT_ADDRESS = 30`, `WINDOW_S = 600` in the module, injectable clock. Only misses count. Once either limit is passed, **every** lookup of that session or address answers 429 with `Retry-After` and the same fixed text, hit or miss, before the resolver runs (so a limited visitor cannot use the 429 to tell hits from misses); a hit below the limit does not reset the count; a signed-out request never reaches the counter. Bounded memory (cap the number of tracked keys, evict oldest).
7. **Access log filter.** In `tl_api/main.py` where uvicorn's access log is configured, install one `logging.Filter` on `uvicorn.access` that rewrites the request path of `/web/q/<code>` and `/qr/resolve/<code>` (T06's route) to `/web/q/<redacted>` and `/qr/resolve/<redacted>` in the record's args before any handler formats it; a request without those paths is untouched byte for byte. Test with a handler attached to the logger.
8. **Runbook.** `docs/runbooks/web-client.md` gets a "Scan labels" section: the address crews must check before signing in, the miss limits, the log filter, and that a reverse proxy in front must strip or mask `/web/q/` and `/qr/resolve/` paths in its own access log (one paragraph, no config for a named product).

## Tests (names; own files)
`packages/tl-web/tests/test_scan_page.py` (the five readers: nobody, plain user, cleared, user without the view word, agent token: card or the one miss, byte-compared; signed-out bounce before any statement via a statement counter; `next` table; headers incl. `no-referrer`; card under 30 KB with no `<script`; markup in card text is escaped), `packages/tl-web/tests/test_scan_limit.py` (limits per session and per address, 429 for hits and misses alike once limited, hits do not count, window slides, key cap), `packages/tl-api/tests/test_access_log_filter.py` (redaction, other paths untouched), `packages/tl-web/tests/test_sign_in_next.py` (item 2). Providers are injected as the S2 tests inject them (a fake provider; no entry-point install); plus one test with the real `awp.IWP` provider (T04) reading through `registry.load_scan_cards` when installed.

## Allowed paths
- `packages/tl-web/src/tl_web/pages/scan.py`, `scan_limit.py` (create), `templates/scan.html` (create), `static/tl.css` (append the tone classes), `routers.py` (the one line), `app.py` (`next`, the referrer replacement)
- `packages/tl-api/src/tl_api/main.py` (the filter only), `packages/tl-web/tests/{test_scan_page.py,test_scan_limit.py,test_sign_in_next.py}`, `packages/tl-api/tests/test_access_log_filter.py`
- `docs/runbooks/web-client.md`, `docs/reports/P2-QR/S3.md`, `dev/accept/P2-QR/S3.py` (SQLite, `PASS <check>` lines, final `S3 ok`)
Read-only: the resolver and the module (`tl_mod_qr`), schema, other pages.

## Acceptance (once each, one at a time; the box OOMs on combined tl-api and tl-web runs; whole-repo pyright is OOM-killed: when another heavy run is live use ruff plus pyright on the touched paths)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-web/tests/test_scan_page.py
just gate packages/tl-web/tests/test_scan_limit.py packages/tl-web/tests/test_sign_in_next.py
just gate packages/tl-api/tests/test_access_log_filter.py
just gate packages/tl-web/tests/test_web_headers.py packages/tl-web/tests/test_web_auth.py packages/tl-web/tests/test_web_csrf.py
just gate-pg packages/tl-web/tests/test_scan_page.py
uv run python dev/accept/P2-QR/S3.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: a revoked code renders its card. Targets: the resolver runs before the sign-in bounce; `next` pattern loosened to `startswith("/web/q/")`; a limited visitor still gets the card for a hit; the log filter skipped for `/qr/resolve/`; `Referrer-Policy` left as `same-origin` on the card.

## Report
`docs/reports/P2-QR/S3.md` (<= 60 lines): deviations first; the byte-equal evidence for the miss page; the limits chosen; gate output (<= 5 lines per command); mutation 3 lines; signatures T11 needs (the routes, the 429 text). Builder return <= 15 lines. Commit `P2-QR-S3: ...` with the trailers the dispatch message names; no model names.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
