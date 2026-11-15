# Permits — permit to work, isolations, gas tests

This is the high-level design for a permit-to-work module, increment **P2-PTW**. Brief §7.1 (an IWP expects a permit by
Issued), §9 M3 (readiness "permits planned", pack section "permits"), §9 M9 (scaffold ↔ permits). Status: design v0.1,
2026-11-15, owner request of the same day. Build plan: `docs/tickets/P2-PTW/README.md`. Workface status by QR:
`specs/qr-workface.md`. The same binding rules as `inspections.md` apply (`12-extension-plan.md` §0).

Throughline records who asked, who approved, who issued, what was tested and when a permit was valid. It does not
replace the site's safety rules or the signed paper where the law or the client asks for it.

## 1. Decision: a new module `permits`

Package `tl-mod-permits` (`packages/tl-modules/permits`, `tl_mod_permits`), schema `schema/modules/permits/`, docs
`docs/modules/permits/`. It is its own module because safety has its own people and its own module role (a permit
authority is not a QC lead), and nothing in it needs code from another module. It is the first module built after
the hooks: commands, read routes, tools and CLI groups all live in the module's package and are declared in its
`ModuleSpec` as lazy references (P2-X4 S1; the runbook of X4 T04 is the pattern).

## 2. Users and what each does

| Who | Does | Access (table word) |
|---|---|---|
| Foreman (permit holder) | Requests a permit for his work package, accepts it at issue, revalidates each shift, hands it back | `user` on `permits` |
| Anyone on the job | Suspends a permit (stop work) | `user` |
| Supervisor or area owner | Approves or rejects a request | `controller`, never the requester |
| Permit authority (safety; module superuser) | Issues, resumes after a suspension, closes, cancels; verifies isolations | `controller` |
| Gas tester, isolation crew | Record gas tests; apply and remove isolations | `user` |
| Superintendent | Reads the permit board by area | `read` |
| Agent | Reads; proposes a request that a person accepts | closed until allowed |

## 3. Permit types: the first set

`hot_work`, `confined_space`, `work_at_height`, `excavation`, `isolation` (lockout of energy: electrical, mechanical,
process), and `general` (cold work, the catch-all). The set is an enum in the schema; a seventh type is an additive
schema change. What each type demands is data, in one fixture file (`schema/fixtures/permits/types.yaml`), not code:

| Type | Gas test | Isolation | Longest validity | Precautions asked at issue (tick list) |
|---|---|---|---|---|
| `hot_work` | Yes (flammables) | No | 1 shift | Fire watch named, extinguisher, combustibles cleared, spark containment |
| `confined_space` | Yes (O2, flammables, toxics) | Yes | 1 shift | Attendant named, rescue plan, ventilation, entry log |
| `work_at_height` | No | No | 7 days | Fall protection, exclusion zone, tool lanyards, scaffold tag checked |
| `excavation` | No | No | 7 days | Services located, shoring or batter, barriers, spoil set back |
| `isolation` | No | Yes | 7 days | Isolation points listed, locks and tags applied, zero energy proven |
| `general` | No | No | 7 days | Job hazard assessment attached |

Every type is revalidated at each shift change whatever its longest validity.

## 4. Records and lifecycles

| Record | Key | States | Offline class |
|---|---|---|---|
| `permits.Permit` | `P123-PTW-0001` | Requested → Approved → Active ⇄ Suspended → Handed back → Closed; Rejected, Cancelled | `none` |
| `permits.Isolation` | `P123-ISL-0001` | Applied → Verified → Removed | `none` |
| `permits.GasTest` | `P123-GAS-0001` | none (a reading is a fact) | `none` |

Permits are online only: a permit is an act on the authority, like a scaffold tag. What the crew does without signal
is in `specs/qr-workface.md` §8.

**Permit.** Fields: `permit_type`, `for_record_id` (the IWP or other record the work belongs to; the confidentiality
subject), `area` (text ≤ 64), `location_text` (≤ 120), `work_description` (the envelope description), `holder`,
`requested_by`, `needed_from`, `needed_until`, `approved_by`, `issued_by`, `issued_at`, `valid_until`,
`precautions` (the ticked list, from the type), `revalidation_count`, `last_revalidated_at`, `suspend_reason`,
`handback_note`, `closed_by`, `reject_reason`, `cancel_reason`, `lapse_flagged_for`.

