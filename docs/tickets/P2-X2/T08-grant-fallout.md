# P2-X2-T08: DONE-gate fallout of S1, an agent files only under an explicit grant

Branch p2/x2-t08-grant-fallout, base p2/x2@d001c381. Fixtures, worlds and scripts only; no product code.

## Failing (RecordNotFoundError: no scope, agent_scope.py check_filing)
- awp test_progress / test_week `test_the_acceptance_checks_pass[sqlite]` (progress_world.py: agent:bot files)
- engineering test_generic_commands registry-record refusal test
- materials test_actions `test_agent_reservation_is_a_proposal`

## Do
- Give each agent an account and an explicit `user` grant (as dev/accept/P2-INS/s1_world.py grant_agent).
- A company-scope filing needs a grant on a module that declares company roles.
- No assertion weakened; the registry-record refusal stays the thing tested.
- Grep tests and dev for other agent filings hit the same way; fix and list them.

## Gate
`just check`; `just gate` on awp, engineering, materials tests and every dir touched.
Report docs/reports/P2-X2/T08.md.
