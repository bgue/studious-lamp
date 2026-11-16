# P2-FORMS-INTAKE S6 — The public `/i/<code>` route, staging, limits, settings and the purge job

kind: piece
review: full
branch: p2/forms-s6-intake-route
worktree: /home/user/wt/forms/s6
Depends on: S2, S3, CR1 (merged), **S7c merged** (`tl_core/qr/codes.py`, the four commands, the accept-side body delete, the staged-item helper of `forms_world.py`) and **I02 merged**
(`tl_mod_forms/intake_page.py`). Not dispatchable before both. The builder starts with `git merge p2/ip`. It is the only piece of the INTAKE slice that edits `tl_web/app.py`, `tl_api/auth.py` and
`tl_api/app.py`, and it does not run in the round of W2 (both edit `tl_web/app.py`).
Gated: **human gate, security, one schema line (D34); the owner is the approver** (APPROVALS line before merge; the orchestrator never approves). Security review row: this piece, scoped to its commit range. Labels: api, web, module, security.
Heavy runs: at most 2 at once; the gate runner kills a run over about 10 minutes (split the gates below).

## Why
ADR-0032 (accepted) decisions 1, 4, 5, 10, 11, 12, 13, 15. The first route of the web client with no session: everything a stranger can reach is hostile input, and everything the page says must be the same
for a live and a dead code. Staging is its own stream, never a proposal. The page render is I02's (pure); the commands (issue, revoke, accept, reject) are S7c's; this piece is the route, the writes of a received
item, the limits and the purge.

## Decisions this spec makes (record in the report and in `packages/tl-modules/forms/AGENTS.md`)
- **D19 purge is a job kind plus a service function.** `purge_due(uow, now)` in `tl_mod_forms/intake.py` is the only code that deletes `forms_intake_body` rows besides S7c's accept handler; a repo test pins
  exactly those two places. The job kind `forms.intake_purge` wraps it (pattern: `tl_core/threads/reminders.py` `ThreadReminderKind`). Scheduling is the caller's: the CLI `tl intake purge` is an I04 line and the runbook (I07)
  says to run it daily; S6 adds no scheduler.
- **D20 one service for the write, no command door.** A stranger never reaches `commands.py`. `tl_mod_forms/intake.py` has `resolve_code(conn, presented, today) -> LiveCode | None` (one exit for every miss) and
  `receive_item(uow, live, answers_body, form_key, now) -> Received | Replayed`. The actor is `INTAKE_ACTOR` (`svc:intake`, holds no word), source `f"intake:{code_id}"`, scope = the code's scope. Read how S3 appends
  `Record.Created {key: null}` for a record with no number and do the same for `forms.IntakeItem`.
- **D21 limits count every request, not failures.** Per address and per presented code, sliding hour windows, process-local and bounded (an LRU of at most 10 000 keys each; a key is the address, or the hash of the presented segment as D35 says, so memory is bounded and the code is never kept). The value comes from the settings `forms.intake.rate_per_address_per_hour` and `.rate_per_code_per_hour` (platform), read through
  the settings resolver and cached for at most 30 seconds. The gate runs **before the body is read and before the code is looked up**; a limited request gets the one 429 page (`render_busy`, `Retry-After`) whether the
  code is live, dead or malformed. The front-door limiter stays a release gate (runbook, I07).
- **D22 item id and receipt word.** `item_id` = a valid ULID built from the first 128 bits of `sha256(f"{code_id}:{form_key}")` with the top three bits cleared (so the first Crockford symbol is 0 to 7); the same
  form key therefore writes once (a unique stream: a second append of the same stream is a replay and answers the thank-you page). The receipt word is `grouped`-style `XXXX-NN` derived from the item id
  (four `ALPHABET` symbols and two digits): the same on a refresh, no information about the record, the code or the template.
- **D23 stored text.** Answers are coerced by kind from form strings (`number` through `float`/`int` with a finite check; `choice` exact match; `text` NFC-normalised, control characters (category Cc, tab and newline included: fields are one line) and bidi
  controls (U+202A to U+202E, U+2066 to U+2069, U+200E, U+200F, U+061C) removed, trimmed), unknown and duplicate form names ignored, then `validate_answers(fields, answers, fmt=2, partial=False, intake=True)`.
  The stored body is canonical JSON `{"answers": [...]}` of at most 8192 UTF-8 bytes (D36); `salt` = 16 random bytes as 32 hex; `body_mac` = HMAC-SHA-256 keyed by those salt bytes over the body bytes. The salt lives in the body row only.
