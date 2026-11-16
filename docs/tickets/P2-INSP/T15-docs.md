# P2-INSP-T15 - Docs: inspections and checklists (module pages, runbook, reference, AGENTS row)

Status: staged (r6; dispatch after INSP-T14 merges; with PTW-T16 and QR-T12 in one batch; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: P2-INSP-T14 (demo merged; the verbs and texts are final)
Branch: `p2/insp-t15-docs`
Worktree: `/home/user/wt/insp/t15` (from `p2/ip-r3`)

## Goal
Inspections and checklists are documented for a person and for the next agent, as built. Pattern: `docs/tickets/P2-PUNCH/T09-docs.md` and its merged result (`docs/runbooks/punch-list.md`, `docs/reference/punch.md`, `docs/modules/quality/README.md`). Write only what is built: the eleven commands (plan, schedule, record, verify, reinspect, cancel; create, edit, publish, revise, retire), the states and moves, numbering `INS` and `CHK` (read the real prefixes from `schema/modules/quality`), the readiness check `inspections_planned`, the CLI groups `tl insp` and `tl checklist`, the five API routes, the MCP reads and `propose_inspection`, the terminal log and record screen (palette id `inspections`; scheduling and recording answers are CLI only: the runner screen is follow-up T11), the scan card, the generator section. Not built (list once, pointing at `docs/build-spec/DEFERRED.md` and the plan's follow-up slice): the runner screen, checklist screens, navigation lines, hook-declared surfaces beyond what S2 did. Read `.claude/skills/throughline-docs/SKILL.md` first.

## Brief
1. `packages/tl-modules/quality/README.md` and `AGENTS.md`: add the as-built inspection and checklist sections (words `quality.checklist.*`, `quality.inspection.*` from `schema/settings/access-words.yaml`; verifier differs from recorder; published is immutable; hidden subject reads as missing; `insp_rules.py`, `insp_views.py`, `checks.py`, `scan_card.py`); keep the punch text unchanged.
2. Root `AGENTS.md` "Where things go": one row for inspections and checklists (module paths, schema, CLI `insp*.py checklist*.py`, API `routes/insp.py`, MCP `insp_tools.py`, TUI `inspection_text.py widgets/inspection_log.py`, demo `dev/demos/P2-INSP.sh`, runbook, generator). Append only; the other two increments append their rows in the same batch (the orchestrator resolves the append conflict).
3. `docs/modules/quality/README.md` (add an inspections section), `docs/runbooks/inspections.md` (create: plan, schedule, record, verify, reinspect at the terminal and in the TUI; what each refusal means, quoted from the S2 report and the CLI tests; who holds which word; checklists: create, publish, revise; readiness; what an agent may propose; the generator), `docs/reference/inspections.md` (create: routes, tools, verbs, commands).
4. `docs/reference/access-words.md`: the six new words, copied from the yaml. `docs/modules/quality/access-words.md` if it lists words.

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/reports/P2-INSP/{S1,S2}.md`, `docs/reports/P2-IP/{INSPT05,INSPT06,INSPT07,INSPT08,INSPT10,INSPS3,INSPT14}.md`, `docs/build-spec/module-designs/inspections.md` (sections 1-9)
- `docs/runbooks/punch-list.md` and `docs/modules/quality/README.md` (shape only), `packages/tl-modules/quality/README.md`

## Allowed paths
- `packages/tl-modules/quality/README.md`, `packages/tl-modules/quality/AGENTS.md`, `AGENTS.md` (one row), `docs/modules/quality/`, `docs/runbooks/inspections.md`, `docs/reference/inspections.md`, `docs/reference/access-words.md`
- `docs/reports/P2-IP/INSPT15.md` (create)

## Acceptance
```
ls packages/tl-cli/src/tl_cli/insp.py packages/tl-cli/src/tl_cli/checklist.py packages/tl-api/src/tl_api/routes/insp.py packages/tl-mcp/src/tl_mcp/insp_tools.py packages/tl-tui/src/tl_tui/widgets/inspection_log.py dev/demos/P2-INSP.sh
uv run tl insp --help
uv run tl checklist --help
```
Expected: every path and command named in the new pages exists (the report lists the `ls` and the two help outputs' first lines). No `just check` (docs only; the orchestrator runs it at DONE).

## Tests to add
None (docs).

## Escalation triggers
A verb, route or tool in the reports differs from what the runbook needs to say (write which); a word in the yaml differs from the S1 report.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines. Commit subjects `P2-INSP-T15: ...` with the trailers the dispatch message names; no model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
