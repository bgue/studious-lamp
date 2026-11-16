# P2-QR-T11 - Demo `dev/demos/P2-QR.sh`: eight clauses, SQLite then Postgres

Status: ready (written r6; base `p2/ip-r3`; QR-S2, S3, T04, T06, T07 and the INSP and PTW cards merged)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests
Depends on: P2-QR-S3, T04, T06, T07; P2-INSP-T09; P2-PTW-T09 (all merged)
Branch: `p2/qr-t11-demo`
Worktree: `/home/user/wt/qr/t11` (from `p2/ip-r3`)

## Goal
`just demo P2-QR` runs the eight clauses of `docs/tickets/P2-QR/README.md` "Demo" once on SQLite and once on Postgres, one `PASS clause N: ...` line each. **A PASS line is printed only after a real check returned success** (a command's exit code and an output comparison, or a driver assertion); a miss prints `DEMO FAILED` and exits non-zero; there is no `echo PASS` on a path that checked nothing. Pattern: `dev/demos/P2-PUNCH.sh` and `p2_punch_demo.py` (header, backends, `tl serve` on a loopback port, driver modes, cleanup trap; read the header comment of the .sh first) and `dev/demos/P2-WEB1.sh` for the web sign-in. State changes only through real commands; no projection write anywhere. Clause 5 (scaffold card) prints `PASS clause 5: deferred (scaffold card not built)` only when `tl_mod_scaffold` has no `scan_card` (check with the driver, not an `echo`); it is the one clause allowed to print `deferred`, and the line says why.

## Clauses (the README is the spec of record; read each verb from the merged CLI and the reports, the merged CLI wins and a difference is the first line of your report)
Setup by commands: project `P123`, `api.public_base_url` set through the settings CLI (read how `P0-I8-A.sh` sets a key; the refusal text of clause 1 is `qr`'s `MSG_BASE`), people `uma` (plain reader), `sue` (module superuser where a verb needs it), `dora`; one IWP made as `P2-I2.sh` makes it (number read back from `tl awp iwp ls`, never assumed), one inspection (`tl insp plan`, verbs from `docs/reports/P2-IP/INSPT05.md` and `packages/tl-cli/tests/test_cli_insp.py`) and one permit (`tl permit request`, verbs from `docs/reports/P2-IP/PTWT04.md`) on it.
1. Label: with the setting unset `tl qr label <IWP key>` is refused with the fixed message; after setting it a label file is written; the QR text is `<base>/web/q/<16 chars>` and the file holds no key, id or project code outside the grouped print (the scan `test_cli_qr.py::test_label_writes_an_svg_or_the_note_and_prints_no_code` does; reuse its way of reading the code from the file; the code is never printed to stdout).
2. Signed out, `GET /web/q/<code>` and `GET /web/q/<nonsense>` give the same 303 to sign-in (compare status and the `Location` up to the `next` value); signed in as `uma` through the web sign-in (`P2-WEB1.sh`), the page shows the banner, key, "as of" and the lines.
3. One miss: a malformed code, an unknown code, a revoked code (`tl qr revoke`, `--project` required) and the code of a record restricted after the label was made (restrict a record as `P2-I3.sh` or the P2-PUNCH demo clause 5 does) give byte-identical 404 bodies and headers for `uma`. Expired and no-view-word are not makeable by commands without a clock or an account lacking `qr.view` (`docs/reports/P2-QR/T06.md`, learnings): the clause line says "4 of 6 miss kinds; expired and no-word in test_scan_page.py" and the report repeats it. Agreed r6, README clause 3 is amended by this line.
4. Rotate: the old code is a miss, the new one resolves; `tl qr ls <key>` shows both rows and never a code; the miss counter: eleven misses from one session give one 429 on the eleventh.
5. Scaffold card: as above.
6. Agents: an agent token gets 401 on `/web/q/...` and the closed guard's 403 on `GET /qr/codes` and `/qr/resolve/<code>` before any lookup; a signed-in person gets the one 404 miss; `tl qr export --format jsonl` rows equal `tl qr ls` rows (field by field, as `test_cli_qr.py` does).
7. `tl qr resolve` (code from stdin, never argv) on an embedded ledger prints the same card text the page shows (compare the banner and the lines).
8. A label for the inspection and one for the permit each resolve to their status card (the banner for the inspection by its state, for the permit `REQUESTED - not approved`; the permit card also carries the `Gas test` line once PTW-T09b merged: assert it only if present).

## Context (read these, nothing else)
- `docs/tickets/P2-QR/README.md` (Demo), `dev/demos/P2-PUNCH.sh`, `dev/demos/p2_punch_demo.py` (abridged: header and one mode of each kind), `dev/demos/P2-WEB1.sh` (the sign-in helper only)
- `docs/reports/P2-QR/{S3,T06,T07}.md`, `docs/reports/P2-IP/{INSPT05,PTWT04}.md`; may explore `packages/tl-cli/tests/test_cli_qr.py`, `packages/tl-web/tests/test_scan_page.py`

## Allowed paths
- `dev/demos/P2-QR.sh` (create, executable), `dev/demos/p2_qr_demo.py` (create), `docs/reports/P2-IP/QRT11.md` (create)

## Acceptance
```
uv run ruff format --check dev/demos/p2_qr_demo.py
uv run ruff check dev/demos/p2_qr_demo.py
uv run pyright dev/demos/p2_qr_demo.py
just demo P2-QR
```
Expected: eight `PASS clause N` lines per backend, no `DEMO FAILED`, exit 0, no leftover files or databases. Run the demo once; Postgres down means `ge` and stop (do not skip the backend). No pytest, no `just gate`, no `just check`. To prove the checks are real the report names, for each clause, the one comparison that would fail if the feature broke (not a mutation run).

## Escalation triggers
A clause cannot pass without a change in `packages/`, `schema/` or `dev/seed` (name the clause and the missing verb or text); a restricted record cannot be made with the verbs named; the demo needs more than the two files; the web sign-in cannot be driven without a browser.

## Report requirements
`docs/reports/P2-IP/QRT11.md` <= 60 lines: the PASS lines of each backend (<= 5 decisive lines each), one line per clause naming its surface (CLI, web, API, MCP none). Standard report (`docs/templates/haiku-report.md`), deviations first. Commit subjects `P2-QR-T11: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
