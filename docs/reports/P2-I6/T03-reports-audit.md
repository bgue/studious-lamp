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
| 10 | Materials | consumable usage by cost code | `tl mat report consumables_by_cost_code` | `/projects/{project}/materials/reports/{name}` | unverified | OK | - |
| 11 | Materials | heat number traceability | `tl mat report heat_trace --heat H` | `/projects/{project}/materials/reports/{name}` | yes | OK | - |
| 12 | Requisitions/WO | open requisitions | `tl req ls` (`--state`, `--kind`) | `/projects/{project}/requisitions` (list) | yes | OK | - |
| 13 | Requisitions/WO | scaffold register (status, tag colour, inspection due) | none | none | n/a | BLOCKED-BY I4-B | D03-scaffold-register |
| 14 | Requisitions/WO | scaffold quantities on hire | none | none | n/a | BLOCKED-BY I4-B | D04-scaffold-quantities-on-hire |
| 15 | Requisitions/WO | labor requisition forecast by craft/week | none (`tl req ls --kind labor` lists, does not forecast) | none | n/a | GAP | D05-labor-requisition-forecast |
| 16 | Requisitions/WO | WO backlog | `tl wo ls` (`--state`, `--assigned`) | `/projects/{project}/work-orders` (list) | yes | OK | - |

Notes:
1. Non-empty: from the demo scripts and the tests named in the report; `acc_t05a` asserts non-empty for `movement_log`, `stock_on_hand` and `heat_trace` H-7781; `consumables_by_cost_code` is not asserted anywhere (unverified). Long seed not run.
2. "constraints by type" is mapped to `constraints_by_category` (`awp_report.py` maps the name to the `category` field): an assumption, see Open questions.
3. Requisitions and WO rows are list reads (`ls`) with no report name in the CLI or the API; scaffold and equipment rows wait for I4-B; the forecast is deferred (`DEFERRED.md`, roadmap 3c).
