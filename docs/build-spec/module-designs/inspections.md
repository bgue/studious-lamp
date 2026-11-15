# Inspections — checklists, planned inspections, results, link to punch

This is the high-level design for inspections, brought forward from Phase 3 (`09-phase3-plan.md` Increment 2) as
increment **P2-INSP**. Brief §9 M5, §10.5 (checklist runner), §12. Status: design v0.1, 2026-11-15, owner request of
the same day. Build plan: `docs/tickets/P2-INSP/README.md`. Workface status by QR: `specs/qr-workface.md`.
Rules that bind it: additive only, hidden looks exactly like missing, agents closed by default, five-reader walk on
every new read, reports are CSV/JSONL exports, surfaces come through the ModuleSpec hooks (`12-extension-plan.md` §0).

## 1. Decision: inspections extend the `quality` module

Inspections are new record types inside `quality` (package `tl-mod-quality`, `schema/modules/quality/`), not a new
module. Reasons:

1. A failed inspection raises punch items. Inside one module that is one unit of work with no module-to-module import.
2. P2-PUNCH was built for it: its plan says Phase 3 "adds its classes to the same schema directory and the same
   `ModuleSpec`", and the punch states were chosen to match the deficiency of `quality.md`.
3. One set of quality words and one module role. A QC inspector holds `quality` roles once, not twice.
4. Nothing existing changes: `quality.PunchItem`, its events, words and screens stay as they are.

What it costs: `quality` is an in-tree module whose punch surfaces live in `tl_api.routes`, `tl_mcp` and `tl_cli`.
The new inspection surfaces go in the module's own package and are declared through the hooks (`read_routers`,
`tools`, `cli_groups`, lazy refs; P2-X4 S1). The punch surfaces do not move.

Not in this increment (each stays where the Phase 3 plan has it): the Issue engine, NCR, CAR, QSR, instruments and
calibration, witness sign-off by guest link, the full `ITP` record. `scaffold.ScaffoldInspection` (P2-I4B) is left
alone; see §9.

## 2. Users and what each does

| Who | Does | Access (table word) |
|---|---|---|
| QC inspector | Plans and schedules inspections, runs the checklist at the workface, records the result | `user` on `quality` |
| Foreman | Asks for an inspection of his work package, sees what is planned, due and failed; reads status from a QR | `user` (request), `read` |
| Superintendent | Reads the log by area and package; sees hold points that stop work | `read` |
| QA lead (module superuser) | Publishes checklists, verifies results, cancels, reopens | `controller` on `quality` |
| Agent | Reads; proposes a planned inspection that a person accepts | closed until allowed |

## 3. Records and lifecycles

| Record | Key | States | Offline class |
|---|---|---|---|
| `quality.Checklist` (the question set) | `P123-CHK-0001` | Draft → Published → Retired | `none` |
| `quality.Inspection` | `P123-INS-0001` | Planned → Scheduled → Done → Verified; Cancelled | `draft_only` (see below) |

**Checklist.** Fields: `title`, `discipline` (text ≤ 64), `version` (integer, starts at 1), `questions`, `supersedes_id`.
`questions` is a list of at most 60, each with `id` (`q1`…), `text` (≤ 200), `kind` (`yes_no_na`, `number`, `text`,
`choice`), `required`, `unit`, `min`, `max`, `choices` (≤ 8), `fails_when` (`no`, or out of range). A Published
checklist never changes. A change is a new version: a new record with `supersedes_id`, and the old one is Retired.
This is the "versioned question set" of `quality.md`, held as a record so that it needs no schema package. Three
sample checklists ship as fixtures (`schema/fixtures/quality/checklists/`): hydrotest pre-check, flange joint
make-up, scaffold handover.

**Inspection.** Fields: `subject_id` (the record inspected: an IWP, a tag, a scaffold, a document; the confidentiality
subject), `for_iwp_id` (the work package it serves, may equal `subject_id`), `checklist_id` and `checklist_version`
(pinned when scheduled), `point` (`hold`, `witness`, `review`, `surveillance`), `area` (text ≤ 64), `planned_on`,
`scheduled_for`, `inspector`, `result` (`accept`, `reject`, `conditional`), `done_at`, `answers` (the list as
recorded), `note`, `verified_by`, `verified_on`, `reinspection_of_id`, `cancel_reason`.

- The result is computed, not typed: `reject` when a required question fails, `conditional` when a non-required one
  fails, else `accept`. The rule is a pure function (`insp_rules.result_of`), so the screen, the CLI and the handler
  agree.
