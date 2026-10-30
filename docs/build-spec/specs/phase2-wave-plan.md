# Phase 2 wave plan after the plan check (waves 0 and 1 in detail, the rest in outline)

Status: v0.1, 2026-10-30, planner tier. Replaces the wave 0 and wave 1 rows of `08-phase2-plan.md` §0.2; later waves
keep that table with the changes below. Inputs: `specs/wave0.md`, `m3-wbs-cwp.md` v0.2, `m4-materials.md` v0.2,
`web-client-i1.md`, owner decisions and answers 1–18, plan check F1–F11. Cap: 3 heavy agents (skill rule 6).

## 1. Waves

| Wave | Streams (one heavy agent each at a time) | Size | Starts when | Ends when |
|---|---|---|---|---|
| 0 | **P2-W0**: A roles (RM-S1–S4), B core (W0-B1, W0-B2, OC), C tickets and tools (A1–A3, OC-T1–T3, docs, demo); TA, TB tests at C3 | 7 pieces, 11 tickets | plan check on `wave0.md` answered; P2-Q10 answered or every gate the owner's | P2-W0 C4: demo `P2-W0` green on both adapters, `just tour` once |
| 1 | A **M3 P2-I1** ∥ B **M4 P2-I3** ∥ C **web P2-WEB1** | M3 4 pieces, 14 tickets; M4 4 pieces, 15 tickets; WEB1 4 pieces, 8 tickets + 6 twin tickets | P2-W0 C4 (WEB1 S1 may start earlier, see §2) | M3 and M4 at C4; WEB1 at C4 or carried into wave 2 (nothing depends on it) |
| 2 | **P2-I2** fanout: WS-A (IWP, constraints, sign-off) ∥ WS-B (readiness engine, checks, screens); C: web twins of I2 logs inside I2 | as `08-phase2-plan.md` I2, re-cut by the same plan-check rules | M3 on the trunk (M4 may still run; its check is found by entry point) | I2 C4; `materials_reserved` turns `ok` on a real IWP (moved from the M4 demo) |
| 3 | **P2-I4-A** ∥ **P2-I5**; C: **P2-WEB2** (create forms, incl. the receipt entry twin) if the owner wants it now | as 08 | I2 and M4 on the trunk; P2-Q1 (rules of credit) and P2-Q11 answered | both C4 |
| 4 | **P2-I4-B** ∥ **P2-I6 prep** (marts, report audit) | as 08 | I4-A on the trunk | both C4 |
| 5 | **P2-I6** alone; full parity suite and the phase mutation sweep on dedicated time; phase exit | as 08 | I4-B and I5 on the trunk | phase-exit demo: an IWP issued with documents, materials and scaffold checks, both adapters |

Rules carried into every wave: tests deferred to one tests ticket per increment at C3 (Sonnet), pieces leave reference,
stub and acceptance script; `just tour` once per increment at C4; Haiku for isolated tickets, Sonnet builders for
pieces, fewer and larger pieces (rule 12); security reviews are owner-optional (Sec rows recorded per increment),
except the web review below; each new module log ships its web twin in the same increment from wave 2 on (decision 3).

## 2. Where the web client fits (orchestrator's question)
- **WEB1 needs RM-S2 only** (roles in `allowed_actions` and `run_command`). RM-S2 merges in wave 0 round 2, and wave 0
  slot A goes idle in rounds 5–6 (`wave0.md` §7), so WEB1 S1 (foundation) may start there in slot A;
  the rest of WEB1 runs in wave 1 as stream C. This puts the web beside, not behind, the two module streams.
- **Why stream C and not a later wave:** WEB1 shares no module directory and no schema file with M3 or M4, and owner
  decision 3 wants new modules to ship terminal and web together; holding WEB1 to wave 2 would leave M3 and M4 logs
  without twins and push the twin debt into I2.
- **Twins of the wave-1 logs** (plan check F9, unconditional): 6 tickets added to WEB1 after its S4 and after the
  M3 and M4 C2 (their routes and client methods exist): M3 CWP register + CWA register; WBS tree + path; external
  packages; M4 stock + movement log; receipt log + MTO lines; item library + locations. Two logs per ticket, ≤ 4 files.
  The receipt entry form is a create form: WEB2 (answer 7: increment 1 is view and act).
- **Registries:** WEB1 S1–S2 touch `tl_api/{auth,app,commands}.py`, root `pyproject.toml`, `uv.lock`,
  `openapi.json`. WEB1 merges S1–S2 before M3 S4 and M4 S3 reach C2; M4 stays the wave-1 registry owner and merges
  last; the later side regenerates, never hand-merges (08 §0.3).
- **Security:** the web stays off in production until its security review passes (answer 8), so the WEB1 review of
  S1–S3 is the one review the plan schedules whatever the default; its timing (WEB1 C4) needs the owner's yes.
  Browsers: current and previous versions of Chrome, Edge, Firefox, Safari (answer 9).
- **Test deferral** applies to WEB1 too: its supervisor recasts `web-client-i1.md` §11 "Tests added" as acceptance
  scripts plus one tests ticket at C3 when writing piece specs.

## 3. Checkpoints and order inside wave 1
1. W0 C4 → M3 S2 (slot A) and M4 S1 (slot B) start together; both are schema pieces with a human gate, approved in
   one sitting. WEB1 continues in slot C.
2. M3 C2 (S4, S5, T10, T03a–b) and M4 C2 (S3, S4, T04a–b) → their screen and tool tickets go; WEB1 twin tickets go.
3. M3 critical path S2 → S3 → S4 → T10 → T03a → T03b → T05a → T05b/c → T11 → T08; M4 S1 → S2 → S3 → T04a → T04b →
   T06a → T06b → T06e → T11 → T09. Streams alternate builders and workflows inside their own slot.
4. M3 merges first (C4); the M4 demo needs it (plan check F10, clause 6); M4 merges last and regenerates pinned lists.
5. Wave 1 exit = M3 C4 + M4 C4; WEB1 C4 may follow inside wave 2 with its review.

## 4. Open items for the owner
P2-Q10 (who approves schema and permission merges); the WEB1 security review timing (answer 8); P2-Q4 A, P2-Q5 B,
P2-Q9 A confirmed as assumed; `awp.release.signoff_roles` default `[superuser]`; whether `RejectReceipt` is a
disposal (superuser) or a delivery refusal (user, as specified); whether WEB2 runs in wave 3 (slot C) or later.
Before wave 2: P2-Q6, P2-Q7, P2-Q8. Before wave 3: P2-Q1, P2-Q11, P2-Q13.
