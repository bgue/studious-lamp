---
name: subagent-throughput-process
description: Token-efficient way to run Throughline's multi-agent build - short-lived supervisors seeded from STATE.md, Haiku-first tickets, one deterministic test gate, capped mutation and review passes, a fable design check before any big plan is carried out, and the TL92 telegraph code for all agent-to-agent traffic. Load it before spawning or messaging a supervisor, reviewer or workflow, before planning an increment or phase, and when writing a relay or handoff.
---

# Subagent throughput process

This file is the single source of truth for how the build runs. `docs/build-spec/01-tiers.md`, `02-task-protocol.md`,
`04-gates.md`, `KICKOFF.md` and `SUPERVISOR-PROMPT.md` point here and do not repeat it; where an older line in them
disagrees, this file wins. The rationale and the before/after cost model are in `docs/build-spec/process-v2.md`.

Measured on Phase 1 (124 agent transcripts): supervisors used 93% of all input tokens (11.8 B). The cause is
context × calls: about 430 k tokens of context re-read on each of 1,200–2,400 tool calls per increment (P1-I4:
2,378 calls, 1.03 B). Test logs are not the cause; all tool output together is about 3 MB. Output tokens are
negligible (0.5 M). So the levers are, in order: **smaller contexts, fewer calls, fewer agents alive at once**.

## Rules

1. **Short-lived supervisors.** A supervisor lives for one relay round (at most 3 when the orchestrator has
   nothing to run between them). At the end of each round it rewrites `docs/tickets/<INC>/STATE.md` (format below,
   at most 150 lines) and commits it. The next round is a FRESH supervisor seeded from STATE.md, the plan README and
   the ticket table (`SUPERVISOR-PROMPT.md`). Never resume a supervisor whose context is past about 150 k tokens;
   a usage-limit restart is just the next round. A round reads the spec sections it is told, not the whole spec.
2. **Supervisors plan, they do not build.** Every piece that passes the Haiku-ability checklist (`01-tiers.md` §6)
   is a Haiku ticket; the checklist is run after the interface is in the tree, so read views, routes and client
   methods over existing command models, read tools, CLI read groups, fixtures from tables, `n_a` plugins, screens,
   actors, demo drivers and docs are Haiku work. A truly core piece (`01-tiers.md` §3 table: schema, module spec,
   access-worded commands, money, parsers, job kinds, engines, security) goes to a one-shot `builder` agent with a
   piece spec `docs/tickets/<INC>/S<n>-<slug>.md` (ticket anatomy, `kind: piece`), so it never enters the
   supervisor's context. The supervisor's own diff per round is ≤ 50 lines (registry lines, `just gen`, held tests).
   It reads diffs, reports and `.gate/summary.txt`, never source trees or logs. Target per increment: ≤ 5 pieces,
   10–20 tickets, 0 supervisor-built code.
3. **One test gate.**
   - `just gate [<base>]` / `just gate-pg [<base>]` (`dev/gate.sh`, being added; until it lands, `just check` plus
     the package suites the ticket names): parts run in sequence (check; unit tests of the packages the diff
     touches; `test-tui` if `tl-tui` is touched; parity of the touched directories if adapters or the ledger are
     touched), each part with its own `--basetemp` under the scratchpad, logs there, and `.gate/summary.txt` of
     at most 12 lines whose last line is `GATE: green|red`. `just gate --full` is the whole suite plus parity of
     the touched directories.
   - Inside the ticket workflow the gate is run by a Bash-only `gate-runner` agent between implement and review
     (the workflow runtime has no shell, so this is the deterministic step). A red gate goes back to the author
     once with the summary before any reviewer is spent.
   - Reviewers re-run nothing: they read the diff and the gate summary. Supervisors never run a suite.
   - The full gate runs once, at increment DONE, by the orchestrator. Parity runs only on the directories the
     increment touched; the whole parity suite is phase-exit work on dedicated time.
   - No polling: a part runs in the foreground with a long timeout, or in the background with the harness
     re-invoking on exit. A `sleep`-and-`grep` loop is a defect. Never delete `/tmp/pytest-of-root`. Never `pkill -f`.
