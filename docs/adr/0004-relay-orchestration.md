# ADR-0004 — Relay orchestration: only the top-level session spawns agents

Status: accepted
Date: 2026-10-09
Deciders: orchestrator (autonomous run), for owner review
Brief sections: §25.5; build spec `01-tiers.md` §3, §9

## Context
A capability probe showed that subagents in this harness cannot spawn subagents: a `supervisor` agent has no `Agent`
tool. The build spec assumed supervisors dispatch implementers and reviewers themselves.

## Decision
Keep the three tiers and their responsibilities; move only the *spawning* to the top-level session (the orchestrator):

1. The orchestrator spawns one supervisor per increment or workstream, in the background, and continues it with
   `SendMessage` (same agent, context intact) for each round.
2. A supervisor works in its own persistent worktree (`/home/user/wt/<inc>`, branch `p<n>/i<m>`). Each round it plans,
   writes tickets, builds supervisor-tier pieces, merges passed tickets, and ends its turn with exactly one block:
   `DISPATCH` (ready tickets: id, path, branch), `DONE` (report path), or `BLOCKED` (reason).
3. For each `DISPATCH`, the orchestrator runs the `ticket-batch` workflow (`.claude/workflows/ticket-batch.js`):
   per ticket, an `implementer` (its own worktree, ticket branch off the increment branch) → a fresh `reviewer`
   (detached worktree, re-runs checks) → on changes-requested one retry by a new implementer with the findings →
   re-review. A second changes-requested returns `two-strikes`, which the supervisor takes over.
4. The orchestrator sends the batch outcomes to the supervisor, which merges `pass` tickets (merge commits), takes
   over `two-strikes`, answers `blocked`/`escalate`, and returns the next block.
5. On `DONE`, the orchestrator merges the increment branch into the trunk, runs the gates and the demo, pushes, and
   updates `STATUS.md`.

## Consequences
- Tier economics are preserved: implementers still do ticket work; reviewers still have fresh context.
- Workflow concurrency is capped by CPUs (2 agents at a time in this container), so batches are slower than the
  "4 in parallel" in `01-tiers.md`; batches of up to 4 tickets remain the unit.
- Supervisors never wait on agents; they only work between relays, which keeps their context focused.
- The orchestrator's context grows with relays; it reads structured outcomes, never transcripts.

## Alternatives considered
| Option | Why not |
|---|---|
| Supervisors implement everything themselves | Loses the implementer tier the run exists to use |
| Remote sessions (`create_session`) per ticket | Separate containers, pushes per ticket, no shared worktrees; heavy and slow |
| Orchestrator writes tickets too | Burns the most expensive tier on supervisor work |
