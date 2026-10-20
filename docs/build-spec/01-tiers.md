# Build spec 01 — Tier contracts

> **Process v2 (2026-10-20).** The operating rules (short-lived supervisor rounds, builder pieces, the single test
> gate, capped checks, reviewer tiers, the 3-slot cap, the fable plan check, STATE.md and TL92) are defined once in
> the `subagent-throughput-process` skill (`.claude/skills/subagent-throughput-process/SKILL.md`), rationale in
> `process-v2.md`. This file keeps the role contracts; where a line here disagrees with the skill, the skill wins.

## 1. Summary table

| | Orchestrator (Opus) | Supervisor (Sonnet) | Implementer (Haiku) | Reviewer (Sonnet, fresh) |
|---|---|---|---|---|
| Input | Phase goal, brief, ADRs, latest reports, escalation | Increment or workstream section, fanout plan, brief sections | One ticket + its context files | One PR + its ticket |
| Output | Fanout plan, contracts, ADRs, escalation decisions, phase report | Increment plan, tickets, core-engine code, merged increment branch, increment report, demo script | Diff on the ticket branch + report | Verdict: pass / changes-requested / escalate |
| May write code | Only for a hard-debugging escalation | ≤ 50 diff lines of glue per round (registry lines, `just gen`, held tests); everything else is a piece spec for a **builder** (Sonnet, one-shot, `.claude/agents/builder.md`) or a Haiku ticket | Yes: inside *Allowed paths* only | No |
| May change `schema/**` | Yes, as a schema ticket with human approver | Yes, as a schema ticket with human approver | No | No |
| May merge | Workstream integration branches | Implementer PRs after a pass verdict | Never | Never |
| Escalates to | Human | Orchestrator, then human | Supervisor | Supervisor |
| Context size target | Full brief + plans + reports | One round: STATE.md + the spec sections named in the prompt (≤ ~60k tokens at start, never resumed past ~150k) | ≤ ~40k tokens | Ticket + diff + gate summary (≤ ~40k tokens; `lite` ≤ ~20k) |

Two further hats: **builder** (Sonnet, one-shot: builds one supervisor-tier piece from a piece spec, with tests, the
sentinel mutation check and the gate, then returns ≤ 15 lines) and **gate-runner** (Haiku, Bash only: runs `just gate`
once on a branch and returns the summary). A **plan-check** agent at the strongest tier reviews big plans (skill rule 8).

## 2. Orchestrator (Opus)

**When invoked**

- Phase start: produce the phase plan and first fanout.
- Any fanout of two or more workstreams.
- A supervisor escalation (schema-semantics question, cross-workstream contract change, or two failed attempts).
- Schema change classified `constraining` or `breaking` (§27.5) that touches more than one module.
- Phase exit: integration check, retro, risk register update.

**Deliverables**