4. **Capped checks.**
   - Mutation: one sentinel mutant (proves the baseline passes and the harness kills) plus at most 5 targeted
     mutants on the guards that matter (bounds, access words, hash checks), on core pieces only, run by the
     builder in its own worktree, reported in 3 lines. The 30–60-mutant sweep is a phase-exit activity on a quiet slot.
   - Security review: one fresh review per wave (per increment when the wave is one increment), at DONE while the
     full gate runs, scoped to the plan's `Sec` rows and the commit range `<trunk before wave>..<head>`, ≤ 450 k
     tokens, findings as `F<n> <HI|MD|LO> file:line`. Fixes are builder pieces or Haiku tickets, never supervisor
     edits. The re-check is a short re-run of the reviewer's own proofs on the fix commits only; for LO and MD
     fixes the orchestrator reads the diff instead.
5. **Reviewers by risk.** The ticket header carries `review: lite | full`.
   - `lite` (Haiku, `reviewer-lite`): pure-function, text, docs, fixture and loader-table tickets with a provided test.
   - `full` (Sonnet, `reviewer`): handlers, SQL, routes, access and security paths, screens, parsers, jobs; every piece.
   - Security reviews: the stronger tier. One reviewer per item, never per batch (a batch reviewer mixes diffs
     and loses the second look on the last one; the startup saved is ~5 k tokens).
6. **Concurrency: 3 slots.** At most 3 heavy agents alive: supervisor rounds, builders, security reviewers, and
   each ticket workflow counts as one. The steady state is one supervisor or builder + one workflow of 2–3
   tickets. Two increments in a wave alternate rounds; they do not add slots. Heavy test runs: at most 2 at once
   on the box (16 GB). This cap is what removed the usage-limit stalls (L-P0-I8-O1).
7. **Orchestrator does deterministic work itself.** Merges of passed branches (`git merge --no-ff`, worktree
   removal; a conflict goes to the supervisor round), `just check`, the full gate and the demo at DONE, STATUS and
   APPROVALS lines, pushes. It delegates judgement, not git: every code change, review, ticket and report is an
   agent's. It reads STATE.md, relay blocks and workflow outcome tables, never transcripts or logs.
8. **Fable check before big plans.** Before any big plan is implemented, a fable-tier agent (`plan-check`, spawned
   at the strongest tier available) reviews it for scope, seams, waves and token cost. Big means a phase plan, a
   fanout, a new process, a core-interface ADR, or anything over about 10 tickets. One short pass, findings in TL92
   (`4 PLANCHK <path> | F1 ... | 30`), written under `## Plan check` in the plan file. Implement only after each
   point is answered or explicitly waived there. A supervisor whose round-1 plan has more than about 10 tickets
   asks for it in the relay block (`4 PLANCHK`) instead of dispatching.
9. **Bespoke tools over agent loops.** When agents repeat a multi-call routine, script it, add a `just` recipe,
   and say so in STATE.md. Current and wanted tools:
   - `just gate` / `gate-pg`: the sequential test gate (`dev/gate.sh`). Being added.
   - `just tour <n>`: the screenshot walkthrough. Present.
   - `dev/state.sh <INC>`: STATE.md plus git state in at most 40 lines. Wanted: Appendix A1.
   - `dev/review-pack.sh <base> <branch>`: one-call review pack. Wanted: Appendix A2.
   - `dev/relay-lint`: validates a relay block and its TL92 fields. Wanted: Appendix A3.
10. **Brevity limits** (a reviewer may flag an overrun): relay prose ≤ 8 lines; STATE.md ≤ 150 lines; increment
    report ≤ 80 lines, written from STATE.md; ticket or piece report ≤ 60 lines with ≤ 5 decisive output lines per
    command; builder return ≤ 15 lines; learning ≤ 6 lines; orchestrator → supervisor message ≤ 20 lines (the
    outcome table only); ticket ≤ 3 k tokens with ≤ 20 k of context files, excerpts marked `(abridged)`.
11. **Read order and caching.** Every agent reads its definition, `AGENTS.md`, the spec sections it is told, then
    the file that changes every round (STATE.md, the ticket), in that order, so the stable prefix is cached across
    rounds and across the agents of a batch. Learnings are fetched by id (`grep -n -A6 <id>`), never the whole file.

## STATE.md format (at most 150 lines)

