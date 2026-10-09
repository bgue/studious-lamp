# Build spec 02 — Task protocol

How work moves between tiers: tickets, context packs, reports, reviews, branches, and definitions of done.

## 1. Ticket lifecycle

```
draft → ready → in-progress → in-review → (changes-requested → in-progress)* → merged → closed
                                       └→ escalated → (decision) → ready | abandoned
```

- `draft`: supervisor is writing it. `ready`: Haiku-ability checklist passed, dependencies merged.
- `in-progress`: an implementer owns it (one at a time).
- `in-review`: PR open, reviewer dispatched.
- `escalated`: a *Blocked* entry exists; nobody works it until *Decision* is filled.
- `abandoned`: superseded; the file stays with a one-line reason.

The status line is the first line of the ticket file after the title, so `grep -r '^Status:' docs/tickets` is the board.

## 2. Ticket anatomy

Template: `docs/templates/haiku-ticket.md`. Mandatory sections:

| Section | Content |
|---|---|
| Header | ID (`P0-I1-T06`), title, status, tier (`haiku` / `sonnet`), labels (`schema`, `adapter`, `tui`, …), depends-on, branch |
| Goal | One paragraph: what exists after this ticket that did not before |
| Brief references | Pasted excerpts (tables, bullets) from the brief, not just `§5.1`. The implementer does not open the brief |
| Interfaces | Pasted Protocols, dataclasses, LinkML fragments, SQL shapes the ticket must honour. Verbatim from the repo |
| Context | Exact file paths to read, ≤ 6. Optional `may explore:` glob |
| Allowed paths | Files and directories the ticket may create or change. Everything else is read-only |
| Steps | Optional ordered steps when the order matters |
| Acceptance | Commands with expected outcomes. At least `just check` and one test command |
| Tests to add | File paths and the behaviours each must cover |
| Report | Anything specific the report must contain beyond the template |
| Escalation triggers | Conditions under which the implementer must stop |
| Blocked / Decision | Filled during escalation |

## 3. Context packs

A context pack is the *Brief references* + *Interfaces* + *Context* sections of a ticket. Rules:

- **Paste, don't point.** Implementers never read the brief. The supervisor pastes the lines that matter.
- **Budget:** ≤ ~40k tokens for an implementer: ticket ≤ 3k, context files ≤ 30k, `AGENTS.md` ≤ 2k.
- **Interfaces verbatim.** Copy from the repo at the commit the ticket branches from. If the interface changes later, the ticket is re-issued, not patched in chat.
- **Tests as spec.** Where possible the supervisor commits a failing test file before dispatch and the ticket says "make `tests/.../test_x.py` pass".
- **No transitive reading.** If a context file imports something the implementer would need to understand, either paste the relevant signature into *Interfaces* or add the file to *Context*.

Supervisor context (per increment) is larger: the increment plan, cited brief sections, `03-repo-and-toolchain.md`, the interfaces, and the last increment report. Keep it under ~120k tokens by citing rather than pasting the brief.

## 4. Reports

Implementer report (`docs/templates/haiku-report.md`), returned as the final message and saved by the supervisor to `docs/reports/<increment-id>/<ticket-id>.md`:

1. **Deviations** (first line, or "none").
2. **Changed files** with one line each.
3. **Commands and output** for every acceptance command, trimmed to the decisive lines.
4. **Tests added** and what they cover.
5. **Open questions / Blocked**.

Supervisor increment report (`docs/templates/sonnet-increment.md` §Report): objective met or not, demo path, ticket table with outcomes (merged, taken over, abandoned), gate results, deviations from the plan, escalations and decisions, follow-ups, token/cost notes if available.

## 5. Branches, commits, PRs

- Branches: `p<phase>/i<inc>-t<nn>-<slug>` for tickets (a sibling of the increment branch: git cannot hold both `p0/i1` and `p0/i1/...`); `p<phase>/i<inc>` increment branch; `p<phase>/integration`; `main`.
- Commits: `<ticket-id>: <imperative summary>` with a body that says what and why. No model names or IDs in any committed content.
- One PR per ticket, from the ticket branch to the increment branch. PR body = the report. Reviewer verdict is posted as a review.
- Merges are merge commits (no squash, no rebase) so ticket history stays legible.
- Generated artefacts are committed in the same PR as the schema or generator change that produced them.

## 6. Review checklist

The reviewer answers each in order and stops at the first hard failure:

1. **Scope:** the diff does what *Goal* and *Acceptance* say, and nothing beyond. "While I'm here" changes → `changes-requested`.
2. **Boundary:** every changed path is inside *Allowed paths*.
3. **Interfaces:** pasted interfaces are honoured verbatim; no redesign.
4. **Verification:** the reviewer re-runs `just check` and the ticket's test command. Pasted output that does not match a re-run → `changes-requested`.
5. **Generated code:** nothing under `packages/tl-schema/src/tl_schema/generated/` or `schema/` changed unless the ticket is labelled `schema` and names an approver.
6. **Immutability:** no UPDATE/DELETE on event tables, no history rewriting.
7. **Dialect:** no SQLite- or Postgres-specific SQL outside `packages/tl-adapters/`.
8. **Logic placement:** no business logic in `packages/tl-tui/`.
9. **Tests:** named tests exist, cover the named behaviours, and fail if the change is reverted (spot-check one).
10. **Conventions:** ruff/pyright clean, commit message format, no model names outside the attribution trailer.
11. **Docs:** docs listed in *Allowed paths* are updated; generated docs untouched.

Verdicts: `pass`; `changes-requested` with numbered findings; `escalate` with the question.

## 7. Two-strikes rule

- An implementer ticket that returns `changes-requested` twice is taken over by the supervisor. The ticket records `taken-over: <reason>`.
- A supervisor-built engine that fails its gates twice is escalated to the orchestrator with the failure evidence.
- The rule exists to stop cheap retries from becoming expensive thrash. It is not a penalty; it is a routing decision.

## 8. Definitions of done

**Ticket**

- All acceptance commands pass on the reviewer's re-run.
- Reviewer verdict `pass`; merged to the increment branch by the supervisor.
- Report saved under `docs/reports/`.

**Increment**

- Every ticket in the plan is merged or explicitly abandoned with a reason.
- `just check`, `just test` green on the increment branch; `just test-parity` where adapters changed; `just test-tui` where screens changed.
- Demo script runs clean from `just dev up` on a fresh clone.
- Increment report written; follow-ups filed as `draft` tickets in the next increment folder.
- Docs definition of done met (`throughline-docs` skill §4): package READMEs and AGENTS.md current, runbooks for new operations, learnings recorded.

**Phase**

- The brief's exit criteria for the phase (§16) are demonstrated on a simulated project (§29.5) where the simulator exists, else on seed data.
- Phase report by the orchestrator; risk register (§17) updated; ADRs current.
- Human sign-off on every gate named in the fanout plans (or a logged delegated approval in `docs/reports/APPROVALS.md`).
- `docs/memory/LEARNINGS.md` curated and archived for the phase.

## 9. Project memory

`docs/memory/LEARNINGS.md` is the build's memory: small, actionable facts that are expensive to rediscover. Rules
for reading, writing, and curating it are in the `throughline-docs` skill §3. It is in git, merges with
`merge=union`, and is never read by implementers directly; supervisors paste the entries a ticket needs.
