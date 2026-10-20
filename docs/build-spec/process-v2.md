# Build process v2 — token-efficient tiers

Status: proposed, 2026-10-20, from the measured Phase 0–1 run (124 agent transcripts). This note is the rationale
and the cost model. The **normative rules** live in one place, the `subagent-throughput-process` skill
(`.claude/skills/subagent-throughput-process/SKILL.md`): STATE.md format, TL92 code, caps, slots, the fable check,
and the tool briefs. Companion edits: `SUPERVISOR-PROMPT.md`, `01-tiers.md`, `02-task-protocol.md`, `04-gates.md`,
`KICKOFF.md`, `.claude/agents/*.md`, `.claude/workflows/ticket-batch-v2.js`, and `08-phase2-plan.md` (the first
plan written for this process). Where a line below and the skill differ, the skill wins.

## 1. Diagnosis

| Measured | Value | Reading |
|---|---|---|
| Supervisors | 37 agents, 11.8 B input tokens, 93% of all input | The cost is here and nowhere else |
| Supervisor calls per increment | 1,200–2,400; mean context per call ≈ 430 k | P1-I4: 2,378 calls, 1.03 B tokens |
| Reviewers (ticket + security) | 82 agents, 0.74 B (6%) | Security reviews 120–450 k each and found HIGH or MEDIUM issues in almost every increment |
| Output tokens, all agents | 0.5 M | Output is free; input is the bill |
| Tool-result bytes, all agents | ≈ 3 MB | Test logs are not the problem |
| Ticket workflow agents | 40–80 k each; almost every ticket passed first time | The cheap tier works |
| Usage-limit stalls | 5, of 2–25 h each, at 5–9 concurrent agents | Concurrency above 3 bought nothing |

The bill is **context size × call count**, and both are driven by one design choice: a supervisor is a long-lived
agent, resumed for 8–12 relay rounds plus restarts, that does everything the increment needs in one context.
Every tool call re-reads that context. At 430 k tokens a call, a thirty-step "start the suite in the background,
sleep, grep the log" poll loop costs 13 M tokens and produces nothing; a 60-mutant check costs 25 M; building a
core engine (200 calls) costs 90 M; and the context never shrinks, so every later round pays for every earlier
one. The four patterns that spent the run, in order: polling and re-running suites after environment failures;
building supervisor-tier pieces in the supervisor's own context; mutation checks of 30–60 mutants per piece;
resumption (each round starts where the last left off, including the restarts after usage limits).

Reviewers are a smaller problem of the same kind: they re-run the suite the implementer already ran, in a fresh
worktree with its own `uv sync`, for tickets that pass first time.

## 2. Target cost model (input tokens per single-supervisor increment, order of magnitude)

| Component | Before (measured) | After (target) | How |
|---|---|---|---|
| Supervisor rounds | 600–1,000 M (one agent, ~2,000 calls × ~430 k) | 60–110 M (10 rounds × ~100 calls × ~60–110 k) | Fresh agent per round seeded from `STATE.md`; the round plans, writes tickets and merges, nothing else |
| Core pieces (supervisor-tier) | inside the above | 60–120 M (3–5 builder agents × ~150–250 calls × ~100–150 k) | One-shot builder agents in their own context, discarded after the piece |
| Mutation checks | 20–40 M per piece | 1–3 M per piece | Sentinel + ≤ 5 targeted mutants, run by the builder, never by the supervisor |
| Test runs and polling | 100–300 M | 5–15 M | One `just gate` call per branch (gate-runner agent, Bash only); no polling; full suite once at DONE |
| Ticket reviewers | 5–9 M per ticket | 1.5–3 M per ticket | No re-runs; gate summary instead; Haiku reviewer for pure-function and text tickets |
| Security reviews | 2–4 passes, 120–450 k each, per increment | One review per wave + one re-check of the fix commits | Scoped by the `Sec` list and a diff range |
| Implementers | 10–20 M | unchanged | — |
| **Total** | **≈ 0.7–1.1 B** | **≈ 0.15–0.3 B** | about 3–5× fewer input tokens; wall clock similar or better because nothing waits on a 400 k context |

