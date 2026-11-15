# P2-I4B-T12 — Docs: module README and AGENTS, runbook, contracts As-built, module docs

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: all code tickets except T10a, T10b, T11b (demo and tour are not described here beyond one pointer)
Branch: `p2/i4b-t12-docs`
Worktree: `/home/user/wt/i4b/t12` (from `p2/i4b` head)

## Goal
The scaffold module is documented where the next agent looks: package README and AGENTS, a runbook, the module page, and the contracts As-built note. Load skill `throughline-docs` first and follow its rules (README sections, no model names, no marketing).

## Brief references (pasted)
> Facts to state, all from merged reports: module `tl-mod-scaffold`, record types `scaffold.Scaffold` and `scaffold.ScaffoldInspection`; states Requested, Designed, Erecting, Inspected, In Use, Modify, Dismantle, Removed (D2); ten access words (`tests/.../test_access_words.py` lists them; `scaffold.tag.green` is controller, the rest user); a fail inspection on Inspected or In Use moves to Modify, on Erecting stays (D2); release needs a green tag; dismantle holds while a requiring IWP is Issued, In progress or On hold, or another open scaffold request of that IWP exists (D3); job `scaffold.inspections_due` from setting `scaffold.inspection.interval_days`, one flag per scaffold and due day; readiness checks `scaffold_tagged` (D9) and `labour_requested` (D10); reads: views `scaffold_list`, `scaffold_detail`, `due_list`, `export_rows` (CSV with formula guard, JSONL; D12); API: nine commands at the door, routes `GET /projects/{p}/scaffolds`, `/scaffolds/{key}`, `/scaffold-due`, `/scaffold-export` (D13, D14); TUI: palette `scaffolds`, register and record screens (keys s, o, x, X), toolcrib screen keys F2 issue, F3 return, Ctrl+R (D11, D15); no CLI group and no MCP tools yet (DEFERRED, waits for the X4 hooks: command splat in `tl_api/commands.py` and router line in `app.py` then move into `module.py`).
> S1-F4 (supervisor decision): the module reads `cur_requisitions_scaffold_request` directly because the requisitions api has no single-request read; record it in `phase2-contracts-draft.md` §3 under As built.

## Context (read these, nothing else)
- `docs/reports/P2-I4B/{S1,T01,T05a,T05b,T06,T07a,T07b,T09a,T09b1,T09b2}.md` (read the decisive lines only)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/templates/runbook.md`, `docs/runbooks/punch-list.md` (model), `packages/tl-modules/quality/README.md` and `AGENTS.md` (models), `docs/modules/quality/` (model)
- `docs/build-spec/phase2-contracts-draft.md` §3 (As built block only)

## Allowed paths
- `packages/tl-modules/scaffold/README.md`, `packages/tl-modules/scaffold/AGENTS.md` (create)
- `docs/runbooks/scaffold.md` (create); `docs/modules/scaffold/` (create: the module page, as `docs/modules/quality/` has)
- `docs/build-spec/phase2-contracts-draft.md` (edit: §3 As built, S1-F4 and the direct SQL, one paragraph)
- `docs/reports/P2-I4B/T12.md` (create)
Not allowed: `AGENTS.md` at the repo root (the DONE round writes its table row), the plan README, STATE.

## Acceptance
```
just check
(no docs link test exists; none to run)
```
Every path and command a doc names must exist: check each with `ls` or `--help`, paste ≤ 5 lines.

## Tests to add
none (docs).

## Report requirements
Standard report; list each doc and its line count; any fact in the brief you could not confirm in the code.

## Escalation triggers
- Stop if a fact above contradicts the code; write both.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-15; review F1-F2)
The code is the source of truth: the register and record screens bind what T07b built (record screen: Esc and F5), and
F2 (issue), F3 (return) and Ctrl+R belong to the toolcrib modal (T07a). The brief's key list and D15 wording were wrong;
the docs as written follow the code and are accepted. F2 inside the toolcrib modal wins over the app-level F2 toggle,
which is not a priority binding (T07a decision, covered by its nav tests).
