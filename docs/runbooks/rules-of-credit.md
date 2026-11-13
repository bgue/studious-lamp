# Runbook — rules of credit: set and read the edition, record progress, read earned %, roll up and export by cost code

Purpose: say how much of an IWP is earned when its work is done. The rules of credit give each step of each commodity a share of the item; a person records the steps, the figure is kept per IWP, and the earned hours roll up to cost codes for a week's CSV export. Module reference: `packages/tl-modules/awp/README.md`.

## When to use
- Trigger: a project adopts a new edition of the rules of credit, or the default edition must be checked.
- Trigger: a foreman has finished steps or field work and the earned % of an IWP is wrong or missing.
- Trigger: the week's progress export by cost code is needed for the cost review.

## Before you start
- Access (`schema/settings/access-words.yaml`): `awp.view` (read), `awp.progress.record` (user role: record steps, item moves and hand steps), `awp.iwp.edit` (user role: start work, complete field work). Changing the edition is a project setting write, not an awp word: the settings rules of `docs/runbooks/settings.md` apply.
- The edition is `package@version`, for example `co.acme.awp@1.1.0`. An edition that is not adopted, or that holds no rules, is refused.
- An IWP's figure is kept with the edition in force when it was recorded. Changing the edition later does not rewrite a recorded figure.
- Every command takes `--project P123`. Use `--db` or `TL_DB` for the ledger; never print a `postgresql://` URL.

## Steps

### 1. Read the edition in force
```
uv run tl awp roc ls --project P123
uv run tl awp roc show --project P123
uv run tl awp roc show --project P123 --edition co.acme.awp@1.1.0
```
Expected: `edition <key>`, `source default|setting|argument`, `commodities: <n>`, then one line per commodity with its kind and the steps and weights in package order. `--edition` shows that edition, not the one in force (`source argument`). An unknown edition prints its `error:` line and exits 1.

### 2. Set the edition
```
uv run tl awp roc set co.acme.awp@1.1.0 --project P123 --reason "adopted for the Q4 cycle"
```
Expected: `set awp.rules_of_credit.set project:P123 "co.acme.awp@1.1.0"`, or `unchanged ...` when the project already has it. A value that is not `package@version` gives `error: edition: expected package@version`. `--reason` is optional and recorded with the change.

### 3. Record progress
Every step is a person's word (`awp.progress.record`); the IWP's steps are read from the scope items.

```
uv run tl awp iwp step P123-IWP-PIP-0001 <item key> <step> --project P123 --expected-version 7
uv run tl awp iwp step P123-IWP-PIP-0001 <item key> <step> --undo --project P123 --expected-version 8
uv run tl awp iwp item-move <item key> install --project P123 --expected-version 3
uv run tl awp iwp item-move <item key> verify --project P123 --expected-version 4
uv run tl awp iwp item-move <item key> return --project P123 --expected-version 5
```
- `iwp step` marks one step of one scope item done by hand; `--undo` unmarks it. Use it only for a step no record proves.
- `item-move` takes a scope item from planned to installed (`install`), from installed to verified (`verify`), or back to planned (`return`).
- `--expected-version` is the IWP's version (for `iwp step`) or the item's version (for `item-move`) that you read. A stale version is refused with `error: the record changed since it was read`.

Field work: `uv run tl awp iwp start-work P123-IWP-PIP-0001 --project P123 --date 2026-11-09 --expected-version 9` moves an Issued IWP to In progress (`awp.iwp.edit`); `uv run tl awp iwp complete-field P123-IWP-PIP-0001 --project P123 --date 2026-11-20 --expected-version 10` completes the field work of an In progress IWP. Both print `… version <n>`.

In the TUI the same actions are on the week screen, step 5 (`w` start work, `f` complete field work); see `docs/runbooks/weekly-cycle.md`.

### 4. Read earned %
```
uv run tl awp iwp progress P123-IWP-PIP-0001 --project P123
```
Expected: `iwp <number>`, `earned <pct>  edition <edition>`, `items: <n>`, then `<key>  <pct>  <steps earned or ->` for each item and `note: <text>` for each note. A missing or hidden IWP is `error: no IWP <number>`. The figure is the stored percentage of the IWP's hours.

### 5. Roll up and export by cost code
```
uv run tl awp export progress --project P123 --period 2026-W46
uv run tl awp export progress --project P123 --period 2026-W46 --out progress-2026-W46.csv
```
Expected: CSV with the header `period,scope,cost_code,earned_hours,budget_hours,earned_pct,as_of_seq`, one line per cost code, and the `Unallocated` line last. The `Unallocated` line holds earned hours that reach no WBS node. An empty cell means no budget. Cells starting with `=`, `+`, `-` or `@` get a leading apostrophe. `--out` writes mode 0600. The export is computed on read: it stores nothing and writes no event. A reader sees only what they may open; budgets are computed from the same visible records.

## Verify
- `uv run tl awp roc ls --project P123` prints the edition you set, with `source setting`.
- `uv run tl awp iwp progress <number> --project P123` shows the `earned` line after your step.
- The CSV header and the `Unallocated` line are as listed in step 5.

## Known limits
- The rules of credit are a package: an edition with no `rules_of_credit` is refused, and a commodity with no entry is credited as `piping`.
- Hand progress (`iwp step`) is for steps no record proves; agents propose it (see below), they do not record it.
- The export is not stored: there is no row to read back later, only the CSV you wrote.

## What agents may do
- MCP `propose_progress` files a proposal of steps; a person with `awp.progress.record` accepts it in the review queue (`docs/runbooks/proposal-review-queue.md`). Nothing is recorded by the proposal.
- MCP reads: `get_iwp_progress` (the earned figure of one IWP), `get_progress_rollup` (the rollup by cost code). Each needs its `mcp.<tool>` action in the agent's identity.

## Roll back
- A wrong step: `iwp step … --undo` with the current version, then mark it again.
- A wrong edition: `uv run tl awp roc set <previous edition> --project P123 --reason "..."`. Recorded figures keep the edition they were recorded with.

## Related
- `docs/runbooks/weekly-cycle.md` (week, PPC, TUI step 5), `docs/runbooks/iwp-readiness.md` (issue and sign-off before work starts), `docs/runbooks/settings.md` (project setting writes), `docs/reference/awp.md` (reads and export).
