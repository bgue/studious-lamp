# Build spec 01 — Tier contracts

## 1. Summary table

| | Orchestrator (Opus) | Supervisor (Sonnet) | Implementer (Haiku) | Reviewer (Sonnet, fresh) |
|---|---|---|---|---|
| Input | Phase goal, brief, ADRs, latest reports, escalation | Increment or workstream section, fanout plan, brief sections | One ticket + its context files | One PR + its ticket |
| Output | Fanout plan, contracts, ADRs, escalation decisions, phase report | Increment plan, tickets, core-engine code, merged increment branch, increment report, demo script | Diff on the ticket branch + report | Verdict: pass / changes-requested / escalate |
| May write code | Only for a hard-debugging escalation | Yes: engines, interfaces, test scaffolds, and any ticket that fails the Haiku-ability checklist | Yes: inside *Allowed paths* only | No |
| May change `schema/**` | Yes, as a schema ticket with human approver | Yes, as a schema ticket with human approver | No | No |
| May merge | Workstream integration branches | Implementer PRs after a pass verdict | Never | Never |
| Escalates to | Human | Orchestrator, then human | Supervisor | Supervisor |
| Context size target | Full brief + plans + reports | Increment plan + cited brief sections + interfaces (≤ ~120k tokens) | ≤ ~40k tokens | Ticket + diff (≤ ~60k tokens) |

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

1. **Increment plan** (`docs/templates/sonnet-increment.md`) at `docs/tickets/<increment-id>/README.md`: objective, demo, Sonnet-built pieces, ticket table with dependencies, order of work, risks, escalation triggers.
2. **Tickets** (`docs/templates/haiku-ticket.md`), one file per implementer task at `docs/tickets/<increment-id>/T<nn>-<slug>.md`.
3. **Sonnet-tier code**: interfaces, engines, generators, test scaffolds (tests that implementers must make pass). Built before dependent tickets are dispatched.
4. **Merged increment branch** with every gate green (`04-gates.md`).
5. **Increment report** (`docs/templates/sonnet-increment.md` §Report) at `docs/reports/<increment-id>.md`.
6. **Demo script** `dev/demos/<increment-id>.sh` wired to `just demo <increment-id>`.

**Working method**

1. Read the increment section and every brief section it cites. Write the increment plan.
2. Identify the Sonnet-tier pieces (engines, interfaces) and build them first, with tests. Get them reviewed (reviewer agent, then orchestrator or human for anything in the Sonnet-authored list below).
3. Write tickets. Run the Haiku-ability checklist (§6) on each. Split or keep anything that fails it.
4. Dispatch implementers: `Agent(subagent_type: "implementer", isolation: "worktree")`, one ticket each, at most four in parallel, only with disjoint *Allowed paths*.
5. For each returned PR: run `Agent(subagent_type: "reviewer")` in a fresh context. On `pass`, re-run `just check && just test` on the merged state, then merge to the increment branch. On `changes-requested`, send the findings back to the same implementer (`SendMessage`) once; on a second failure take the ticket over (two-strikes).
6. After the last merge: `just test-parity` where the increment touches adapters, `just test-tui` where it touches screens, the demo script, the report.

**Sonnet-authored by rule (never a Haiku ticket)**

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

Everything in this table also needs an orchestrator or human review before merge (`04-gates.md`).

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

## 5. Reviewer (Sonnet, fresh context)

- One PR, one ticket, one verdict. Never the author's context.
- Re-runs `just check` and the ticket's test command; does not trust pasted output alone.
- Findings cite `file:line` and the ticket line or `AGENTS.md` rule violated.
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

- **Worktrees.** Every supervisor and implementer runs in its own git worktree (`isolation: "worktree"`). Branch names: `<phase>/<inc>/<ticket>` (e.g. `p0/i1/t06-sqlite-ledger`); increment branch `p0/i1`; integration branch `p0/integration`; default branch `main`.
- **Merge order.** Set in the fanout plan from the dependency DAG. Later-merging workstream's supervisor resolves conflicts, never by rewriting another branch's history (merge commits only).
- **Interfaces first.** A fanout never starts before the shared interfaces are committed on the integration branch.
- **Parallelism limits.** ≤ 4 implementers per supervisor, ≤ 5 supervisors per fanout. More parallelism is paid for in integration time, not saved.
- **Reporting.** Supervisors write reports to `docs/reports/`; the orchestrator reads them rather than the transcripts.
