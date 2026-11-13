# P2-I6-T03 — §12 base reports audit (M3 AWP/WBS, M4 Materials, M9 Requisitions/WO)

| # | Module | §12 report | CLI command | API route | Non-empty on seed? | Status | Draft ticket |
|---|---|---|---|---|---|---|---|
| 1 | AWP/WBS | CWP/IWP status | `tl awp report cwp_status`; `tl awp report iwp_status` | `/projects/{project}/awp/reports/{name}` | yes | OK | - |
| 2 | AWP/WBS | IWP readiness & constraint log | `tl awp report iwp_readiness`; `tl awp report constraint_log` | `/projects/{project}/awp/reports/{name}` | yes | OK | - |
| 3 | AWP/WBS | constraints by type/owner/age | `tl awp report constraints_by_category` (type); `constraints_by_owner`; `constraints_by_age` | `/projects/{project}/awp/reports/{name}` | yes | OK | - |
| 4 | AWP/WBS | backlog of ready IWPs (weeks of backlog) | none | none | n/a | GAP | D01-awp-ready-iwp-backlog |
| 5 | Materials | stock on hand by location/item | `tl mat report stock_on_hand` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 6 | Materials | transaction log | `tl mat report movement_log --since --until` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 7 | Materials | MTO vs received vs issued | `tl mat report mto_status` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 8 | Materials | shortages against IWPs | `tl mat report shortages` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 9 | Materials | equipment utilisation & location | none | none | n/a | BLOCKED-BY I4-B | D02-materials-equipment-utilisation |
| 10 | Materials | consumable usage by cost code | `tl mat report consumables_by_cost_code` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 11 | Materials | heat number traceability | `tl mat report heat_trace --heat H` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 12 | Requisitions/WO | open requisitions | `tl req ls` (`--state`, `--kind`) | `/projects/{project}/requisitions` (list) | no | OK | - |
| 13 | Requisitions/WO | scaffold register (status, tag colour, inspection due) | none | none | n/a | BLOCKED-BY I4-B | D03-scaffold-register |
| 14 | Requisitions/WO | scaffold quantities on hire | none | none | n/a | BLOCKED-BY I4-B | D04-scaffold-quantities-on-hire |
| 15 | Requisitions/WO | labor requisition forecast by craft/week | none (`tl req ls --kind labor` lists, does not forecast) | none | n/a | GAP | D05-labor-requisition-forecast |
| 16 | Requisitions/WO | WO backlog | `tl wo ls` (`--state`, `--assigned`) | `/projects/{project}/work-orders` (list) | no | OK | - |

Notes:
1. Non-empty evidence, AWP rows 1-3: `dev/seed/demo_project/awp.py` makes 50 CWPs in four states (lines 63, 66) and `dev/seed/demo_project/constraints.py` makes 24 IWPs and about 40 constraints on 20 of them, in the categories of `TEXTS` (lines 1, 55, 59-71). The P2-I2 checks `status_checks` (3 IWPs counted) and `readiness_checks` (blocked names) in `dev/accept/P2-I2/t09a_checks.py` run on the test world `awp_world`, not on `dev/seed`. Materials rows 5-8 and 11: `dev/accept/P2-I3/T05a.py` `check_csv_quotes_formula_reason` asserts the movement log is non-empty, `check_stock_equals_view` and `check_route_json_200` assert stock rows, `check_mto_status_sums_work_package` asserts 3 lines, `check_heat_trace_h7781` asserts On hand rows for H-7781; `shortages` is in `dev/demos/P2-I3.sh` lines 268-270. These P2-I3 checks run on the ledger that `dev/accept/P2-I3/S3.py --keep` builds, not on `dev/seed`. Seed evidence for rows 5-8 and 11: `dev/seed/demo_project/materials.py` makes receipts with 3 to 5 heats per line (`heat_no`, lines 345-366), the stock lots they make, movements of every kind, and a take-off with reservations and shortages (module docstring, lines 1-3).
2. Row 10 is `yes` by seed construction only: `dev/seed/demo_project/materials.py` lines 693-700 issue 100 movements and always set a cost code on a consumable issue (12 consumable items in `dev/seed/demo_project/data/materials/items.csv`); the lot is drawn at random and no test asserts a row. Rows 12 and 16 are `no` on seed: `dev/seed` has no requisitions or work orders (a seed section is a later item); the reads are shown non-empty by `packages/tl-cli/tests/test_req_read.py` (`test_req_ls_count_equals_the_data_lines_and_order_is_by_key` asserts `requisitions: 3`, `test_wo_ls_after_approve_and_schedule` asserts `work orders: 1`) and `dev/demos/P2-I4.sh` lines 176-186. The long seed was not run.
3. Assumptions: "constraints by type" is mapped to `constraints_by_category` (`awp_report.py` maps the name to the `category` field); rows 12 and 16 are list reads (`ls`) with no report name in the CLI or the API; scaffold and equipment rows wait for I4-B; the labour forecast is deferred (`docs/build-spec/DEFERRED.md`, roadmap 3c).
