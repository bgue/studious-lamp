# Cost display and commenting

Brief §13 ("costing frontend"), §9 M11 (the mirror, built in P1-I4), §12, §16 Phase 5. Plan `11-phase5-plan.md` I1.
Status: design v0.1. Reads only data that exists today; **(proposed)** it can be built earlier than Phase 5 when
the owner wants it (README §2 row 11).

## Users and stories
Cost controller, project manager, superintendent and area manager (read), workface planner (earned vs budget),
commercial lead (values behind a notice).
- As a **cost controller** I open the cost code tree for a period and see hours, quantities and money across budget,
  actual, earned, forecast to complete and estimate at completion, with variances that stand out.
- As a **superintendent** I drill from a cost code to the IWPs and welds that earned its quantities this week.
- As a **PM** I leave a comment on a code for the period review and see last period's comments beside it.
- Later, as a **cost controller** I edit a forecast and push it back to the cost system after approval.

## Records and states
| Record | States |
|---|---|
| `CostCode`, `CostSnapshot` (M11, built) | The mirror; imported per period by admin; never edited here |
| Earned quantities per code (M3 rollup, Phase 2) | Read from the rollup events; exported as CSV |
| Comments | **(proposed)** the record thread of the `CostCode` with a period tag (`#period:2026-W43`) rather than a new record; threads are built and ledgered; a `CostComment` record only if the owner wants comments without threads |
| `ForecastEdit` (later) | Draft → Submitted → Approved → Pushed; one per code and period |

## Logs and record screens (log standard)
**Cost code tree** (home): the hierarchy with a period selector (`[` `]` previous and next period, `p` pick) and a
measure chooser (hours, quantity, money). Columns: Code, Description, Budget, Actual, Earned, FTC, EAC, Variance
(number and %), with amber and red by thresholds in the colour rule (meaning only, never decoration). Filters by WBS
node, discipline, variance over a threshold. Panel: identity `4210 · Piping field welds`; state `Period 2026-W43 ·
as of 2026-10-27`; summary `hours · budget 12 400 · earned 7 180 · 58% · FTC 5 900`. Sections: Measures (table
Measure × budget, actual, earned, FTC, EAC), Trend (last six periods as a small table or Unicode bars),
Contributing records (table Record, Type, Quantity, UOM, Period: IWPs, welds, joints, consumable issues), WBS nodes
(allocation %), Comments (last three, Enter for the thread), Links. Actions: Open thread, Comment (`c`), Export view
(`x`), Drill to records. Later: Edit forecast (cost role), Submit, Approve.
**Period compare**: two snapshots side by side (the XER compare pattern) with movement per measure.
**Records without cost code** (data health, M11 report) as a log with action Set cost code.
**Tiles:** codes over budget, earned vs burned this period, records without a cost code.

## Workflows and approvals
None in the first increment beyond import (admin) and comments. Forecast editing later: a draft per code and period,
submitted by a cost controller, approved by the PM, pushed by a connector (Q1; human gate), with the pushed values
ledgered and the cost system staying the source of truth.

## Links to other modules
M3 (WBS allocation, rollup, progress export), M4 (consumable issues by cost code), M6 and M7 (quantities), M9 (work
orders and requisitions by code), M5 (NCR rework by code), M10 Commercial (values by cost code on notices), schedule
(activities by cost code where the P6 export carries them).

## Integrations
Cost snapshot import (built; CSV per period); a cost system connector for import and later write-back (Q1); export of
the view as CSV or XLSX; MCP read tools (`cost_code`, `variance_report`); feed digest card per period close
**(proposed)**.

## Reports (§12)
Quantities by cost code vs budget; records without cost code; IWPs vs P6 dates; variance by period; earned vs
burned by code and discipline. Lake: cost trend by period.

## Confidentiality and roles
**(proposed)** Money is visible only to a cost role (P2-Q3) and admins; hours and quantities to every `user`; a
subcontractor party sees nothing here. Comments are the thread's visibility. Forecast edits need the cost role;
pushing needs admin and the connector gate. Agents read what their principal may read and propose nothing here.

## First increment vs later
First (Phase 5 I1, or earlier): the tree with the measure matrix and period selector, variance rules, drill-through,
comments as threads, period compare, exports, tiles, reports. Later: forecast editing and write-back (separate
increment after Q1); cash flow and commitments if the cost system supplies them; cross-project benchmarking (lake,
Phase 5 I4).

## Open questions for the owner
Q1 which cost system and method; P2-Q3 a cost role. New: may everyone see money, or hours and quantities only
**(proposed split)**? Are comments as record threads acceptable, or must a comment be its own numbered record for
the period review? Is the period a week, a month or the cost system's calendar? Should this module move before Phase 5?