- **Request.** The foreman names the type, the work, the place, the window and the record it is for.
- **Approve or reject.** A controller who is not the requester. Reject needs a reason.
- **Issue.** The permit authority ticks the type's precautions, and the permit becomes Active with `valid_until` at
  the end of the current shift (or the window's end if sooner). Issue is refused when the type needs a gas test and
  there is no passing test newer than `permits.gas_test.valid_minutes`, or needs an isolation and a linked isolation
  is not Verified, or a precaution is unticked.
- **Revalidate.** At each shift the holder confirms conditions are unchanged; `valid_until` moves to the end of the
  next shift, never past the type's longest validity from issue. A gas-test type needs a fresh passing test first.
- **Lapsed.** An Active permit whose `valid_until` has passed is shown as **Lapsed** everywhere. Lapsed is a derived
  word (a pure function of state, `valid_until` and the clock), not a workflow state, so no clock writes a state
  change. A daily-and-shift job flags each lapse once with a `Permit.Lapsed` event so readiness and feeds notice.
  A lapsed permit is revalidated or handed back; it is never silently active.
- **Suspend and resume.** Anyone with `user` can suspend with a reason (the stop-work rule). Only the permit
  authority resumes. A failing gas test on an Active permit of a gas-test type suspends it in the same step.
- **Hand back and close.** The holder hands back with a note that the site is safe; the authority closes. Closed,
  Rejected and Cancelled are final. A later change of mind is a new permit.

**Isolation** (a record, because it has a life and is shared). Fields: `point_text` (≤ 120, what is isolated),
`point_record_id` (a tag or equipment record when one exists), `energy` (`electrical`, `mechanical`, `process`,
`other`), `method` (≤ 120), `lock_number`, `tag_number`, `applied_by`, `applied_at`, `verified_by`, `verified_at`,
`removed_by`, `removed_at`. A permit depends on isolations by a link; one isolation can serve several permits.
Verification is by a controller who did not apply it. Removal is refused while any permit that depends on it is
Approved, Active or Suspended (the refusal names a permit the actor cannot see only as "a permit you cannot see").

**Gas test** (a record, because it is evidence with a time and a tester). Fields: `permit_id`, `taken_at`, `tester`,
`instrument_text` (≤ 64; a link to an instrument record when calibration exists), `o2_pct`, `lel_pct`, `h2s_ppm`,
`co_ppm`, `result` (`pass`, `fail`; computed from the limits in settings, never typed), `note`.

**Type-specific extras** (excavation depth, fire watch name beyond the tick, client permit number) are property
values on the permit, added by a schema package when a project wants them (P2-X5a). None is built here.

## 5. Commands and access words

| Command | Word → table word | Rule |
|---|---|---|
| `RequestPermit` | `permits.request` → user | `for_record_id` visible to the actor; a hidden one reads as missing |
| `ApprovePermit`, `RejectPermit` | `permits.approve` → controller | Never the requester (fixed message) |
| `IssuePermit` | `permits.issue` → controller | The guards of §4; sets `valid_until` |
| `RevalidatePermit` | `permits.revalidate` → user | Active or Lapsed; holder or a controller |
| `SuspendPermit` | `permits.suspend` → user | Active or Lapsed, with a reason |
| `ResumePermit` | `permits.resume` → controller | Suspended; the issue guards run again |
| `HandBackPermit` | `permits.handback` → user | Holder or a controller |
| `ClosePermit`, `CancelPermit` | `permits.close` → controller | Close from Handed back; cancel from Requested or Approved |
| `ApplyIsolation`, `RemoveIsolation` | `permits.isolation.apply` → user | Remove runs the dependency check |
| `VerifyIsolation` | `permits.isolation.verify` → controller | Never the person who applied it |
| `LinkIsolation`, `UnlinkIsolation` | `permits.isolation.apply` → user | Not while the permit is Active |
| `RecordGasTest` | `permits.gastest.record` → user | Result computed; a fail suspends an Active permit |

Plus `permits.view` → read. Twelve words. Agents: one proposable command, `propose_permit` (a `RequestPermit` a
person accepts). No agent tool approves, issues, revalidates, resumes or closes.

Settings (new, project scope, lockable): `permits.shift_hours` (12), `permits.shift_start` (`06:00`),
`permits.gas_test.valid_minutes` (240), `permits.required_for_iwp` (false), and the gas limits `permits.gas.o2_min_pct`
(19.5), `o2_max_pct` (23.5), `lel_max_pct` (5), `h2s_max_ppm` (5), `co_max_ppm` (25). The limits are conservative
defaults; the project's safety lead owns the values.

## 6. Links: IWPs, readiness, scaffold, areas

- **IWP.** A permit is requested for an IWP (`for_record_id`) and linked to it. The readiness check `permits_planned`
  exists today as a placeholder that answers `n_a`. This increment makes it real under the same name (the frozen
  contract and the stored evaluations keep working; a second name such as `permit_ready` would put two permit rows on
  every IWP). The placeholder's entry-point line leaves the awp package and the permits package registers the check.

| Answer | When |
|---|---|
| `n_a` | No permit names the IWP and `permits.required_for_iwp` is off (the default) |
| `blocked` | The setting is on and no permit exists; or a linked permit is Rejected, Suspended or Lapsed and no other live permit of that type exists |
| `pending` | A linked permit is Requested (awaiting approval) |
| `ok` | Every linked permit that is not Cancelled, Closed or Rejected is Approved or Active and not Lapsed |

  Approved is enough for release planning: a permit is issued on the day, at the workface. Whether today's permit is
  actually live is the question the QR answers (`specs/qr-workface.md`).
- **Scaffold.** A `work_at_height` permit may link the scaffold it uses; the permit record and its scan card show the
  scaffold's tag colour. Refusing issue on a red tag is a small guard added after P2-I4B is on the trunk (Later).
- **Areas.** `area` is text, as on punch items and inspections; the board groups by it. A link to an `awp.CWA` is an
  ordinary link. Areas as records are a Phase 4 matter.
- **Inspections.** No dependency. A pre-entry checklist can be a `quality.Inspection` on the permit when both exist.

## 7. Screens (terminal; log standard and the `tui-layout` skill apply)

- **Permit register.** Number, Subject, State (Lapsed shown in place of Active), Type, Area, Holder, Valid until,
  For (IWP). Filters: `o` open, `a` awaiting my approval, `l` lapsed or due for revalidation, by type, by area.
  Panel: identity `P123-PTW-0031 · Weld repair, rack 12 level 2`; state `Active · valid until 18:00 · revalidated 1×`;
  summary `Hot work · area A1 · holder J. Soto · for IWP-PIP-0042`. Sections: Work, Precautions (tick table),
  Gas tests (table Time, O2, LEL, H2S, CO, Result, Tester), Isolations (table Number, Point, State, Lock),
  Timeline, Files, Links. Actions per state as §5.
- **Permit board.** What is live now, grouped by area: Number, Type, Holder, Valid until, with Lapsed and Suspended
  first. This is the superintendent's and the authority's start-of-shift screen.
- **Isolation register.** Number, Point, Energy, State, Lock, Tag, Permits (count that depend on it).
- Screenshots of the register, the record, the board and the isolation register go into the tour.
- Web: only the scan status page. Web twins come with a later web increment.

## 8. CLI, API, MCP, reports

- **CLI** `tl permit request | approve | reject | issue | revalidate | suspend | resume | handback | close | cancel |
  ls | show | board | export`, `tl isolation apply | verify | remove | link | unlink | ls | show`,
  `tl gastest record | ls`. Write options take the key a read prints.
- **API** read routes `GET /permits`, `/permits/{key}`, `/permits/board`, `/permits/isolations`,
  `/permits/isolations/{key}`, `/permits/{key}/gas-tests`, `/permits/export`; commands through the command door from
  the module's `commands` hook. Hidden or unknown key: the same 404 body; counts after the visibility filter.
- **MCP** `list_permits`, `get_permit`, `permit_board`, `list_isolations`, `propose_permit`; closed until allowed.
- **Reports** are exports: `tl permit export --format csv|jsonl` (the register: number, type, state, area, holder,
  issued, valid until, revalidations, closed), `--gas-tests` (one row per reading), `tl isolation export`.
- Five-reader walk on every route, tool and export.

## 9. Confidentiality

A permit is hidden through `for_record_id`, as a requisition and a scaffold are. A gas test is hidden through its
permit. An isolation carries its own subject (`point_record_id`, or none) and is at the lowest class otherwise; a
refusal that would name a hidden permit uses the fixed "a permit you cannot see" text. One part is added to the
subject rule in `tl_core/confidentiality.py` (a security row).

## 10. Demo clauses (`dev/demos/P2-PTW.sh`, both adapters)

1. Hot work: request for an IWP; approve by the requester is refused, by another controller it passes; issue is
   refused without a gas test, refused with a failing one, passes after a passing one; the permit is Active with a
   `valid_until` at shift end.
2. Shift change: with the clock moved past `valid_until` the permit reads Lapsed on every surface; the job flags it
   once (a second run writes nothing); revalidate needs a fresh gas test, then it is Active again.
3. Stop work: a plain user suspends; a plain user cannot resume; the authority resumes; hand back and close.
4. Confined space with an isolation: issue refused until the isolation is Verified by someone other than the applier;
   removing the isolation is refused while the permit is live, allowed after close.
5. Readiness: `n_a` with no permit; `pending` on request; `ok` on approval; `blocked` when suspended or lapsed.
6. Hidden subject: a permit for a restricted record answers a plain user as a number that never existed, on CLI, API,
   MCP, board and export; board counts unchanged.
7. One state over CLI, API, TUI and MCP; `propose_permit` is pending until accepted; no tool issues or resumes.
8. Export: CSV and JSONL rows equal `tl permit ls`.

## 11. Later

Scaffold red-tag guard on issue; a Permits section in the IWP pack; simultaneous-operations clash warning (two
permits, one place); entry log for confined space; type extras through schema packages; link to calibrated
instruments; suspend and revalidate from the phone; guest holders from a subcontractor (Phase 3 parties); client
permit systems by inbound endpoint.

## 12. Owner questions (the build proceeds on the default)

| # | Question | Default |
|---|---|---|
| 1 | First set of types? | The six of §3 |
| 2 | Who approves and who issues? | Approve: a `permits` controller who is not the requester. Issue: the same word level, a separate fine word (`permits.issue`) so a project can split them by module role |
| 3 | Keep the readiness name `permits_planned` or add `permit_ready`? | Keep `permits_planned`; label it "Permits" on screens |
| 4 | Is an IWP with no permit ready? | Yes by default (`n_a`); `permits.required_for_iwp` makes it `blocked` |
| 5 | Shift pattern and gas limits? | 12-hour shifts from 06:00; limits of §5; both are project settings the safety lead can change |
| 6 | May anyone suspend, and only the authority resume? | Yes |
