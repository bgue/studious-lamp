# P2-I4-B — Scaffold module, its two readiness checks, the toolcrib screen (workstream B of Increment 4)

Status: r1. 10 items (2 pieces' worth of core in one piece S1, 9 tickets), no plan check needed (not more than about 10). S1 and T06 specs written and dispatchable; the rest is staged in round 2.
Plan sources: `docs/build-spec/08-phase2-plan.md` "Increment 4" (B rows T03 to T10, demo clauses 2, 3, 6), `phase2-contracts-draft.md` §3 and §1, `phase2-owner-questions.md`
(P2-Q9 settings), `roadmap-2026-11-07.md` (W3-2, W3-3, 3c), `docs/tickets/P2-I4A/STATE.md` (names reused). Board: `STATE.md`.
Branch `p2/i4b` from trunk @d4e92ffc (requisitions I4-A, I5, PUNCH, X1 merged). Worktree `/home/user/wt/p2-i4b`. Piece branch `p2/i4b-s1-scaffold`, ticket branches `p2/i4b-t<nn>-<slug>`, worktrees `/home/user/wt/i4b/<id>`.
In this increment the piece B4 of the plan is called **S1**.

## Objective
After this increment a new module `scaffold` (package `tl-mod-scaffold`) holds the scaffold asset and its inspections. A scaffold is registered from an approved `ScaffoldRequest`, then designed, erected, tagged green
by a person holding the scaffold superuser word, released into use, modified, dismantled and removed. A failed inspection turns the tag red and sends the scaffold back to Modify. A job lists what is due for inspection from the project setting
`scaffold.inspection.interval_days`. A dismantle is refused while an open IWP still `requires` the scaffold. The readiness checks `scaffold_tagged` and `labour_requested` answer for an IWP.
Reads over API (and client fakes), a TUI register with a record view, and an exported register (CSV or JSONL; owner rule 2026-11-14: reports are simple exports). The toolcrib screen issues and takes back a tool in one line, keyboard only.
Out of scope: scaffold hire quantities and material lines (W3-3, Phase 3), MCP tools, CLI groups (X4 supplies the hook, TRAPS), web pages, thread `/dispatch`.

## Demo clauses (B's, in `just demo P2-I4`; A's script exists, T10 adds these; both adapters)
2. A scaffold request for the IWP becomes a scaffold Requested -> Designed -> Erecting -> Inspected, tagged green; the scaffold readiness check is `ok`; a failed inspection turns the tag red, the scaffold goes to Modify, the check is `blocked`.
3. The inspection due list from the interval setting (job `scaffold.inspections_due` flags an overdue scaffold once); a dismantle is refused while an open IWP uses the scaffold, allowed after the IWP closes.
6. The toolcrib screen issues a tool to a person and takes it back, one line each, keyboard only.
Screenshots of each new screen go into the tour (`dev/tour/phase2.py`, actors written `user:<name>`; T11).

## Pieces and tickets
| Id | Item | Tier | Depends | Review |
|---|---|---|---|---|
| S1 | schema, lifecycle, tag colour, dismantle check, job (plan B4/T03) | builder | trunk | full + Sec |
| T01 | read views `tl_mod_scaffold/views.py`: register rows, detail, inspections, due list; `export_rows(rows, "csv"\|"jsonl")` | haiku | S1 | full |
| T05 | checks `scaffold_tagged`, `labour_requested` over the frozen readiness contract (plan T05) | haiku | S1 | full |
| T06 | toolcrib screen (plan T06), provided test | haiku | I3 | full |
| T09b1 | API read routes, with the five-reader walking test (plan T09b, part 1) | haiku | T01 | full |
| T09b2 | client methods and fakes (plan T09b, part 2) | haiku | T09b1 | full |
| T07a | TUI scaffold register, record view, register entry of both screens in the nav and `commands.py` (T06 glue) (plan T07a) | haiku | T09b2, T06 | full |
| T10 | simulator actor `scaffold_supervisor`; B's demo clauses in `dev/demos/P2-I4.sh` (plan T10) | haiku | T05, T07a | full |
| T11 | tour shots of register, record view and toolcrib in `dev/tour/phase2.py` (owner rule) | haiku | T07a, T06 | lite |
| T12 | docs: module README and AGENTS, runbook `docs/runbooks/scaffold.md`, `AGENTS.md` table row, `docs/modules/scaffold/` | haiku | all | lite |
Checkpoints (plan): C1 = S1 merged; C2 = T09b1 and T09b2 merged; C3 = T05, T06, T07a merged; C4 = T10 clauses 2, 3, 6 green and SR4 closed.

## Order of work
Round 1: S1 and T06 (disjoint paths, T06 depends only on I3). Round 2 (after S1 merged): T01, T05 (provided tests from S1 names), and the staged tickets refined from S1's report. Then T09b1 -> T09b2; T07a with T05 results; T10; T11; T12.
Merge order inside the increment: S1 -> T01 -> T09b1 -> T09b2 -> T05, T06, T07a -> T10 -> T11 -> T12.

## Design points the next rounds rely on (decisions in STATE.md)
- Check semantics (T05): `scaffold_tagged` is `n_a` when the IWP requires no scaffold, `ok` when every required scaffold has a green tag and `rules.due_state` is not `overdue`, else `blocked` with the scaffold keys in the note. `labour_requested` is `ok` when an approved `LaborRequisition` with `for_record_id` = the IWP covers the IWP window, else `blocked` (pending if one is requested and not approved: use the contract's status words, read `phase2-contracts-draft.md` §1 first).
- All reads take `viewer=` (lowest default); the five-reader walk is a test in T09b1 (no clearance, cleared, restricted subject, company admin, agent token).
- Register export is a function in `views.py`; its exposure as a report is registration glue after X4 (hooks), not a ticket here.

## Risks and escalation triggers
- S1 touches shared files (`confidentiality.py`, root `pyproject.toml`, pinned lists): merge conflicts go to the orchestrator; S1 is the only item touching them.
- X4 changes `ModuleSpec` (`tl_core/modules.py`) while S1 builds: S1 must not touch it; hooks come later (TRAPS).
- Escalate if an interface another workstream consumes must change (`open_requisitions_for`, readiness `Check`), or the brief is silent on a confidentiality choice.

## Blocked / Decision
(none yet; decisions D1 to D8 in `STATE.md`)
