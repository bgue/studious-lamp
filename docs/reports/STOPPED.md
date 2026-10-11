# Run stopped: end of scope (Phase 0 complete)

The autonomous build run stopped on 2026-10-11 because it reached the end of the scope in `docs/build-spec/KICKOFF.md` ("until the end of Phase 0"). This was not a failure, and no stop condition other than end of scope fired.

## Where things stand
- **Trunk:** `claude/wizardly-allen-m2v96s`, pushed. Increments P0-I1 to P0-I8 are merged, with one line each in `docs/reports/STATUS.md`.
- **Gates on the final trunk:**

  | Gate | Result |
  |---|---|
  | `just check` | green |
  | `just test` | 5302 passed |
  | `just test-tui` | 608 passed |
  | `just test-parity` | 2166 passed on SQLite and Postgres |
  | `just demo P0-I8` | nine PASS lines, one per §16 exit clause |

- **Phase report:** `docs/reports/PHASE-0.md`. The audit against brief §16 is `docs/reports/PHASE-0-AUDIT.md`. The risk register is `docs/reports/RISKS.md` (ADR-0007).
- **Nothing is deployable.** Authentication, permissions and secret handling are dev stubs (ADR-0005), and those decisions are human gates.

## What needs the owner
The human gates are listed in `docs/reports/PHASE-0.md` §6(a), H1 to H9. In short:

| # | Gate |
|---|---|
| H1 | SQLite to Postgres migration (T99) |
| H2 | Drop the old feed index on existing databases |
| H3 | Secrets at rest |
| H4 | The real auth and permission model |
| H5 | Key custody, retention and object lock |
| H6 | Watch the first CI run on GitHub Actions; the workflow has never run |
| H7 | The locked-value clearing question |
| H8 | Review the delegated approvals in `docs/reports/APPROVALS.md` |
| H9 | Open brief questions that Phase 1 will meet |

Also review the MPL-2.0 allowance in ADR-0006, which the owner confirmed during the run.

## How to resume
1. Read `docs/reports/PHASE-0.md`, then decide the human gates that Phase 1 needs first, at least H4.
2. Set the scope in `docs/build-spec/KICKOFF.md` (for example "until the end of Phase 1") and start from `docs/build-spec/07-phase1-plan.md`.
3. Recommended for the next run:
   - keep about 3 active agents at a time (L-P0-I8-O1);
   - read the scope from KICKOFF.md at each phase boundary (L-P0-I8-O2).
