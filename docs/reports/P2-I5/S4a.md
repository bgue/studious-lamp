# Report — P2-I5-S4a

Branch: `p2/i5-s4a-weekly-plan`   Commit(s): see `git log` (head of branch)

## Deviations
Two small ones. (1) `CloseWeek` added to the pinned controller list in `packages/tl-api/tests/test_commands.py::test_the_controller_actions_are_exactly_the_commands_marked_controller` (a pin the gate found; same file the spec lists). (2) `tests/tools/proposable_exclusions.toml` does not exist on the base, so nothing was added there; lines for the merge are below. Branch name differs from the spec's Worktree field only by the supervisor's instruction.

## Changed files
- `tl_mod_awp/handlers/week.py` (new) — the four handlers, `miss_reasons`, `parse_week_hours`, `iso_week`
- `tl_mod_awp/week_views.py` (new) — `list_weeks`, `week_detail`, re-export `miss_reasons`; viewer filter on every read
- `tl_mod_awp/{commands,module,errors}.py` — 4 command models and rows, one `ProposableCommand`, `WeekRuleError`, `WeekStateError`
- `tests/test_week.py` (new), `tests/progress_world.py` (`WeekWorld`, `week_checks`), `dev/accept/P2-I5/S4a.py`
- `docs/reference/openapi.json` (regenerated; +4 paths, +4 bodies only); pinned: `packages/tl-api/tests/test_commands.py` (count +4, `CloseWeek` controller pin), `packages/tl-mcp/tests/test_mcp_write_tools.py` (+`propose_week_commitment`). `tests/services/test_modules.py` needed no change.

## Commands and output
```
$ just check                                   -> licences ok, rc=0
$ uv run python dev/accept/P2-I5/S4a.py        -> 19 PASS lines, "S4a ok"
$ just gate packages/tl-modules/awp/tests ...  -> part 1: exit 0, 299 passed; gate: PASS
$ just gate test_commands test_mcp_write_tools test_modules -> exit 0, 290 passed; gate: PASS
```
(The second gate failed once on the controller pin above; fixed, re-run green.)

## The three greps
- `intent` in `handlers/week.py`: one hit, the docstring saying handlers never read it; no code reads `cmd.intent` (test pins `cmd.intent` absent).
- Payload keys written vs declared: Opened {week, week_start, at, feed_policy}; IwpCommitted {iwp_id, foreman, committed_hours, at, feed_policy}; OutcomeRecorded {iwp_id, outcome, miss_reason, at, feed_policy}; Closed {ppc, at}. All declared in `week_events.yaml`; Closed carries no `feed_policy`.
- `viewer` in `week_views.py`: 8 hits; both reads pass `viewer` to `not_hidden`, a hidden plan is not-found, a hidden IWP's commitment is dropped with the note `some commitments not shown`.

## ADR-0027 lines for the merge (file absent on base)
```
OpenWeeklyPlan = "a week is judged by the people who planned it"
RecordWeekOutcome = "a week is judged by the people who planned it"
CloseWeek = "a week is judged by the people who planned it"
```
`propose_week_commitment` (access `user`) is the one `ProposableCommand` row, in `module.py`.

## Mutation
Sentinel (stale-version check off) killed. 5/5 killed: PPC rounding, Issued-state guard, miss-reason check, outcomes-missing check, close word (`awp.week.close` to `awp.week.commit`). Extra: hours lower bound `<= 0` to `< 0` killed (+0 tests added, `0.0` case already present). Survivors none.

## Tests added
- `test_week.py` — 20 cases: ISO-week normalisation, open/duplicate, commit states and the move, foreman default, hours bounds, stale, outcomes and corrections, close/PPC (66.7, 100.0, 0.0), empty close, views and hidden plan, wiring of words and the one proposal, rebuild equality with ppc, no `intent`.

## Learnings (proposed)
`tl_core.feed.cards.POLICY_EVENT_TYPES` does not list the `WeeklyPlan.*` quiet events, so `feed_policy: none` on them is data only today and the feed may still make cards for Opened, IwpCommitted and OutcomeRecorded. The "card on Closed only" test therefore pins the payload keys, not the feed rows. Hidden-source test tables need a row for every record, else unlisted ones read as hidden.

## Open questions / Blocked
4 Should `POLICY_EVENT_TYPES` (tl_core, outside this piece) gain the three quiet week events so the card really appears on Closed only? Not blocked.
