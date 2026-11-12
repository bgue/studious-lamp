# P2-I4A-T04e1 — CLI writes: `tl req` and `tl wo` verbs, and the two groups

Status: ready (S2 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: S2 (merged)
Branch: `p2/i4a-t04e1-cli-writes`
Worktree: harness-created under `/home/user/wt/i4a/t04e1` (from `p2/i4a` head)

## Goal
A person raises, edits, approves, rejects and cancels requisitions and runs the work order from the terminal. This ticket creates the two groups `tl req` and `tl wo` (T04d adds the reads later) and every write verb. Each verb builds one S2 command, gates it with `require_command`, and runs the handler `REQUISITIONS_COMMANDS` names, as `awp_iwp_write.py` does (import `_execute`, `_line`, `_handler` from `awp_write.py`; do not copy them). No fulfil verb (deferred, roadmap 3c).

## Brief references (pasted)
> Records are named by the key reads print (`P123-REQ-LAB-0001`, `P123-WO-0001`, L-P2-I3-3) and resolved to an id with the key lookup `tl_cli/link.py` uses; unknown or hidden is `error: no requisition <key>` / `error: no work order <key>` (one text each). `--project`, `--actor` as in `awp_iwp_write.py`. Every state verb takes `--expected-version N`; default is the version read in the same unit of work. Output one line via `_line`: `<verb> <key>  version <v>`.
> `tl req` verbs (exact names; options are the contract):
> - `raise-labor --subject T --craft C --headcount N --start D --end D [--classification X] [--shift X] [--requirements T] [--need-by D] [--priority P] [--for IWPNUMBER]`
> - `raise-material --subject T --line ITEMKEY:QTY:UOM (repeatable, 1..200) [--from-location ID] [--need-by D] [--priority P] [--for IWPNUMBER]`
> - `raise-general --subject T --type CODE [--need-by D] [--priority P] [--for IWPNUMBER]`
> - `raise-scaffold --subject T --purpose T --days N [--need-by D] [--priority P] [--for IWPNUMBER]`
>   all four build `RaiseRequisition(requisition=<body with kind>, for_record_id=...)`; `--for` is an IWP number resolved by key; print `raised <key>  version <v>`. There is no `--requester` (the actor is the requester).
> - `edit KEY [--subject] [--need-by] [--priority] [--craft] [--headcount] [--start] [--end]` -> `EditRequisition` (only the options given; none given is a usage error, exit 2)
> - `approve KEY`, `reject KEY --reason R`, `cancel KEY --reason R`
> `tl wo` verbs: `schedule KEY --start D --finish D [--hours H]`, `assign KEY --to user:X`, `start KEY [--at ISO]`, `complete KEY [--hours H] [--at ISO]`, `close KEY`.
> A `ForbiddenError` or handler refusal prints through `service_errors()` (`error: ...`, exit 1), never a traceback. No password or token option exists (ADR-0009).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_iwp_write.py` (all), `awp_write.py` (lines 1-130), `main.py` (lines 125-160, imports near line 80)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/{commands.py, module.py}`, `docs/reports/P2-I4A/S2.md`
- `packages/tl-cli/tests/test_cli_awp.py` (lines 1-60: the world helper loaded by path)

## Allowed paths
- `packages/tl-cli/src/tl_cli/req.py` (create: `app`, `wo_app` Typers and `register_all()` calling the write modules' `register`), `packages/tl-cli/src/tl_cli/req_write.py` (create: `register(req_app, wo_app)`)
- `packages/tl-cli/src/tl_cli/main.py` (one import and two `add_typer` lines: `req`, `wo`)
- `packages/tl-cli/tests/test_req_write.py` (create), consequential pins of the CLI command list (union form, listed)
- `docs/reports/P2-I4A/T04e1.md` (create)
- `packages/tl-cli/src/tl_cli/awp_write.py`: only a keyword-only `table` parameter on `_handler` and `_execute` (default `AWP_COMMANDS`, existing callers unchanged); Decision D-r3a

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_req_write.py packages/tl-cli/tests/test_cli_awp.py
```

## Tests to add
`packages/tl-cli/tests/test_req_write.py`, ledger built by the module's commands through the `req_world.py` helper (`packages/tl-modules/requisitions/tests/req_world.py`, loaded by path as `test_cli_awp.py` does `awp_world`; no projection writes): raise-labor, raise-material (one item key), raise-general, raise-scaffold each print `raised <key>` with keys `-0001`; `--for` an IWP; approve as the superuser opens `P123-WO-0001`; a plain user's approve is `error: forbidden` (exit 1); reject and cancel need `--reason`; schedule, assign, start, complete, close walk one work order to Closed; a stale `--expected-version` is refused; unknown key prints one text; `edit` with no option exits 2; no output holds `Traceback`.

## Escalation triggers
- A verb needs a command model that is not in `REQUISITIONS_COMMANDS`; a key lookup for a material item does not exist; a CLI command-list pin cannot be updated in union form.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T04e1: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
D-r3a (orchestrator, 2026-11-11, after attempt 1 blocked): `_handler(model, *, table=AWP_COMMANDS)` and `_execute(db, build, *, table=AWP_COMMANDS)` in `awp_write.py`; `req_write.py` passes `table=REQUISITIONS_COMMANDS`. No copy of the dispatch.
D-r3b: a key lookup that finds a requisition or work order the caller may not see answers exactly as an unknown key (same text, same exit code): `get_record` then `confidentiality.is_hidden` for the caller's viewer; add one test with a restricted subject only if a command can make one today (else say so in the report; Q5).
