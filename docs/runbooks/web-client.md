# Runbook — Run the web client on the dev ledger

Purpose: start the web client (`/web`, package `tl_web`) on the dev ledger, sign in, open the logs and a record, and
recover from first-run problems. Package: `packages/tl-web/README.md`. Spec: `docs/build-spec/specs/web-client-i1.md`.

## When to use and before you start
- Trigger: a developer or a demo needs the pages in a browser, or a page answers 404, 403 or 503.
- Access: the repository, `uv` and `just` (the SessionStart hook installs both). Safe during business hours: yes (a
  local file ledger, `dev/data/tl.db`, git-ignored). The web is mounted only when `TL_WEB` is on.

## Steps
1. Create the dev ledger and a record, as in `docs/runbooks/tui-dev.md` step 1:
   ```
   uv run tl init --dev
   uv run tl record create --project P123 --key V-0001 --title "Valve 1"
   ```
2. Start the server, which serves the API and the web on one port:
   ```
   TL_PROJECT=P123 just serve       # 127.0.0.1:8765
   ```
   `GET /web/` redirects (303) to `/web/p/<TL_PROJECT>/rfis`; without `TL_PROJECT` it answers 404.
3. Sign in at `/web/sign-in` with `demo` / `demo` (the dev admin from `tl init --dev`). Expected: a 303 to `/web/`,
   then the RFI log. Agent accounts have no password and no web session.
4. Open the other pages by path, for example `/web/p/P123/correspondence` or `/web/p/P123/wbs`. A record opens at
   `/web/p/P123/records/<record_id>` with the tabs Details, Properties, History, Links, Trace, Thread and Files.
   `?mode=technical` shows record ids, for an admin only.
5. Sign out (a POST to `/web/sign-out`): the cookie is cleared and the browser goes to `/web/sign-in`.

## The demo
`just demo P2-WEB1` runs `dev/demos/P2-WEB1.sh` over HTTP with a cookie jar (curl), against a `tl serve` on a free
loopback port, on SQLite and on Postgres. Each of its five clauses ends in a PASS line.

## Settings
- `TL_WEB`: `on` or `off`. Unset means on where `TL_ENV` is dev, test or ci, and off elsewhere. Anything else is refused.
- `TL_WEB_SECRET`: at least 32 bytes; required outside dev, test and ci, refused at start-up when short. Dev makes one
  per process, so a restart invalidates the CSRF tokens of open pages.
- `TL_WEB_ORIGIN`: the origin a POST must carry when it is not the request's own (for example behind a proxy).

## Sessions and cookie
- Sign-in sets `tl_session`, the same opaque 12-hour token `POST /auth/sign-in` returns: `HttpOnly`,
  `SameSite=Strict`, `Path=/web`, `Max-Age=43200`, and `Secure` except on a loopback host in dev, test or ci.
- The cookie is read for `/web/` paths only; the JSON API ignores it and stays bearer-only.
- A role change, a disabled account or an expired session applies on the next request.

## Screenshots
The page tests save PNGs with their `shoot` helper to `/home/user/wt/p2-web1/.accept/shots`, outside the repository.
`.accept/` is git-ignored, so do not add the PNGs to a commit. The helper needs `node` and Chromium.

## Where errors show
- A refused action appears on the status line `#log-status`, prefixed `! `.
- A hidden record, file or number, and an absent one, get the same 404 page.
- Sign-in attempts are audited in the ledger; server errors go to the `tl_api` logger on the `just serve` terminal.
  A password is never logged or echoed.

## Troubleshooting
- **404 on a page or a row.** Hidden (ADR-0016) or absent. By design; do not work around it in the page.
- **403 `csrf_refused`.** The POST had no `X-CSRF-Token` or `csrf` field, or its `Origin` (else `Referer`) is neither
  the server's own nor `TL_WEB_ORIGIN`. Reload for a fresh token; behind a proxy set `TL_WEB_ORIGIN`.
- **503 `preview_busy` on a picture or a viewer.** Two renders are running. The answer carries `Retry-After: 2`. A file
  over 50 MB, or one that is not a PDF, is not drawn: 404 `no_preview`.
- **Sent back to `/web/sign-in`.** The 12-hour session ended, the server restarted with a dev secret, or the browser
  refused the cookie (`Secure` on plain http to a non-loopback host).
- **`TL_WEB` refused at start-up.** The value is not `on` or `off`.
- **Empty table, no error.** No rows are visible to the person. Compare with the terminal's list (`uv run tl rfi ls`
  is the RFI log; see `docs/runbooks/correspondence.md`).

## Roll back
Stop `just serve`. The web client keeps no store of its own; its sessions are the API's. To start over, delete
`dev/data/tl.db` and run `uv run tl init --dev`.
