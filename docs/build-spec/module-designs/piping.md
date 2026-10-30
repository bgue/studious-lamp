# M6 — Piping: lines, isos, spools, welds, NDE, bolted joints

Brief §9 M6, §10.5 (weld daily log, boltup entry), §12, §16 Phase 3. Plan `09-phase3-plan.md` I3 (lines, isos,
spools, welds, NDE, qualifications) and I4 (bolted joints, boltup). Status: design v0.1.

## Users and stories
Piping superintendent, welding foreman, weld log clerk, QC welding inspector, welding engineer (WPS,
qualifications), NDE coordinator and NDE contractor (inbound), bolting technician, materials (heat numbers),
fabrication shop (party).
- As a **weld log clerk** I enter the day's fit-ups and welds by iso in a grid, and the screen tells me before Enter
  if the welder is not qualified, has lost continuity, or the WPS is not pinned.
- As an **NDE coordinator** I see which welds the selection rules picked, which requests are open with the
  contractor, and the rejects that triggered penalty selection and repair welds.
- As a **piping superintendent** I see inch-dia and weld counts earned per iso and IWP without a spreadsheet.
- As a **bolting technician** I record a joint's torque with the tool I used, and the system refuses a tool out of
  calibration.

## Records and states
| Record | States |
|---|---|
| `Line` | Design → Installed → Tested → Reinstated (follows welds, joints, test packages); owner decision: lines are not tags |
| `Isometric` | Register of iso numbers; revision is the pinned document revision |
| `Spool` | Planned → In fabrication → Fabricated → Shipped → Received → Installed |
| `Weld` | Planned → Fit-up → Welded → Visual accepted → NDE requested → NDE accepted; NDE rejected → Repair weld (links original, index R1, R2); PWHT done where required; Complete |
| `WelderQualification` | Valid → Expiring → Expired; continuity lapses per process and position |
| `NDESelectionRule`, `NDERequest`, `NDEResult` | Request: Requested → Reported → Accepted / Rejected |
| `BoltedJoint` | Open → Assembled → Torqued → Verified → Broken for test → Reinstated |
| `BoltupRecord` | One per pass; tool and calibration link |

## Logs and record screens (log standard)
**Weld log** (home), filtered by iso, line, welder or IWP. Columns: Weld, Iso and rev, State, Type, Size, Welder,
Weld date, NDE (method and result), Repair, Heat. Panel: identity `W-0127 · P-1234-ISO-07 rev C`; state `NDE
requested · since 2026-11-02`; summary `BW 6" sch 40 · field · welder J. Lee · WPS-14`. Sections: Status (fit-up,
weld, visual, NDE, PWHT as a table Step, Date, By, Result), Materials (heat numbers of both sides, lot links),
NDE (table Request, Method, State, Report), Repairs, Links (iso, spool, line, IWP, test package), Files (NDE report).
Actions: Planned: Record fit-up. Fit-up: Record weld (guards: qualification, continuity, WPS pinned). Welded:
Record visual. Visual accepted: (system selects NDE), Request NDE. NDE rejected: Create repair weld. Any: Record
PWHT, Raise NCR, Open thread. Agents: none beyond reads.
**Weld daily log** (fast entry, §10.5): choose an iso, a grid with one row per weld: fit-up date, weld date, welder,
WPS; guard failures show in the row before Enter; a soft block raises a constraint with source `check` (R-P3-9).
**NDE backlog.** Request, Welds, Method, State, Requested, Age, Contractor. Actions: Record result (user or inbound),
Cancel request.
**Welder register.** Welder, Process, Positions, Range, Expiry, Last weld, Continuity. Action: Record qualification.
**Spool tracker.** Spool, Iso, State, Shop, Location, Welds (done/total), Heat. **Line list.** Line, Class, Size,
Service, Test package, State.
**Joint register.** Joint, Line, State, Size and rating, Tool, Torqued, Verified, Test package. **Boltup entry**
(fast entry): joint, tool, measured values, passes; the tool's calibration state is shown before Enter. Actions:
Record boltup, Verify, Break for test, Remake.
**Tiles:** NDE backlog by method, reject rate this month, welds awaiting PWHT, joints to reinstate.

## Workflows and approvals
Weld map import from derived iso data (`PublishMapping` kind `weld_map`, controller, compensable) with weld number
validation; NDE selection per piping class percentage with lot management and penalty selection on rejects (job
`piping.nde_select`); welder qualification and continuity at weld record time; repairs link the original and bump
the repair index; joint break and remake cycles ledgered with the tool's calibration record; progress quantities
(count, inch-dia, joints torqued) feed the Phase 2 rules of credit and roll up to IWP, CWP and cost code; welds
supersede the generic scope items of M3 by a typed column.

## Links to other modules
Documents (iso revision pinned, WPS, WPQ, NDE report, procedure); IWP (scope, progress); materials (heat → lot →
receipt → MTR); quality (inspections, NCR on rejects, deficiencies); test packages (M7 readiness reads weld and joint
states); subsystems (M8); models (spatial context via spool, iso, line); cost codes (quantities); external party
(NDE contractor, fabrication shop).

## Integrations
Inbound NDE results: an `InboundEndpoint` fixture with HMAC and a JSONata mapping to `RecordNDEResult` (service actor
with `user` access; refused for a weld with no open request). Webhooks `NDE.Rejected`, `Weld.Completed`,
`Spool.Received`. MCP read tools (weld, iso progress, NDE status). Threads `/raise ncr` against welds. Feed burst
cards ("J. Lee recorded 14 welds on ISO-1234 rev C"). **(proposed)** The §20.2 bulk uploader lands here: NDE reports
matched to welds by filename pattern, reviewed in a grid before commit.

## Reports (§12)
Weld log; weld progress by line, iso and area; welder performance and repair rate; NDE status and backlog; NDE reject
rate by welder and method; PWHT status; boltup log and joint status. Lake: `mart_weld_progress`, `mart_nde_rejects`.

## Confidentiality and roles
All records `internal`. Record a weld, visual or boltup: `user` (crew or clerk); weld map import, NDE rule changes,
qualification records: `controller`; NDE result: `user` or the inbound service actor; a fabrication shop or NDE
contractor as a party sees its own spools and requests (Phase 3 I8). Agents read only.

## First increment vs later
First (Phase 3 I3): lines, isos, spools, welds, qualifications, weld map import, daily log, NDE rules, requests,
results, inbound endpoint, progress into rules of credit, reports, marts. Then I4: bolted joints, boltup records,
boltup entry, break and remake.
Later: spool shipping and receiving against M4; PMI and hardness as NDE methods; PWHT charts as files; welder
performance dashboards; offline daily log and boltup entry (I5, I8); PWA entry (Phase 5); a line-list loader.

## Open questions for the owner
P3-Q6 hard or soft continuity blocks; P3-Q7 NDE contractor endpoint or account; P3-Q12 welder qualifications as a
loader or fixtures. New: the line list has no loader today (lines are not tags): is the line list the first M6 legacy
load? Who may change NDE selection percentages mid-project (controller, or a welding engineer role)? Repair numbering
convention (`W-0127R1`) and whether a cut-out gets a new weld number.
