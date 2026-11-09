# Outside review, 2026-11-09

Five read-only questions put to the planner tier at the owner's request (2026-11-09, "ask your hardest questions").
Each answer is abridged; file and line evidence is in the reviewers' returns. Sections 1-2 are added when those reviews finish.

## 3. Write paths (one dispatcher)

Entry points that append events and how they compare with the API's order (`run_command`: authorizer -> reserved
check -> company/admin -> module word -> `check_intent` -> intent carrier -> handler):
- API JSON routes: the reference. `POST /types/{t}/records` skips `run_command` (no reserved check, no intent): MD.
- `TableCommandRunner` (rules, inbound, thread dispatch, accepted dispatch proposals): module word checked, but no
  reserved check, no company/admin step for module commands, and **no intent** (an accepted proposal's intent is lost
  on this path): MD.
- CLI: module handlers gated by `require_command`; intent on four commands only. **HI: admin commands (rule, action,
  enricher, endpoint, integration app, link admin-flag) check only that someone is signed in; the API requires admin.**
  Being fixed on `p2/fix-cli-admin`. Latent: company-scope core commands are not escalated to admin in the CLI or the
  embedded TUI client.
- TUI embedded: module words via its own gates, admin/controller via its own code; no intent.
- MCP: propose tools carry intent and accept re-checks access; two direct tools match the API's agent exceptions.
  Read-side confidentiality in MCP was not traced (open question).
- Simulator: goes through the API. Files service and jobs append after their own checks.
- The CLI has about 143 direct handler calls (not 440; that figure likely counted imports).

Recommended single write path: a `tl_core.dispatch` (registry of command specs, a `Caller` resolved by each entry point,
one `dispatch(uow, command, caller)` doing reserved -> platform word -> module word -> agent rule -> intent -> handler,
one refusal error family). Lock it with the existing gate sweep extended to every package and a ruff banned-api rule
for direct handler imports. Migration about 17 points (~30 agent-hours): extract the dispatcher (3), runner and proposal
accept (3), CLI codemod (5), embedded TUI (3), MCP and two API routes (1), lint lockdown (2). Owner decision needed:
whether the dev-file `--actor` freedom stays.

## 4. Build-process economics (how to halve the cost per merged ticket)

Working model (±30%): a clean ticket costs about 8-12 M input tokens; one fix round 6-10 M; at about 1.5 fix rounds per
ticket a merged ticket costs about 2.5 times a clean one. In the 36 hours to 2026-11-09, 43 of 291 commits (15%) were
fixes, pins, snapshots or regenerations. Most fix rounds have deterministic, preventable causes.

Five changes, ranked:
1. **Pin manifest.** Settings, access words and offline classes are pinned by count in 9+ test files over 6 packages,
   so every new setting touches about 12 files and parallel branches conflict. Generate one manifest
   (`tl_schema.generate` -> `generated/manifest.py`), snapshot it once (`tests/tools/test_manifest.py`), and make surface
   tests compare against the manifest instead of a number. One builder piece (~15 files), plus a `just check` guard
   that rejects new count pins.
2. **Pre-dispatch ticket lint** (`dev/ticket-lint.sh`, first step of the ticket workflow): every named test path exists
   or is listed to add; provided tests live under `docs/tickets/<INC>/provided/` (outside pyright) so they cannot break
   `just check` on other branches; allowed-path globs match something; commit prefix shown once.
3. **A gate that fits the box.** The workflow's 10-minute part timeout is shorter than tl-tui (22 min) and tl-cli
   (45 min) runs; replace it with a per-test timeout (`pytest-timeout`). Add a lock in `dev/gate.sh` so two gates queue
   instead of killing each other (out of memory).
4. **Run `dev/review-pack.sh` before every review.** Boundary and format findings go back to the author as a cheap fix,
   so the reviewer spends on logic. Delete the stale `ticket-batch.js`.
5. **Honest demos.** No unconditional `echo PASS`: a PASS line only from a real check; add a `just check` guard.

Gate design for under 60 minutes on this box: lock and per-test timeout; fix the two slowest tests first (tl-schema's
repeated `generate.main`, tl-cli's per-test schema creation -> a copied template database); `pytest-xdist -n 2
--dist loadfile` for the large packages; select tests from the diff (`dev/impact.toml`); keep the pytest cache for
`--lf`; skip directories unchanged since the last green trunk run; condition waits instead of wall-clock asserts, and a
"flaky" line that re-runs failures alone once and opens a ticket (the test is never hidden; the gate stays red).

The orchestrator should stop: running per-folder gates by hand; editing code; answering widening questions that belong
in the ticket template; resolving pin conflicts; keeping worktrees and notes outside the repository (a container restart
wiped them; keep worktrees under the repository and push after each green gate).

## 5. Roadmap risk and strategy (for the owner)

**Riskiest assumption:** that the first users will work in an 80x24 terminal (install with `uv`, WSL2 on Windows, keyboard
entry of weekly plans, progress, requisitions and punch items). No user test exists yet. Test it in a week: give the
loopback starter bundle to two or three people in pilot roles for 30 minutes each, unaided, and record where they stop;
ask whether they would use it daily or need a browser or phone.

**Fastest path to a first field deployment** (2-5 people, one project, Postgres behind TLS, 4-6 weeks):
- Merge the release first, then pull three deferred rows ahead of the pilot: refuse the public try-it object secret in
  prod; the plain-http guard for every API client user; one full Postgres parity run. About 1.5 points.
- Weekly plans and progress (I5) first, trimmed: keep rules of credit, progress, roll-up and CSV, weekly plan, commit,
  PPC, waive and hold rule, look-ahead, the "mine" IWP log and landing, HTML pack; defer the PDF pack, closeout, the
  subcontract CSV and five of seven KPI tiles. Saves about 2.5-3 points.
- Punch list right after I5 (3-4 points).
- Requisitions (I4-A) trimmed: keep raise, edit, approve, reject, cancel, the work-order lifecycle, logs and the propose
  tool; defer stock fulfilment (FIFO lots), `tl req fulfil`, the labour forecast and reports. Saves about 2.5 points and
  avoids the first module-to-module import.
- Wave 4 (text Gantt, schedule comments) and the drawings panel after the pilot starts.
- Net: about 17-19 points to a pilot-ready trunk instead of about 40-45.

**Release:** nearly safe. First merge the trunk into `p2/rel` (96 commits behind; four doc or generated conflicts),
re-run the affected gates, rebuild the wheels and the starter (its ledger predates the intent column) and re-run the
smoke. Owner checks: a public bind without `TL_ENV` exits and says why; prod refuses to start without an object secret
or with an enabled demo account (ask for this test's name; not seen in the smoke output); a dev token gets 401 in prod;
the TUI refuses a non-loopback plain-http server without printing secrets; the old local ways still work. Nobody outside
the build has followed the runbook yet. The name `tl-cli` is taken on PyPI by an unrelated package: rename the
distribution before publishing.

**Owner decisions recommended:**
1. Who the first field users are, when, and whether their data is kept (recommend one project, 2-5 people, planner first,
   data kept, with a 1-2 point "0.1 ledger opens on 0.2" test).
2. Terminal only for the pilot, or read-only web pages moved ahead (decide after the one-week user test).
3. Reorder as above and take the small pre-pilot security bar in place of the optional wave review.
