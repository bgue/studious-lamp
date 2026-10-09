# ADR-0003 — Repo-native project memory, docs skill, and SessionStart hook

Status: accepted
Date: 2026-10-09
Deciders: repository owner
Brief sections: §25.2, §25.5, §29.1

## Context
A long unattended run (hours, many parallel agents in separate worktrees, an ephemeral container) needs three
things the build spec did not yet provide: memory of small lessons across sessions, consistent documentation
habits, and an environment that rebuilds itself after a container restart. External memory plugins (several
community "Engram" packages and hosted memory services) were considered.

## Decision
1. **Memory lives in git** as `docs/memory/LEARNINGS.md`: append-only entries with IDs, evidence, and status;
   `merge=union` so parallel workstreams append without conflicts; read by the orchestrator and supervisors at
   session start; never read directly by implementers (supervisors paste what a ticket needs); curated and archived
   by the orchestrator at each phase exit.
2. **A project skill, `throughline-docs`**, holds the rules for every doc type, the docs definition of done, the
   memory rules, and the run-log formats. Agents load it on demand, so it costs nothing until used.
3. **A SessionStart hook** (`.claude/hooks/session-start.sh`, registered in `.claude/settings.json`) installs `just`,
   installs and starts native PostgreSQL 16, creates `tl_test`, exports `PATH` and `TL_PG_URL`, runs `uv sync` once
   the workspace exists, and sets a git identity. It is synchronous, idempotent, and remote-only.

## Consequences
- No external memory service, OAuth, or egress is needed; memory survives container reclaim and is reviewable.
- Implementer context stays bounded: no automatic memory injection into the cheap tier.
- Supervisors carry a small extra duty per increment (record learnings, meet docs DoD), checked by the orchestrator.
- Session start is slower the first time (apt install of Postgres); warm starts take well under a second.

## Alternatives considered
| Option | Why not |
|---|---|
| Community "Engram" plugin with hooks on every tool call | Injects context into the implementer tier; not built for many concurrent writers; local store lost with the container; community beta |
| Hosted memory service (MCP over OAuth) | Needs an interactive sign-in an unattended run cannot do; egress may be refused; memory outside git is unreviewed |
| No memory beyond reports | Lessons get buried in reports and are rediscovered at cost |
