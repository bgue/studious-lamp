# Run paused: owner request after P1-I2

The autonomous build run paused on 2026-10-13 after increment P1-I2, because the owner asked to stop there to keep
capacity for the rest of the week. This is not a failure, and no stop condition in `docs/build-spec/KICKOFF.md` fired.
The scope in KICKOFF.md (to the end of Phase 1) is unchanged; the next run resumes at P1-I3.

## Where things stand
- **Trunk:** `claude/wizardly-allen-m2v96s`, pushed. Done in Phase 1: P1-I0 (authentication, admin, Postgres for the
  services), P1-I1 (standards registry, numbering patterns, tags), P1-I2 (document control core). One line each in
  `docs/reports/STATUS.md`; increment reports in `docs/reports/P1-I0.md`, `P1-I1.md`, `P1-I2.md`.
- **Gates on the P1-I2 tree** (`p1/i2` 621fbcf; the trunk merge adds only a KICKOFF.md doc change, and `just check`
  and `just demo P1-I2` were re-run on the trunk):

  | Gate | Result |
  |---|---|
  | `just check` | green |
  | `just test` | 7150 passed, 1 skipped; one load-related `ReadTimeout` in `tl-api/tests/test_stream.py` that passes alone |
  | `just test-tui` | 785 passed |
  | `just test-parity` | 4314 passed on SQLite and Postgres (run alone, about 2 hours) |
  | `just demo P1-I2` | nine clauses pass on SQLite and Postgres |

- **Decisions this run:** ADR-0008 (owner decisions for Phase 1), ADR-0009 (authentication), ADR-0010 (module record
  storage, with two addenda), ADR-0011 (document control permissions, interim), ADR-0012 (class-aware stale pins,
  owner decision). Delegated approvals are in `docs/reports/APPROVALS.md`.
- **Nothing is running.** No supervisor, workflow or heartbeat routine is active; the hourly heartbeat was deleted.

## Open items for the owner
| Item | Where |
|---|---|
| Phase 0 screenshot tour: make one now, or open the Phase 1 tour with a Phase 0 recap | KICKOFF.md REPORTING (tour rule added 2026-10-13) |
| A document-controller role (ADR-0011 makes the controlling acts admin-only until then) | ADR-0011 |
| Confidentiality is recorded but not enforced; all signed-in people and agents read a project's documents and transmittals | ADR-0011 "Known limits" |
| Option C of the stale rule: an informational "newer revision in review" marker | ADR-0012 |
| Release gates and earlier human gates still open (front-door rate limiter, H1-H9 from Phase 0) | `docs/reports/PHASE-0.md` §6(a), `docs/reports/P1-I0.md` |

## Known flaky tests
- `tl-tui/tests/test_remote_client.py::test_the_next_good_call_reports_live_again` and
  `tl-api/tests/test_stream.py::test_mapped_errors_leave_the_connection_usable` time out under parallel or full-suite
  load and pass alone. Both are older tests; worth a robustness fix in P1-I3.

## How to resume
1. Read this file, `docs/reports/STATUS.md` and `docs/reports/P1-I2.md`.
2. Start the next run with `docs/build-spec/KICKOFF.md`, beginning at Phase 1 Increment 3 (derivation pipeline,
   `docs/build-spec/07-phase1-plan.md`). Keep about 3 agents active (L-P0-I8-O1); run `just test-parity` alone
   (L-P1-I1-10); run `uv sync --all-packages` in the main checkout after a new package lands.
3. At the Phase 1 exit, produce the screenshot tour from the increment reports' Showcase sections.
