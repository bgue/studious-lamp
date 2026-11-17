# Process v3: demo first, fewer handoffs (pilot on P2-FORMS)

Owner asked 2026-11-17 ("analyze the process ... extremely bureaucratic and slow"; "write the plan and pilot it
on forms"). Where this file and `.claude/skills/subagent-throughput-process/SKILL.md` disagree, this file wins
**for the pilot branch `p2/v3-forms` only**. After the pilot the owner decides: adopt, adjust or drop.

## 1. What went wrong (P2-IP: permits, inspections, QR)

| Symptom | Evidence |
|---|---|
| Paperwork outweighs code | PTW 24 tickets, 1,881 ticket lines for 5,576 source lines; IP 52 tickets, 25 reports |
| Handoffs, each a round trip | PTW demo: 4 dispatches, last block a one-line ruling (generator clock) |
| Problems found last | 85 s list read on the full demo project found only by the screenshot tour; gastest TypeError found only by the demo |
| Each module hand-wired 7+ times | CLI read, CLI write, API routes, API client, MCP tools, embedded client, TUI screens, fakes, walk pins, offline row, subject rows; each a ticket |
| Every module taxes every read | the per-row hidden-record check is a 105 KB statement (16 subject rows, two hops, forms draft chain) |
| Four branch levels | ticket, increment, ip-r3, ip-int, trunk, main |
| Gates longer than the box allows | full suite > 2 h on 4 cores; 30-min background cap; reruns for timeouts, restarts, clobbered logs |

Root causes: the process minimised tokens per call, not time to a working demo; assurance is per ticket
(gate + review + report) while realistic data, speed and the demo come last; the platform makes each module
re-declare itself on every surface.

## 2. The rules for the pilot

1. **Demo first.** A module's first unit is a thin vertical slice on the full demo project: the generator
   section, one write, one list, one record screen, and the module's demo script with timings. The demo script
   is the acceptance test of every later unit (each adds clauses; none may break one).
2. **Units, not tickets.** A unit is what one builder can finish in one sitting: 5 to 8 per module. Spec at
   most one page: goal, demo clause(s) it must make green, the area it may touch, the tests it adds. No context
   packs; the builder reads the code. The builder may change fixtures, the demo generator and demo scripts of
   its own module without asking.
3. **Tier by unit.** Builder tier by default; the cheapest tier only for mechanical units (docs, registrations,
   small scripts). The orchestrator writes specs; no supervisor rounds in the pilot.
4. **One review per unit**, full, fresh context. A security review only for units that touch confidentiality,
   access, or a public route; one wave review at DONE as before.
5. **Speed budget is a gate.** Every list read and every report of the module returns in under 1 s (median of
   5, as the restricted viewer `user:treyes` and a full viewer) on the full demo project (SQLite) —
   `tests/perf/test_budget.py` on a full demo ledger cached by the hash of the generator and the schema, built
   under a file lock with an atomic rename. It also caps the size of the hidden-record statement. A unit that
   breaks the budget is gate-red.
6. **Every module ships a basic report** (owner, 2026-11-17: "a basic report per module that provides that
   module's line-level data (e.g. RFIs or inspections)"): `tl report <module>` writes the module's line-level data (one row per
   record: RFIs, letters, documents, IWPs, constraints, requisitions, work orders, punch items, scaffolds,
   inspections, permits, QR codes, form submissions ...) as CSV or JSONL, columns = the module's log columns plus
   its key dates. Hidden records are left out exactly like missing ones. Part of every module's definition of done.
7. **Fast gate per unit:** `just gate-changed` = ruff and pyright on changed files, the tests of the touched
   packages, the confidentiality walk files (`tests/confidentiality/test_*walk*.py`, the twin channels and the
   hidden-equality tests), the module's demo on SQLite, the speed budget. A diff that touches adapters,
   `confidentiality.py` or a projection also runs `just gate-pg tests/confidentiality` with a per-test timeout. The whole suite runs
   at DONE (and nightly when the box is idle), never two heavy runs at once.
8. **Less ceremony.** Unit report at most 15 lines (what, demo output, deviations). A commit check
   (`dev/commit-check.sh`, also run by the gate) refuses model names outside trailers; reviewers do not flag
   formatting of commit subjects. The orchestrator makes fixes of at most 30 lines itself (rulings, renumbering,
   report fixes) and says so in the commit; never in confidentiality, access, routes or schema files, and the
   unit's reviewer (or the next unit's) reads each such diff. One board in `docs/tickets/P2-FORMS/STATE.md`, at most 60 lines.
9. **One integration branch.** Unit branches merge into `p2/v3-forms` (cut from `p2/ip-int`); it goes to trunk
   at DONE together with IP. No intermediate branches.
10. Kept unchanged: APPROVALS lines for schema and core-interface changes, hidden looks exactly like missing,
    additive events only, no paid model calls, trailers, DEFERRED rows, TL92 between agents, at most 3 heavy
    agents and 2 heavy test runs.

## 3. Pilot units

Platform units first (they serve every module), then forms. Base `p2/v3-forms` (cut from `p2/ip-int`, with
PERF1 merged; the IP release goes to trunk from this branch). Demo clauses keep the forms README numbering:
1–6 the slice and agents, 7 hidden looks missing on every forms read, 8 a draft is invisible, 9 web fill,
10 intake (signed-in).

| Wave | Unit | What | Tier | Review | Sec rows |
|---|---|---|---|---|---|
| 1 | P1 speed | Per-row hidden-record check made index-friendly, building on PERF1 (same rows for every viewer: differential test); `tests/perf/test_budget.py` on a cached full demo ledger | builder | full + security | hidden == missing; author exemption; two-hop chain |
| 1 | P0 report | `tl report <module>` + `reports` module hook (core interface: APPROVALS); forms, RFIs, correspondence, documents, and the existing awp/materials/scaffold exports wrapped | builder | full + security | export carries record text: hidden records absent, low-viewer output identical to a ledger without them |
| 1 | P2 tools | `just gate-changed` (with a lock for its heavy parts) and `dev/commit-check.sh` | cheapest | full (it chooses which tests run) | — |
| 2 | F1a slice | Forms generator section (T09), read routes (T04), `tl form` CLI (T05), forms report registration, every forms/intake client method and hook row (owns `tl_tui/client.py`, `embedded.py`, forms hooks, `MCP_ACTIONS` for the pilot), five-reader walk for its routes; demo clauses 1–3, 7, 8 | builder | full | walk proves 7 and 8 |
| 2 | P0b reports | `tl report` registrations for the remaining modules (tags, IWPs, CWPs, constraints, activities, requisitions, work orders, punch, inspections, permits, isolations, QR codes) | cheapest | lite | same test pattern as P0 |
| 3 | F1b TUI | Forms log and runner screen (T07) with its walk; demo clause 4 | builder | full | walk |
| 3 | F1s sources | Form sources for quality and permits (S3s): an inspection or a permit check filled through a form binding | builder | full + security | two modules; access words |
| 4 | F2 agents | MCP tools (T06), draft resume (T08), walks for both (T10); demo clauses 5–6 | builder | full | walk |
| 4 | F3 web | Web fill page (W2) and cards (B2–B4), walk for `/web/forms`; demo clause 9 | builder | full | walk |
| 4 | F4 intake | `tl intake` code issue/revoke, signed-in routes, ls/show/accept/reject/purge, TUI log (I01, I03r, I04, I05); demo clause 10, signed-in only | builder | full + security | no code hash, body or salt in any read |
| 5 | F5 done | Docs, runbook, tour shots, highlights page | cheapest | lite | — |

F2, F3 and F4 merge one after another (never in one round), because F1a owns the shared files they touch.
The owner-gated public route (S6), its anonymous walk (I06), the no-login demo (I07) and the poster label (I08)
stay out of the pilot (DEFERRED row). Wave review at DONE over `316c5a02..<p2/v3-forms head>` with the Sec rows
above. At most 3 heavy agents and 2 heavy test runs at once, as before.

Old forms tickets T04–T12, I01, I03r, I04, I05, W2, B2–B4, S3s are folded into these units; their files stay as
reference for the builders (excerpts, not context packs).

## 4. What we measure (pilot report, `docs/reports/P2-FORMS/V3-PILOT.md`)

Wall-clock from first dispatch to demo green; handoffs (dispatches + re-dispatches + rulings); tokens from the
workflow usage lines; late surprises (a defect found after its unit merged); lines of spec and report per line
of code. Compared with P2-PTW (24 tickets, 4 demo dispatches).

## Plan check

Planner-tier pass 2026-11-17, 12 findings; answers:
- F1 HI S3s needs a builder and security review -> accepted: unit F1s, wave 3, before F2/F3.
- F2 HI clauses 7 and 8 dropped -> accepted: kept in F1a; web = 9, intake = 10.
- F3 HI record text with only a full review -> accepted in part: a five-reader walk in the same unit as each
  surface (F1a, F1b, F2, F3, F4); security review added for P0 and kept for P1, F1s, F4; F1a–F3 rely on their
  walks, the full review and the wave review.
- F4 HI gate-changed drops gate-pg -> accepted: rule 7 runs gate-pg on confidentiality/adapter/projection diffs
  with a per-test timeout; walk files listed; P2 gets a full review.
- F5 HI P1 approval and PERF1 -> accepted: PERF1 is merged into `p2/v3-forms` with an APPROVALS line; P1 builds
  on it; the IP release goes to trunk from `p2/v3-forms`, so no separate landing on `p2/ip-int`; P1 adds its
  own APPROVALS line (owner asked for the pilot 2026-11-17) after its security review.
- F6 MD flaky budget and cache race -> accepted (rule 5).
- F7 MD shared files -> accepted: F1a owns them; F2/F3/F4 merge one after another.
- F8 MD waves and slots -> accepted: waves 1–5 in the table.
- F9 MD rule 6 has no owner citation; P0 too big -> accepted: owner quote in rule 6; P0 split into P0 and P0b.
- F10 MD orchestrator fixes unreviewed -> accepted (rule 8).
- F11 MD S6 blocks I06–I08; Q7; wave range -> accepted: out of the pilot, DEFERRED row; wave range set. Q7
  (clearance class for forms) goes to the owner; until answered the pilot keeps CR1's current rule.
- F12 LO cost; F1 too big -> accepted: F1 split into F1a and F1b; the full ledger is built once per generator
  hash, not per unit.
