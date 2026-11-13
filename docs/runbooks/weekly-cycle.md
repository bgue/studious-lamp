# Runbook — the weekly cycle: look ahead, open the week, commit, record outcomes, close, read PPC

Purpose: run one planning week for a project: read the look-ahead, open the week's plan, commit issued or in-progress IWPs to it, record done or missed for each, close the week and read its PPC (plan percent complete). The same steps run in the TUI on keys 1 to 5. Module reference: `packages/tl-modules/awp/README.md`.

## When to use
- Trigger: the weekly planning meeting for a project, on or before the Monday of the week.
- Trigger: a week's outcomes are known and the week must be closed, or the PPC tile is stale.

## Before you start
- Access (words in `schema/settings/access-words.yaml`; `user` is the user role, `controller` the superuser role, see `docs/reference/access-words.md`):

| Step | Word | Table word |
|---|---|---|
| read the look-ahead, the plans, the PPC | `awp.view` | `read` |
| open a week | `awp.week.plan` | `user` |
| commit an IWP, record an outcome | `awp.week.commit` | `user` |
| close a week | `awp.week.close` | `controller` |
| waive a check-raised constraint (step 2) | `core.constraint.waive` | `controller` |

- An IWP can be committed only when it is `Issued` or `In progress`, and not on hold. Issue it first (`docs/runbooks/iwp-readiness.md`).
- A week is an ISO week, written `YYYY-Www`. `--date` on `open` takes any day of the week and the Monday is kept.
- The ledger is given by `--db` or `TL_DB`. Do not paste a `postgresql://` URL into a ticket.
- Every command below takes `--project P123`.

## Week states
`Draft` (opened, nothing committed) → `Committed` (the first commitment) → `Closed` (`week close`). A closed week takes no more commitments and no outcome changes.

## Steps

### 1. Read the look-ahead
```
uv run tl awp look-ahead --project P123 --weeks 4
```
Expected: the activities under way or starting in the next weeks, each with the IWPs linked to it. `--weeks` is 1 to 26, default 4. The look-ahead is not on MCP.

### 2. Open the week
```
uv run tl awp week open --project P123 --date 2026-11-09
```
Expected: `open 2026-W46  version 1`. A second open of the same ISO week is refused.

### 3. Commit IWPs to the week
```
uv run tl awp week commit 2026-W46 P123-IWP-PIP-0001 --project P123 --hours 40.0 --foreman user:ada --expected-version 1
```
Expected: `commit 2026-W46  version 2`. `--hours` is above 0 with one decimal place at most 9999999999.9. `--expected-version` is the plan version you read; a stale version is refused with `error: the record changed since it was read`. A second commit of the same IWP replaces the first.

### 4. Record outcomes
```
uv run tl awp week outcome 2026-W46 P123-IWP-PIP-0001 done --project P123 --expected-version 2
uv run tl awp week outcome 2026-W46 P123-IWP-PIP-0002 missed --reason <key> --project P123 --expected-version 3
```
Expected: `outcome 2026-W46  version <n>`. `missed` needs `--reason`; the keys come from `tl awp week reasons --project P123` (keys, not labels). `done` takes no reason. An outcome can be corrected until the week is closed.

### 5. Close the week
```
uv run tl awp week close 2026-W46 --project P123 --expected-version 4
```
Expected: `close 2026-W46  version 5`. Closing is refused when nothing is committed, when the week is not committed yet, or while any commitment has no outcome. Closing writes the PPC. There is no reopen command: a closed week is final.

### 6. Read PPC
```
uv run tl awp week ls --project P123
uv run tl awp week show 2026-W46 --project P123
uv run tl awp week ppc --project P123 --weeks 4
uv run tl awp report kpi_ppc --project P123
uv run tl awp report kpi_constraint_free --project P123
```
Expected: `ls` shows each plan as `<week>  <state>  <commitments> ppc <x|->`, latest first. PPC is the IWPs done over the IWPs committed, as a percentage with one decimal place (`66.7`); a week with nothing committed shows `-`. `week ppc` pools the last closed weeks (default 4) and prints `ppc <x|->  weeks <k>`. `kpi_ppc` is the same tile for the last 4 closed weeks. `kpi_constraint_free` is the share of live IWPs with no open blocking constraint.

## In the TUI
Open the palette (`Ctrl+P`) and choose `week` (Weekly cycle). The steps line shows the five steps; keys `1` to `5` switch between them.

| Key | Step | Actions on the highlighted row |
|---|---|---|
| `1` | Look-ahead | read only |
| `2` | Constraints | `x` waives the highlighted check-raised constraint; asks for a reason (`core.constraint.waive`) |
| `3` | Release | `s` sign off the highlighted Ready IWP; `i` issue it to its foreman |
| `4` | Commitments | `o` open this week (when none is open); `c` commit an Issued or In progress IWP (IWP, hours, foreman); `d` done; `m` missed, asks the reason; `z` close the week after a confirm |
| `5` | Progress | `w` start work on an Issued IWP; `f` complete field work on an In progress IWP; the screen shows the KPI line |

Step 2 lists a waived constraint as `waived` and does not count it in the summary. `tl awp iwp show` prints `waived by <who>: <reason>` for each waived constraint on the IWP.

## Who holds which word
- Planners and foremen hold `awp.week.plan` and `awp.week.commit` (user role).
- Closing a week needs `awp.week.close` (superuser role).
- Waiving a check-raised constraint needs `core.constraint.waive` (superuser role). A waive is a clear of a check-raised constraint by a holder of that word, with a reason; there is no separate waive command.
- Running the job queue (`tl awp worker`, which applies the hold rule) needs `awp.worker.run` (superuser role, company scope as built: a project-only superuser is refused).

## What an agent may propose
An agent (MCP or API) never writes these; it files a proposal that a person accepts in the review queue (`docs/runbooks/proposal-review-queue.md`):
- `propose_week_commitment` (MCP): a commitment of one IWP to a week. The accepting person needs `awp.week.commit`.
- `propose_progress` (MCP): hand progress on the steps of an IWP. The accepting person needs `awp.progress.record`.

An agent is refused with `agent_must_propose` for the commands that only a person may run, in particular `ClearConstraint` (any clear, including a waive) and `CloseWeek`. Read tools for agents: `list_weekly_plans`, `get_weekly_plan`, `get_iwp_progress`, `get_progress_rollup`, `list_kpis`.

## Verify
- `uv run tl awp week ls --project P123` shows the week with `Closed` and a PPC.
- `uv run tl awp week show 2026-W46 --project P123` lists every commitment, each with `done` or `missed`.
- `uv run tl awp report kpi_ppc --project P123` shows the closed weeks in the tile.

## Known limits
- There is no `plan` verb: planning is `week open` followed by `week commit`.
- A commitment is refused unless the IWP is Issued or In progress and not on hold.

## Roll back
- Before close: an outcome is corrected by recording it again with the same `week outcome` command (the last one stands).
- After close: there is no reopen command. A closed week is final; record the correction in the next week's plan.

## Related
- `packages/tl-modules/awp/README.md` (events, words, reads), `packages/tl-modules/awp/AGENTS.md` (rules), `docs/runbooks/rules-of-credit.md` (progress and earned %), `docs/runbooks/iwp-readiness.md` (constraints, sign-off, issue, hold), `docs/reference/awp.md` (reads and routes).