- **D24 headers and mount.** Every answer under `/i/` (including 404, 405, 413, 429 and a 500) carries `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'` and never a `Set-Cookie`; the middleware wraps the whole stack as
  `WebHeadersMiddleware` does (read `tl_web/app.py`; copy its stack wrapping). The page's one stylesheet is `/web/static/intake.css` (created here: plain CSS, no `url()`, no `@import`, class `hp` hides the honeypot).
  `/i/` is outside `/web` on purpose (the cookie is `Path=/web`): `tl_api/auth.py` gets an open prefix `/i/` (one constant and one condition; the middleware does not resolve a session there).
- **D25 access log.** `tl_api/accesslog.py` (create): a `logging.Filter` for the `uvicorn.access` logger that replaces the path segment after a listed prefix with `<code>`; prefixes are a tuple argument `("/i/",)` so QR S3 appends
  `"/web/q/"` later. `tl_api/main.py` installs it before `uvicorn.Config`; the `--insecure-dev` warning middleware prints the redacted path. No other log line carries the path of `/i/`.
- **D34 the code hash never leaves (S7c security review).** `code_hash` of `IntakeCode.Issued` gets `tl:webhook: omit` in `schema/modules/forms/events.yaml` (one annotation block on that slot, the S2w mechanism; `just gen`; the catalog list
  of omitted slots grows by one and the pin in `packages/tl-core/tests/test_webhook_omit.py` is updated, named in the report). It stays out of every read view: I03's `CodeRow` has no such attribute and no view selects it (a repo test, below). This is the only schema line in S6 and
  is part of the owner's approval (the APPROVALS line names it).
- **D35 the per-code limiter cannot reveal a live code (S7c review).** The per-code key is `sha256(normalise_code(segment))` when the segment is a code, else `sha256(segment cut to 64 bytes)`: case, space and hyphen variants of one code count together, a malformed segment still counts. The counter is read and bumped
  by the same function for a live, a dead and a malformed segment, **before** `resolve_code` runs and with no read of any code state; the threshold, the 429 bytes and the `Retry-After` value are the same in all three; nothing in the limiter's key, value or log depends on whether a row exists.
  A test drives the same number of requests at a live and a dead code and sees the 429 on the same request number, with identical bytes.
- **D36 byte caps count bytes (S2 review F1).** The request body cap is on bytes received: the stream is read in chunks and stops at 8193 bytes (a `Content-Length` over 8192 is refused before reading, a missing or false one is not trusted); never `len(str)`. Each text answer is bounded in characters by its field (280) **and** the whole stored body in bytes:
  `len(canonical_json.encode("utf-8")) <= 8192` is checked after cleaning and before the insert (a body of 280 four-byte characters per field must be refused when it passes 8192 bytes, though far under 8192 characters). `body_bytes` of the item records that byte length.
- **D26 not built here:** a feed card for the controller role (count and heading only: a count view arrives with I03/I05, the item events have `feed_policy: none`), any photo, captcha, minimum fill time, outbox. Say so in the report.

## Goal
1. `tl_mod_forms/intake.py`: `LiveCode`, `resolve_code` (normalise with `tl_core.qr.codes`, hash, look up `cur_forms_intake_code` by `code_hash`; live = Active, `expires_on >= today`, setting `forms.intake.enabled`
   true, the pinned template version exists, is Published, `content_hash` equals the pinned `template_hash`; otherwise `None`), `pending_count`, `receive_item`, `purge_due`; the job kind in `jobs.py`; registration of the kind where
   modules register job kinds (read `ThreadReminderKind` and its wiring; one line).
