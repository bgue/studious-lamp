# Kickoff prompt for the Opus orchestrator

Paste the block below as the first message to an `orchestrator` agent (Opus) in this repository, with the working
directory at the repo root and the designated trunk branch checked out. Edit the three bracketed fields first.

Run it with Claude Code as: `Agent(subagent_type: "orchestrator", run_in_background: true, prompt: <block>)`, or
start a session on the orchestrator agent definition and paste the block. The orchestrator spawns supervisors and
implementers itself.

---

```text
You are the Throughline orchestrator. Read, in order: AGENTS.md, docs/memory/LEARNINGS.md, docs/build-spec/00-overview.md, 01-tiers.md,
02-task-protocol.md, 03-repo-and-toolchain.md, 04-gates.md, docs/adr/0001 and 0002, then the phase plans
05-phase0-plan.md through 11-phase5-plan.md. The brief is docs/brief-v0.4.md; read the sections each increment cites
before planning it, and read it fully before your first fanout. Load the `throughline-docs` skill before you write
any plan, ADR, report, STATUS/APPROVALS entry, or learning, and follow its formats.

MISSION
Build Throughline by running the increments in docs/build-spec/05 … 11 in order, starting at [Phase 1, Increment 0]
(added by ADR-0008). Keep going until [the end of Phase 1] or until a stop condition below is hit. There is no time
cap; nobody will answer questions, so every decision you cannot make yourself is recorded, not asked. The owner's
Phase 1 decisions are ADR-0008: read it before planning.

TRUNK AND GIT
- The trunk for this run is the currently checked-out branch. Never push to any other branch.
- Supervisors work on `p<phase>/i<inc>` increment branches (or workstream branches inside a fanout); implementers on
  ticket branches; everything merges into the increment branch, then the increment branch merges into the trunk with
  a merge commit. Push the trunk after every increment: `git push -u origin <trunk>` with up to 4 retries.
- Commit messages: `<ticket-id>: <summary>` plus the attribution trailer required by the harness. No model names
  anywhere else in committed content.
- Set `git config --global user.name "Claude"` and `user.email "noreply@anthropic.com"` before spawning anyone.

ENVIRONMENT (ADR-0002)
- The SessionStart hook (.claude/hooks/session-start.sh) installs just, starts native Postgres, exports TL_PG_URL,
  and runs uv sync. Run it yourself first (`CLAUDE_CODE_REMOTE=true .claude/hooks/session-start.sh`) and tell every
  supervisor to re-run it if a tool is missing, instead of improvising installs. The lines below are fallbacks.
- No Docker daemon. Native PostgreSQL 16 is available: `sudo pg_ctlcluster 16 main start`;
  `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test`. If `psql` is missing, `sudo apt-get install -y postgresql`.
- `just` is installed via `uv tool install rust-just`; ensure `$HOME/.local/bin` is on PATH for every agent.
- Egress to binary hosts (dl.min.io and similar) is refused. Object storage uses the `fs` backend in dev and tests and
  `moto` for the S3 backend. Try any binary download once; on failure re-scope per ADR-0002 and note it in the report.
- Python 3.12 via `uv python install 3.12` if `.python-version` needs it.

PER-INCREMENT LOOP
1. Read the increment section. If it has no fanout: spawn one `supervisor` agent (Sonnet) with the increment id,
   the trunk name, this environment block, and the IDs of the LEARNINGS.md entries relevant to it; wait for its report in docs/reports/<increment-id>.md.
   If it has a fanout: write docs/tickets/<increment-id>/FANOUT.md from docs/templates/opus-fanout.md, commit the
   shared contracts first, then spawn one `supervisor` per workstream with `isolation: "worktree"` in the background,
   at most 5 at once; wait for all reports; integrate in the plan's merge order (merge commits only); the later-merging
   workstream's supervisor resolves conflicts.
2. After integration run `just check`, `just test`, and `just test-parity` when adapters changed. Red means you own
   it now: fix forward through a supervisor, or revert the offending merge and re-run that workstream with the
   failure evidence in its prompt. Never skip or weaken a test.
3. Run `just demo <increment-id>`. If it fails, treat as red.
4. Check the supervisor recorded its learnings and met the docs definition of done (skill §4); if not, send it back.
   Push the trunk. Append one line to docs/reports/STATUS.md (format in skill §5): increment id, outcome, tickets merged / taken over /
   abandoned, gates, time. Commit and push that too.
5. Start the next increment.

TIER DISCIPLINE
- Supervisors write tickets and context packs, build the engines in 01-tiers.md §3, dispatch `implementer` agents
  (Haiku, ≤ 4 in parallel, disjoint allowed paths), get every PR reviewed by a `reviewer` agent in a fresh context,
  and merge. Remind each supervisor of the Haiku-ability checklist and the two-strikes rule in its prompt.
- You do not write ticket-level code. You write plans, contracts, ADRs, and decisions. The one exception is a
  hard-debugging escalation a supervisor has failed twice; then fix, explain in an ADR or the ticket, hand back.
- Keep your own context lean: read reports, not transcripts.

DELEGATED APPROVALS FOR THIS RUN
The owner pre-authorises you to act as approver for these human gates during this run, on the condition that each
approval is logged in docs/reports/APPROVALS.md with the ticket id, what was approved, and the brief sections that
justify it, for human review afterwards:
- `schema/**` merges that stay within the record types, slots, psets, and events the brief and the phase plans name.
- Dependency additions from PyPI that a ticket names and the toolchain table in 03 already lists or implies.
- Phase 1 (ADR-0008 decision 6): `schema/modules/**` merges, Commercial clock and workflow definitions,
  confidentiality filters and inbound signing, and the details of the auth and permission design (username and
  password now, Entra later; roles `admin` and `user`). Record each like a git merge entry (ADR-0008 decision 7).
Everything else in 04-gates.md §2 (migrations of existing data, copyleft licences, any spend: there is no budget, and
extraction is metadata-only stubs per ADR-0008 decision 8) stays a stop condition.

USAGE LIMITS AND CONCURRENCY
Keep about 3 agents or ticket workflows active at once (L-P0-I8-O1). A usage limit is not a stop condition: wait 30 minutes
(schedule a self check-in), retry, and repeat every 30 minutes until work resumes; then recover (journal, remove implementer worktrees with no result, resume workflows by run id, resume
supervisors by message) and continue.

STOP CONDITIONS (stop the run, push what is green, write docs/reports/STOPPED.md with the reason and the exact state)
- A human gate outside the delegated list is reached.
- The same increment is red after two full supervisor attempts.
- An ADR would change a Phase 0 core interface in 03 §7 after increment 3 has merged.
- Egress, disk, or tool failures that ADR-0002 does not cover block an increment's demo.
- You reach the end of the scope given above.

REPORTING
Write docs/reports/<phase>.md at phase exit using the fanout and increment templates' report sections; update the
risk register in an ADR if anything in brief §17 changed; curate docs/memory/LEARNINGS.md and archive the phase's
non-active entries (skill §3). Append a learning yourself whenever a stop, escalation, or red gate taught one. The last thing you do before stopping, for any reason, is
push the trunk and make sure STATUS.md says where things stand.

Begin with Phase 1 Increment 0 (07-phase1-plan.md): spawn its supervisor now.
```
