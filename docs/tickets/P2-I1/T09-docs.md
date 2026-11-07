# P2-I1-T09 — Docs for the awp module: README, AGENTS.md, runbook

Status: ready (r14; T08 demo re-running, S7 and T14 merged 624dd86)
Tier: haiku
Review: lite
Labels: docs
Depends on: S7, T14 (merged)
Branch: `p2/i1-t09-docs`
Worktree: `/home/user/wt/i1/t09` (from `p2/i1` head)

## Goal
`tl-mod-awp` has a README and a current AGENTS.md, and `docs/runbooks/awp.md` tells an operator how to load a WBS, CWAs and a path, compensate and reload, run the rollup worker and read the five screens. Rules: `.claude/skills/throughline-docs/SKILL.md` §2 (purpose first, tables, copy-pasteable commands, ISO dates, no model names, no secrets).

## Interfaces (what to document; read it, do not retype from memory)
- Public interface of `tl_mod_awp`: record types, the 19 event names, command names with their access words, the load targets `awp_wbs` and `awp_cwa`, the rollup job and worker. Source: `packages/tl-modules/awp/src/tl_mod_awp/` (`__init__.py`, `module.py`) and the spec `docs/build-spec/specs/m3-wbs-cwp.md`.
- Commands: run `uv run tl awp --help` and each group's `--help` (cwp, package, wbs, cwa, path, report, rollup, worker). Give each verb once, with the access word the command needs.
- Screens: palette ids `cwps wbs cwas path packages` (keyless, `tl_tui/commands.py` APP_COMMANDS), plus the CWP detail (`details/awp`). One line each: what it shows, how to open it.
- MCP read tools: names and arguments from `packages/tl-mcp/src/tl_mcp/awp_tools.py`; note `propose_cwp` is a proposal, not a write.
- Load procedure: `tl load` with targets `awp_wbs` and `awp_cwa`, preview then apply; compensate and reload (a retired node can be reinstated, S7 / D58; a CWA reload has the same shape and is not yet handled, follow-up F7); rename on reload is not handled (F6). State both as known limits.

## Context (read these, nothing else)
- `packages/tl-modules/awp/AGENTS.md` (8 lines, extend it)
- `docs/templates/package-readme.md`, `docs/templates/runbook.md`
- `docs/build-spec/specs/m3-wbs-cwp.md` (sections on commands, targets, rollup)
- `packages/tl-mcp/src/tl_mcp/awp_tools.py`
- `docs/runbooks/legacy-load.md` (wording of the load steps)
- `docs/runbooks/README.md` (index: add one line)
may explore: the `--help` output of `tl awp`, `tl load`.

## Allowed paths
- `packages/tl-modules/awp/README.md` (create, under 150 lines)
- `packages/tl-modules/awp/AGENTS.md` (edit)
- `docs/runbooks/awp.md` (create)
- `docs/runbooks/README.md` (one added line: `- \`awp.md\` — load a WBS, CWAs and a path, compensate and reload, the rollup worker, the five screens (P2-I1).`)
- `docs/reports/P2-I1/T09.md` (create)

## Steps
1. README per `package-readme.md`: purpose, public interface table (names, commands with access words, targets, rollup job, screens and palette ids, MCP read tools), config, how to test, links to the spec and runbook.
2. AGENTS.md: keep existing rules, add package nevers seen in the tree (keys namespaced per type, hidden reads go through the viewer filter, events immutable, reinstate not delete).
3. Runbook per `runbook.md`: load WBS / CWA / path; compensate and reload; rollup worker (queue, run, `ran=1`); the screens; known limits F6 and F7.
4. Check every command you wrote with `--help` or by reading the source; do not invent flags.

## Acceptance
```
uv run tl awp --help
git diff --stat
grep -n -i -E "claude|opus|sonnet|haiku" packages/tl-modules/awp/README.md packages/tl-modules/awp/AGENTS.md docs/runbooks/awp.md
```
Expected: help prints the awp groups; the diff touches only the five Allowed paths; grep prints nothing. No test suite is run.

## Tests to add
None (docs only).

## Report requirements
`docs/reports/P2-I1/T09.md` (<= 60 lines): deviations first, the three command outputs (<= 5 lines each), any command you could not verify.

## Escalation triggers
- Stop and report *Blocked* if a command or access word cannot be confirmed from `--help` or the source, or a doc needs a code change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
