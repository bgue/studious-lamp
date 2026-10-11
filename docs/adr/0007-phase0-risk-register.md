# ADR-0007 — Risk register after Phase 0

Status: accepted
Date: 2026-10-11
Deciders: orchestrator (autonomous run), for owner review
Brief sections: §17 (risks and open questions), §15 (targets), §16 (Phase 0 exit)

## Context
The KICKOFF asks the orchestrator to record, in an ADR, any change to the brief §17 risk register at phase exit. Phase 0 changed it:
- it measured risks R1 and R2;
- it confirmed that Q5 and Q6 (identity and permissions) block any deployment;
- it found risks the brief does not list. Among them:
  - a quadratic unique-index pattern on Postgres;
  - dev URLs that use the superuser;
  - type packages as untrusted input;
  - the youth of DuckLake;
  - shared-container flakiness and usage limits in agent-driven development.

## Decision
`docs/reports/RISKS.md` is the risk register from Phase 0 on. It keeps the brief's identifiers (R1–R17, Q1–Q18) and adds X1 onward for risks found during the build. Each row has a likelihood, impact, owner (human or agent) and status. The brief stays unchanged, because only humans edit it. Each later phase exit updates `RISKS.md` and records material changes in an ADR like this one.

Changes recorded at this exit:

| Item | Change | Evidence |
|---|---|---|
| R1, rebuild time | Measured. A 100k-record full rebuild (360,455 events) takes 332 s on SQLite and 2,299 s on Postgres, within "hours, not days". A quadratic feed index was fixed (D-S65). Shadow and per-module rebuild are not built. | `docs/reports/P0-I8-perf.md` |
| R2, pset query performance | Mitigated for filters on SQLite and Postgres through schema-declared indexes and set-based compilation. Link-count filters, pset sort and SQLite text search miss 150 ms and are recorded as deviations D1–D3. | `docs/reports/P0-I8-perf.md` |
| Q5, Q6, identity and permissions | Remain open, and now block deployment: ADR-0005 is a dev stub. | ADR-0005, `docs/reports/PHASE-0.md` |
| X1 onward | New build-run risks: superuser dev URLs (C4), package input (X22), DuckLake pinning, licences (ADR-0006), and agent-run concurrency and usage limits. | `docs/reports/RISKS.md` §2 |

## Consequences
- Contracts changed: none.
- Tickets re-issued: none.
- Gates affected: none. The human gates are collected in `docs/reports/PHASE-0.md` §6(a).

## Alternatives considered
| Option | Why not |
|---|---|
| Edit brief §17 | The brief is human-owned; agents record divergence in ADRs. |
| One ADR per risk | Too many small ADRs. A single register file with an ADR per phase exit keeps the history readable. |
