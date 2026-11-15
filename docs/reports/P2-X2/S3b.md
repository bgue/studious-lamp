# Report — P2-X2-S3b (stopped agent's proposal stays held through accept_or_fail)

Branch `p2/x2-s3b-held-accept`, base `p2/x2@be36175a`. Spec: `docs/tickets/P2-X2/S3b-held-accept.md`.

## Deviations
- The existing `env` fixture of `packages/tl-cli/tests/test_cli_agent_stop.py` was already broken on the base (10
  errors: the agent had no module grant, so `file_link` was refused as an unknown scope). Fixed in place with
  `filing_support.grant_filing` (in the spec's allowed paths). The new CLI test depends on it.
- Spec-named gate path `tests/services/test_proposals.py` is at the repo root (not under packages); used as given.

## Change
- `agent_stop.AgentStoppedError(ForbiddenError)`; `require_not_stopped` raises it (text `STOPPED_TEXT` unchanged).
- `proposals.accept_or_fail`: `except agent_stop.AgentStoppedError: raise` before the generic `ServiceError`
  clause, so nothing is appended (no `Proposal.Failed`); docstring updated. Every other failure is as before.
- Callers: CLI, API route (403 as any `ForbiddenError`), MCP and batch review all call `accept_or_fail` or
  `accept_proposal` and map `ForbiddenError` already; no change needed. Hidden == missing is untouched (the
  scope-hiding refusals are other classes and still take the failure path as before).

## Tests added
- `test_agent_stop.py::test_accept_or_fail_of_a_stopped_agent_is_a_plain_refusal_and_the_proposal_stays_held`:
  refusal text, event rows unchanged, both proposals pending, `held_count` 2 unchanged, accept works after resume.
- `test_cli_agent_stop.py::test_accepting_a_stopped_agents_proposal_is_refused_and_it_stays_held`: `tl proposal
  accept` exits 1 with the stop text, no `failed` line, event count unchanged, held still counted, status pending,
  accept prints `accepted` after `tl agent resume`.

## Mutation
- sentinel (`require_not_stopped` does not raise): killed.
- m1 (re-raise clause replaced by `pass`): killed.
- m2 (plain `ForbiddenError` raised, class not used): killed.
3 of 3 targeted killed; no survivors.

## Gate
- `just check`: exit 0.
- `just gate` test_agent_stop.py, tests/services/test_proposals.py, test_api_agent_stop.py: part 1 exit 0, 54 passed.
- tl-cli run separately and gate-pg: see status return.
