# Build spec 06 — Phase index and cross-phase rules

| Phase | Plan | Increments | Exit (§16) |
|---|---|---|---|
| 0 Foundations | `05-phase0-plan.md` | 8 | Generic records in TUI/API/MCP, live updates, signed webhook, restore |
| 1 Information backbone | `07-phase1-plan.md` | 8 | PDF → derived → published with traceability, feed and webhook |
| 2 Execution planning and materials | `08-phase2-plan.md` | 6 | IWP issued with documents, materials, scaffold readiness |
| 3 Quality and piping | `09-phase3-plan.md` | 8 | Weld → NDE → test package → certificate; model overlay; inbound NDE |
| 4 Completions and turnover | `10-phase4-plan.md` | 3 | Subsystem MC certificate with snapshot and dossier |
| 5 Expansion | `11-phase5-plan.md` | 6 (outline) | v1 release checklist |

Total: 39 increments. At 10–25 implementer tickets per increment, Phases 0–4 are roughly 500–800 Haiku tickets,
40–60 Sonnet supervisor runs, and 25–35 Opus orchestrator calls (one per phase start, one per fanout increment,
one per phase exit, plus escalations).

## Cross-phase rules

1. **Schema first in every module increment.** Types, psets, file slots, expected links, spatial paths, merge
   policies, and settings keys are declared and merged (human gate) before handlers and screens are ticketed.
2. **Each module ships with simulator actors and a legacy mapping template** before its increment closes (§29.8).
3. **Correspondence domains, clocks, and contractual workflows** always carry a commercial or legal human gate.
4. **Environment constraints** in ADR-0002 apply to every phase: no Docker dependency, `fs` object store in tests,
   native Postgres for parity, no download retry loops.
5. **Phase order is fixed; increment order within a phase may be re-sequenced by the orchestrator** with an ADR when
   a dependency or a pilot's need justifies it.
6. **Phase exit is demonstrated on a simulated project** (§29.5) and, when available, on mirrored or loaded legacy
   data (§29.9). The orchestrator's phase report records both.
7. **Budget heuristic:** one supervisor per 2–3 record types; one orchestrator fanout per increment that has two or
   more workstreams; escalations beyond two per increment trigger a retro note.
