# P2-I3-T10 — Docs: tl-mod-materials README and AGENTS.md, materials runbook

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T11 merged (all code and screens are final)
Branch: `p2/i3-t10-docs`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
A reader with only the repo can use and extend M4 materials. After this ticket: the module README and package AGENTS.md exist, a runbook walks the daily jobs, and the runbook index points to it.

## Rules (pasted from the docs skill)
Purpose in the first sentence. Tables for parallel facts, numbered steps for procedures. Commands in fenced blocks, copy-pasteable from the repo root. README under about 150 lines. No model names, no secrets. Link the single source (spec, ADR, generated docs) instead of restating. Templates: `docs/templates/package-readme.md`, `docs/templates/runbook.md`; delete guidance lines, leave no placeholders. Dates ISO.

## Facts to document (take EVERY name, command, access word, key and id from `--help` and the source, never from memory; if a fact below is not found in the source, write what the source says and list the difference in the report)
README.md (public interface):
- names: package, import path, registered entry points
- commands with their access words, including the 10 controlling acts that agents are denied (find them in `tl_core.auth` AGENT_ACTIONS and `tl_mod_materials` commands.py)
- load targets and their loaders (`tl load ... --company`); the `mto` publish target; the readiness check `materials_reserved`
- the six screens: keys S M E D I W and their palette ids (`tl_tui` commands.py, app.py, keymap)
- the ten MCP tools (`MATERIALS_MCP_ACTIONS`, `materials_tools.py`)
- offline classes (what works without the API; find in the tl-tui offline registry)
AGENTS.md (package): short list of package-specific nevers and conventions found in the source and `docs/reports/P2-I3/*.md` (stored `available`, Decimal quantities, no SQL arithmetic, MTR rule, reserve check, hidden = missing).
docs/runbooks/materials.md: load the item library with `tl load ... --company`; locations; receive and accept with the MTR; issue, transfer, return, adjust; reservations and shortages; the movement log; rebuild (`just rebuild-projections`). Each step a copy-pasteable command checked against `--help`.
docs/runbooks/README.md: one line, same style as the others.

## Context (read these, nothing else)
- `docs/build-spec/specs/m4-materials.md` (§ on commands, screens, demo), `docs/tickets/P2-I3/text-contracts.md`
- `docs/reports/P2-I3/*.md` (skim headings only)
- `packages/tl-modules/materials/pyproject.toml`, `.../src/tl_mod_materials/{commands.py,actions.py,errors.py}`
- `packages/tl-mcp/src/tl_mcp/materials_tools.py`; `packages/tl-cli/src/tl_cli/{mat*.py,load.py}`
- `docs/runbooks/legacy-load.md` (style precedent)
may explore: `uv run tl mat --help` and each subcommand's `--help`, `uv run tl load --help`

## Allowed paths
- `packages/tl-modules/materials/README.md` (create)
- `packages/tl-modules/materials/AGENTS.md` (create)
- `docs/runbooks/materials.md` (create)
- `docs/runbooks/README.md` (one line added)
- `docs/reports/P2-I3/T10.md` (create)

## Acceptance
```
uv run tl mat --help
uv run tl load --help
just scan-secrets
```
Expected: every command in the docs appears in the help output; scan clean. Also `grep -n -i -E 'opus|sonnet|haiku|claude' <the four doc files>` prints nothing. Do not run `just test`.

## Tests to add
None.

## Report requirements
Standard report (`docs/templates/haiku-report.md`, <= 60 lines): deviations first, then each fact group with the source file it came from, and the output of each acceptance command (<= 5 lines).
Commit subject `P2-I3-T10: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report Blocked if a command or key named above does not exist in the source.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
