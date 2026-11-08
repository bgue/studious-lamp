# P2-I2-T04d — CLI reads: `tl awp iwp ls|show|scope` and `tl constraint ls|show|groups`

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli, read, confidentiality
Depends on: T04a, T04a2, C2 (merged). Readiness verbs are NOT here (D27: T04d2 after S4)
Branch: `p2/i2-t04d-cli-reads`
Worktree: harness-created under `/home/user/wt/i2/t04d` (from `p2/i2` head)

## Goal
Two new read modules, each exposing `register(app: typer.Typer) -> None` that adds its commands to the Typer it is given (the glue ticket T04g makes the groups and adds the register calls; this ticket
edits neither `awp.py` nor `main.py`). `awp_iwp_read.register(iwp_app)`: `ls`, `show`, `scope`. `constraint_read.register(app)`: `ls`, `show`, `groups`.
Output is one fact per line, two spaces between fields, `-` for none, thousands separators and one decimal on hours (use `hours`, `cell` as `awp_read.py` does).

## Brief references (pasted)
> IWP reads (`tl_mod_awp.iwp_views`, no access check inside; `open_uow(db, readonly=True)`; same shape as `cwp_ls`/`cwp_show` in `awp_read.py`):
> - `ls [--state S] [--discipline D] [--foreman user:X] [--limit N]` -> `iwps: <n>` then `<number>  <state>  <discipline|->  <foreman|->  <hours|->  <scope_count>  <title cut 60>`; filters pass to `iwp_list`.
> - `show NUMBER` -> `iwp <number>`, `title`, `state`, `discipline`, `foreman`, `cwp`, `planned <start> to <finish>`, `hours`, `crew`, `scope <n>` then `  <type>  <count>` per `scope_by_type`, `pins <n>`,
>   `open constraints <n>`, `signoffs <n>` then `  <by>  <role>  <at>` per signoff (never the record hash). A missing, hidden or void IWP is `error: no IWP <number>` (one text for all three, exit 1).
> - `scope NUMBER [--limit N]` -> `scope: <n>` then `<number|->  <type>  <commodity|->  <qty|->  <uom|->  <est_hours|->  <description cut 60>`; `None` is `error: no IWP <number>`.
> Constraint reads (`tl_core.constraints`: `list_constraints`, `count_constraints`, `get_constraint`, `review_groups`, `BY_WORDS`; all take `viewer=session_viewer(db)` from `tl_cli.session`):
> - ENTRY CHECK FIRST (D25): before any read, require the word `tl_core.constraints.commands.VIEW_WORD` for module `ACCESS_MODULE` on the project scope, for the invoking actor, exactly as
>   `handlers.require_edit` (`packages/tl-core/src/tl_core/constraints/handlers.py` ~line 183) does with `require_word(conn, holder_for_actor(conn, actor), scope=, module=, word=normalise_word(VIEW_WORD), what=VIEW_WORD)`;
>   a `ForbiddenError` prints the same text as an unknown id would not hide: `error: forbidden: ...` exit 1 (the word is a role gate, not a hidden-record answer). Put the check in one helper in `constraint_read.py`
>   used by all three verbs. The actor is `--actor` (default `DEV_ACTOR`, `acting(db, actor)`).
> - `ls [--subject KEY] [--state S] [--category C] [--phase P] [--blocking|--advisory] [--owner user:X] [--limit N]` -> `constraints: <total>` (`count_constraints`, same filters, so the total is the visible count) then
>   `<key>  <state>  <severity>  <category>  <phase>  <owner|->  <due|->  <age>d<*>  <description cut 60>` (`*` when `aging`). `--subject KEY` resolves the record key to its id with the lookup `tl_cli/link.py` uses;
>   an unknown or hidden subject is `error: no record <key>`.
> - `show KEY` -> `constraint <key>`, `state`, `severity`, `category`, `phase`, `source`, `owner`, `due`, `raised <raised_on>  age <n>d`, `check`, `target <kind|ref type: text|->` (never print a hidden target: the view already
>   drops it), `description`, `cleared <at> by <who>: <reason>` when cleared. An absent or hidden-subject constraint is `error: no constraint <key>` (same text: hidden looks like missing).
> - `groups --by owner|category|age [same filters as ls]` -> `groups: <n>` then `<label>  <count>  blocking <b>  aging <a>`; `--by` outside `BY_WORDS` is a usage error (exit 2). Groups are built with `review_groups` over the filtered list.
> The CLI never widens the viewer; it prints keys and fields the views return, nothing it queries itself.

## Interfaces (verbatim from repo)
`packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py`: `iwp_list(conn, scope, *, state, discipline, foreman, limit)`, `iwp_detail(conn, scope, number)`, `iwp_scope(conn, scope, number, *, limit)`.
`packages/tl-core/src/tl_core/constraints/queries.py`: `list_constraints/count_constraints(conn, scope, *, subject_id, state, category, phase, blocking, owner, [limit,] [today,] viewer)`, `get_constraint(conn, id, *, viewer)`.
`ConstraintView` fields: id key state scope subject_id phase severity category source owner description check_name clear_reason target_kind target_id target_ref_type target_ref_text effective_at due_at cleared_at cleared_by raised_on age_days aging phase_ungated.
`get_constraint` takes an id; `show KEY` first finds the constraint id by `list_constraints(..., limit=500)` filtered on key in Python, or by one `SELECT id FROM cur_core_record WHERE key=:k AND type='core.Constraint'` read; do not invent a new core query.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_read.py` (lines 1-60 and `cwp_ls`, `cwp_show`, `register`), `packages/tl-cli/src/tl_cli/derive_support.py` (helpers), `packages/tl-cli/src/tl_cli/session.py` (`session_viewer`, `fail`)
- `packages/tl-core/src/tl_core/constraints/handlers.py` (lines 175-195 only), `docs/reports/P2-I2/T04a.md`, `docs/reports/P2-I2/T04a2.md`, `dev/accept/P2-I2/t04a2_checks.py` (seed helpers)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_iwp_read.py` (create), `packages/tl-cli/src/tl_cli/constraint_read.py` (create)
- `dev/accept/P2-I2/T04d.py` (create; helper `t04d_checks.py` if over 70 lines), `docs/reports/P2-I2/T04d.md` (create)
Not here: `awp.py`, `main.py`, any write verb, readiness, new pytest (S5), any change to `tl_core` or `tl_mod_awp`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04d.py
just gate packages/tl-cli/tests/test_cli_awp.py
```
`T04d.py` (seed a SQLite ledger with the C2/T04a2 helpers, build a throwaway `typer.Typer`, call both `register`s, drive it with `CliRunner`; one `PASS <check>` per line; final `T04d ok`): `iwp ls` count and order; `iwp show` lines and no
record hash anywhere in the output; `iwp scope`; unknown IWP and hidden IWP print byte-identical errors; `constraint ls` total equals the number of lines; filters (state, owner, blocking); `groups --by` each of the three, `--by x` exit 2;
a viewer without `core.constraint.view` is refused by all three verbs BEFORE any read (assert no SELECT runs: count statements with a before_cursor_execute listener); a hidden-subject constraint is `error: no constraint <key>`
and absent from `ls` and its total; output carries no `Traceback`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T04d: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and report *Blocked* if the word check needs a holder the CLI cannot build, if `show KEY` cannot find the constraint without a new core query, or if a snapshot test outside Allowed paths breaks (the glue ticket owns pins).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
