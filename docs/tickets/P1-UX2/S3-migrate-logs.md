# P1-UX2-S3 — Every log except documents on LogScreen, actions wired, remaining code labels

Status: draft (dispatch in wave 2, after S1 and S2 are merged)
Tier: sonnet
Kind: piece
Review: full
Labels: tui, tests
Depends on: S1 (allowed_actions, document/engineering/correspondence command runners), S2 (LogScreen, ActionFormScreen)
Branch: `p1/ux2-s3-migrate-logs`

## Goal
Tag register, correspondence (register, triage inbox, clocks), the RFI log, the Commercial register, the evidence
trail, the schedule screens that list records, the review queue, the integration registry and the schema workbench list
all stand on `LogScreen`: breadcrumb, list, panel (below, right at 160+ columns), actions bar, keys row, summary line.
For tags, correspondence items, RFIs and commercial notices the actions bar is fed by `client.allowed_actions(record_id)`
and an action runs the existing command through its form. Raw codes in any cell become plain words. The document
register is NOT in this piece (S4).

## Brief references (pasted, abridged)
> SCOPE §1/§2 as in S2. Actions come from the server, never guessed by the screen: the bar shows exactly the offers
> returned for the highlighted record, mapped to keys; a refusal from the command is shown in the status line; hidden
> records answer as missing. Example RFI bar: `[a] Answer  [c] Close  [e] Escalate  [Enter] Open record`.
> P1-UX2 D6: a raw code in a cell (`Structural`, `Isometric`, `Piping` read as STR/ISO/PIP) is fixed where the labels
> are loaded; `schema/**` is never edited here (stop and list instead).
> AGENTS: no business logic in the TUI. The screen decides nothing about who may do what.

## Interfaces
```python
# tl_tui/log_actions.py (new): presentation of server offers, keyed by command name
@dataclass(frozen=True)
class ActionUi: key: str; fields: tuple[FormField, ...] = (); confirm: str | None = None
                build: Callable[[dict[str, str], str, int|None], Command]   # (form values, record id, version) -> command model
ACTION_UI: Mapping[str, ActionUi]        # AnswerTechnical a (answer text, cost/schedule choice), CloseTechnical c (reason), EscalateTechnical e, IssueTechnical ...
def log_actions(offers, ui, run) -> list[LogAction]      # an offer whose command has no UI entry is NOT shown (logged once); never invents one
def run_module_command(client, name: str, cmd) -> CommandResult   # picks correspondence_command / engineering_command
```
Each migrated log keeps its existing public class name, `KEY_HINTS` becomes the keys row (navigation and filters
only), and its summary/count line stays. Keys that collide with an action key are moved (the RFI log keeps `a`, `c`,
`e` for Answer, Close, Escalate as in the owner's example; the evidence key moves) and the change is listed in the
report, `keymap.py`, the help screen and the README table row.
Screens with no server-asked actions today (schedule, review queue, integration registry, schema workbench) show
their existing action keys exactly as the screen enables them now (their own role logic is unchanged); no new server
call is added for them.

## Context (≤ 10 files; read the first four fully, the rest by function)
- `packages/tl-tui/src/tl_tui/widgets/log_screen.py`, `action_form.py`, `log_text.py` (S2)
- `packages/tl-tui/src/tl_tui/widgets/domain_screen.py`, `correspondence_screen.py`, `tag_register.py`
- `packages/tl-tui/src/tl_tui/widgets/{schedule_screen,review_queue,integration_screen,schema_screen}.py`
- `packages/tl-tui/src/tl_tui/{labels_load.py,display.py,keymap.py}`
- `packages/tl-tui/tests/test_plain_walk.py`, `test_tour_leaks.py`, `fakes_correspondence.py`
may explore: the matching `*_text.py` modules and `tests/test_*_screen.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/log_actions.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/{tag_register,correspondence_screen,domain_screen,schedule_screen,review_queue,integration_screen,schema_screen}.py`
- `packages/tl-tui/src/tl_tui/{tag_text,correspondence_text,rfi_text,commercial_text,evidence_text,schedule_text,integration_text,schema_text,thread_text}.py`
- `packages/tl-tui/src/tl_tui/{labels_load,display,keymap}.py` (S3 alone edits `labels_load.py` and `display.py`; S4 must not)
- `packages/tl-tui/src/tl_tui/widgets/help_screen.py`, `palette.py`, `commands.py` only if a moved key shows there
- `packages/tl-tui/tests/**` EXCEPT S5's (`test_details_registry.py`, `test_record_plain.py`, `test_record_screen.py`, `test_rfi_record.py`, `test_timeline_text.py`, `fakes_rfi_record.py`) and `test_document_register.py`, `test_document_*`, `fakes_documents.py` and `__snapshots__` entries of the document register (S4)
- `packages/tl-tui/README.md` (table rows of the migrated screens and the key-map note only; no "Log screens" section)
- `docs/reports/P1-UX2/S3.md` (create)

Consequential pins (rule 12): snapshots, id-based queries (`#tags-table` -> `#log-table`) and key tests that break only
because the screen is now a LogScreen are updated here, each with a counterpart that pins the unchanged part (e.g. the
same rows and cells), and listed in the report. Anything else outside Allowed paths stops.

## Steps (commit per screen; `just gate` only at the end)
1. Tag register, then correspondence screen (three tabs share the base), then domain screen (RFI log, Commercial, evidence). Actions via `allowed_actions`; forms via `ACTION_UI`.
2. Schedule, review queue, integration registry, schema workbench: structural move, same behaviour, existing keys in the bar.
3. Code-label audit: open every migrated log (and the document register's fake data) as a plain user with the fixture data; every raw code in a cell goes through `code_label`; fix the loader where a code list is not reaching `Labels`. Report each fix (code, where). A code missing from the schema's lists is listed, not invented.
4. Update `test_plain_walk.py` exclusions/ids as needed; `KNOWN_LEAKS` stays empty.

## Acceptance (run these, once)
```
just check
just gate packages/tl-tui | tee .gate/summary.txt
just gate-pg packages/tl-tui/tests/test_embedded_real_services.py
```
Expected: PASS; only snapshots of the migrated screens changed (listed).

## Tests to add
- `packages/tl-tui/tests/test_log_actions.py` (new): offers map to keys; an offer without a UI entry is not shown; Answer opens the form and sends `AnswerTechnical` with the typed text; a refusal from the command lands in the status line; the bar for an RFI differs between an answerer fake and a reader fake (fake `allowed_actions` returns the lists).
- `packages/tl-tui/tests/test_log_migration.py` (new): each migrated log shows `#log-crumb` of the form `<project> › <log name> › <number>: <title>` for the highlighted row, is wide at 170 columns and stacked at 100, and has an actions bar and keys row.
- Existing screen tests: updated for ids and keys (pins), plus the cell-label assertions for the code audit.

## Mutation (builder, own worktree, 3 lines)
Sentinel plus 2: (1) bar shows an offer with no UI entry; (2) `allowed_actions` failure leaves the previous row's actions in the bar. Each killed.

## Report requirements
`docs/reports/P1-UX2/S3.md` ≤ 60 lines: deviations first (moved keys, code-label fixes), consequential pins, commands, learnings.

## Escalation triggers
- A log cannot move to the base without changing what a command does or a viewer may see.
- A code label needs `schema/**` (list code, list, file).
- More than ~3 000 diff lines: stop at a screen boundary, commit, report what is left (the next round splits by area).
