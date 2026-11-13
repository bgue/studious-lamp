# P2-I5-T13 — Docs: awp README and AGENTS, three runbooks, reference page, access words

Status: ready (T12b merged into `p2/i5`)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T12 (T12b)
Branch: `p2/i5-t13-docs`
Worktree: harness-created under `/home/user/wt/i5/t13` (from `p2/i5` head)

## Goal
What P2-I5 built (weekly cycle, rules of credit and progress, the IWP pack, waivers and holds, the KPI tiles, the
foreman landing, the agent proposals) is documented for a person and for the next agent. Write only what is built.
Struck items (roadmap 3c: closeout and subcontract screens, the PDF pack, demo clauses 7-8, web pages) go in one
"Not built yet" list that points to `docs/build-spec/DEFERRED.md`, and nothing else is said about them.

## Brief
1. `packages/tl-modules/awp/README.md` and `AGENTS.md`: add the I5 commands, events, words, reads (look-ahead, week
   reads, rollup and CSV export, KPIs, pack), the hold and waive rules and the worker word, as built (reports S1-S4b).
2. Root `AGENTS.md` "Where things go": update the awp row with the I5 places (CLI `tl awp week|roc|progress|iwp pack`,
   TUI weekly cycle screens and landing, MCP `propose_progress`, `propose_week_commitment`, demo `dev/demos/P2-I5.sh`).
3. Runbooks (create; shape of `docs/runbooks/awp.md`): `docs/runbooks/weekly-cycle.md` (open, plan, commit, record
   outcomes, close a week at the terminal and in the TUI keys 1-5; PPC; who holds which word; what an agent may
   propose and what it is refused: `agent_must_propose` for ClearConstraint and CloseWeek), `docs/runbooks/rules-of-credit.md`
   (set and read rules of credit, record progress, earned %, rollup and CSV export by cost code), `docs/runbooks/iwp-pack.md`
   (`tl awp iwp pack NUMBER --out FILE`, what the HTML holds, the QR). Exact verbs from the T01, T04, T04b, T06a,
   T06b, T07a reports and `tl awp --help` output.
4. `docs/reference/awp.md`: add the I5 routes, MCP tools and verbs (reports S4a, T11a1, T11a2, T11b, T11c, T12a).
5. `docs/reference/access-words.md`: the awp words from `schema/settings/access-words.yaml` lines 16-38 that are not
   yet listed (week, progress, closeout, subcontract, worker, waive), copied as the yaml states them.
6. `docs/runbooks/README.md`: one line per new runbook.

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`; `docs/reports/P2-I5/{S1,S2,S3,S4a,S4b,T01,T04,T04b,T06a,T06b,T06c2,T07a,T09,T12,T12a}.md`
- `docs/runbooks/awp.md` (shape, first 60 lines), `docs/reference/awp.md`, `packages/tl-modules/awp/{README,AGENTS}.md`

## Allowed paths
- `packages/tl-modules/awp/{README.md,AGENTS.md}`, `AGENTS.md` (awp row only), `docs/runbooks/{weekly-cycle,rules-of-credit,iwp-pack,README}.md`,
  `docs/reference/{awp.md,access-words.md}`
- `docs/reports/P2-I5/T13.md` (create)

## Acceptance
```
just check
```
Expected: no drift; every path and verb named in the new pages exists (the report lists the check: `ls` of each path
and the `tl awp week --help`, `tl awp roc --help`, `tl awp iwp --help` lines used).

## Tests to add
None (docs).

## Escalation triggers
- A verb, route or tool in the reports differs from `--help` output (write which); a word in the yaml differs from a report.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I5-T13: ...`;
the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files,
including the report (do not discuss trailers or models there).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
