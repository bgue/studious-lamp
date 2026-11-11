# P2-I4A-T10b — `dev/demos/P2-I4.sh`: the trimmed clauses, both adapters

Status: staged (dispatch after T04c1, T04d, T04e1, T07d, T08b merge)
Tier: haiku
Kind: ticket
Review: full
Labels: demo
Depends on: T04c1, T04d, T04e1, T07d, T08b
Branch: `p2/i4a-t10b-demo`
Worktree: harness-created under `/home/user/wt/i4a/t10b` (from `p2/i4a` head)

## Goal
`just demo P2-I4` runs the four clauses below once on SQLite and once on Postgres, one `PASS clause N: ...` line each. **A PASS line is printed only after a real check returned success** (a command's exit code and an output comparison, or a driver assertion); a miss prints `DEMO FAILED` and exits non-zero; there is no `echo PASS` on a path that checked nothing. Pattern: `dev/demos/P2-I3.sh` and `p2_i3_demo.py` (header, backends, driver modes, TUI through the palette). Deferred, so not claimed anywhere in the script: stock fulfilment, FIFO lots, the shortage constraint, the labour forecast, reports (roadmap 3c). Thread dispatch and web pages are not built.

## Clauses and their exact verbs (use these; never re-derive an argument)
Setup by commands: project `P123`; `sue` holds the module superuser role on `requisitions` (`tl admin` module-role grant, as `req_world.py` does through `grant_module_role`; the shell uses the `tl` verb `P2-I3.sh` uses for its materials superuser), `uma` and `rob` plain users; one IWP and one material item made as `P2-I3.sh` and `p2_i2_demo.py` make theirs.
1. **Raise to close.** `tl req raise-material --subject "Flanges" --line <ITEMKEY>:10:ea --for <IWPNUMBER>` as uma prints `raised P123-REQ-MAT-0001`; `tl req ls --for <IWPNUMBER>` lists it `Requested`; `tl req approve P123-REQ-MAT-0001` as uma is `error: forbidden`, as sue it prints `approve ... version`; `tl wo show P123-WO-0001` shows `requisition P123-REQ-MAT-0001` and state `Open`; `tl wo schedule P123-WO-0001 --start 2026-11-16 --finish 2026-11-20`, `tl wo assign P123-WO-0001 --to user:rob`, `tl wo start P123-WO-0001`, `tl wo complete P123-WO-0001 --hours 40`, `tl wo close P123-WO-0001`; `tl wo ls --state Closed` shows it. A second requisition `tl req raise-labor --subject Pipefitters --craft Pipefitter --headcount 6 --start 2026-11-02 --end 2026-11-13` is rejected with `tl req reject P123-REQ-LAB-0001 --reason "No budget"`; a third (`P123-REQ-LAB-0002`) is cancelled with `tl req cancel P123-REQ-LAB-0002 --reason "Not needed"`; `tl req show` shows `Rejected` and `Cancelled`. The final state of each is read back with a `req show` or `wo show` and compared.
2. **General requisition with a type pset (clause 5 of the plan).** `tl req raise-general --subject "Rack 12 lift" --type crane_lift` prints `raised P123-REQ-GEN-0001`; `tl pset set P123-REQ-GEN-0001 crane_lift.load_t=40` and `crane_lift.radius_m=18` (assignment form: read `packages/tl-cli/src/tl_cli/pset.py` lines 46-95 and use it as written); `tl pset get` prints both values back; the demo compares them.
3. **Numbering under two writers (clause 7).** Two background loops of ten `tl req raise-labor ...` each, started together, then two of ten `raise-general`; afterwards `tl req ls --kind labor --limit 100` and `--kind general` each show every key from `-0001` to `-<n>` exactly once, where `n` is the number of requisitions of that kind raised so far, counted by the script itself (not read from the output): no gap, no duplicate, and the 20 new keys of each kind distinct. Run the same check on the keys of each kind separately (the numbers are per kind).
4. **One state over API, TUI, MCP (clause 8).** Driver: the `ApiClient` over a `TestClient` and `tl req show` give equal answers for `P123-REQ-MAT-0001` (`get_requisition`, `list_requisitions`); the TUI at 170x44 reached by the palette ids `requisitions` and `work-orders` (never `action_*`) shows the requisition log with the keys of clause 1 and the work order backlog with `P123-WO-0001` `Closed`; MCP `list_requisitions` and `get_requisition` agree; an agent calls `propose_requisition` (labour, `for_key` the IWP key), the proposal is pending and no `req ls` row appears, then `uma` accepts it and the next labour key (`-<n+1>`, counted as in clause 3) exists with requester `user:uma`; a person without `requisitions.view` is refused by `tl req ls`, by the API list route (403) and by the MCP list tool. The hidden-subject case cannot be made by a command today and is not claimed here (STATE OPEN Q5).

## Context (read these, nothing else)
- `docs/tickets/P2-I4A/README.md` (demo clauses), `dev/demos/P2-I3.sh`, `dev/demos/p2_i3_demo.py` (abridged: header and one mode of each kind)
- `docs/reports/P2-I4A/{T04c1,T04d,T04e1,T07d,T08b}.md` (command lines, palette ids, route names)
may explore: `dev/accept/P2-I4A/`, `packages/tl-modules/requisitions/tests/req_world.py`

## Allowed paths
- `dev/demos/P2-I4.sh` (create, executable), `dev/demos/p2_i4_demo.py` (create), `docs/reports/P2-I4A/T10b.md` (create)

## Acceptance
```
just check
just demo P2-I4
```
Expected: four `PASS clause N` lines per backend, no `DEMO FAILED`, exit 0, no leftover files or databases. Run the demo once; Postgres down means `ge` and stop (do not skip the backend). No pytest, no `just gate`. To prove the checks are real, the report names, for each clause, the one comparison that would fail if the feature broke (not a mutation run).

## Escalation triggers
- A clause cannot pass without a change in `packages/` or `schema/`; a screen cannot be opened through the palette; a verb above differs from the merged CLI (the merged CLI wins: report the difference as the first line); the demo needs more than the two files.

## Report requirements
`docs/reports/P2-I4A/T10b.md` <= 60 lines: the PASS lines of each backend (<= 5 decisive lines each), one line per clause naming its surface (CLI, API, TUI palette, MCP). Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T10b: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