```
# <INC> STATE  r=<round> base=<sha> C=<checkpoint> ck=<0|1> gate=<pass|fail|n/a> wt=<worktree>
## BOARD   <id> <t|p> <todo|stg|disp|pass|mrg|abn|2s|gr|blk> <l|f> <sha|-> <note, ≤ 8 words>
## DEC     D<n> <date> <one line: what, why, where recorded>
## SEC     F<n> <HI|MD|LO> <fixed@sha|open> <one line>
## OPEN    Q<n> <question> needs <orch|owner|builder> raised <id>
## NEXT    1. ... (≤ 8 numbered lines)
## REFS    <where staged references, stubs and held tests live>
## TRAPS   <env traps seen this increment: OOM, tmp, pg down, timeouts ...>
```

Checkpoints `C<k>` are named in the phase plan per increment (C1 schema and spec merged; C2 commands and
registrations merged; C3 all tickets merged; C4 DONE). The board is the live ticket table; `README.md` keeps the
objective, demo and order of work and is written once.

## TL92: telegraph code for agent-to-agent traffic

All relays, handoffs, dispatch notes, review returns and agent-to-agent messages use TL92: telegraphic, no
articles or filler, one fact per token where possible, segments separated by ` | `, every message ends with `30`.
Messages addressed to the human owner stay plain English.

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 2 | blocker (BLOCKED state) | 31 | gate result follows |
| 4 | decision asked (what follows is the question) | 73 | ok, no action |
| 9 | security matter follows | 88 | increment done (DONE state): full gate and merge requested |
| 13 | understood, ack (opens an orchestrator message) | 95 | approval needed (human gate) |
| 19 | dispatch order follows (DISPATCH state) | 99 | stop condition |
| 25 | busy, retry later (usage limit) | 30 | end of message |

Abbreviations:
- **Results:** `P` pass, `F` fail, `ck0`/`ck1` `just check` exit, `g0`/`g1`/`g-` gate exit or not run, `n/m`
  passed/total, `sq` sqlite, `pg` postgres, `2a` both adapters.
- **Work:** `T05b` ticket, `S4` builder piece, `t`/`p` ticket or piece, `l`/`f` lite or full review, `@abc1234`
  commit, `st@` STATE.md commit, `r<n>` round, `C<k>` checkpoint, `mrg` merged, `stg` staged, `disp` dispatched,
  `abn` abandoned, `2s` two-strikes, `gr` gate red, `ge` gate environment failure, `blk` blocked, `esc` escalate,
  `fx` fix, `+t` test added, `dec` decision, `PLANCHK` fable check requested.
- **Severity:** `HI` / `MD` / `LO`, then `F<n>` finding.

Relay block (the last thing in every supervisor reply; `dev/relay-lint` checks it):
```
=== RELAY ===
19|88|2 <INC> r<n> base@<sha> ck<0|1> g<0|1|-> st@<sha> C<k>
<id> <repo-relative path> <branch> <t|p> <l|f>        (one line per dispatched item; none for 88 or 2)
95 <schema paths and ids | none>
9 <F<n> HI|MD|LO fx@sha +t ... | none>
4 <question | PLANCHK path | none>
REPORT <path | none>
NOTE <one line>
30
=== END ===
```

Example relay:
```
=== RELAY ===
19 P2-I1 r3 base@31e272f ck0 g0 st@9c1d2e4 C1
T04 docs/tickets/P2-I1/T04-ewp-mirror.md p2/i1-t04-ewp-mirror t l
S4 docs/tickets/P2-I1/S4-rollup.md p2/i1-s4-rollup p f
95 none
9 F1 HI fx@ab12cd3 +t
4 none
REPORT none
NOTE rollup needs T03 cmds mrg first: done r2
30
=== END ===
```

Example orchestrator to supervisor (the whole message):
```
13. T04 P@c09a578 44/46 2a ck0 mrg. S4 P@c45de16 83/83 2a mrg. 19 next: T06a T06b T07c. 9 F3 dec: reject scope mismatch. 30
```

Example workflow outcome line (one per item, returned by `ticket-batch-v2.js`):
```
T06a P@1f2e3d4 g0 l 1 | T06b 2s@5a6b7c8 g0 f 2 F1 F2 | S5 gr@9d8e7f6 g1 p 2
```

