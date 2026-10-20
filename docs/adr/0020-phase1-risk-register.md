# ADR-0020 — Risk register after Phase 1

Status: accepted
Date: 2026-10-20
Deciders: orchestrator (autonomous run), for owner review
Brief sections: §17 (risks and open questions), §16 (Phase 1 exit), §18 (security)

## Context
KICKOFF asks for an ADR at each phase exit that records any change to the brief §17 register. ADR-0007 did this for Phase 0. Phase 1 changed it:
- it answered part of Q5 and Q6 (identity, roles, confidentiality) without making anything deployable;
- it built the extraction pipeline (R4) with stubbed content, the integration layer (R6), threads (R16), clocks (R11) and the module seam, none of them with a real customer or provider behind it;
- it found risks the register did not list: untrusted-file cost, side-channel leaks of hidden records, privilege escalation through generic and automation paths, last-writer-wins automation, and coupling through pinned lists.

## Decision
`docs/reports/RISKS.md` stays the register. It keeps the brief identifiers (R1–R17, Q1–Q18) and the build-run identifiers (X1 onward), and gains X24–X28. The brief stays unchanged, because only humans edit it. Phase 2 risks are ranked in `docs/build-spec/phase2-risks.md` (R-P2-1 to R-P2-20) and are carried into `RISKS.md` at the Phase 2 exit, not copied now. The rows below are the material changes.

| Item | Change | Evidence |
|---|---|---|
| Q5, identity and hosting | Partly answered: accounts, scrypt passwords, sessions, lockout, agent tokens and an Entra seam (ADR-0009). Deployment is still blocked on Entra ID, a front-door rate limiter and a penetration test. | ADR-0009, `docs/reports/PHASE-1.md` §6 |
| Q6, external parties | Partly mitigated for internal readers: classes `internal`, `restricted`, `privileged` are enforced on every read path (ADR-0016). No external accounts. | ADR-0016, `P1-I5.md` |
| X11, permission model | Partly mitigated: three roles, typed access words, a fail-closed controller list. No project roles, per-record lists or separation of duties. | ADR-0011, ADR-0013, P1-SEC1 |
| R4, extraction accuracy | Pipeline and review gate built; accuracy unmeasured because content extraction is a stub by owner decision. | ADR-0008 decision 8, `P1-I3.md`, `P1-I3-B.md` |
| R6, integration sprawl | Mitigated: registry with owners, kill switch, service actors, propose-by-default rules. | ADR-0017 |
| R16, threads | Partly mitigated: opt-in by setting, preview then confirm, agents only propose. | ADR-0018 |
| R11, contractual clocks | Built; the definitions are illustrative and await commercial or legal review. | ADR-0019, `APPROVALS.md` |
| X7, Postgres only in tests | Largely closed: every service and CLI group runs on both backends. Pool, LISTEN/NOTIFY and `query_db` remain. | `P1-I0-B.md` |
| X13, feedback loop | Worse: the suite takes 1–2 h and the whole parity suite does not fit a background run. Process v2 and `just gate` respond. | `STATUS.md`, `process-v2.md` |
| R12, X15, schema change and upgrade | Unchanged in substance: all changes additive and hand-approved. The classification gate is P1-I8 work; the orchestrator re-checks R12, R13, R14 and R17 after P1-I8 merges. | `PHASE-1.md` §8 |
| X24–X28 | New: untrusted-file cost, hidden-record side channels, privilege escalation through generic and automation paths, automation without conflict detection, pinned-list coupling. | `docs/reports/RISKS.md` §2 |
| R10, X1–X4, X17 | Updated with Phase 1 counts (14 HIGH, at least 61 MEDIUM found and fixed) and the process v2 response. | `PHASE-1.md` §5 |

## Consequences
- Contracts changed: none.
- Tickets re-issued: none.
- Gates affected: none. The human gates are collected in `docs/reports/PHASE-1.md` §6.
- Phase 2 starts from `docs/build-spec/phase2-risks.md`, whose R-P2-3 (workflow roles as a client claim) predates P1-SEC1; its wave-0 item becomes a verification.

## Alternatives considered
| Option | Why not |
|---|---|
| Edit brief §17 | The brief is human-owned; agents record divergence in ADRs. |
| Copy the Phase 2 risks into `RISKS.md` now | They are forecasts without Phase 2 evidence; the file would hold two registers. Cite and merge at the Phase 2 exit. |
| One ADR per changed row | Too many small ADRs. One ADR per phase exit keeps the history readable (ADR-0007). |