2. `tl_web/intake.py`: the gate middleware (D21, D24) and the router with exactly `GET /i/{code}` and `POST /i/{code}`; every other path or method under `/i/` (and `/i`) answers the neutral 404 bytes.
   GET: the form from `render_form` (title = template title, heading = the code's heading, fields of the pinned version, purpose and `accepts_as` never shown, `form_key = secrets.token_hex(16)`).
   POST (`application/x-www-form-urlencoded` only, else the neutral 404; at most 8192 bytes counted as D36 says, else the fixed 413 page): in this order: honeypot `website` non-empty gives the thank-you page and stores nothing; resolve the code
   (miss: neutral 404); `forms.intake.pending_per_code_max` reached: `render_full`; coerce and validate (D23; problems: the form again with `error_ids`, status 422, the typed values back); `receive_item` in one unit of work;
   thank-you with the receipt word. Nothing in any answer names a record, key, state, count or earlier submission.
3. `tl_web/static/intake.css`; the open prefix in `tl_api/auth.py`; `("/i/", 8192)` in the body limits of `tl_api/app.py` (this and nothing else in that file); `tl_api/accesslog.py` and its install.
4. Docs: forms `README.md` and `AGENTS.md` (D19 to D26, the route's contract), `packages/tl-web/README.md` one row (`/i/`). No runbook (I07).

## Allowed paths
- `packages/tl-modules/forms/src/tl_mod_forms/{intake.py,jobs.py}` (create), `.../{module.py,names.py}` (edit: the job-kind line, names)
- `packages/tl-web/src/tl_web/intake.py` (create), `.../tl_web/app.py` (edit: the mount call and nothing else), `.../tl_web/static/intake.css` (create), `packages/tl-web/README.md` (one row)
- `packages/tl-api/src/tl_api/{auth.py,app.py,main.py,accesslog.py}` (the lines named above only)
- `schema/modules/forms/events.yaml` (D34: the one annotation on `IntakeCode.Issued.code_hash`), regenerated `packages/tl-schema/src/tl_schema/generated/**` (`just gen`), `packages/tl-core/tests/test_webhook_omit.py` (the pinned count), `packages/tl-modules/forms/tests/test_webhook_answers.py` (add `code_hash` cases)
- `packages/tl-modules/forms/{README.md,AGENTS.md}`; tests below under `packages/tl-modules/forms/tests/`, `packages/tl-web/tests/`, `packages/tl-api/tests/`, `tests/`
- Pinned lists (named in the report with old and new count) only where they fail because of the new route or kind (candidates: `packages/tl-web/tests/test_web_imports.py`, a job-kind list)
- `docs/reports/P2-FORMS/S6.md` (create)
Not allowed: `schema/**` beyond the D34 line, `tl_core/**` (an escalation; the pin file above is a test), `tl_core/confidentiality.py`, `commands.py` and `handlers/**` of forms (S7c), `intake_page.py` (I02), `tl_cli`, `tl_mcp`, `tl_tui`, any other module.

## Tests to add
Lint-clean where they land (`ruff format`, `ruff check`, strict `pyright`; `# pyright: ignore[...]` on a deliberately wrong-typed call). Statement-count assertions ignore `BEGIN`, `COMMIT`, `ROLLBACK`.
Time is injected (a clock argument), never slept. Each test builds its own world with the helpers of `forms_world.py` (a published public template, an issued code with a known plain code).
- `packages/tl-web/tests/test_intake_dead_codes.py`: unknown, malformed (15, 17 symbols, wrong alphabet), revoked, expired (the day after `expires_on`), retired template, `forms.intake.enabled` false: GET and POST each give
  status 404 with **byte-identical** body and identical headers; `/i`, `/i/`, `/i/x/y`, `PUT`, `DELETE`, `HEAD` likewise neutral.
- `test_intake_limits.py`: address limit and code limit each give one 429 page with `Retry-After`, identical for a live, a dead and a malformed code; the limit is applied before the body is read (a body that would be a 413 is a 429
  when limited); the counters are bounded (11 000 distinct codes keep at most 10 000 keys) and keep no code text; settings changes apply within the cache window; a limited address does not block another.
- `test_intake_post.py`: a good POST stages one item (one `Record.Created`, one `IntakeItem.Received`, one body row; actor `svc:intake`, source `intake:<code id>`, scope of the code); the same form key twice writes once and both
  answers are the same thank-you page; the receipt word is stable and carries no code, id or template text; the pending cap gives `render_full` and no write; the honeypot filled gives the same thank-you shape and **no** event and no row;
  invalid answers re-render with `error_ids`, 422, nothing stored; 8193 bytes give the fixed 413; a wrong content type is neutral.
- `test_intake_hostile.py`: `\x1b[31m`, NUL, U+202E, 10 000 characters, 300 form fields, duplicate and unknown names, invalid UTF-8 bytes, a number of `1e999` and `nan`, a choice not in the list: refused or cleaned with no 500; the stored body holds
  none of the removed characters; markers placed in answers appear **only** in `forms_intake_body.body`: scan every `event` row payload, every `cur_*` table, the feed, the audit rows and a webhook delivery built for the item
  (none may contain a marker, the code, the plain address or the salt).
- `test_intake_headers.py`: the D24 headers on 200, 404, 405, 413, 422, 429 and a forced 500; no `Set-Cookie` on any; a request carrying a valid session cookie of a signed-in person is treated as anonymous (same bytes, nothing about the person).
- `test_intake_page_blind.py`: the GET page of two codes with different contexts and different controller roles differs only in the template title, heading and fields; the page and the thank-you hold no key, project, state, count or name of the context.
- `test_intake_purge.py` (forms): retention boundary (`retention_days` minus a second is kept, plus a second is purged; per-company override honoured); rejected and undecided items purged, accepted ones have no body; `IntakeItem.Purged` once and a re-run
  is a no-op; a batch is bounded (100 per run); a rebuild of projections keeps body rows; a repo test pins that `DELETE FROM forms_intake_body` occurs in exactly `intake.py` and S7c's `handlers/intake.py`; the job kind runs through `JobRunner` once.
- `test_intake_limits.py` additions (D35): case, space and hyphen variants of one live code share one counter; a live and a dead code reach 429 on the same request number with byte-identical bodies and headers; no limiter structure holds a code (scan keys and values for the plain and grouped code).
- `test_intake_post.py` additions (D36): a body of 8193 bytes made of multi-byte characters under 8193 characters gives the 413; 8192 bytes passes; four fields of 280 four-byte characters (over 8192 stored bytes) are refused with the form again and nothing stored; `body_bytes` equals the stored byte length.
- `packages/tl-modules/forms/tests/test_webhook_answers.py` (D34): `IntakeCode.Issued` delta and full bodies hold no `code_hash` key (absent, not null), thin has no detail; `test_intake_code_hash_private.py`: `tl_mod_forms/intake_views.py` (if merged; else skipped with a reason) and every `*views*.py` of forms name no `code_hash`, and the result types have no such attribute.
- `packages/tl-api/tests/test_accesslog.py`: the filter replaces the code in an access record, leaves other paths alone, takes the prefix tuple; a captured log of a full GET and POST holds no code.
- The anonymous-reader walk over the whole route family and the five-reader walk of the signed-in queue are I06; say in the report which of your tests it supersedes.

## Gate
`just check` (`NODE_OPTIONS=--max-old-space-size=6144`); then one run at a time (split to stay under about 10 minutes each; name each run in the report):
1. `just gate packages/tl-web/tests/test_intake_dead_codes.py packages/tl-web/tests/test_intake_limits.py packages/tl-web/tests/test_intake_headers.py packages/tl-web/tests/test_intake_page_blind.py`
2. `just gate packages/tl-web/tests/test_intake_post.py packages/tl-web/tests/test_intake_hostile.py packages/tl-api/tests/test_accesslog.py`
3. `just gate packages/tl-modules/forms/tests/test_intake_purge.py`
4. `just gate packages/tl-web/tests/test_web_headers.py packages/tl-web/tests/test_web_auth.py packages/tl-web/tests/test_web_imports.py` (the `/web` rules are unchanged: proof)
5. `just gate-pg packages/tl-modules/forms/tests/test_intake_purge.py packages/tl-web/tests/test_intake_post.py`

## Mutation cap
One sentinel plus at most 5 targeted: the limit check moved after the body read; the honeypot stores an item; the body cap measured in characters (the D36 test must fail); the `code_hash` annotation removed (the webhook test must fail); the per-code key built from the raw segment (the D35 variants test must fail). 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/S6.md`; first line deviations or none. List: the route contract, D19 to D26 as applied, every pinned file with old and new count, the scan result of the hostile test,
and one line on what a stranger can still learn (answer: that a code is dead, the same for all causes). Commit `P2-FORMS-S6: ...` with the session trailers; no model names in committed text.
