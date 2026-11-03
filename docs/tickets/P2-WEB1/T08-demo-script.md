# P2-WEB1-T08 — The demo script `just demo P2-WEB1`

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs, demo, web
Depends on: S1, S3, S4, S6, T01, T02, T05, T15 (merged on `p2/web1`)
Branch: `p2/web1-t08-demo`

## Goal
`just demo P2-WEB1` runs the five clauses of the web client spec once on SQLite and once on Postgres, over HTTP with `curl` and a cookie jar against a real
`tl serve`, and ends each clause with a `PASS clause N` line. The script holds no business logic; the in-process version of the same clauses is
`packages/tl-web/tests/test_web_demo_clauses.py` (S5).

## Brief references (pasted)
> 1. `tl serve` on a seeded ledger; `curl -c jar -d username=... -d password=... /web/sign-in` -> 303 and a cookie with `HttpOnly`, `SameSite=Strict`;
>    `curl -b jar /commands/AnswerTechnical` -> 401 (cookie ignored by the JSON API).
> 2. `GET /web/p/P123/rfis` has the seven region ids in order; rows match `tl rfi ls` for P123; a restricted RFI is absent for amy and present for the
>    controller (dora); its number answers amy with the generic 404 page.
> 3. Selecting an RFI shows its panel and only the offered actions; `POST .../do/AnswerTechnical` without `X-CSRF-Token` -> 403 `csrf_refused`; with it ->
>    200 and the panel shows the new state.
> 4. The document log shows a page-1 image for a PDF revision; `/web/p/P123/files/{id}/view` serves the viewer with the CSP header;
>    `/web/files/{id}/content` returns the bytes whose SHA-256 the file info states.
> 5. `?mode=technical` shows record ids for the admin (demo) and the "for admins" status line for amy.

Real paths (this file wins over the spec text): the log page is `/web/p/P123/rfis` and `/web/p/P123/documents`; the panel is
`/web/p/P123/rfis/panel/{number}`; the action is `POST /web/p/P123/records/{record_id}/do/{command}`; the CSRF token is in the page (`<meta name="csrf-token" content="...">` in `base.html`, read it with `sed`).
Region ids: take the seven `id="..."` values from `templates/log.html` and the templates it includes (`crumb.html`, `status.html`, `actions.html`) in page order and compare with `grep -o 'id="[a-z-]*"'`.

## Interfaces (verbatim from repo at the branch point)
Models to copy, not import: `dev/demos/P1-UX2.sh` (backend loop, `tl init --dev`, users amy/dora/demo, seed of RFIs and a 3-page PDF document through the CLI),
`dev/demos/P1-I0.sh` (starting `tl serve` on a free loopback port in its own process group, `stop_server`, `TL_DEMO_URL`), `dev/demos/P1-I5.sh` lines 185-191
(`tl corr class set <number> --project P123 --to restricted --reason ...`).

## Context (read these, nothing else)
- `dev/demos/P1-UX2.sh`, `dev/demos/P1-I0.sh`
- `dev/demos/p1_i0_demo.py` (only `pg-create` and `pg-drop`; reuse, do not edit)
- `packages/tl-web/src/tl_web/templates/{base,log}.html`
may explore: `dev/demos/P1-I5.sh` (restricted class lines only), `templates/{crumb,status,actions}.html` (region ids)

## Allowed paths
- `dev/demos/P2-WEB1.sh` (create, executable)
- `docs/reports/P2-WEB1/T08.md` (create)

## Steps
1. Header comment: the five clauses as above, backends (`TL_DEMO_BACKENDS`, default "sqlite postgres"; Postgres is a throw-away database dropped afterwards;
   unreachable = failure), `set -euo pipefail`, `fail()`, `step()`, `quiet()` as in P1-UX2.sh.
2. Per backend: init, users (demo is the admin; amy a plain user; dora a document controller), standards, three RFIs, one document with a 3-page PDF rendition,
   then dora sets one RFI (the third) to `restricted`. Start `tl serve`; wait on `/health`.
3. Clauses 1 to 5 with `curl -s -o body -D headers -w '%{http_code}'`; assert with `grep`/`case`, never with a sleep loop. Each clause ends `echo "PASS clause N"`.
4. Stop the server (process group) and drop the Postgres database on exit (trap), as the models do. Nothing is left behind.

## Acceptance
```
bash -n dev/demos/P2-WEB1.sh
just check
```
Expected: no output from `bash -n`; `just check` exit 0. Do **not** run `just demo` or a test suite (the orchestrator runs the demo at C4). Paste the
`bash -n` result and `just check` tail in the report.

## Tests to add
none (the demo is its test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`, <= 60 lines). Commit subject `P2-WEB1-T08: <summary>`; end the message with the attribution line your harness requires, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer; no model names. Setup first: `uv sync --all-packages`,
`NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- Stop and report *Blocked* if `tl corr class set` does not accept an RFI number (then give the exact error and the CLI that does restrict an RFI), if the page does not
  carry a CSRF token you can read with `sed`, or if any path outside Allowed is needed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