The usage-limit stalls were caused by concurrency, not by totals; the 3-slot rule in §3(f) is what removes them.

## 3. Changes

### (a) Short-lived supervisors seeded from `STATE.md`

One supervisor agent per relay round. It reads `docs/tickets/<INC>/STATE.md`, does the round, rewrites
`STATE.md`, commits, and ends with the relay block; the orchestrator spawns a fresh supervisor for the next round
with the same prompt. Nothing is ever "resumed": a usage-limit restart is just the next round. A round that has
nothing to dispatch and nothing to merge (for example it only waits on a builder piece) does not exist; the
orchestrator runs the builder and comes back.

`STATE.md` is the only handoff. Its format (header line with round, base, checkpoint, gate; then `BOARD`, `DEC`,
`SEC`, `OPEN`, `NEXT`, `REFS`, `TRAPS`; ≤ 150 lines) is defined in the skill. The board replaces the ticket table of
`README.md` as the live board; `README.md` keeps the objective, demo and order of work and is written once. The
increment report is produced from `STATE.md` at DONE and is ≤ 80 lines. The orchestrator merges `pass` branches
itself before spawning the next round (skill rule 7), so a round starts from a merged base and spends no calls on git.

### (b) Supervisor scope: plan, specify, merge; build nothing

The supervisor-tier rows of `01-tiers.md` §3 still exist (schema, access-worded commands, money, parsers, job
kinds, auth, numbering, sync), but *supervisor-tier* no longer means *supervisor-built*. Three routes:

1. **Haiku ticket** wherever the §6 checklist passes once the interface is in the tree. The Phase 1 evidence
   (L-P1-I3B-6, L-P1-I4-16, L-P1-I6: every ticket from a provided test passed first time) says the checklist is
   conservative, not generous. Routes and client methods for read views, report functions, read tools, CLI read
   groups, fixtures from tables, `n_a` plugins, screens, actors, demo drivers and docs are all Haiku work.
2. **Builder piece** for everything that is truly core: a one-shot Sonnet agent (`.claude/agents/builder.md`) that
   takes a piece spec `docs/tickets/<INC>/S<n>-<slug>.md` (same anatomy as a ticket: goal, pasted brief lines,
   interfaces, allowed paths, acceptance, tests), builds it on a piece branch with tests, runs the sentinel mutation
   check and `just gate`, commits, and returns a ≤ 15-line report. It goes through the same workflow as a ticket
   (`kind: piece`, always a full reviewer, then orchestrator or human sign-off per `04-gates.md` §3). The
   supervisor never sees the builder's context.
3. **Supervisor glue**, ≤ 50 diff lines per round: registry splat lines, `just gen`, merge commits, held tests
   restored, `STATE.md`. A supervisor that finds itself writing a function writes a piece spec instead.

The ratio to aim for per increment: ≤ 5 builder pieces, 10–20 Haiku tickets, 0 supervisor-built code.

### (c) One gate, run once, by a Bash-only agent

- `just gate [<base>]` (being added) is the only test entry point for agents: sequential parts (check; unit tests of
  the packages the diff touches; `test-tui` if `tl-tui` touched; parity of the touched directories if adapters or
  the ledger are touched), each part with its own `--basetemp`, logs under the scratchpad, and a ≤ 12-line
  `.gate/summary.txt` whose last line is `GATE: green|red`. `just gate --full` is the whole suite plus parity of the
  touched directories and runs once, at increment DONE, on the merged branch. Parity on untouched directories and the
  full parity suite are phase-exit work on dedicated time (R-P2-18).
- The gate runs in the workflow through a `gate-runner` agent (Haiku, Bash only, ~5 k tokens): the workflow API has no
  shell, so this is the nearest thing to a deterministic step. The supervisor never runs a suite; it reads summaries.
  Reviewers never re-run anything; they read the diff and the summary. A red gate goes back to the implementer once
  with the summary before any reviewer is spent.
