# P2-I1-T15 — The sim's ground truth records what an accepted proposal creates

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: sim
Depends on: T14 (merged).
Branch: `p2/i1-t15-sim-accepted-records`   (from p2/i1)

## Goal
T08 clause 10 (`tl sim assert --run wk1`) fails: the approver accepts the workface planner's `propose_cwp`, the accept
creates real `awp.CWP` records (`simwk1-CWP-CIV-0001`, `-0002`), and `run_assertions` reports them
`unexpected_record` because no ground-truth item names them (see `docs/reports/P2-I1/T08.md` on branch
`p2/i1-t08-demo`, section Blocked). A record made by accepting a logged proposal is an intended record: the ground
truth must say so.

## Interfaces (read; change only what Steps say)
- `packages/tl-sim/src/tl_sim/actors/base.py` `Recorder.decide` (about line 427): accepts with
  `desk.accept_proposal(proposal_id)` and notes `gt.PROPOSAL_ACCEPTED`.
- `packages/tl-sim/src/tl_sim/groundtruth.py`: `RECORD_CREATED`, `PROPOSAL_ACCEPTED`, the item shape.
- `packages/tl-sim/src/tl_sim/assertions.py` `run_assertions`, the records block (about lines 255-275): every record
  not in `created` is `unexpected_record` unless an operator made it.

## Steps
1. Find what `desk.accept_proposal` returns (the Desk implementation and the API accept route it calls). If the
   answer names the record the accept created (an id or key), then in `decide`, after a successful accept, also note
   a `gt.RECORD_CREATED` item for that record (`ref` = its key via `self.key_of`, `expect` = `{"record_type": <type>}`
   or the fields the other RECORD_CREATED notes use). If the answer does not name it, read the record created by the
   accept from the ledger the way the actor already reads keys (`self.key_of`), and note it the same way.
2. Do not widen the operator excuse in `assertions.py`; the fix is in the ground truth.
3. Tests in `packages/tl-sim/tests/`: an accepted `propose_cwp` (or the fake world's creating proposal) gives a
   `RECORD_CREATED` ground-truth item and `run_assertions` reports no `unexpected_record`; a rejected one gives none.

## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/base.py`, `packages/tl-sim/src/tl_sim/groundtruth.py` (only if a helper is needed)
- `packages/tl-sim/tests/**`
- `docs/reports/P2-I1/T15.md` (create)
Stop and report Blocked if the fix needs a change outside these paths.

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-sim | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
