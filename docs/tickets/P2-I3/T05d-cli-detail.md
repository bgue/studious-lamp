# P2-I3-T05d — `tl mat mto show` and `tl mat item-projects` (the S5 fields)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: T05b (merged), S5 (merged), r9 glue (`mat_detail.py` stub, `register` call in `mat.py`)
Branch: `p2/i3-t05d-cli-detail`

## Goal
Two read verbs over the S5 views: one take-off line with its reservations and open receipts, and the per-project quantities of one company item. Read only; same line style as `mat_read`.

## Brief references (pasted)
> `mto show LINE_KEY --project P`: first the line as `mto list` prints it (`<key>  <item_code>  required <q>  reserved <q>  issued <q>  short <q>  for <work_package or ->  <item_title>`; reuse the code in `mat_read`, import its helper or move nothing), then one line per reservation `reserved <lot>  <location>  <qty> <uom>` and one per open receipt `receipt <number>  <state>  <received_on>  <qty> <uom>  <supplier_text or ->`. With none: `no reservations` / `no open receipts`. Unknown key: `MtoLineNotFoundError` -> `error: ...`, exit 1.
> `item-projects CODE`: `item <code>  projects: <n>`, then `<project>  on hand <q>  reserved <q>  available <q>  <uom>` per project; an unknown or unreadable item prints `no projects for item <code>` and exits 0 (the view answers `[]`).
> Quantities through `mat_read.qty`, empty values through `derive_support.cell`. Read only: `open_uow(db, readonly=True)`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views_detail:
#   class MtoLineDetailView(MtoLineView): reservations: list[ReservationRowView]; open_receipts: list[OpenReceiptView]
#   class OpenReceiptView: number state received_on qty(Decimal) uom supplier_text
#   class ItemProjectView: project title on_hand reserved available (Decimal) uom
#   mto_line_detail(conn, scope, key, *, viewer=None) -> MtoLineDetailView       item_projects(conn, code, *, viewer=None) -> list[ItemProjectView]
# tl_mod_materials.views: ReservationRowView(lot location mto_line mto_line_id qty item_code iwp_id); MtoLineView(key item_code item_title uom required reserved issued short work_package ...)
# tl_cli.mat_read: qty(Decimal) -> str; Limit; (mto_list prints the first line style) ; tl_cli.derive_support: Project, cell, service_errors
# tl_cli/mat_detail.py (stub): def register(app: typer.Typer) -> None  (called from mat.py); sub-group `mto`: mat_read._group(app, "mto")
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/mat_detail.py`, `packages/tl-cli/src/tl_cli/mat_read.py` (whole), `packages/tl-cli/src/tl_cli/mat.py`
- `dev/accept/P2-I3/T05b.py` (the harness to copy)
may explore: `views_detail.py` lines 40-70

## Allowed paths
- `packages/tl-cli/src/tl_cli/mat_detail.py` (edit: fill `register`)
- `dev/accept/P2-I3/T05d.py` (create), `docs/reports/P2-I3/T05d.md` (create)
Not here: `mat.py`, `mat_read.py`, any view, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T05d.py
```
`T05d.py` (you write it, exit 0, one `PASS <check>` per line), as `T05b.py` (CliRunner on `tl_cli.mat.app`, copy of the seed, project `P123`): (1) `mto show` of a seed line key (read the three keys with `mto list`; the key has a random 4-hex suffix) prints the head line then `no reservations` and the open receipts or `no open receipts`; (2) after a reservation posted by a handler in the script (copy the S3 seed script's way to run `handle_reserve_stock`), `mto show` prints a `reserved` line with the lot; (3) an unknown key exits 1 with `error:` and no traceback; (4) `item-projects` of a seed item used in `P123` prints `projects: 1` and the P123 line; an unknown code prints `no projects for item X` exit 0; (5) `tl mat mto ls` and `tl mat receipt ls` (the `ls` alias, glue r9) both exit 0 with `--project P123`.

## Tests to add
None (T11 owns tests).

## Report requirements
Standard report, <= 60 lines, deviations first. Commit subjects `P2-I3-T05d: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if an interface above is missing, or `item-projects` needs a viewer (it must not: the CLI is the controller path, as `mat_read`).

## Blocked
(implementer writes here)
