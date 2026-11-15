# P2-X2-T06 — Runbook: agent grant checklist, stop switch, queue cap

Status: staged behind T05 (dispatch when T05 is merged; names below re-read from the merged tree, round 4)
Tier: haiku
kind: ticket
review: lite
Labels: docs
Depends on: T05
Branch: `p2/x2-t06-runbook`
Worktree: `/home/user/wt/x2/t06`

## Goal
`docs/runbooks/accounts-and-access.md` gains an "Agents: grant checklist, stop switch" section an admin can follow before a pilot agent files, and
`docs/runbooks/settings.md` documents `ai.agents.max_pending_per_project`. Docs only; every command is one that exists and is copied from the merged CLI.

## Brief references (pasted)
> P2-X2: an agent files only where it holds the module `user` word on the scope (explicit grant; a derived role from the account role does not count, D7); a core command (no module) needs at least one explicit module role
> on the scope (D2); without it the agent is refused as for a scope that does not exist (140), so a missing grant looks like a missing project. An admin grants with `GrantModuleRole` (`tl admin roles grant`); no data migration.
> The command's own word (controller, admin) is checked at accept, by a person. Order at filing: replay, filing check, stop check, queue cap, budget, precheck.
> Stop: `tl agent stop NAME [--reason TEXT]`, `tl agent resume NAME`, `tl agent stopped [--json]`; new filings refused, pending ones held, accept refused while stopped; events `Agent.Stopped`, `Agent.Resumed`; an agent never runs these.
> Cap: key `ai.agents.max_pending_per_project`, int, default 100, 1..100000, scopes platform, company, project, risk advanced; counts pending proposals in the queue (a project, or the company) that the filing agent may read;
> refused with the fixed text `this review queue is full; ask a reviewer to clear it, then file again` (API 429 `queue_full`); accepting or rejecting reopens the queue. `ai.agents.daily_proposals` 0 switches an agent's filing off; the cap cannot.

## Interfaces (verbatim commands, from the merged CLI and the existing runbook)
```
uv run tl admin user add triage --kind agent
uv run tl admin token issue triage --label pilot
uv run tl admin roles grant triage --project P1 --module documents --role user --reason "pilot agent files on P1 documents"
uv run tl admin roles effective triage --project P1
uv run tl agent stop triage --reason "runaway filing"
uv run tl agent stopped
uv run tl agent resume triage
uv run tl config set ai.agents.max_pending_per_project 50 --project P1 --reason "pilot queue"
```
(`--module '*'` grants every module; the role table in step 11 says an agent may hold `viewer` and `user`, never `superuser`.)

## Merged outputs for the `Expected:` lines (round 4, copied from the CLI source)
- `roles grant` prints `granted user on documents for project:P1 to triage` (a repeat: `already held: user on documents for project:P1 to triage`); options are `--project`, `--module`, `--role`, `--reason`, all required.
- `roles effective triage --project P1` prints one line per module, `<module>  <roles or ->  <source>`; the source for an agent must read `granted` (or `granted_all_modules` after `--module '*'`); `derived` is not enough (D7).
- `agent stop` prints `stopped agent:triage`; `agent resume` prints `resumed agent:triage`; `agent stopped` prints `agent:triage  since <ts>  by <actor>  held N  <reason or ->` or `none stopped`; `--json` gives a list.
- `config set` prints `set`, `scheduled` or `unchanged` with the key, the layer and the value; the cap is `risk: advanced`, so `--reason` is required.
- Numbering: the last numbered step in `accounts-and-access.md` is 14 (revoke a grant), so the new steps are 15 to 21. A step is a command and its `Expected:` line; keep the section under about 45 lines.
- Gate paths exist: `tests/ci/test_ci_workflow.py`, `tests/tools/test_relay_lint.py` (run `just gate tests/ci tests/tools/test_relay_lint.py`).

## Context (read these, nothing else)
- `docs/runbooks/accounts-and-access.md` (lines 1-45 and 60-135) and `docs/runbooks/settings.md` (lines 20-45 and 83-90)
- `docs/tickets/P2-X2/README.md` and `docs/tickets/P2-X2/STATE.md` (decisions D2, D6, D7)
- `.claude/skills/throughline-docs/SKILL.md` (runbook shape)
may explore: `docs/runbooks/api-retries.md` (how X1 words a setting and its refusal)

## Allowed paths
- `docs/runbooks/accounts-and-access.md`, `docs/runbooks/settings.md`
- `docs/reports/P2-X2/T06.md` (create)

## Steps
1. In `accounts-and-access.md`, after "Module roles" and before "What a grant does not change", add `### Agents: grant checklist and stop switch` with numbered steps continuing the runbook's numbering (the next number after the
   last step that exists; check) and an `Expected:` line after every command, in the runbook's own style:
   a. create the agent and issue its token; b. list the modules and projects it will file in; c. grant `user` per project and module (or `--module '*'`) with a reason; d. check with `roles effective` that the source reads
   `granted` (a `derived` source is not enough for an agent); e. what a missing grant looks like (the agent is told the scope is unknown; look at the grants, not the project); f. stop, list and resume, with what
   each does and that accept is refused while stopped; g. the queue cap and where to set it (link to settings.md).
2. Add to "What a grant does not change": a grant gives filing only; accepting still needs the person's own word. Add to Roll back: `tl agent stop` first, then revoke the grant.
3. In `settings.md`, add one short subsection "Agent limits" (after the schedule step or in Related, where the runbook keeps key notes) naming `ai.agents.max_pending_per_project` and `ai.agents.daily_proposals` with the facts above. Do not
   invent values or commands not listed under Interfaces.
4. Links to the files only; no model names; no TUI claims beyond "the accounts screen (`F10`) shows an agent's Filing line and held count" (T03).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate tests/ci tests/tools/test_relay_lint.py
```
Expected: `just check` clean (format, links if checked); gate passes. Every command in the new section was run or is copied from `tl agent --help`, `tl admin roles --help` and `tl config set --help` output pasted in the report (<= 5 lines each).

## Report requirements
Standard report plus: the step numbers added, the help output lines used, and one line confirming no command appears that the CLI does not have.

## Escalation triggers
Stop and write *Blocked* if a command above is not in the merged CLI; if the merged cap text or setting differs from the brief references.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
