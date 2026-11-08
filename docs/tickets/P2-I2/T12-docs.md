# P2-I2-T12 — Docs for IWPs, constraints and readiness

Status: staged (r10). Ready when T10b is merged.
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T10b (merged)
Branch: `p2/i2-t12-docs`
Worktree: harness-created under `/home/user/wt/i2/t12` (from `p2/i2` head)

## Goal
`tl-mod-awp` README and AGENTS.md cover IWPs, scope, sign-off, issue and readiness; `docs/runbooks/iwp-readiness.md` tells an operator how to build an IWP, read and clear constraints, read readiness, sign off and issue; a reference page lists the IWP, constraint and readiness read surfaces. Rules: `.claude/skills/throughline-docs/SKILL.md` §2 (purpose first, tables, copy-pasteable commands, ISO dates, no model names, no secrets).

## Interfaces (what to document; read it, do not retype from memory)
- Public interface of `tl_mod_awp` (new record types, events, commands with access words from `AWP_COMMANDS`), the core constraint commands (`tl_core.constraints`, ADR-0024), the readiness engine and checks (`tl_core.readiness`, `tl_mod_awp/readiness`, nine checks, D9), `IWP.Ready` webhook.
- Commands: `uv run tl awp --help`, `tl awp iwp --help`, `tl awp readiness --help`, `tl constraint --help`, `tl awp report --help` (six new reports). Each verb once with its access word.
- Screens and web pages: palette ids from `tl_tui/commands.py`, web paths from `packages/tl-web/README.md` (the TW1-TW3 pages); MCP IWP tools from `tl_mcp/awp_tools.py` (read tools; scope proposal is a proposal).
- Known limits, from `docs/tickets/P2-I2/STATE.md` OPEN and `docs/build-spec/DEFERRED.md`: Q1 hold-on-new-constraint rule, list-level counts follow-up (D33), WBS opt-in, agents hold no `core.constraint.*` word (D37).

## Context (read these, nothing else)
- `packages/tl-modules/awp/README.md`, `AGENTS.md`, `docs/runbooks/awp.md` (extend, do not rewrite), `docs/reference/awp.md`
- `docs/templates/package-readme.md`, `docs/templates/runbook.md`, `docs/runbooks/README.md`
- `docs/adr/0024-constraints-on-any-record.md` (decisions list only), `docs/reports/P2-I2/S3.md`, `S4.md`, `T10b.md`
may explore: the `--help` output named above.

## Allowed paths
- `packages/tl-modules/awp/README.md`, `packages/tl-modules/awp/AGENTS.md` (edit)
- `docs/runbooks/iwp-readiness.md` (create), `docs/runbooks/README.md` (one added line)
- `docs/reference/awp.md` (edit: IWP, constraint and readiness sections)
- `docs/reports/P2-I2/T12.md` (create)

## Acceptance
```
uv run tl awp --help
git diff --stat
grep -n -i -E "claude|opus|sonnet|haiku" packages/tl-modules/awp/README.md packages/tl-modules/awp/AGENTS.md docs/runbooks/iwp-readiness.md docs/reference/awp.md
```
Expected: help prints the awp groups; the diff touches only the Allowed paths; grep prints nothing. No test suite is run.

## Tests to add
None (docs only).

## Report requirements
`docs/reports/P2-I2/T12.md` <= 60 lines: deviations first, the three command outputs (<= 5 lines each), any command you could not verify.

## Escalation triggers
- Stop and report *Blocked* if a command or access word cannot be confirmed from `--help` or the source, or a doc needs a code change.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
