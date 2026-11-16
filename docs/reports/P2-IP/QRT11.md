# Report — P2-QR-T11 (demo `dev/demos/P2-QR.sh`)

Branch: `p2/qr-t11-demo`   Commit(s): the demo commit on top of `3f6720d1` (blocked report, superseded)

## Deviations
1. NOT DONE: `just demo P2-QR` exits 1. SQLite passes 8 of 8; Postgres passes clauses 1-6 and fails at clause 7 (Open questions 1).
2. Agent grant by the admin CLI (`tl admin user add triage --kind agent`, `tl admin roles grant triage --module '*' --role user`), not `dev/demos/agent_grant.py`, which raises `AttributeError: 'PostgresUowFactory' object has no attribute 'close'` on Postgres. Outside Allowed paths; not edited.
3. No QR is drawn: `segno` (the `labels` extra) is not installed, so every label carries the no-QR note. The QR text is checked only when an SVG is present.
4. Clause 3's hidden miss is a permit made `--for` a correspondence item that `dora` restricts after the label. No command restricts an IWP or an inspection. A `visible` check proves uma sees the card before the restriction.
5. Grants beyond the ticket: `sue` module superuser on `awp`, `quality`, `permits`, `qr` (revoke needs the QR controller word); `dora` on `documents`.
6. Ruling (a): base address in a scratch copy of `platform.yaml` under the demo's temp dir; `TL_SETTINGS_PLATFORM_FILE` only inside the label calls; shipped file unchanged.

## Changed files
- `dev/demos/P2-QR.sh` — new, executable: setup, eight clauses, cleanup trap.
- `dev/demos/p2_qr_demo.py` — new: platform copy, label check, web clauses, card compare, no-code, export compare.
- `docs/reports/P2-IP/QRT11.md` — this report.

## Commands and output
```
$ uv run ruff format --check dev/demos/p2_qr_demo.py  -> 1 file already formatted
$ uv run ruff check dev/demos/p2_qr_demo.py           -> All checks passed!
$ uv run pyright dev/demos/p2_qr_demo.py              -> 0 errors, 0 warnings, 0 informations
$ TL_DEMO_BACKENDS=sqlite bash dev/demos/P2-QR.sh     -> "[sqlite] clauses 1-8 passed", exit 0
$ just demo P2-QR                                     -> exit 1 after 1407 s (sqlite ~10 min, postgres ~13 min)
sqlite (5 decisive PASS lines; clauses 2, 5, 7 also PASS):
PASS clause 1: unset: refused "error: set api.public_base_url first", no file; set: label, no key/id/project
PASS clause 3: malformed, unknown, revoked, hidden: byte-identical 404 pages and headers (Date aside)
PASS clause 4: rotated <old> to <new>; ls "scan codes: 3", no code; eleventh lookup 429
PASS clause 6: agent 401 (scan path), 403 (/qr/codes, /qr/resolve); export rows equal ls rows
PASS clause 8: inspection "HOLD POINT - not released"; permit "REQUESTED - not approved"; CLI equal to web
postgres: clauses 1-6 PASS (same lines). Then:
FAIL uma's scan gave 500, not a card  (driver card-compare, clause 7)
pg8000 FATAL 57P03 "the database system is in recovery mode"; recipe `demo` exit 1
Timing: postgres signed-in card lookups 114-120 s (SQLite 2-4 s).
```

## Clauses: surface, and the comparison that fails if the feature breaks
1. CLI + file. Output and file hold no KEY, record id, project or register id outside the grouped print, and no code.
2. Web. Signed-out code and nonsense path: 303, same body, same Location before `?`; uma's card key = KEY.
3. Web. Malformed, unknown, revoked and hidden codes for uma: status, headers (Date aside) and body equal.
4. Web + CLI. Old code 404; new code's card; `ls` lists old, revoked and new rows; eleventh lookup 429.
5. None. The driver checks `tl_mod_scaffold` has no `scan_card`.
6. API (403 on `/qr/codes`, `/qr/resolve`), web (401 agent, 404 uma), CLI (`export` jsonl equals `ls`, field by field).
7. CLI (`tl qr resolve`, stdin) against uma's card: banner, key, title and lines equal.
8. Web + CLI. Inspection banner by state; permit banner equal to `REQUESTED - not approved`.
MCP: none.

## Tests added
none (the ticket adds a demo, not tests).

## Learnings (proposed)
- `agent_grant.py` cannot run on Postgres (`PostgresUowFactory` has no `close`); a dev/demos ticket should fix it.
- On this host Postgres card lookups take about 115 s. The kernel OOM-killed Postgres backends three times this session at 7.5-8.8 GB anon RSS, on the scan lookup path (core hidden filter; core unchanged).
- Permits can be made `--for` a correspondence item and hidden by restricting it; IWPs and inspections cannot be restricted by a command.
- The miss counter is 10 per session and 30 per address in 600 s; every demo miss from one address counts toward 30.

## Open questions / Blocked
1. Acceptance not met on Postgres: clause 7 fails because a backend was OOM-killed during a card lookup. Decide: (a) accept a SQLite pass with the Postgres failure logged; (b) a core ticket for the hidden-filter memory growth (outside these paths); (c) rerun on a host with more memory.
2. QR text unverified here. Install the `labels` extra (`segno`), or accept the no-QR note? The ticket does not name the extra, so it is not added.
3. `agent_grant.py` Postgres bug: a separate dev/demos ticket, if wanted.
