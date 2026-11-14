# P2-PUNCH-T09 — Docs: the quality module, runbook and reference

Status: staged (dispatch after T08 merges)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T08
Branch: `p2/punch-t09-docs`
Worktree: harness-created under `/home/user/wt/punch/t09` (from `p2/punch` head)

## Goal
The punch list is documented for a person and for the next agent. Write only what is built: raise, edit, clear, verify, reopen, void, the log, the record screen, the MCP reads and the propose tool, the generator section. Inspections, deficiencies, ITPs, the Issue engine, the walkdown screen, photos, feed cards and web pages are not built: say so once, in a "Not built yet" list that points to `docs/build-spec/DEFERRED.md`, and describe nothing else about them. The Phase 3 compatibility table of `docs/tickets/P2-PUNCH/README.md` ("Record shape and Phase 3 compatibility") is carried into the module README unchanged in meaning.

## Brief
1. `packages/tl-modules/quality/README.md` and `AGENTS.md` (S1 made stubs): as-built commands and words (`quality.view`, `quality.punch.raise|edit|clear|verify|reopen|void`), states and moves, numbering `PUN`, the subject join (a punch item is hidden when its source is; hidden looks like missing), `views.py` and `api.py`, verifier differs from clearer, the module's package rules (no business logic in screens, every read takes `viewer=`).
2. Root `AGENTS.md` "Where things go": one row for quality (module, schema, CLI `punch.py punch_write.py punch_read.py`, API `routes/punch.py`, MCP `punch_tools.py`, TUI `punch_text.py widgets/punch_log.py`, demo `dev/demos/P2-PUNCH.sh`, runbook, generator `dev/seed/demo_project/quality.py`).
3. `docs/modules/quality/README.md` (create: the model of `docs/modules/correspondence/`), `docs/runbooks/punch-list.md` (create: raise, clear, verify at the terminal and in the TUI, what each refusal means, who holds which word, numbering, what an agent may propose, the generator; the exact verbs and texts from the T02 and T06 reports), `docs/reference/punch.md` (create: the three routes, the three tools, the verbs, the six commands).
4. Stale pointers: `docs/reference/access-words.md` (the seven quality words, copied from `schema/settings/access-words.yaml`), `docs/build-spec/specs/offline-classes.md` (one row, if S1 did not add it).

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/reports/P2-PUNCH/{S1,S2,T02,T05,T06,T07,T08}.md`
- `docs/modules/correspondence/` and `docs/runbooks/correspondence.md` (shape only, first 60 lines each), `packages/tl-modules/quality/README.md`

## Allowed paths
- `packages/tl-modules/quality/{README.md,AGENTS.md}`, `AGENTS.md` (one row), `docs/modules/quality/`, `docs/runbooks/punch-list.md`, `docs/reference/{punch.md,access-words.md}`, `docs/build-spec/specs/offline-classes.md`
- `docs/reports/P2-PUNCH/T09.md` (create)

## Acceptance
```
just check
```
Expected: no drift; every file path and command named in the new pages exists (the report lists the check: `ls` of each path and the `tl punch --help` output lines).

## Tests to add
None (docs). The report states which doc-lint recipe `just check` ran, if any.

## Escalation triggers
- A verb, route or tool in the T02, T03, T05 or T06 reports differs from what the runbook needs to say (write which); a word in the yaml differs from the list above.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed (none expected). Commit subjects `P2-PUNCH-T09: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