- A `reject` or `conditional` result raises one punch item per failed question, in the same unit of work, linked
  `raised_against` the inspection. The punch item's source is the inspection's subject, so its visibility follows
  the same record. Category A for a failed required question on a hold point, else B.
- A rejected inspection is not re-run. `ReinspectInspection` plans a new one with `reinspection_of_id`.
- Offline: answers may be captured offline as a draft (`RecordInspectionResult` is the draft command, as
  `RaisePunchItem` is for a walkdown). Numbering, verification and the punch items happen on the authority.

**ITP-lite, and why no ITP record.** An ITP says which inspections a piece of work needs and at which point (hold,
witness, review, surveillance). In this increment that plan is simply the set of Planned inspections linked to the
IWP, each carrying its `point`. That gives the readiness check and the hold-point view without a second record.
The full `ITP` / `ITPLine` with per-party points and approval stays in Phase 3 and later links to these inspections;
no field here needs renaming for it.

## 4. Commands and access words

All are module commands (`by_module` moves, `extra="forbid"`, `expected_version` on state commands). New words go in
`schema/settings/access-words.yaml`.

| Command | Word → table word | Rule |
|---|---|---|
| `CreateChecklist`, `EditChecklist` | `quality.checklist.edit` → user | Draft only |
| `PublishChecklist`, `RetireChecklist`, `ReviseChecklist` | `quality.checklist.publish` → controller | Publish refuses an empty or malformed question list; revise makes version n+1 in Draft |
| `PlanInspection` | `quality.inspection.plan` → user | Subject must be visible to the actor; refusal for a hidden subject reads as a missing record |
| `ScheduleInspection` | `quality.inspection.plan` → user | Needs a Published checklist, a date and an inspector; pins the version |
| `RecordInspectionResult` | `quality.inspection.record` → user | Scheduled only; answers validated against the pinned version; result computed; punch items raised |
| `VerifyInspection` | `quality.inspection.verify` → controller | Never the person who recorded it (fixed message) |
| `ReinspectInspection` | `quality.inspection.plan` → user | From a Done or Verified inspection with `reject` or `conditional` |
| `CancelInspection` | `quality.inspection.cancel` → controller | Planned or Scheduled, with a reason |

Reads use the existing `quality.view`. Six new words. Generic commands on both types: property values, links,
files and the life of links, refused once Cancelled or Retired (the punch pattern). Agents: one proposable command,
`propose_inspection` (a `PlanInspection` a person accepts). No agent tool records, verifies or cancels.

## 5. Readiness for IWPs

`inspections_planned` exists today as a placeholder that always answers `n_a` (`tl_mod_awp.checks_na`). This
increment makes it real, under the same name and the frozen contract (`tl_core/readiness/types.py`). The placeholder's
entry-point line is removed from the awp package and the quality package registers the check (two checks with one
name is an error by contract).

| Answer | When |
|---|---|
| `n_a` | No inspection names this IWP and `quality.inspections.required_for_iwp` is off (the default) |
| `blocked` | The setting is on and none is planned; or a linked inspection is still Planned (no date, no inspector); or a hold-point inspection is Done with `reject` and has no reinspection |
| `pending` | Every linked inspection is Scheduled or better, and one scheduled before the IWP's planned start is not yet Done |
| `ok` | Every linked inspection is Scheduled or better and nothing above applies |

`resolve_via` names the inspections to open; counts are "scheduled or done / all". Cancelled inspections do not count.
The check reads only the quality tables and `watches` `quality.Inspection`, so a change re-evaluates the IWP.
Hold points during the work (a hold not yet released) are shown on the IWP's inspection list and on the scan page;
they do not un-ready an issued IWP. A separate "hold points released" guard on IWP closeout is listed under Later.

## 6. Screens (terminal; log standard and the `tui-layout` skill apply)

- **Inspection log.** Columns: Number, Subject, State, Point (H/W/R/S), Scheduled, Inspector, Result, For (IWP).
  Filters: `o` open, `d` due today or overdue, `h` hold points, `m` mine, by area. Panel: identity
  `P123-INS-0042 · Flange make-up, rack 12`; state `Scheduled · 2026-11-18 · M. Okafor`; summary
  `Hold point · checklist CHK-0003 v2 · for IWP-PIP-0042`. Sections: Scope, Answers (table Question, Answer, Note),
  Punch items raised, Timeline, Files, Links. Actions: Schedule, Run checklist, Verify, Reinspect, Cancel.
- **Run a checklist.** One question per screen, a key per answer (`y`, `n`, `a` for n/a, digits for a number, `t`
  for text), a note line, back and forward, a review page that shows the computed result and the punch items it will
  raise, then one confirm. The screen holds no rule: it calls `insp_rules` and the command.