## Appendix A — bespoke tool briefs (Haiku tickets; one ticket each, `review: lite`)

Common rules: bash, `set -euo pipefail`, no network, no Python beyond `uv run` of what exists, exit 0 on
success, 1 on a finding, 2 on bad usage; every line of output ≤ 160 characters; a test file under
`dev/tests/` runs each script against a fixture git repository built in `tmp_path` and pins the exact output.

### A1 `dev/state.sh <INC> [<base>]` (≤ 40 lines of output; `just state <INC>`)

Inputs: increment id; optional base ref (default: the `base=` field of `docs/tickets/<INC>/STATE.md`, else the trunk).
Reads: STATE.md, `git log --oneline <base>..HEAD` of the increment branch, `git worktree list`, `git branch --list '<branch>-*'`.
Output, in order: (1) the STATE.md header line verbatim; (2) `BOARD` lines verbatim, at most 15 (`+n more` when cut);
(3) `LOG` commits since base, at most 10, `<sha7> <subject ≤ 60>`; (4) `WT` open worktrees under `/home/user/wt/`
whose branch starts with the increment branch, `<path> <branch> <head sha7> <clean|dirty>`; (5) `HEADS` ticket
branches not merged into the increment branch, `<branch> <sha7>`; (6) `NEXT` lines verbatim. A missing STATE.md
prints `STATE none` and exits 1. Total ≤ 40 lines, sections separated by a line with the section name only.
Acceptance: the test pins the output on a fixture with 2 tickets, 1 worktree, 3 commits.

### A2 `dev/review-pack.sh <base> <branch> [<ticket path>]` (≤ 60 lines; `just review-pack`)

Inputs: base ref, branch, optional ticket or piece spec path (default: found from the branch name through
`docs/tickets/<INC>/<id>-*.md`).
Output, in order: (1) `DIFFSTAT` of `git diff --stat <base>...<branch>`, at most 20 lines; (2) `SYMBOLS` changed
Python symbols: `def`/`class` names added, removed or whose body changed, `<file>:<name> <+|-|~>`, at most 20;
(3) `PATHS` every changed path not matched by the ticket's *Allowed paths* globs (`OK` when none; the report path
`docs/reports/<INC>/<id>.md` is always allowed); (4) `TESTS` for every path under *Tests to add*: `present|missing`,
and for every file under `docs/tickets/<INC>/provided/` named in the ticket: `cmp same|differs <target>`; (5)
`COMMITS` `<sha7> <subject>` since base, with `BAD-MSG` on any subject not matching `^<id>: ` and `MODEL-NAME` on
any body line outside the trailer that names a model; (6) `GATE` the last line of `.gate/summary.txt` on the
branch's worktree, or `g-`. Exit 1 if any PATHS, missing TESTS, `differs`, `BAD-MSG` or `MODEL-NAME` line was printed.
Acceptance: the test pins a pack for a fixture ticket with one out-of-boundary file and one differing provided test.

### A3 `dev/relay-lint [<file>]` (stdin by default; ≤ 10 lines; `just relay-lint`)

Input: a supervisor reply or a file containing one. Checks, in order, printing one `E<n> <line no> <reason>`
per failure: (1) exactly one `=== RELAY ===` … `=== END ===` block, and it is the last thing in the text;
(2) prose before the block ≤ 8 lines; (3) first line matches
`^(19|88|2) [A-Z0-9-]+ r[0-9]+ base@[0-9a-f]{7,} ck[01] g[01-] st@[0-9a-f]{7,} C[0-9]$`; (4) with `19`, at least one
item line `^[A-Z0-9a-z]+ docs/tickets/\S+ \S+ [tp] [lf]$` and every item path exists; with `88` or `2`, no item
lines; (5) exactly one line each of `95 `, `9 `, `4 `, `REPORT `, `NOTE `, in that order, each ≤ 160 characters;
with `88`, `REPORT` names an existing file; (6) the line before `=== END ===` is `30`; (7) no model name outside
the block's `NOTE`. Exit 0 and print `OK <state> <INC> r<n> <n items>` when clean. Acceptance: the test runs the
three example blocks above (clean) and six broken variants (one per rule) and pins the messages.
