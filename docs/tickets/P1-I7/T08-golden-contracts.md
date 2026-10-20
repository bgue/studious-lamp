# P1-I7-T08 — Golden contract cases for inbound mappings and action results

Status: ready
Tier: haiku
Labels: tests
Depends on: — (the runtime and executors are in the tree)
Branch: `p1/i7a-t08-golden-contracts`

## Goal
The mapping runtime and the two action executors have golden cases that pin what they must answer. The runners are provided (`tests/contract/test_inbound_golden.py` and `test_action_results_golden.py`); the data files `tests/golden/inbound/mappings.json` and `tests/golden/actions/results.json` hold one seed case per category. You add cases until every category meets its minimum (the tables `MINIMUM` in the two runners) and the failure codes of `REQUIRED_CODES` are all covered. You change no code, only the two JSON files.

## Brief references (pasted)
> **Brief 18.5 / 18.7.** A mapping turns a payload into allow-listed commands, or into a refusal; it never raises. An action returns a completed outcome with a JSON result, or a failed one with a problem code; a failure the receiver caused may be retried, one we caused or the receiver refuses outright may not.
>
> **FANOUT D5 and D8.** The mapping profile allows a fixed set of functions; the server never parses an expression. The webhook executor: 2xx completed (a JSON object as it is, any other JSON under `value`, text under `text`); 3xx a failure; 408, 425, 429 and 5xx retryable; any other 4xx not; an answer cut by the transport or over 64 KiB fails and is never truncated; egress and resolution refusals happen before any connection.
>
> **Why the details matter.** A golden file is a promise to later maintainers: each expected value is worked out from the JSONata or HTTP rules written above, not copied from what the runtime printed. If the runtime disagrees with your reading of the rules, that is a finding: write it under *Blocked* with the expression, do not bend the golden.

## Interfaces (verbatim from the repo at the branch point)
The shape of a case is written in the docstring of each runner (read them: `docs/tickets/P1-I7/provided/t08-test_inbound_golden.py.txt` and `t08-test_action_results_golden.py.txt`). In short.

`mappings.json`: `{"cases": [...], "checks": [...]}`.
```json
{"name": "single-feed-post", "category": "single", "expression": "{\"command\": \"PostToFeed\", \"args\": {\"body\": contractor}}",
 "payload": {"contractor": "acme-nde"}, "status": "ok", "commands": [{"command": "PostToFeed", "args": {"body": "acme-nde"}}]}
{"name": "invalid-a-number", "category": "invalid_output", "expression": "5", "payload": {}, "status": "invalid_output", "problem_codes": ["invalid_output"]}
{"name": "refuses-now", "expression": "$now()", "accepted": false, "problem_codes": ["function_not_allowed"]}
```
Statuses: `ok`, `invalid_output` (not commands, a command outside the allow-list, a server-set field such as `actor` anywhere, an unknown key on the command), `limit` (more than 50 commands, or too slow or too large), `error` (does not parse). Problem codes you will meet: `invalid_output`, `limit`, `syntax`, `function_not_allowed` (a function outside the allow-list), `not_allowed` (a construct outside the profile: a lambda, partial application, a regular expression). Allowed functions include `$string`, `$number`, `$uppercase`, `$lowercase`, `$trim`, `$length`, `$join`, `$split`, `$count`, `$sum`, `$max`, `$substring`, `$substringBefore`, `$round`, `$keys`, `$exists`, `$not`, `$boolean`; the list is `MAPPING_ALLOWED_FUNCTIONS` in `packages/tl-core/src/tl_core/integration/contract.py`. A function not in it (`$pad`, `$now`, `$eval`, `$random`, `$match`) is `function_not_allowed`.

`results.json`: `{"webhook": [...], "job": [...]}`.
```json
{"name": "retry-503", "category": "webhook_retryable", "answer": {"status": 503}, "expect": {"status": "failed", "problem_code": "http_error", "retryable": true, "http_status": 503}}
{"name": "ok-json-object", "category": "webhook_completed", "answer": {"status": 200, "excerpt": "{\"ok\": true}"}, "expect": {"status": "completed", "http_status": 200, "result": {"ok": true}}}
{"name": "refused-plain-http", "category": "webhook_refused", "url": "https://10.0.0.1/h", "answer": {"status": 200}, "expect": {"status": "failed", "problem_code": "egress_denied"}}
{"name": "job-raises", "category": "job_failed", "job": "raises", "expect": {"status": "failed", "problem_code": "job_error"}}
```
The runner's hosts: `nde.example.net` resolves to a public address, `internal.example.net` to `10.1.2.3`, any other name does not resolve (`unresolvable`, retryable). The runner's jobs: `echo` (completes with the action, attempt, parameters and target keys), `raises`, `mismatch` (the code is registered under the wrong name), `returns-text`, `huge`, `not-json`, `refuses` (fails with `no_capacity`), `broken` (its factory raises), and the name `missing-job` (not registered).

## Context (read these, nothing else)
- `tests/golden/inbound/mappings.json` and `tests/golden/actions/results.json` (the files you edit)
- `docs/tickets/P1-I7/provided/t08-test_inbound_golden.py.txt` and `t08-test_action_results_golden.py.txt` (the runners)
- `tests/contract/test_integration_contract.py` (read only; the shared contract checks and the NDE sample)
- `packages/tl-core/src/tl_core/integration/contract.py` (the allow-list) and `executors/webhook.py`, `executors/job.py` (read only)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages: the stub's two lint-silencing header lines come out when you implement it (L-P1-I3-3).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean, and it was run against a reference implementation, with mutation checks (L-P1-I3-12).
- Commit your report at `docs/reports/P1-I7/P1-I7-T08.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Keep every signature, widget id, key binding, printed text and status message exactly as the STEPS and the test say.
- Do not run `just test` or `just test-parity` (they take an hour and the box is shared). Run the acceptance commands once each.
- The test count below was counted from the provided file; a parametrized test counts once per case (L-P0-I8A-8).


## Allowed paths
- `tests/golden/inbound/mappings.json` (edit)
- `tests/golden/actions/results.json` (edit)
- `tests/contract/test_inbound_golden.py` (create; byte-identical copy of the provided runner)
- `tests/contract/test_action_results_golden.py` (create; byte-identical copy of the provided runner)
- `docs/reports/P1-I7/P1-I7-T08.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t08-test_inbound_golden.py.txt` to `tests/contract/test_inbound_golden.py` and `t08-test_action_results_golden.py.txt` to `tests/contract/test_action_results_golden.py`.
3. Run both once: the coverage tests (`test_the_golden_file_covers_every_category_enough` and `test_every_category_has_enough_cases_and_every_failure_code_is_seen`) fail and say what is missing.
4. Add cases to the two JSON files until they pass. For each case work out the expected answer from the rules in *Brief references* first, then run it. Use short names in `kebab-case`, unique across the file. Keep two-space-friendly JSON (`indent=1` as the seed has it).
5. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest tests/contract/test_inbound_golden.py tests/contract/test_action_results_golden.py -q
```
Expected: `just check` clean; both runner files pass. Aim well above the minimums where a category has distinct behaviour to pin (for example every status of the retryable table, a JSONata filter that matches nothing, a nested object in `args`).

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- A case where the runtime's answer disagrees with the rules above: *Blocked*, do not record it.
- Never edit a runner, a contract file or any code. Stop if you need to.
- A case that takes more than a few seconds is a `limit` case; keep the count of those at the minimum (each starts a child process).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
