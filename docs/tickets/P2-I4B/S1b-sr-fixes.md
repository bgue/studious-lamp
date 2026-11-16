# P2-I4B-S1b — SR-I4B fixes to the scaffold dismantle check

Status: ready
Tier: sonnet
Kind: ticket
Review: full
Depends on: S1 (merged)
Branch: `p2/i4b-s1b-dismantle-fix`
Worktree: `/home/user/wt/i4b/s1b`

## Goal
Close four SR-I4B findings in `packages/tl-modules/scaffold`.

## Fixes
- F1 (MD): every hidden requiring IWP shared one `states` key, so a later one overwrote an earlier and a holding one could be lost. Keep every hidden IWP's blocker (never its id); `_REQUIRING_SQL` gets an ORDER BY.
- F3 (LO): the refusal for hidden IWPs names no state: "a work package you cannot see requires this scaffold", or "N work packages you cannot see require this scaffold".
- F4 (LO): the CSV formula guard also covers a leading tab and carriage return.
- F6 (LO): `TagScaffoldGreen` joins the hidden-scaffold parametrisation.
- Out of scope: F2 (`open_requisitions_for` viewer), F5 (`resolve_via` in the event payload).

## Interfaces
`rules.dismantle_blockers(iwp_states, other_open_requests, hidden_iwp_states=())`; `rules.MSG_HIDDEN_IWP`; `dismantle_inputs` returns `(states, requests, hidden_states)`.

## Allowed paths
`packages/tl-modules/scaffold/**`, this ticket, its report.

## Tests
Two hidden IWPs (holding, Draft) refuse; several hidden count and show no state; tab/CR guard; rules count.
