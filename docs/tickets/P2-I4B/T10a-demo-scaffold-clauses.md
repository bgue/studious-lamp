# P2-I4B-T10a — Demo clauses 5 and 6: the scaffold lifecycle and the due list and dismantle

Status: ready after T09c merges (needs the error rows for the refusal text)
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: S1, T05a, T05b, T07b, T09a, T09c (T05b and T07b merged)
Branch: `p2/i4b-t10a-demo-scaffold`
Worktree: `/home/user/wt/i4b/t10a` (from `p2/i4b` head)

## Goal
`just demo P2-I4` gains B's clauses, numbered after A's four: **clause 5** (plan clause 2): a scaffold request for the IWP becomes a scaffold Requested, Designed, Erecting, Inspected, tagged green; the IWP's `scaffold_tagged` check is `ok`; a failed inspection turns the tag red, the scaffold goes to Modify and the check is `blocked`. **Clause 6** (plan clause 3): the job `scaffold.inspections_due` flags an overdue scaffold once; a dismantle is refused while the IWP that requires the scaffold is Issued, and allowed after that IWP is cancelled (decision D17: Cancelled stands for "closes", a final state outside the holding set; Closed needs signoffs the demo does not stage). Both on SQLite and Postgres. Clause 7 (toolcrib) is T10b.

## Brief references (pasted)
> Plan clause 2 and 3 text above. D16: the job runs in process with `JobRunner`, never `tl awp run` or `tl awp worker` (the word `awp.worker.run` fails in the demo world). Scaffold commands go over the API door (no CLI group exists, Q2 deferred): `POST` of each command with the person's session, as `dev/demos/p2_i4_demo.py` does for the requisition checks. Roles: uma holds `user` on scaffold by derivation; sue needs `scaffold superuser` for `TagScaffoldGreen` (one `tl admin roles grant sue --project P123 --module scaffold --role superuser --reason demo`; expect the grant line in the output).

## Interfaces (verbatim from repo at the branch point)
Driver: new `dev/demos/p2_i4b_demo.py` (the A driver `p2_i4_demo.py` is not edited; copy its `World` class, `PASSWORDS`, `passed`, `miss`, `check` by hand, `main(argv)` dispatching on the first argument). Modes this ticket: `scaffold REQ_KEY IWP` (clause 5 and 6 in order; one `PASS clause N: ...` line per check).
Command order, fields and expected states: `dev/accept/P2-I4B/S1.py` `check_lifecycle`, `check_dismantle`, `check_job`. Job: `inspections_due.request(uow, "P123", <date>)` with a date 8 days after the tag day, then `JobRunner(open_uow, queue, [InspectionsDueKind()], worker_id="demo").run_until_idle()` (S1.py lines 105-124 show the exact calls); the second run on the same day writes nothing.
IWP to Issued for the dismantle check: the `requires` link is added with the door command `AddLink` (relation `requires`, from the IWP to the scaffold); the IWP is moved to Issued with `TransitionWorkflow` by_module in the driver, the transition list `IWP_PATH["Issued"]` of `packages/tl-modules/scaffold/tests/scaffold_world.py` (copy the list, do not import the test helper). Then `tl awp iwp cancel P123-IWP-... --reason ... --project P123` from the script (a CLI step, real), and the driver mode `scaffold-after` (dismantle allowed, state Dismantle).
Readiness: evaluate with the awp readiness job in process (build the runner as `tl_cli/awp_run.py` `build_worker` does, minus the word check; read that function only), then read the check with the API route `GET /projects/P123/awp/iwps/{number}/readiness` or `tl awp readiness show`.
Door refusal text: the dismantle refusal answers 409 `scaffold_dismantle_refused` (T09c) and its message names the IWP number.

## Context (read these, nothing else)
- `dev/demos/P2-I4.sh` (end of `run_backend`, the helpers `as`, `expect`, `refuse`, `clause`), `dev/demos/p2_i4_demo.py` (the `World` class and `main`)
- `dev/accept/P2-I4B/S1.py`
- `packages/tl-cli/src/tl_cli/awp_run.py` (`build_worker`), `packages/tl-modules/scaffold/tests/scaffold_world.py` (`IWP_PATH`, `World.call`)
- `docs/reports/P2-I4B/{T09a,T05a,T05b}.md` (decisive lines)
may explore: `tl req raise-scaffold --help` (flags: `--subject --purpose --days --for`)

## Allowed paths
- `dev/demos/p2_i4b_demo.py` (create); `dev/demos/P2-I4.sh` (edit: header comment lines for clauses 5 and 6, and a block before the final `drop_pg` in `run_backend`; A's clauses 1-4 unchanged)
- `docs/reports/P2-I4B/T10a.md` (create)

## Steps (script, after clause 4)
1. Grant sue superuser on scaffold (the line above). 2. `as uma tl req raise-scaffold --project P123 --subject "Scaffold level 1 east" --purpose "Access to the pipe rack" --days 14 --for "$IWP"`; read the key from the `raised <key>` line; `as sue tl req approve <key> --project P123`. 3. `driver_b scaffold <key> "$IWP"`. 4. `as ada tl awp iwp cancel "$IWP" --reason "demo: work package closed" --project P123`; `driver_b scaffold-after`. 5. The script prints `PASS clause 5` and `PASS clause 6` itself after the driver exits 0, as A does for clause 4. The requisition for an IWP that is later Cancelled may refuse a second scaffold request: raise the second only if the first path needs it; the dismantle check needs one scaffold and one Issued IWP.

## Acceptance
```
just check
TL_DEMO_BACKENDS=sqlite just demo P2-I4
TL_DEMO_BACKENDS=postgres just demo P2-I4
```
Expected: `PASS clause 1` to `PASS clause 6`, then `P2-I4 demo OK`. Both demos are long: run each in the background with a long timeout, once; paste the `PASS` lines and the last line only. If the Postgres run is red on the environment (cluster down), say so; do not retry in a loop.

## Tests to add
none beyond the demo (the driver is the test); it must pass ruff and pyright (`just check`).

## Report requirements
Standard report; first line lists any deviation from the steps (for example how the IWP reached Issued).

## Escalation triggers
- Stop if an IWP cannot reach Issued without a step this ticket does not name, or if the readiness job cannot be built without a file outside Context; write what is missing.
- Stop if the A clauses change output.

## Blocked
(implementer writes here)

## Decision
D17 2026-11-15 Cancelled stands for "the IWP closes" in the dismantle demo; T10a.
