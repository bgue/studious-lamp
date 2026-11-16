# P2-PTW-T16 - Docs: permits to work (module package, module pages, runbook, reference, AGENTS row)

Status: staged (r6; dispatch after PTW-T15 merges; with INSP-T15 and QR-T12 in one batch; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: P2-PTW-T15 (demo merged; the verbs and texts are final)
Branch: `p2/ptw-t16-docs`
Worktree: `/home/user/wt/ptw/t16` (from `p2/ip-r3`)

## Goal
The permit module is documented for a person and for the next agent, as built. Pattern: `docs/tickets/P2-PUNCH/T09-docs.md` and its merged result. Write only what is built: the ten permit commands and six isolation and gas test commands, the states and moves (Requested, Approved, Active, Lapsed as a shown state, Suspended, Handed back, Closed, Rejected, Cancelled), numbering (real prefixes from `schema/modules/permits`), the type table and gas limits as settings (defaults stand until the safety lead signs: say so), the lapse job and its clock parameter, the readiness check `permits_planned`, the CLI groups `tl permit`, `tl isolation`, `tl gastest`, the seven API routes, the MCP reads and `propose_permit`, the terminal register and record screen (palette id `permits`; issue, cancel and request are CLI only), the scan card with its gas test and isolation lines, the generator section. Not built (list once, pointing at `docs/build-spec/DEFERRED.md` and the plan's follow-up slice): the board and isolation register screens, navigation lines, a scheduler for the lapse job, offline permits. Read `.claude/skills/throughline-docs/SKILL.md` first.

## Brief
1. `packages/tl-modules/permits/README.md` and `AGENTS.md` (S1 made stubs): as-built commands, words (`permits.*`, from the yaml), the separation rules (approver differs from requester; verifier differs from applier; only the authority resumes), hidden permit reads as missing ("error: no permit <KEY>"), views, rules, guards, the package rules (every read takes `viewer=`; no limit hard-coded).
2. Root `AGENTS.md` "Where things go": one row for permits (module package, schema, CLI `cli_permit_*.py cli_isolation.py cli_gastest.py`, API `routes.py`, MCP `tools.py`, TUI `permit_text.py widgets/permit_log.py`, demo `dev/demos/P2-PTW.sh`, runbook, generator `dev/seed/demo_project/permits.py`). Append only; the other two increments append in the same batch.
3. `docs/modules/permits/README.md` (create: model `docs/modules/correspondence/`), `docs/runbooks/permits.md` (create: request, approve, record a gas test, apply and verify an isolation, issue, suspend, resume, revalidate, hand back, close at the terminal and in the TUI; every refusal quoted from the reports and tests; the safety-lead defaults; the lapse job and how to run it; what an agent may propose), `docs/reference/permits.md` (create: routes, tools, verbs, commands).
4. `docs/reference/access-words.md`: the twelve words, copied from the yaml.

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/reports/P2-PTW/*.md`, `docs/reports/P2-IP/{PTWT04,PTWT06a,PTWT07b,PTWT10,PTWT11,PTWS4,PTWT15}.md`, `docs/build-spec/module-designs/permits.md` (sections 1-9)
- `docs/runbooks/punch-list.md` and `docs/modules/correspondence/README.md` (shape only), `packages/tl-modules/permits/README.md`

## Allowed paths
- `packages/tl-modules/permits/README.md`, `packages/tl-modules/permits/AGENTS.md`, `AGENTS.md` (one row), `docs/modules/permits/`, `docs/runbooks/permits.md`, `docs/reference/permits.md`, `docs/reference/access-words.md`
- `docs/reports/P2-IP/PTWT16.md` (create)

## Acceptance
```
ls packages/tl-modules/permits/src/tl_mod_permits/cli_permit_write.py packages/tl-modules/permits/src/tl_mod_permits/cli_isolation.py packages/tl-modules/permits/src/tl_mod_permits/cli_gastest.py packages/tl-modules/permits/src/tl_mod_permits/routes.py packages/tl-modules/permits/src/tl_mod_permits/tools.py packages/tl-tui/src/tl_tui/widgets/permit_log.py dev/demos/P2-PTW.sh
uv run tl permit --help
uv run tl isolation --help
uv run tl gastest --help
```
Expected: every path and command named in the new pages exists (the report lists the `ls` and the help outputs' first lines). No `just check` (docs only; the orchestrator runs it at DONE).

## Tests to add
None (docs).

## Escalation triggers
A verb, route or tool in the reports differs from what the runbook needs to say (write which); a word in the yaml differs from the S1 report; a gas limit default differs from what the S1 report says.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines. Commit subjects `P2-PTW-T16: ...` with the trailers the dispatch message names; no model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
