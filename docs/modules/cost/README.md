# Module spec: cost (M11, cost snapshots)

Status: accepted (built in P1-I4). Brief sections: §9 M11, §8 and §18 (access). Decisions: ADR-0015 (this module), ADR-0010 (module storage), ADR-0013 (roles).

## Purpose
The cost module is a read-only mirror of the cost system. It keeps the cost code hierarchy and, for each imported period, the figures per code: hours, quantity and amount, each as budget, actual, earned, forecast to complete (FTC) and estimate at completion (EAC). A report can say what the matrix was in an earlier period. The module is not the cost system: figures are never edited here, only imported. Operations are in the runbook [schedule-snapshots](../../runbooks/schedule-snapshots.md) (the cost import section); the increment report is `docs/reports/P1-I4.md`.

## Record types
| Type | Key | Tables | Workflow |
|---|---|---|---|
| `cost.CostCode` | the code (`4210-PIP-WLD`) | `cur_cost_costcode` (the latest matrix), `cur_cost_snapshot_value` (the figures per snapshot) | none |
| `cost.CostSnapshot` | `<period>@<revision>` (`2026-09@1`) | `cur_cost_cost_snapshot` | none; a corrected file is the next revision of the period |

## Events
| Event type | Meaning |
|---|---|
| `CostCode.Defined` | A cost code was mirrored (parent, unit of measure, description) |
| `CostCode.Revised` | Its description, parent or unit changed in a later snapshot |
| `CostCode.MeasuresRecorded` | The figures of one snapshot for the code |
| `CostSnapshot.Defined` | One imported period: source name, as-of date, counts, SHA-256 of the file |

## Import (`ImportCostSnapshot`)
`tl cost import FILE --project P --period 2026-09 --as-of 2026-09-30` reads a CSV export and **previews** what it would create and change (nothing is written). With `--apply` an admin imports it as one correlated batch: new codes, revised codes, the figures, and the snapshot. The reader is strict and bounded: at most 10 MiB, 20 000 rows, 60 columns, 20 000 characters per line, 20 levels of hierarchy, figures of at most 1e15 with a plain decimal shape; control characters and text-direction marks are refused with the same text rules as the rest of the platform (`tl_core.text`). The same plan runs in the preview and in the apply, so they cannot disagree. A late snapshot (an earlier as-of date) adds history and leaves the matrix of a later one alone.

## Who can do what
| Act | Who |
|---|---|
| Preview an import (writes nothing) | any signed-in person |
| Apply an import | admin (the figures are money and Phase 1 has no cost role) |
| Reads: codes, snapshots, one code's history | `document.read` |
| Agents | read only; no agent applies an import |

## Reports and reading
* `tl cost report budget [--unit hours|quantity|amount] [--parent CODE] [--over]`: per cost code the budget, actual, earned, forecast to complete and estimate at completion of the latest snapshot, the variance (budget minus EAC, negative is over budget), the percentage spent and how many records link to the code. A figure the snapshot did not state is `-`, never zero.
* `tl cost report uncoded --type T`: the records of a type that no active link `references` a cost code from.
* Reads: `tl cost snapshots|codes|show`, the API (`/projects/{project}/cost-snapshots`, `/projects/{project}/cost-codes`), the TUI client and thirteen MCP tools shared with the schedule module (`list_cost_codes`, `get_cost_code`, `list_cost_snapshots`).
* The functions are `tl_mod_cost.reports`; every query is bound to the project scope.

## Links
A record may link to a cost code with the core `AddLink` (relation `references`); the link follows the code key and does not pin a snapshot.
