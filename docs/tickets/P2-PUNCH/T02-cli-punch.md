# P2-PUNCH-T02 — CLI group `tl punch`: raise, edit, clear, verify, reopen, void, ls, show

Status: staged (dispatch after T01 merges; the dataclass names are in `views.py` and its report)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, access
Depends on: T01
Branch: `p2/punch-t02-cli`
Worktree: harness-created under `/home/user/wt/punch/t02` (from `p2/punch` head)

## Goal
A person raises, edits, clears, verifies, reopens and voids punch items, and lists and shows them, from the terminal. The ticket creates the group `tl punch`. Each write verb builds one S2 command (`commands.py`: `punch_item` is the record id read with `get_record` from the key, `--from KEY` becomes `from_record_id` (an id), `--due` is `due_on`, `--expected-version` is `expected_version`), gates it with `require_command`, and runs the handler `PUNCH_COMMANDS` names, as `awp_iwp_write.py` does (import `_execute`, `_line`, `_handler` from `awp_write.py`; do not copy them). Reads open `open_uow(db, readonly=True)`, pass `viewer=session_viewer(db)` (`tl_cli.session`) and first require the word `quality.view` for the actor on the project scope as `constraint_read.require_view` does.

## Brief references (pasted; options are the contract)
> Records are named by the key reads print (`P123-PUN-0001`; L-P2-I3-3), resolved to an id with `get_record` (as `tl_cli/link.py` does); unknown or hidden is `error: no punch item <key>` (one text). `--from KEY` takes the key any read prints (an IWP number, a tag number, a document number, a correspondence number): an unknown or hidden key is `error: no record <key>` (exit 1) and nothing is written. `--project` and `--actor` as in `awp_iwp_write.py`. State verbs take `--expected-version N` (default: the version read in the same unit). `ls --overdue` passes `today=date.today().isoformat()`. A source key that resolves under the actor's viewer gives the id; else `error: no record <key>`. Write output is one line via `_line`: `<verb> <key>  version <v>`.
> - `raise --subject T [--description T] [--area A] [--system S] [--due D] [--category A|B|C] [--assignee user:X] [--from KEY]` -> `raised <key>  version <v>` (there is no `--raised-by`: the actor is the raiser)
> - `edit KEY [--subject] [--description] [--area] [--system] [--due] [--category] [--assignee]` -> `edited ...` (none given is a usage error, exit 2)
> - `clear KEY --note N` -> `cleared ...`; `verify KEY` -> `verified ...`; `reopen KEY --reason R` -> `reopened ...`; `void KEY --reason R` -> `voided ...` (a missing `--note` or `--reason` is exit 2)
> - `ls [--state S] [--area A] [--system S] [--assignee user:X] [--category C] [--from KEY] [--overdue] [--limit N]` -> `punch items: <n>` then one line per item, two spaces between fields, `-` for none: `<key>  <state>  <category>  <area>  <system>  <due>  <assignee>  <subject cut 50>` (ordered by key; `<n>` is the page `total`)
> - `show KEY` -> exactly these lines: `punch item <key>`, `state  <State>`, `subject  <text>`, `category  <C>`, `area  <a|->`, `system  <s|->`, `due  <date|->`, `assignee  <a|->`, `raised by  <actor>`, `raised from  <key|->`, `cleared  <by|->  <date|->  <note|->`, `verified  <by|->  <date|->`, `reopened  <n>  <reason|->`, `void  <reason|->`
> A `ForbiddenError` or handler refusal prints through `service_errors()` (`error: ...`, exit 1), never a traceback. No password or token option exists (ADR-0009).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_iwp_write.py` (all), `awp_write.py` (lines 60-135), `constraint_read.py` (`require_view`), `session.py` (`session_viewer`), `main.py` (lines 75-90 and 155-165)
- `packages/tl-modules/quality/src/tl_mod_quality/{commands.py, module.py, views.py}`, `docs/reports/P2-PUNCH/{S2,T01}.md`
- `packages/tl-cli/tests/test_cli_awp.py` (lines 1-80: how the world helper is loaded by path)

## Allowed paths
- `packages/tl-cli/src/tl_cli/punch.py` (create: `app`, `register_all()`), `punch_write.py` (create: `register(app)`), `punch_read.py` (create: `register(app)`)
- `packages/tl-cli/src/tl_cli/main.py` (one import and one `add_typer(punch.app, name="punch")` line)
- `packages/tl-cli/tests/test_cli_punch.py` (create), consequential pins of the CLI command list (union form, listed)
- `docs/reports/P2-PUNCH/T02.md` (create)
The dependency `tl-mod-quality` is already in `packages/tl-cli/pyproject.toml` (S1).

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_cli_punch.py packages/tl-cli/tests/test_cli_awp.py
```

## Tests to add
`packages/tl-cli/tests/test_cli_punch.py`, ledger built by the module's commands through `punch_world.py` (`packages/tl-modules/quality/tests/punch_world.py`, loaded by path as `test_cli_awp.py` loads `awp_world`; no projection writes; a hidden source is a restricted correspondence item made by the helper): raise prints `raised P123-PUN-0001  version <v>` and `-0002`; raise with `--from` an IWP prints `raised from` that key in `show`; `--from` unknown prints `error: no record <key>` and `ls` is unchanged; clear by `rob`, verify by `rob` is refused with the S2 fixed message (exit 1), by `uma` is `error: forbidden`, by `sue` prints `verified`; `show` lines exactly as above after each state; reopen and void need their option (exit 2) and work; clear on a void item prints `a void punch item accepts no further change`; the self-verify refusal text is `the person who cleared a punch item may not verify it`; a stale `--expected-version` is refused; `edit` with no option exits 2; `ls` filters each narrow, `--overdue` with a frozen day, count equals data lines; an unknown key and a key of another project print byte-identical errors; a hidden-source item gives `error: no punch item <key>` for `uma`, the same text as an unknown key, and is absent from `ls` for `uma`; an actor without `quality.view` (`World.person(name, ())`: an account whose roles derive no module role; if it cannot be created, write it under Blocked) is refused before any SELECT (count statements with a `before_cursor_execute` listener); no output holds a 32-hex id or `Traceback`.

## Escalation triggers
- A verb needs a command model that is not in `PUNCH_COMMANDS`; `show` needs a field the T01 dataclasses lack (write which); a CLI command-list pin cannot be updated in union form.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T02: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
