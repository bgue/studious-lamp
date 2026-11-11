# P2-I4A-T12 — Docs: module README, runbook, reference page, stale references

Status: staged (dispatch after T10b merges)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T10b
Branch: `p2/i4a-t12-docs`
Worktree: harness-created under `/home/user/wt/i4a/t12` (from `p2/i4a` head)

## Goal
The requisitions module is documented for a person and for the next agent, and three stale pointers from S1 and S2 are closed. Write only what is built: raise, edit, approve, reject, cancel, the work order lifecycle, logs, the propose tool. Fulfilment, FIFO lots, the shortage constraint, the labour forecast and reports are not built: say so once, in a "Not built yet" list that points to `docs/build-spec/DEFERRED.md`, and describe nothing else about them.

## Brief
1. `packages/tl-modules/requisitions/README.md` and `AGENTS.md`: update to the as-built commands, words (`requisitions.view|raise|edit|cancel|approve|reject|schedule|assign|start|complete|close`; the `fulfil` word exists with no command), `views.py` and `api.py`, states, numbering, confidentiality rule (a requisition inherits its subject's class), the first module-to-module import is not yet present (S3 deferred): say so.
2. Root `AGENTS.md` "Where things go": one row for requisitions (module, schema, CLI `req.py req_write.py req_read.py`, API `routes/requisitions.py`, MCP `requisition_tools.py`, TUI `requisition_text.py work_order_text.py`, demo `dev/demos/P2-I4.sh`, runbook).
3. `docs/modules/requisitions/README.md` (create: the model of `docs/modules/correspondence/`), `docs/runbooks/requisitions.md` (create: raise, approve, run a work order at the terminal and in the TUI, what a refusal means, who holds which word, numbering, what an agent may propose; the exact verbs of `tl req` and `tl wo` from the T04d and T04e1 reports), `docs/reference/requisitions.md` (create: the four routes, the four tools, the verbs).
4. Stale pointers: `docs/reference/access-words.md` (the 12 requisitions words, copy of `schema/settings/access-words.yaml` lines 44-56), `docs/build-spec/specs/offline-classes.md` (the five types: four requisition kinds `draft_only`, `WorkOrder` `none`), `docs/build-spec/phase2-contracts-draft.md` §3 (the Raised payload is flat; Revised carries `changes` {field: [old, new]}).

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/reports/P2-I4A/{S1,S2,T04d,T04e1,T08b,T10b}.md`
- `docs/modules/correspondence/` and `docs/runbooks/correspondence.md` (shape only, first 60 lines each), `packages/tl-modules/requisitions/README.md`

## Allowed paths
- `packages/tl-modules/requisitions/{README.md,AGENTS.md}`, `AGENTS.md` (one row), `docs/modules/requisitions/`, `docs/runbooks/requisitions.md`, `docs/reference/{requisitions.md,access-words.md}`, `docs/build-spec/specs/offline-classes.md`, `docs/build-spec/phase2-contracts-draft.md` (§3 only)
- `docs/reports/P2-I4A/T12.md` (create)

## Acceptance
```
just check
```
Expected: no drift; every file path and command named in the new pages exists (the report lists the check: `ls` of each path and `tl req --help`, `tl wo --help` output lines).

## Tests to add
None (docs). The report states which doc-lint recipe `just check` ran, if any.

## Escalation triggers
- A verb, route or tool in the T04d, T04e1, T04c1 or T08b reports differs from what the runbook needs to say (write which); a word in the yaml differs from the list above.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T12: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