- **Checklist list and record.** Number, Title, Discipline, Version, State, Questions (count). Record shows the
  questions as a table. Actions: Publish, Revise, Retire.
- The IWP record gains nothing in this increment; its Readiness section shows the check, and the inspections are
  reached through Links. A dedicated IWP tab is under Later.
- Screenshots of the log, the record, the runner and the checklist record go into the tour (`dev/tour/phase2.py`).
- Web: only the scan status page (`specs/qr-workface.md`). Full web twins of these screens are a later web increment.

## 7. CLI, API, MCP, reports

- **CLI** `tl insp plan | schedule | record | verify | reinspect | cancel | ls | show | export` and
  `tl checklist create | edit | publish | revise | retire | ls | show`. Write options take the key a read prints.
  `tl insp record` takes answers as `--answer q1=yes` repeats or `--answers-file` (JSON, bounded).
- **API** read routes `GET /quality/inspections`, `/quality/inspections/{key}`, `/quality/checklists`,
  `/quality/checklists/{key}`, `/quality/inspections/export`; commands through the command door from the module's
  `commands` hook. Hidden or unknown key: the same 404 body. Counts and totals are taken after the visibility filter.
- **MCP** `list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`, `propose_inspection`; each closed
  until listed for the agent.
- **Reports** are exports, nothing more: `tl insp export --format csv|jsonl` (one row per inspection: number, subject
  key, IWP, point, state, result, scheduled, done, inspector, open punch count) and `--answers` (one row per answer).
  The same rows from the API export route. No report engine, no layout.
- Five-reader walk (no clearance, cleared, restricted subject, company admin, agent token) on every route, tool and
  export above.

## 8. Confidentiality

An inspection is hidden through its subject record, exactly as a punch item is hidden through its source. One part is
added to the subject rule in `tl_core/confidentiality.py` (a security row in the plan). A checklist is company
reference data at the lowest class and carries no project text. An inspection may be planned only against a record
that itself names no subject, or one whose subject is stored on it (scaffold), so no chain is longer than two hops.

## 9. Scaffold inspections

`scaffold.ScaffoldInspection` (P2-I4B) stays the record of a tag decision. This increment does not change or replace
it. A QC inspector who wants a full checklist on a scaffold plans a `quality.Inspection` whose subject is the
scaffold; the two are tied by an ordinary link. Folding them into one type is not needed and would break "additive
only".

## 10. Demo clauses (`dev/demos/P2-INSP.sh`, both adapters)

1. Checklist: create, publish; an edit of the published one is refused; revise gives version 2 and retires version 1.
2. Plan a hold-point inspection for an IWP, schedule it, record answers with one required failure: result `reject`,
   one punch item category A appears, linked to the inspection; verify by the recorder is refused, by another
   controller it passes.
3. Reinspect: a new inspection names the first; all answers pass; result `accept`.
4. Readiness: `n_a` with nothing planned; `blocked` while Planned; `ok` once Scheduled; `blocked` again after the
   reject; `ok` after the reinspection is scheduled.
5. Hidden subject: an inspection on a restricted record answers a plain user exactly as a number that never existed,
   over CLI, API, MCP and export; totals unchanged.
6. One state over CLI, API, TUI and MCP; an agent's `propose_inspection` is pending until a person accepts; no tool
   records or verifies.
7. Export: CSV and JSONL have the same rows as `tl insp ls`.
8. With P2-QR merged: the inspection's code resolves to its status card (clause lives in the P2-QR demo).

## 11. Later

Instruments and calibration; witness parties and guest sign-off; the full ITP; checklist import from a file (needs
the untrusted-file envelope); photos per answer; a "hold points released" guard on IWP closeout; an Inspections tab
on the IWP; web twins; a QC inspector actor in the simulator; running a checklist from the phone.

## 12. Owner questions (the build proceeds on the default)

| # | Question | Default |
|---|---|---|
| 1 | Extend `quality` or make a new module? | Extend `quality` (§1) |
| 2 | Must the verifier differ from the inspector, and is verify a QA-lead act? | Yes to both (`controller`, never the recorder) |
| 3 | Is an IWP without any planned inspection ready? | Yes by default (`n_a`); a project turns on `quality.inspections.required_for_iwp` to make it `blocked` |
| 4 | Are question sets as records enough, or are free-layout forms needed? | Question sets only; free layouts are not built |
| 5 | Should a failed question always raise a punch item? | Yes, one per failed question, in the same step; the inspector can void a wrong one afterwards |
| 6 | Do scaffold inspections move into this type? | No; they stay as built and are linked (§9) |
