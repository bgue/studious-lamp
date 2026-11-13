# P2-I5-T01 — CLI `tl awp roc ls|show|set`

Status: ready (S1, S2 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, settings
Depends on: S1 (package content, setting), S2 (`progress.engine`)
Branch: `p2/i5-t01-roc-cli`
Worktree: harness-created under `/home/user/wt/i5/t01` (from `p2/i5` head)

## Goal
A planner reads the rules of credit in force and adopts an edition for a project from the terminal. Reads and one setting write; no schema, no new word, no new event.

## Brief references (pasted)
- Rules of credit are the section `rules_of_credit` of a schema package (`PackageDoc.rules_of_credit: list[CreditRule]`; `CreditRule` has `commodity`, `kind`, `steps`; `CreditStep` has `name`, `weight`, `evidence`). The project setting `awp.rules_of_credit.set` holds `package@version`; empty means `co.acme.awp@1.1.0` (`names.DEFAULT_EDITION`).
- `engine.edition_key(conn, scope)` is the key in force; `engine.rules_for(key)` returns `Rules(edition, by_commodity)` or raises `RulesOfCreditError` with the fixed text `the edition of the rules of credit is not adopted` (unknown or not adopted) or `... holds no rules`.
- Output, one fact per line, two spaces between fields:
  - `roc show [--edition E] --project P`: `edition <key>`; `source default|setting|argument` (argument when `--edition` is given; setting when the stored value is non-empty); `commodities: <n>`; then per commodity in the order of the package `<commodity>  <kind>  <name> <weight>, <name> <weight>, ...`.
  - `roc ls --project P`: `editions: <n>` then `<key>  <n commodities>  in force` for the edition in force only (the registry lists no other edition with rules yet; do not scan it).
  - `roc set EDITION --project P [--reason R] [--actor A]`: refuse a value that is not `package@version` with `error: edition: expected package@version` (exit 1, check first, never echo the value); check the edition with `rules_for` (its error text, exit 1, never echo the value); then set the setting at layer `project:<P>` exactly as `tl_cli/config.py` `set_` does (`change_setting`, `source="cli"`, `--actor` through `refuse_agent` from `tl_cli.actors`); print `set awp.rules_of_credit.set project:<P> "<edition>"` (or `unchanged ...` as `set_` does).
- The CLI never widens the viewer; these reads need none (package content is not record text).

## Interfaces (verbatim from repo)
```python
# tl_mod_awp/progress/engine.py
def edition_key(conn: Connection, scope: str) -> str
def rules_for(key: str) -> Rules          # raises RulesOfCreditError
# tl_core/settings/service.py
def change_setting(uow, *, key, layer, value=None, reset=False, actor, source, reason=None, accept_risk=False, applies_at=None, ...) -> Outcome
# tl_cli/derive_support.py: Project (option), Actor (option), DEV_ACTOR, acting, fail, scope_of, service_errors
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_iwp_read.py` (module shape, `register`), `packages/tl-cli/src/tl_cli/config.py` (`set_` only, lines 243-288), `packages/tl-cli/src/tl_cli/awp.py`, `packages/tl-cli/src/tl_cli/actors.py`
- `packages/tl-modules/awp/src/tl_mod_awp/progress/engine.py` (lines 80-93, 160-205)
- the provided test `docs/tickets/P2-I5/provided/T01_test_awp_roc.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_roc.py` (create): `register(app: typer.Typer) -> None` adds the group `roc` with `ls`, `show`, `set`
- `packages/tl-cli/src/tl_cli/awp.py`: one import and one `awp_roc.register(app)` line
- `packages/tl-cli/tests/test_awp_roc.py` (create: copy of the provided test, byte-identical)
- `docs/reports/P2-I5/T01.md` (create)
- consequential pins: none expected; a test outside these paths that breaks only because `tl awp` has a new group is updated and listed

## Steps
1. Copy the provided test to its path. 2. Write `awp_roc.py` after `awp_iwp_read.py`'s shape (one `session`-less read opens `open_uow(db, readonly=True)`; `db: DbTarget = ctx.obj`). 3. Register in `awp.py`.

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_awp_roc.py packages/tl-cli/tests/test_cli_awp.py
```
Expected: all pass, `just check` clean. `cmp` of the test against the provided copy is identical.

## Tests to add
The provided test (copied). Add nothing else.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, the `cmp` line. Commit subjects `P2-I5-T01: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- `change_setting` refuses the admin actor of the test for a reason that needs a word or a flag the ticket does not name (write the refusal text under Blocked).
- The provided test fails on a line the ticket does not explain.
- A pinned test outside Allowed paths breaks for another reason than the new group.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