- No polling. A gate part runs in the foreground with a long timeout, or in the background with the harness
  re-invoking on exit. A `sleep`-and-`grep` loop is a defect.
- Mutation checks: a **sentinel** (one mutant that must be killed, proving the baseline passes and the harness kills)
  plus **≤ 5 targeted mutants** on the guards that matter (bounds, access words, hash checks), run by the builder in
  the piece's own worktree, reported in three lines. The 30–60-mutant sweeps of P1-I5 and P1-I6 found real gaps but
  at 20–40 M tokens each; the sweep stays available as a phase-exit activity on a quiet slot.

### (d) The ticket workflow (`ticket-batch-v2.js`, beside the original)

- **Deterministic acceptance:** not possible inside the script (no filesystem or shell in the workflow runtime), so
  the v2 script inserts the `gate-runner` agent between implement and review, and again after a retry. Its
  structured result (`green`, `summary`, `failing`) is passed into the reviewer prompt.
- **Reviewer tier:** the ticket header gets `review: lite | full`. `lite` (Haiku, `reviewer-lite.md`) for tickets
  whose diff is pure functions with a provided test, fixtures, templates, reports, or docs; `full` (Sonnet) for
  anything touching routes, access, adapters, screens, parsers, or a `Sec` row. Builder pieces are always `full`.
- **One reviewer per item, not per batch.** Fresh context per PR is cheap (the startup cost is ~5 k) and keeps a
  finding attributable; a batch reviewer would mix three diffs in one context and lose the second-look property for
  the ticket it reads last. The workflow keeps one reviewer per item.
- Reviewers read the implementer's worktree read-only; no detached worktree, no second `uv sync` (2+ minutes and
  ~20 k tokens of output each, L-P1-I4-9).

### (e) Brevity limits (enforced by the prompts; a reviewer may flag an overrun as a finding)

| Artefact | Limit |
|---|---|
| Relay prose before the block | ≤ 8 lines |
| `STATE.md` | ≤ 150 lines |
| Increment report | ≤ 80 lines, generated from `STATE.md` |
| Ticket or piece report | ≤ 60 lines; ≤ 5 decisive output lines per command |
| Builder report (returned, not committed) | ≤ 15 lines |
| Learning entry | ≤ 6 lines |
| Orchestrator → supervisor round message | ≤ 20 lines: the batch outcome table and nothing else |
| Ticket context pack | ticket ≤ 3 k tokens, context files ≤ 20 k; excerpts marked `(abridged)` |

### (f) Concurrency: three slots, security once per wave

- **3 slots**, counted in agents: a supervisor round, a builder, a gate-runner, a reviewer and a security review are
  one slot each; a batch of N implementers is N slots while implementing and N while reviewing. The steady state is
  one supervisor or builder round + a batch of 2, or a batch of 3. Two increments in a wave alternate rounds; they
  do not add slots. The run never exceeds 3; this is the rule that removed the usage-limit stalls (L-P0-I8-O1).
- **Security review once per wave** (per increment when the wave is one increment), in a fresh context, at the
  wave's DONE while the full gate runs: scoped to the union of the `Sec` rows and the diff range
  `<trunk before wave>..<merged head>`, ≤ 450 k tokens, findings as a numbered list with `file:line`. Fixes are
  builder pieces (not supervisor edits); one re-check reads only the fix commits. Security reviews stay because they
  found HIGH or MEDIUM issues in almost every increment; what changes is that they run once per wave with a named
  scope instead of two to four passes per workstream.
- A usage limit is a pause of the orchestrator only; nothing is resumed afterwards, the next round starts from
  `STATE.md` and the workflow journal.

### (g) The orchestrator: relay, merge, record; never fix