1. **Fanout plan** (`docs/templates/opus-fanout.md`) saved as `docs/tickets/<phase>-<inc>/FANOUT.md`: workstreams, owner supervisor per workstream, interfaces each workstream provides and consumes (pasted as Python Protocols or LinkML fragments), merge order, integration branch, conflict owner, human gates named, exit criteria.
2. **Contracts**: any interface two workstreams share is written into `03-repo-and-toolchain.md` §7 (or the module's own `INTERFACES.md`) before supervisors start, so no supervisor invents it.
3. **ADRs** (`docs/templates/adr.md`) for every decision that changes a contract, an event schema, an adapter boundary, or the phase sequence.
4. **Escalation decisions** written back into the raising ticket under *Decision*, with the ADR reference if one was needed.
5. **Phase report** in `docs/reports/<phase>.md`: exit criteria status, what slipped, risk register deltas, next fanout.

**Rules**

- Decompose until each workstream is ownable by one supervisor in one worktree with explicit interfaces to the others. If a workstream still needs cross-talk to progress, split differently.
- Prefer sequential increments over wide fanouts when interfaces are not yet stable (Phase 0 increments 1–3 are sequential for this reason).
- Never approve a human gate. Name the gate and who approves it.
- Spend: the orchestrator is the most expensive tier. Do not use it to poll, to review implementer PRs, or to write tickets. Those are supervisor work.

**Mechanics (Claude Code)**

- Spawn supervisors with `Agent(subagent_type: "supervisor", isolation: "worktree", run_in_background: true)`, one per workstream, each given the path of its workstream section in the fanout plan.
- Collect increment reports from `docs/reports/`, then integrate in the merge order of the plan.
- For a deterministic review pipeline across many PRs, the `Workflow` tool may be used when the user has opted in; otherwise sequential `Agent` calls.

## 3. Supervisor (Sonnet)

**Owns** one increment (`05-phase0-plan.md`) or one workstream of a fanout, from plan to merged, green, demoed, and reported.

**Deliverables**

1. **Increment plan** (`docs/templates/sonnet-increment.md`) at `docs/tickets/<increment-id>/README.md`: objective, demo, builder pieces, ticket table with dependencies, order of work, risks, escalation triggers. Written once; the live board is `STATE.md`.
2. **Tickets** (`docs/templates/haiku-ticket.md`), one file per implementer task at `docs/tickets/<increment-id>/T<nn>-<slug>.md`, header field `review: lite | full`.
3. **Piece specs** `docs/tickets/<increment-id>/S<n>-<slug>.md` (ticket anatomy, `kind: piece`) for every supervisor-tier piece (the table below): interfaces, provided tests or test names, the guards the sentinel and targeted mutants must cover. Built by a `builder` agent before dependent tickets are dispatched.
4. **`STATE.md`** rewritten and committed at the end of every round (skill format, ≤ 150 lines).
5. **Increment report** (≤ 80 lines, from `STATE.md`) at `docs/reports/<increment-id>.md`, written in the DONE round.
6. **Demo clause list** in the plan; the demo script `dev/demos/<increment-id>.sh` is a Haiku ticket from it.

**Working method (one round per agent; skill rules 1, 2, 7, 8)**

1. Round 1: read the increment section and every brief section it cites. Write the plan, the first piece specs and `STATE.md`. More than about 10 tickets: ask for the plan check (`4 PLANCHK`) and dispatch in round 2.
2. Every round: verify the board against `git log` (the orchestrator merged the `P` items); decide each `2s`, `gr`, `blk`, `esc` item (re-spec, split, escalate); write the next batch of 2–3 items with disjoint *Allowed paths* and all dependencies merged; run the Haiku-ability checklist (§6) on each ticket; commit the provided tests, stubs and interfaces; rewrite `STATE.md`; end with the TL92 relay block.
3. Never: build a piece, run a suite or a mutation check, merge, read a log, or continue past the relay block.
4. The DONE round (after the orchestrator's `31` full-gate and `9` security results): report, learnings, README and `AGENTS.md` updates, `88` with `REPORT`.

**Supervisor-tier by rule (never a Haiku ticket; built by a `builder` from a piece spec)**

| Area | Why |
|---|---|
| Ledger append + inline projector transaction, hash chain integration | Correctness of the whole system rests on it (§5) |
| Current-state DDL generator core (LinkML → DDL diff) | Cross-dialect, generated-code policy (§5.4) |
| Effective-schema compiler, package merge, conformance rules | Schema semantics (§27.3) |
| Workflow engine evaluation (guards, required psets/links) | Contractual consequences (§8, M10) |
| Numbering allocator (sequence, gap-free, reserved ranges) | Concurrency (§8, Q7) |
| Query-language parser and SQL compiler | Shared by TUI, API, MCP, rules (§10.2, §18.2) |
| Auth, RBAC/ABAC, confidentiality filters | Security (§8) |
| Sync and merge engine, merge policies | §22 |
| Webhook signing, outbox delivery ordering | §18.4 |
| Any migration or data-conversion job | §24.2, §27.5 |

Everything in this table also needs a `full` reviewer and then an orchestrator or human sign-off before merge
(`04-gates.md` §3). Being in this table makes a piece *builder* work, not supervisor work: the supervisor writes the
spec, the builder writes the code. A piece other tickets cannot be tested without is a piece, not a stub (L-P1-I3-5).

**Escalation triggers** (write under *Blocked* in the increment plan, then call the orchestrator)

- An interface another workstream consumes must change.
- The brief is ambiguous on schema semantics, confidentiality, or merge policy and the choice is not reversible.
- The same engine failed its gates twice under the supervisor.
- A ticket would require touching more than one package's public interface.

## 4. Implementer (Haiku)

**Operating rules**

1. Read `AGENTS.md`, then the ticket, then only the files in the ticket's *Context* list. Do not browse the repo beyond that unless the ticket says `may explore: <paths>`.
2. Work on the ticket's branch inside the worktree given. Write only inside *Allowed paths*.
3. Implement exactly the interfaces pasted in the ticket. If the pasted interface and the repo disagree, stop and report under *Blocked*; do not reconcile them yourself.
4. Add the tests the ticket names in the paths it names. Run every *Acceptance* command. Keep the output.
5. Commit as `<ticket-id>: <imperative summary>`.
6. Return the report (`docs/templates/haiku-report.md`): deviations first, then commands and outputs, then open questions.

**Stop conditions** (return with *Blocked* rather than guessing)

- A needed file is not in the context list and the ticket does not allow exploring.
- An acceptance command fails for a reason outside *Allowed paths*.
- The ticket asks for something `AGENTS.md` forbids.
- Two attempts at the same failing test have not passed it.

**Start checklist** (first lines of the report echo these)

- Ticket ID and branch.
- Allowed paths acknowledged.
- Commands to run acknowledged.

## 5. Reviewer (fresh context; `full` is Sonnet, `lite` is Haiku)

- One branch, one ticket, one verdict. Never the author's context. One reviewer per item, never per batch.
- Re-runs nothing: the `gate-runner` ran `just gate` on the branch before the review, independently of the author,
  and the reviewer reads its summary. A summary that does not cover a touched package is a finding, not a re-run.
- `review: lite` (Haiku) for pure-function, text, docs, fixture and loader-table tickets with a provided test; it
  returns `escalate` ("needs a full review") when the diff touches a route, an access word, an adapter, a screen,
  a parser or a job. `full` (Sonnet) for everything else and for every piece.
- Findings cite `file:line` and the ticket line or `AGENTS.md` rule violated, in TL92 when returned to the orchestrator.
- `escalate` when the diff exposes a question the ticket cannot answer (interface mismatch, missing spec).
- Checklist in `02-task-protocol.md` §6.

## 6. Haiku-ability checklist

A ticket goes to an implementer only if every answer is **yes**:

1. Can it be completed by reading ≤ 6 files besides `AGENTS.md` and the ticket?
2. Are all interfaces it depends on already in the repo (not "to be designed")?
3. Does it have a test file to make pass, or acceptance commands with expected output?
4. Is the expected diff ≤ 400 lines across ≤ 5 files?
5. Does it avoid every row of the Sonnet-authored table (§3)?
6. Does it avoid `schema/**`, migrations, dependencies, and public-interface changes?
7. Can a reviewer verify it from the diff and the commands alone?

One **no** means the supervisor builds it or splits it until every part passes.

## 7. Suitability matrix

| Work type | Tier | Notes |
|---|---|---|
| Monorepo scaffolding, config files, `just` recipes, CI YAML | Implementer | From a precise file list |
| LinkML class or pset transcription from a brief table | Supervisor authors, implementer adds tests | Schema ticket with human approver |
| Generator wiring (run gen-pydantic, gen-json-schema; write outputs; drift check) | Implementer | |
| Generator logic (type mapping rules, DDL emission) | Supervisor core, implementer for per-type mapping functions with tests | |
| Event type definitions and payload models | Implementer | From the event catalog table in `03` §8 |
| Storage adapter against a Protocol with a provided parity test | Implementer | SQLite first; Postgres by implementer once parity suite exists |
| Command handler for one command against a known event | Implementer | |
| Projector handler for one event type into a generated table | Implementer | Projector engine is supervisor |
| Textual widget or screen from a sketch (§10.6) with snapshot test | Implementer | Logic stays in the client interface |
| CLI subcommand calling a service function | Implementer | |
| FastAPI route for one resource from generated models | Implementer | |
| MCP read tool wrapping one query | Implementer | |
| Webhook delivery worker loop | Implementer | Signing and ordering are supervisor |
| Report template (Jinja2/XLSX) with a fixture | Implementer | |
| Docs: module README, runbook from a template | Implementer | |
| Engines in §3 table | Supervisor | Orchestrator or human review |
| Workstream contracts, ADRs, phase plans | Orchestrator | |

## 8. Escalation ladder

```
Implementer ─(blocked, or 2 failed attempts)─► Supervisor
Supervisor  ─(contract change, schema semantics, 2 failed attempts)─► Orchestrator
Orchestrator ─(human gate, licence, spend, irreversible product decision)─► Human
```

Each step is written into the ticket or plan under *Blocked* before the call. The decision is written back under *Decision*. No escalation lives only in chat.

## 9. Fanout mechanics

> **Harness note (ADR-0004, process v2):** subagents cannot spawn subagents here. The orchestrator spawns every agent;
> supervisors return a TL92 relay block (`19` dispatch, `88` done, `2` blocked) and the orchestrator runs tickets and
> pieces through `.claude/workflows/ticket-batch-v2.js` (implement → gate → review → one retry). The orchestrator
> merges `P` branches itself and spawns a fresh supervisor for the next round. Where this section or §3 says a
> supervisor dispatches, reviews or merges, read it as "asks the orchestrator to".


- **Worktrees.** Every supervisor and implementer runs in its own git worktree (`isolation: "worktree"`). Branch names: `<phase>/<inc>-<ticket>` (e.g. `p0/i1-t06-sqlite-ledger`); increment branch `p0/i1`; integration branch `p0/integration`; default branch `main`.
- **Merge order.** Set in the fanout plan from the dependency DAG. Later-merging workstream's supervisor resolves conflicts, never by rewriting another branch's history (merge commits only).
- **Interfaces first.** A fanout never starts before the shared interfaces are committed on the integration branch.
- **Parallelism limits.** 3 slots in the whole run (skill rule 6): a supervisor round, a builder, a security review or a ticket workflow is one slot each; a workflow holds 2–3 items. Two workstreams of a fanout alternate rounds. More parallelism is paid for in usage-limit stalls and integration time, not saved.
- **Reporting.** Supervisors write reports to `docs/reports/`; the orchestrator reads them rather than the transcripts.
