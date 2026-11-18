# V3-F3 · Web fill page and cards (demo clause 9)
kind: piece · review: full + security · **owner signs off before merge (D42)** · branch `p2/v3-f3-web` · worktree
`/home/user/wt/v3p/f3` · base `p2/v3-forms` (F1a, F1b, F1s merged). Process: `docs/build-spec/process-v3.md` section 2.
Main reference: `docs/tickets/P2-FORMS/W2-fill-page.md` (decisions D27-D31, the six routes, the model block, `forms.js`
rules, its tests and mutation list). Follow it except where this page says otherwise. Old B2, B3, B4 rows in
`docs/tickets/P2-FORMS/README.md` are folded in.

## Changes from W2 (the base moved)
1. Reads: through F1a's forms routes (`tl_mod_forms.routes`, the `read_routers` hook) via `WebReadClient` rows and their
   `MIRRORS` entries, as D27 says; read the routes as merged, not W2's guesses.
2. Bound fill (`GET /web/forms/for/{key}`, `POST /web/forms/for/{key}/submit`): the binding comes from `/forms/for/{key}`;
   the submit goes through `tl_mod_forms.bound.record` (F1s), the same call `tl form record` makes, so the typed
   command's word, the source view word and the scope check apply unchanged. Never post the typed command around it.
   Permit precautions are format 2 `yes_no_na` questions (F1s report). W2's "bound list is empty" test is dropped: the
   first real bindings exist (inspections, permits).
3. B2: the inspection and permit cards' `open_path` points at `/web/forms/for/<key>` when the record has an open binding
   (otherwise unchanged). B3: draft resume on the page (`answers_json` pre-filled from the person's own draft; another
   author's draft id answers like an absent one).
4. Demo clause 9 in `dev/demos/p2_forms_demo.py` + `P2-FORMS.sh`: Playwright (pre-installed; `require('playwright')`
   or the Python package if present, Chromium needs no options), signed in through the test session, on the full demo
   ledger: fill and submit a general template, then fill an inspection from its card link; read both back through the
   API. No CSP violation logged. `PASS clause 9` only after the read-backs. Earlier clauses stay green.

## Rules
Allowed paths as W2, plus the card `open_path` lines in the quality and permits web cards, the forms demo, and its own
tests. No edit of `confidentiality.py`, `tl_core/**`, schema, `tl_api/app.py` or `tl_api/auth.py`; no new dependency.
CSP unchanged (D30): if the renderer needs a relaxation, stop and return `4`. Agents get the closed guard's answer on
every `/web/forms` route.

## Gate
`uv sync --frozen --all-packages` after creating the worktree. `just gate-changed` (if it stops at the deferred
`test_check_wheels` pin, run its later steps by hand and say so); `just gate packages/tl-web/tests`; the probe page
clause once; then `TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`. Report `docs/reports/P2-FORMS/V3-F3.md`, at most 15
lines, with a 5-line plain-English summary for the owner's sign-off at the top. Prefix `V3-F3:`.