Directly (deterministic work, skill rule 7): spawn supervisor rounds and workflows; merge `pass` branches into the
increment branch and the increment branch into the trunk (merge commits; a conflict goes to the supervisor round);
`just check`, `just gate --full` and the demo at DONE (one foreground call each, never a poll); `STATUS.md`,
`APPROVALS.md`, ADRs, fanout plans; read `STATE.md`, relay blocks and workflow outcome tables. Delegated
(judgement): every code change (builder or implementer), every review, every ticket, the increment report
(supervisor round from `STATE.md`), the phase tour (a ticket), and the gate inside a workflow (gate-runner, because
the workflow runtime has no shell). The orchestrator is itself long-lived; it reads structured outputs only and
keeps its own notes in `STATUS.md` so a restart reads two files.

### (g2) Owner rules folded in: the fable check and TL92

- **Fable check** (skill rule 8): a `plan-check` agent at the strongest tier reviews every big plan (phase plan,
  fanout, process change, core ADR, increment plan over ~10 tickets) before it is implemented; findings are answered
  or waived under `## Plan check` in the plan file. Cost: one agent of ~100–200 k tokens per big plan, against the
  200 M+ an increment costs when a plan is wrong (P1-I3's stubbed-then-rebuilt tickets, L-P1-I3-5). This file and
  `08-phase2-plan.md` v0.3 are the first two plans that need it.
- **TL92** (skill section "TL92"): every agent-to-agent message (relay blocks, orchestrator round messages,
  workflow outcome lines, review returns) is telegraph code; the owner's files stay plain English. The saving is
  small in tokens (relays were already short) but large in calls: a fixed grammar lets `dev/relay-lint` reject a
  malformed relay before an orchestrator round is spent on it, and the orchestrator's own context grows by ~10
  lines per round instead of a page.

### (h) Other levers

- **Prompt caching.** The prefix of every agent (agent definition, `AGENTS.md`, the tier section, `STATE.md`) is
  read first and in the same order each round, so the cached prefix is reused across rounds and across the agents of
  one batch; files that change every round (`STATE.md`) are read after the files that do not.
- **Read lists.** The supervisor prompt no longer lists `03-repo-and-toolchain.md`, ADR-0002 or the whole
  `LEARNINGS.md` (≈ 25 k tokens); it names the learning IDs and the supervisor `grep`s them. The orchestrator
  pastes the IDs; `AGENTS.md` carries the environment facts.
- **Logs.** `tail -n 20` and the gate summary, never a whole log into context; logs live in the scratchpad.
- **Agent definitions** stay under 25 lines each; the role contracts live in the spec, cited by section.
- **Ticket generation from references** (stub + provided test, L-P1-I3B-6) stays: it is why tickets pass first time.
- **Bespoke tools** (skill rule 9 and Appendix A): `dev/state.sh`, `dev/review-pack.sh`, `dev/relay-lint` turn three
  repeated multi-call routines (reading the board, assembling a review, checking a relay) into one call each. They
  are specified as `review: lite` Haiku tickets so they cost ~50 k tokens each to build.

## 4. What needs the owner

1. Approve the 3-slot cap as a hard rule (slower waves, no stalls).
2. Approve Haiku reviewers for `lite` tickets (a reviewer tier below Sonnet is new).
3. Approve the mutation cap (sentinel + 5) for core pieces; the 30–60-mutant sweep becomes a phase-exit activity.
4. Confirm `just gate` lands before Phase 2 wave 1; until then the gate-runner runs `just check` and the package
   suites the ticket names.
5. The word "fable" names a model tier in the skill and in `plan-check.md`; `AGENTS.md` rule 9 forbids model names in
   committed content. Either add "fable" to the allowed tier words (as Haiku, Sonnet and Opus are) or rename the
   check. The `plan-check` agent definition carries no `model:` line; the orchestrator passes the tier at spawn, so
   the alias to use is the owner's to name.
6. Build the three tool tickets (skill Appendix A) before Phase 2 wave 1, or accept that wave 1 runs without
   `relay-lint` and `review-pack`.
