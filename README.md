# Throughline — build repository

Throughline is a general contractor's construction management suite: a Textual TUI on an
append-only ledger with realtime access, open APIs/MCP, and layered LinkML schemas.
The product and technical brief is `docs/brief-v0.4.md`; everything else cites it as `§n`.

This repository is built by a three-tier agent workflow:

| Tier | Model | Does |
|---|---|---|
| Orchestrator | Opus (occasional) | Phase plans, fanouts into workstreams, cross-cutting contracts, ADRs, hard escalations |
| Supervisor | Sonnet | Owns an increment or workstream: plans, writes tickets, builds core engines, reviews, integrates |
| Implementer | Haiku | Executes one bounded ticket at a time |

Humans hold the gates the brief already requires (§25.5): schema merges, migrations,
security, contractual workflows and clocks, spend.

Start here:

1. `AGENTS.md` — rules every agent follows.
2. `docs/build-spec/00-overview.md` — how the tiers work together.
3. `docs/build-spec/05-phase0-plan.md` through `11-phase5-plan.md` — every phase, increment by increment.
   `docs/build-spec/KICKOFF.md` is the prompt that starts an autonomous run.
4. `docs/templates/` — ticket, report, fanout, and ADR templates.
5. `docs/tickets/P0-I1/` — worked example tickets for the first increment.

Nothing under `packages/` exists yet. Phase 0 increment 1 creates it (`docs/build-spec/05-phase0-plan.md`).
