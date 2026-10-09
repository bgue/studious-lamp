---
name: throughline-docs
description: How to write and maintain Throughline's documentation and project memory - module READMEs, package AGENTS.md files, runbooks, ADRs, ticket and increment reports, STATUS.md, APPROVALS.md, and docs/memory/LEARNINGS.md. Load it before creating or updating any of those files, when closing a ticket, increment, or phase (docs definition of done), and when recording or curating a learning. For orchestrator and supervisor agents; implementers get the relevant rules pasted into their ticket.
---

# Throughline documentation and memory

Docs in this repository are part of the build ledger: they are how agents in other worktrees, later sessions, and
humans know what exists and why. Write them for a reader who has only the repo, not your transcript.

## 1. Which document, where, who

| Document | Path | Template | Written by | Updated when |
|---|---|---|---|---|
| Brief | `docs/brief-v0.4.md` | — | Humans only | Never by agents. A divergence is an ADR that cites the section |
| Build spec | `docs/build-spec/*.md` | — | Orchestrator | Phase start, re-sequencing (with ADR), contract changes |
| ADR | `docs/adr/<nnnn>-<slug>.md` | `docs/templates/adr.md` | Orchestrator; supervisor drafts as `proposed` | A contract, event schema, adapter boundary, phase order, or gate policy changes |
| Fanout plan | `docs/tickets/<inc>/FANOUT.md` | `docs/templates/opus-fanout.md` | Orchestrator | Before spawning supervisors; decisions log during the fanout |
| Increment plan | `docs/tickets/<inc>/README.md` | `docs/templates/sonnet-increment.md` | Supervisor | Start of increment; ticket table status as work moves |
| Ticket | `docs/tickets/<inc>/T<nn>-<slug>.md` | `docs/templates/haiku-ticket.md` | Supervisor | Before dispatch; *Blocked*/*Decision* during escalation |
| Ticket report | `docs/reports/<inc>/<ticket>.md` | `docs/templates/haiku-report.md` | Implementer returns it; supervisor saves it | On ticket completion |
| Increment report | `docs/reports/<inc>.md` | report half of `sonnet-increment.md` | Supervisor | Increment done |
| Phase report | `docs/reports/<phase>.md` | report sections of the fanout and increment templates | Orchestrator | Phase exit |
| Run status | `docs/reports/STATUS.md` | one line per increment (§5) | Orchestrator | After every increment merge to trunk |
| Delegated approvals | `docs/reports/APPROVALS.md` | one block per approval (§5) | Orchestrator | Each time it uses a delegated gate |
| Stop notice | `docs/reports/STOPPED.md` | free text, state + reason | Orchestrator | When a run stops for any reason other than completion |
| Package README | `packages/<pkg>/README.md` | `docs/templates/package-readme.md` | Supervisor (or a docs ticket) | Package created; public interface, commands, or config change |
| Package AGENTS.md | `packages/<pkg>/AGENTS.md` | short rules list | Supervisor | Package created; a package-specific "never" or convention appears |
| Runbook | `docs/runbooks/<slug>.md` | `docs/templates/runbook.md` | Supervisor of the ops work | An alert, a recovery path, or an operational command is added (§24.6) |
| Learnings | `docs/memory/LEARNINGS.md` | entry format in the file header | Supervisor, orchestrator | When a lesson is learned (§3) |
| Generated docs | `packages/tl-schema/src/tl_schema/generated/docs/` | generator output | Generators only | `just gen`; never edit by hand |

## 2. Writing rules

- Lead with what the reader needs to act. Put the purpose in the first sentence of every file.
- One idea per sentence. Prefer tables for parallel facts and numbered lists for steps.
- Cite the brief as `§n` and other docs by relative path. Cite code as `path:line` only when it is stable.
- Commands go in fenced code blocks and must be copy-pasteable from the repo root.
- No model names or model IDs anywhere in committed docs. Say "orchestrator", "supervisor", "implementer", "reviewer".
- No secrets, tokens, internal hostnames, or personal data. Use `TL_PG_URL`-style variable names instead of values,
  except the documented local dev defaults.
- Do not duplicate: link to the single source (brief, build spec, ADR, generated catalog) instead of restating it.
- Dates are ISO (`2026-10-09`). Status words come from the template's list, nothing else.
- Keep each package README under about 150 lines; move depth into the module's spec or runbooks.

## 3. Project memory (`docs/memory/LEARNINGS.md`)

**Read it** at the start of every orchestrator or supervisor session, before planning.

**Record a learning when** something cost a retry, a failed gate, or an escalation and would cost it again; an
environment or tool behaves unexpectedly; a convention emerged that the build spec does not state; or a reviewer
found the same class of problem twice.

**Do not record** decisions that change contracts (ADR), anything already enforced by a test or generator,
secrets, or narrative (reports).

**How:**
1. Append an entry at the end of *Active* using the header's format. ID `L-<increment-id>-<n>`, unique per increment.
2. State the fact so it can be acted on. Add evidence a reviewer can check.
3. Commit it with the work that taught it, not separately.
4. If it changes how implementers must work, also paste it into the next affected tickets.

**Curate at phase exit (orchestrator):** mark `superseded by` or `promoted to` where a learning became an ADR, an
`AGENTS.md` rule, a skill rule, or a build-spec line; move non-active entries to `docs/memory/archive/<phase>.md`;
keep *Active* under about 150 lines.

**Concurrency:** the file is `merge=union` in `.gitattributes`, so parallel appends from different workstreams merge
without conflicts. Never reorder or rewrite existing entries in a workstream branch; only the orchestrator curates.

## 4. Docs definition of done

**Ticket:** the report is complete (deviations first); any file the ticket's *Allowed paths* lists under `docs/` or
`README.md` is updated; no generated doc was edited by hand.

**Increment:**
- Increment plan's ticket table shows the final status of every ticket.
- Increment report written, including *Learnings* (entries appended or "none").
- Each package the increment created or whose public interface changed has a current `README.md` and `AGENTS.md`.
- Each new operational command, alert, or recovery path has a runbook.
- The demo script runs and its commands match the README.

**Phase:**
- Phase report written; STATUS.md current; APPROVALS.md reviewed for completeness.
- ADRs current; risk register changes recorded.
- LEARNINGS curated and archived (§3).

## 5. Formats for run logs

`docs/reports/STATUS.md`, one line per increment, newest last:

```
| 2026-10-09 14:20 | P0-I1 | done | merged 11 / taken over 1 / abandoned 0 | gates green | demo ok | <trunk sha> |
```

`docs/reports/APPROVALS.md`, one block per delegated approval:

```
- 2026-10-09 · P0-I2-T02 · schema merge `schema/core/psets.yaml` · within §6.3 layers and the P0-I2 plan ·
  approved by orchestrator under KICKOFF delegation · commit <sha>
```

## 6. Templates

`docs/templates/`: `adr.md`, `opus-fanout.md`, `sonnet-increment.md`, `haiku-ticket.md`, `haiku-report.md`,
`package-readme.md`, `runbook.md`. Copy, fill, and delete guidance lines; do not leave placeholders in merged files.
