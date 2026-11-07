# P2-I3-T05b — `tl mat` read verbs and `tl mat report`

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: T05a, T04a (merged)
Branch: `p2/i3-t05b-cli-reads`

## Goal
A new Typer group `tl mat` with the read verbs over `tl_mod_materials.views` and `tl_mod_materials.reports`, in the style of `tl cost` (one line per fact, two spaces between fields,
no writes). The group is NOT added to `tl_cli/main.py` here (registry glue, supervisor, after P2-I1 merges); the acceptance script drives `tl_cli.mat.app` directly. T05c adds the write verbs to the same group.

## Brief references (pasted)
> `tl mat item|loc|po|receipt|stock|lot|mto|report` read verbs (spec §9 T05); reports `stock_on_hand`, `movement_log`, `mto_status`, `shortages`, `heat_trace`, `consumables_by_cost_code`, `--format csv` formula-safe (T05a `to_csv`).
> The CLI process viewer is set by `main.py` from the session (line 239 `confidentiality.set_viewer`); the verbs pass no `viewer`. Reads open `open_uow(db, readonly=True)` with `ctx.obj` as the `DbTarget`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views (signatures: docs/tickets/P2-I3/T04a-api-reads.md Interfaces; models in views.py)
stock(conn, scope, *, lot, location, item, heat, subtree, limit) -> list[StockRowView]      lot_detail(conn, scope, key) -> LotDetailView
movements(conn, scope, *, lot, since, until, kind, limit) -> list[MovementView]
receipts(conn, scope, *, open_only, missing_mtr, limit) -> list[ReceiptView]                 receipt_detail(conn, scope, number) -> ReceiptDetailView
locations_tree(conn, scope, *, limit) -> list[LocationView]                                  po_lines(conn, scope, *, q, limit) -> list[PoLineView]
mto_lines(conn, scope, *, work_package, short_only, limit) -> list[MtoLineView]              items(conn, *, project, limit) -> list[MaterialItemView]
# tl_mod_materials.reports: REPORT_NAMES, build_report(conn, scope, name, *, since, until, heat, cost_codes) -> Report(name, columns, rows, truncated), to_csv(report) -> str
# tl_cli.derive_support: Project (the --project option), OptProject, cell(value, width=40), fail(msg), service_errors()
```
Create `tl_cli/mat.py` (`app = typer.Typer(help="Materials: items, locations, stock, receipts, take-offs.", no_args_is_help=True)`; `mat_read.register(app)`; `mat_report.register(app)`; sub-groups
`receipt` and `mto` made with `typer.Typer` and `app.add_typer`, so T05c can add `receipt receive` and `mto assign`), `tl_cli/mat_read.py`, `tl_cli/mat_report.py`. Verbs (all take `--project`, except `item`, where it is optional; `--limit`
`min=1 max=1000` default 100 on lists):
- `stock [--lot --location --item --heat --subtree]`: header `stock rows: <n>`, then `<lot>  <heat or ->  <item_code>  <location>  on hand <q>  reserved <q>  available <q>  <uom>  <item_title>`
- `lot KEY`: `lot <key>  heat <h>  <item_code>  <item_title>  receipt <n or ->  po line <k or ->`, then one line each: `qty <location>  on hand <q>  reserved <q>  available <q>`, `reserved <mto_line>  <location>  <q>`, `move <date>  <kind>  <q> <uom>  <from or ->  <to or ->  <actor>` (last ten)
- `movements [--lot --since --until --kind]`: `movements: <n>`, then `<date>  <kind>  <lot>  <item_code>  <+/-><q> <uom>  <from>  <to>  <actor>` (sign from `direction`; date = `recorded_at[:10]`)
- `receipt list [--open --missing-mtr]`: `<number>  <state>  <received_on>  <location>  lines <n>  mtr <state>  <title>`; `receipt show NUMBER`: the header line, then `line <n>  <item_code>  <q> <uom>  heat <h or ->  <condition>` and `file <slot or ->  <filename>  <status>`
- `loc`: `<code>  <title indented 2 spaces per depth>  <kind>  lots <n>  lines <n>`; `po [--q]`: `<key>  <item_code>  ordered <q>  received <q> <uom>  promised <date or ->  <supplier_text>`
- `item [--project]`: `<code>  <category>  <base_uom>  projects <n>  <retired or active>  <title>`; `mto list [--work-package --short-only]`: `<key>  <item_code>  required <q>  reserved <q>  issued <q>  short <q>  for <work_package or ->  <item_title>`
- `report NAME [--project] [--since --until --heat] [--format table|csv]`: `table` = columns joined by two spaces, header first, then `rows: <n>` (and `truncated` when set); `csv` = `to_csv` output verbatim. Unknown name, or `heat_trace` without `--heat`: `fail(...)` (exit 1).
  For `consumables_by_cost_code` pass `cost_codes={c.id: c.code for c in tl_mod_cost.views.cost_codes(conn, scope)}`.
Quantities: `format(Decimal, "f")` with trailing zeros kept as the view gives; an empty list prints `no <things> in project <p>` and exits 0. Errors via `service_errors()` (`LotNotFoundError`, `ReceiptNotFoundError` -> `error: ...`, exit 1).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost.py` (group wiring), `cost_read.py`, `cost_report.py` (verb style), `derive_support.py` (lines 25-100)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (models), `reports.py`
- `dev/accept/P2-I3/T05a.py` (how the seed ledger copy is opened)
may explore: `packages/tl-cli/tests/test_cli_cost_read.py` (how a read verb is driven)

## Allowed paths
- `packages/tl-cli/src/tl_cli/mat.py`, `mat_read.py`, `mat_report.py` (create)
- `dev/accept/P2-I3/T05b.py` (create), `docs/reports/P2-I3/T05b.md` (create)
Not here: `main.py`, `views.py`, `reports.py`, pyproject, any write verb, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T05b.py
```
`T05b.py` (you write it, exit 0, one `PASS <check>` per line): copy `.accept/p2-i3.db` to a temp dir, run each verb with `typer.testing.CliRunner().invoke(tl_cli.mat.app, [...], obj=<target>)` for project `P123`:
`stock` header says 2 or more rows and the heat `H-7781` appears; `stock --heat H-0000` prints `stock rows: 0`; `lot P123-RCPT-0001@1` shows a `qty` line and exits 0, an unknown lot exits 1 with `error:`; `movements` lines carry `<date>  <kind>`;
`receipt list` shows `P123-RCPT-0001`, `receipt show P123-RCPT-0001` has 2 `line` lines; `loc` has 9 lines under the header; `po` 15; `item` 50 (no `--project`); `mto list --work-package P123-CWP-PIP-0001` 3 lines, `--short-only` only lines with `short` above 0;
`report stock_on_hand` table has the header `Lot` first, `report shortages --format csv` first line is the CSV header, `report heat_trace` without `--heat` exits 1, `report nope` exits 1; no output line contains `None`; no verb writes (event count of the copy is unchanged).

## Tests to add
None (T11: `packages/tl-cli/tests/test_cli_mat_read.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T05b: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a view lacks a parameter listed above, if a verb needs the `viewer` argument to read, or if the group cannot be driven without `main.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
