# Runbook — change a workflow, an expected link, or a numbering pattern

Purpose: edit the definition files that drive record workflow, expected links and key numbering, and check the change before it is used. Brief: §7.1, §8.

## When to use
- Trigger: a record type needs another state, transition or guard, a new expected link, or a different key pattern.
- Trigger: `tl wf transition` refuses a transition and you need to know which file decides it.

## Before you start
- Access needed: the repository. Files under `schema/**` are a human-gated change (`docs/build-spec/04-gates.md` §2): open it as a schema change and list the paths in the PR.
- Safe to run during business hours: yes for the dev ledger. A running process reads these files once; restart it after an edit.

## Where each rule lives
| Rule | File (under `TL_SCHEMA_DIR`, default `schema/fixtures`) | Read by |
|---|---|---|
| States, transitions, guards | `workflows/<name>.yaml` | `tl_core.workflow.loader` |
| Links a record type is expected to have | `links/<name>.yaml`, annotation `tl:expects_link` | `tl_core.links.expected` |
| Key patterns, gap-free flag, reserved ranges | `numbering/patterns.yaml` | `tl_core.numbering.config` |

## Steps
1. Edit the file. A workflow `expected_links` guard checks the links declared for the target state (`by_state` equal to it), so add the link rule and the guard together.
2. Check the file loads and the rules behave:
   ```
   uv run pytest tests/services/test_workflow.py packages/tl-core/tests/test_workflow_loader.py packages/tl-core/tests/test_expected_links.py packages/tl-core/tests/test_numbering_config.py -q
   ```
   Expected: all pass. A bad file fails with the file name and the problem.
3. Try it on a scratch ledger:
   ```
   TL_DB=/tmp/try.db uv run tl init
   TL_DB=/tmp/try.db uv run tl record create --project P123 --title "Try"
   TL_DB=/tmp/try.db uv run tl wf show --project P123 P123-REC-0001
   ```
   Expected: the new state or key appears; each transition lists its guards as `allowed` or `blocked`.

## Verify
- `just demo P0-I3` still ends with `P0-I3 demo ok`.
- A pattern change affects new keys only. Existing keys and counters are events and are not rewritten.

## Roll back
- Revert the file and restart the process. Events already written (`Workflow.Transitioned`, `Numbering.Allocated`) stay; a record in a state the old workflow lacks needs a transition back, or a new workflow version that keeps the state.

## Numbering: a gap or a conflict
- Keys are allocated in the transaction that creates the record, so a failed create leaves no gap. A concurrent create retries on the counter's version check and takes the next number.
- If `cur_numbering` disagrees with the `Numbering.Allocated` events, rebuild it: `just rebuild-projections numbering` (see `docs/runbooks/rebuild-projections.md`).

## Related
- `packages/tl-core/README.md`; `docs/tickets/P0-I3/README.md` (decisions D8, D11, D12, D17, D18).
