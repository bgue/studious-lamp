# P2-I4B-T06 — toolcrib_text.py and ToolcribScreen: issue and return a tool in one line

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: P2-I3 (merged on trunk: `IssueStock`, `ReturnStock`, `list_materials_stock`)
Branch: `p2/i4b-t06-toolcrib`
Worktree: `/home/user/wt/i4b/t06`

## Goal
The toolcrib fast-entry screen (brief §10.5): one input line, keyboard only. `Ctrl+I` or `Ctrl+R` picks issue or return mode (default issue); the person types `<tool> <person> [xN]` and `Enter`;
the screen sends one `IssueStock` or `ReturnStock` through `client.materials_command` and says what happened on the status line, then clears the line and keeps the focus there for the next one.
All text, parsing and the command builder live in a Textual-free module with a provided test. The screen is unregistered (the nav entry is T07a's glue). A tool is a lot key (a serialised tool has its own lot, typed or scanned) or an item code with one lot in the crib.

## Brief references (pasted)
> §10.5 Toolcrib issue/return (scan-friendly, single-line flow). §M4: Toolcrib mode: fast issue/return screen (scan or type asset/item, person, qty) with keyboard-only flow. Levels: ... Laydown/Yard → Toolcrib → Crew/Gang box. Location kinds include `toolcrib`.
> Movement on an I3 lot: issue = `from_location` the crib, optional `person`; return = `to_location` the crib. A return is refused by the handler when more than the net issued comes back; its text goes to the status line.
> Layout skill `tui-layout`: labels left, words not codes, `—` never typed into a field, errors under the field in words.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_mod_materials.handlers.movements
class Movement(BaseModel):   # extra=forbid
    lot_key: str; qty: str; uom: str; from_location: str | None = None; to_location: str | None = None
    cost_code_id: str | None = None; mto_line_id: str | None = None; reason: str | None = None
    person: str | None = None (<= 120); direction: Literal["in","out"] | None = None
class IssueStock(Command):  movements: list[Movement]   # Command: actor: str, source: str, scope: str ("project:P123")
class ReturnStock(Command): movements: list[Movement]
# ClientInterface (tl_tui.client)
#   list_materials_locations(project, ...) -> list[LocationView]   # LocationView: code title kind parent_code retired lots lines ...
#   list_materials_stock(project, *, lot=None, location=None, item=None, heat=None, subtree=False, limit=1000) -> list[StockRowView]
#       StockRowView: lot heat_no item_code item_title location location_title on_hand: Decimal reserved available uom
#   materials_command(name: str, cmd: Command) -> CommandResult      # name "IssueStock" | "ReturnStock"
# errors: from tl_tui.errors import CLIENT_ERRORS, describe_error  (a refusal goes to the status line, the line keeps what was typed)
```
The provided test `docs/tickets/P2-I4B/provided/T06_test_toolcrib_text.py` is the contract for `tl_tui.toolcrib_text`: `parse_line`, `check_line(mode, parsed)`, `resolve_tool(tool, rows)`, `build_command(...)`, `done_text(...)`, the message constants `NEED_TOOL NEED_PERSON BAD_QTY BAD_MODE`, `no_such_tool(tool)`, `several_lots(tool, n)`, `ToolcribError`, `MODES`. Choose the wording of the constants yourself in plain words (no codes); the test compares against the constants.
Also in the module (not tested by the provided file): `KEYS = "Enter send  Ctrl+I issue  Ctrl+R return  Esc close"`, `mode_title(mode)`, `crib_choices(locations)` (non-retired locations of kind `toolcrib`, by code).

## Context (read these, nothing else)
- `docs/tickets/P2-I4B/provided/T06_test_toolcrib_text.py` (whole), `packages/tl-tui/src/tl_tui/receipt_entry_text.py` (module shape, pure style), `packages/tl-tui/src/tl_tui/widgets/receipt_entry.py` (screen pattern: bindings, `say`, `CLIENT_ERRORS`, client and actor in `__init__`)
- `dev/accept/P2-I3/T06e.py` (whole: seed copy, `EmbeddedClient`, `TlApp` host, screenshots; copy its helpers)
may explore: `packages/tl-tui/src/tl_tui/layout.py`, `widgets/setting_form.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/toolcrib_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/toolcrib_screen.py` (create)
- `packages/tl-tui/tests/test_toolcrib_text.py` (create: the provided file, byte-identical)
- `dev/accept/P2-I4B/T06.py` (create), `docs/reports/P2-I4B/T06.md` (create)
Not here: `app.py`, `commands.py`, `client.py`, `navigation.py`, `layout.py`, any other test, any schema or materials file. A needed client method that is missing: stop.

## Acceptance
```
uv sync --all-packages
cp docs/tickets/P2-I4B/provided/T06_test_toolcrib_text.py packages/tl-tui/tests/test_toolcrib_text.py
just check
just gate packages/tl-tui/tests/test_toolcrib_text.py
uv run python dev/accept/P2-I4B/T06.py
```
`T06.py` (exit 0; one `PASS <check>` per line; a copy of the demo seed with an `EmbeddedClient` as T06e.py; project `P123`; the seed's location `TC1` and a lot with stock there, found with `list_materials_stock`; if the seed has none, receive one with `CreateReceipt` at `TC1` in the script's own setup, listing the call in the report):
(1) at 80x30 and 170x40: open the screen for `TC1`, type `<lot> Ana Ruiz x1` and `Enter`: the status line reads the `done_text`; `list_materials_movements("P123", lot=<lot>)` shows an issue with person `Ana Ruiz`; stock at `TC1` fell by 1; the input is empty and has focus;
(2) `Ctrl+R`, type `<lot> Ana Ruiz`, `Enter`: a return, stock back; returning more than was issued puts the handler text on the status line and the line keeps its text;
(3) an unknown tool and an issue without a person show `no_such_tool` and `NEED_PERSON`, nothing is posted; keyboard only (no mouse call in the script);
(4) screenshots `.accept/shots/T06-toolcrib-80.svg` and `-170.svg` with `app.export_screenshot(title="Toolcrib")`.

## Tests to add
`packages/tl-tui/tests/test_toolcrib_text.py` only (the provided file).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; the shot paths; candidate learnings. Commit subjects `P2-I4B-T06: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Escalation triggers
- Stop and report *Blocked* if the provided test needs a name outside its imports, the crib location cannot be found through the client, the diff passes 400 lines, or the screen needs a client method that is missing.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
