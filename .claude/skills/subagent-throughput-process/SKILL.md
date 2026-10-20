---
name: subagent-throughput-process
description: Token-efficient way to run Throughline's multi-agent build - short-lived supervisors seeded from STATE.md, Haiku-first tickets, one deterministic test gate, capped mutation and review passes, a fable design check before any big plan is carried out, and the TL92 telegraph code for all agent-to-agent traffic. Load it before spawning or messaging a supervisor, reviewer or workflow, before planning an increment or phase, and when writing a relay or handoff.
---

# Subagent throughput process

Measured on Phase 1 (124 agent transcripts): supervisors used 93% of all input tokens (11.8 B). The cause is
context × calls: about 430 k tokens of context re-read on each of 1,200-2,400 tool calls per increment.
Test logs are not the cause; all tool output together is about 3 MB. Output tokens are negligible.
So the levers are, in order: **smaller contexts, fewer calls, fewer agents alive at once**.

## Rules

1. **Short-lived supervisors.** A supervisor lives for one relay round, or at most 3 rounds. At the end of each
   round it writes `docs/tickets/<INC>/STATE.md` (format below, at most 150 lines) and commits it. The next round
   is a FRESH supervisor seeded from STATE.md, the plan README and the ticket table. Never resume a supervisor
   whose context is past about 150 k tokens.
2. **Supervisors plan, they do not build.** Every piece that passes the Haiku-ability checklist (01-tiers §6) is a
   Haiku ticket. A truly core piece (an engine, security, a cross-cutting seam) goes to a one-shot `builder` agent
   with a written brief, so it never enters the supervisor's context. The supervisor reads diffs and reports, not
   source trees.
3. **One test gate.**
   - Use `just gate [paths]` / `just gate-pg [paths]` (dev/gate.sh): parts run in sequence, each with its own
     basetemp, and the summary is 12 lines.
   - Supervisors never re-run a ticket's tests; the reviewer already did.
   - Run the full gate once, at increment DONE.
   - Parity runs only on the directories the increment touched.
   - Never delete `/tmp/pytest-of-root`. Never `pkill`.
4. **Capped checks.**
   - Mutation: one sentinel mutant plus at most 5 targeted mutants, on core pieces only.
   - Security review: one fresh review per increment, or per wave, with a scoped commit list. The re-check is
     a short re-run of the reviewer's own proofs, or the orchestrator reads the diff for LOW/MEDIUM fixes.
5. **Reviewers by risk.**
   - Haiku reviewer: pure-function, text, docs and loader-table tickets.
   - Sonnet reviewer: handlers, SQL, access and security paths.
   - Security reviews: the stronger tier.
6. **Concurrency.** At most 3 heavy agents alive: supervisors, builders, security reviewers. Ticket workflows
   count as one each. Heavy test runs: at most 2 at once on the box (16 GB).
7. **Orchestrator does deterministic work itself.** Merges of passed tickets, `just check`, gate runs, STATUS
   lines and pushes. It delegates judgement, not git.
8. **Fable check before big plans.** Before any big plan is implemented, a fable-tier agent reviews it for scope,
   seams, waves and token cost. Big means a phase plan, a fanout, a new process, a core-interface ADR, or
   anything over about 10 tickets. One short pass, with findings in TL92. Implement only after its points are
   answered or explicitly waived.
9. **Bespoke tools over agent loops.** When agents repeat a multi-call routine, script it, add a `just` recipe,
   and say so in STATE.md. Current and wanted tools:
   - `just gate` / `gate-pg`: the sequential test gate. Present.
   - `just tour <n>`: the screenshot walkthrough. Present.
   - `dev/state.sh <INC>`: STATE.md, `git log` since base, open worktrees and branch heads, in at most 40 lines.
     Wanted.
   - `dev/review-pack.sh <base> <branch>`: diffstat, changed symbols, test-copy `cmp` and Allowed-path check, so
     a reviewer starts from one call. Wanted.
   - `dev/relay-lint`: validates the relay block and its TL92 fields. Wanted.

## STATE.md format (at most 150 lines)

```
# <INC> STATE  base=<sha> ck=<0|1> gate=<pass|fail|n/a>
## BOARD   <ticket> <status: todo|stg|disp|pass|mrg|abn> <sha>
## DEC     D<n> <one line>
## SEC     F<n> <sev> <fixed@sha|open>
## NEXT    1. ... 2. ...
## REFS    <where staged references live>
## TRAPS   <env traps: OOM, tmp, pg down, ...>
```

## TL92: telegraph code for agent-to-agent traffic

All relays, handoffs, dispatch notes and agent-to-agent messages use TL92: telegraphic, no articles or filler,
one fact per token where possible. Messages addressed to the human owner stay plain English.

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 1 | wait / hold | 30 | done, end of message |
| 2 | urgent / blocker | 13 | understood, ack |
| 4 | where to go ahead? (asks for decision) | 19 | dispatch order follows |
| 9 | security matter | 31 | gate result follows |
| 25 | busy, retry later (usage limit) | 73 | ok, no action |
| 95 | approval needed (human gate) | 99 | stop condition |

Abbreviations:
- **Results:** `P` pass, `F` fail, `ck0`/`ck1` `just check` exit, `g0`/`g1` gate exit, `n/m` passed/total,
  `sq` sqlite, `pg` postgres, `2a` both adapters.
- **Work:** `T05b` ticket, `S4` supervisor piece, `@abc1234` commit, `mrg` merged, `stg` staged, `disp`
  dispatched, `abn` abandoned, `fx` fix.
- **Severity:** `HI` / `MD` / `LO`, then `F<n>` finding, `+t` test added, `dec` decision.

Example relay:
```
19 P1-I8 base@31e272f ck0 | T05a2 T07b disp | 9 F1HI F2HI fx@ab12cd3 +t, F3MD fx@.. | 95 none | 31 g0 sq 3409/3409 | 30
```

Example orchestrator to supervisor:
```
13. T05a2 P@c09a578 44/46 2a ck0. T07b P@c45de16 83/83 2a. mrg both. 19 next: T05a3 T05b. 9 F3 dec: reject scope mismatch. 30
```
