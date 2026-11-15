# P2-I4B-S1b report

## Done
- F1: hidden requiring IWPs are no longer keyed by one shared name; `dismantle_inputs` returns a third list (the states of hidden IWPs) and `rules.dismantle_blockers` counts each holding one. `_REQUIRING_SQL` has `ORDER BY cr.key, cr.id`.
- F3: the refusal says "a work package you cannot see requires this scaffold" or "N work packages you cannot see require this scaffold"; no state word, no key. `MSG_HIDDEN_IWP` now lives in `rules` and is re-exported by the handler.
- F4: CSV guard covers leading tab and CR.
- F6: `TagScaffoldGreen` is in the hidden-scaffold parametrisation. It runs as `sue` (a controller-word holder who cannot see the record), because `uma` is refused on the access word before visibility is checked.

## Deviation
- `dismantle_inputs` return shape and `dismantle_blockers` signature grew (optional third argument, so old calls still work). Only the handler calls them.
- The first commit swept in the code and tests along with the ticket; the follow-up commit holds the lint fix and the F6 test change.

## Tests added
two hidden IWPs holding/Draft (plus a third holding) refuse with a count and no state; rules count test; tab/CR guard test; Tag in the parametrisation.

## Mutation
Sentinel (invert holding test): killed. Collapse restored (`hidden_states[:] = [...]`): killed. State word added to refusal text: killed.

## Gate
`just check` ok; `just gate packages/tl-modules/scaffold/tests`: 126 passed; `just gate-pg .../test_scaffold_commands.py`: 92 passed. See .gate/summary.txt.

## Open
F2 and F5 deferred as instructed.
