# P2-I2-T04d2 — CLI readiness reads: `tl awp readiness ls|show`

Status: ready (S4 merged; runs beside or after T04d, no shared file)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, read, confidentiality
Depends on: T04a, S4 (merged). Glue T04g adds the `register` call
Branch: `p2/i2-t04d2-cli-readiness`
Worktree: harness-created under `/home/user/wt/i2/t04d2` (from `p2/i2` head)

## Goal
One new read module `packages/tl-cli/src/tl_cli/awp_readiness_read.py` exposing `register(app: typer.Typer) -> None`; it adds a `readiness` group (`ls`, `show`) to the Typer it is given (the `tl awp` app; T04g calls it, this ticket edits neither `awp.py` nor `main.py`, D27).
Same style as `awp_read.py`: one fact per line, two spaces between fields, `-` for none, `open_uow(db, readonly=True)`, `service_errors()`, `scope_of(project)`, the default viewer (never widened).

## Brief references (pasted)
> Reads (all from the merged tree, no check runs here, no new query):
> - `tl_mod_awp.readiness.views.readiness(conn, scope, iwp_key) -> ReadinessView | None`. `None` is no IWP, a hidden IWP, or one never evaluated; all three answer alike.
>   `ReadinessView`: `iwp_id evaluated_at today ready facts_hash checks`. `CheckResult`: `name version state detail resolve_via count_ok count_total`; `resolve_via` is a list of `RecordRef(record_id, record_type, key)`.
> - `tl_mod_awp.iwp_views.iwp_list(conn, scope, *, state, discipline, foreman, limit)` gives the IWP rows (`number`, `state`, `title`...) the `ls` verb walks.
> - Passing states are `ok` and `n_a` (`readiness.engine.PASSING`); `n_a` counts as passing (D9). Import the frozenset, do not copy it.
> `ls [--state S] [--foreman user:X] [--limit N]` -> `readiness: <n>` then, per IWP in number order, `<number>  <ready|not ready|not evaluated>  <passing>/<total>  <evaluated_at date|->  <blocked check names comma-joined|->`.
>   An IWP never evaluated prints `not evaluated  -/-  -  -`. Blocked means state `blocked`; names only.
> `show NUMBER` -> `readiness <number>`, `ready  yes|no`, `checks  <passing>/<total>`, `evaluated  <evaluated_at>  for  <today>`, then one line per check in name order:
>   `<name>  <state>  <count_ok>/<count_total or ->  <detail cut 80>` and, for each `resolve_via` entry, an indented line `  resolve  <record_type>  <key>`. Never print `facts_hash`, `record_id` or `version`.
>   A missing, hidden, void or never-evaluated IWP is `error: no readiness for <number>` (one text for all four, exit 1).
> The engine already dropped unresolvable references and rewrote keys to ids; the CLI prints what the view returns and looks nothing up itself.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_read.py` (lines 1-60, `cwp_ls`, `cwp_show`, `register`), `packages/tl-cli/src/tl_cli/derive_support.py` (helpers), `packages/tl-modules/awp/src/tl_mod_awp/readiness/views.py`, `docs/reports/P2-I2/S4.md`, `dev/accept/P2-I2/s4_world.py` (seed and evaluate helpers; reuse, do not copy)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_readiness_read.py` (create)
- `dev/accept/P2-I2/T04d2.py` (create; helper `t04d2_checks.py` if over 70 lines), `docs/reports/P2-I2/T04d2.md` (create)
Not here: `awp.py`, `main.py`, write verbs, running a check (`evaluate_now`/`request`), new pytest (S5), any change to `tl_core` or `tl_mod_awp`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04d2.py
just gate packages/tl-cli/tests/test_cli_awp.py
```
`T04d2.py` (seed a SQLite ledger with the S4 world helpers, evaluate one IWP, leave one never evaluated, build a throwaway `typer.Typer`, call `register`, drive it with `CliRunner`; one `PASS <check>` per line; final `T04d2 ok`): `ls` line count and order, evaluated and
not-evaluated forms; blocked names listed; `show` check lines and the `n_a` count in `<passing>/<total>`; no `facts_hash` or record id anywhere in the output; unknown, hidden and never-evaluated IWP print byte-identical errors (exit 1); a hidden pinned
document shows no id or key in `show` output; no `Traceback`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T04d2: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and report *Blocked* if the S4 world helpers cannot produce a hidden pinned document, or a CLI snapshot outside Allowed paths breaks (the glue ticket owns pins).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
