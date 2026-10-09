# ADR-0001 — Three-tier agent workflow (Opus orchestrates, Sonnet supervises, Haiku implements)

Status: accepted
Date: 2026-10-09
Deciders: repository owner
Brief sections: §25, §29.1, §16 ("AI in the loop", "Build the platform once")

## Context
The brief designs Throughline so that most surface area is generated from LinkML and most remaining work is bounded
handlers, projections, screens, and tests (§25.1). Model cost and capability differ by an order of magnitude between
tiers. Using one model for everything either overspends on mechanical work or under-delivers on engine design.

## Decision
Route work by kind, not by convenience:

- **Opus** (orchestrator) only for phase plans, fanouts of two or more workstreams, cross-workstream contracts, ADRs,
  and escalations a supervisor has failed twice. Target ≤ 5% of calls.
- **Sonnet** (supervisor) owns increments: plans, tickets, context packs, the engines listed in `01-tiers.md` §3,
  reviews (in a fresh context), integration, reports.
- **Haiku** (implementer) executes tickets that pass the Haiku-ability checklist (`01-tiers.md` §6): bounded paths,
  pasted interfaces, provided tests, ≤ 400 diff lines.
- Humans hold the gates in `04-gates.md` §2.

The build is ledgered in git: tickets, reports, verdicts, ADRs are files. Escalations are written before they are made.

## Consequences
- Supervisors spend most of their effort writing tickets and context packs; that is the intended cost.
- Interfaces are committed before fanouts, so early Phase 0 increments are sequential.
- Two-strikes routing prevents retry thrash at the cheap tier.
- Agent definitions in `.claude/agents/` encode the tiers for Claude Code; other harnesses map the same roles.

## Alternatives considered
| Option | Why not |
|---|---|
| One strong model for everything | Cost; no separation between author and reviewer context |
| Haiku everywhere with heavy retries | Engines (ledger transaction, schema compiler, workflow guards) need design judgement; retries do not supply it |
| Opus supervises each increment | Too expensive at 10–25 tickets per increment; supervision is mostly ticket writing and review |
