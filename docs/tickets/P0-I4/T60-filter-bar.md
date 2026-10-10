# P0-I4-T60 — Filter bar widget

Status: ready
Tier: haiku
Labels: tui
Depends on: — (the stub, the messages and `RecordGrid.apply_filter` are on the base branch)
Branch: `p0/i4d-t60-filter-bar`

## Goal
`packages/tl-tui/src/tl_tui/widgets/filter_bar.py` has final names, signatures and docstrings; the bodies raise `NotImplementedError`. Implement them. The bar is the text box above the grid where the user types a query-language filter (`status:open title~bevel`). It collects text and shows a result; it parses nothing. The app (supervisor, next round) will send the text to the grid and pass the grid's `FilterResult` back to `show_result`. One provided test file (12 tests) must pass.

## Brief references (pasted)
> **10.2 Filter bar:** structured query builder plus text query language (e.g. `status:open discipline:PIP psets.nde.method=RT due<+7d linked:NCR`). Key `/` focuses the filter.
> **Syntax errors show with their position:** the parser raises `QuerySyntaxError(message, position)`, `position` being a 0-based character offset into the typed text. The grid turns that into `FilterResult(ok=False, message=..., position=...)`; the bar shows the message and a caret under that character.
> **Accessibility (10.3):** meaning never rides on colour alone: errors start with `✗`.

### Specification (the provided tests check it)
- `result_line(result)`: `""` when `result.ok` and `result.count is None`; `"0 matches"`, `"1 match"`, `"12 matches"` for an ok result with a count; for a failure `"✗ <message>"` followed by `" (position <n>)"` when `position` is not `None`.
- `caret_line(text, position)`: `""` when `position is None`; else clamp `position` to `0..len(text)`, and return `" " * (INPUT_OFFSET + cell_len(text[:position])) + "^"` (`cell_len` from `rich.cells` counts terminal cells, so a wide character counts 2).
- `FilterBar.compose`: yield `Input(value=self._text, placeholder=PLACEHOLDER, id="filter-input")`, then `Static("", id="filter-result", markup=False)`, then `Static("", id="filter-caret", markup=False)`.
- `value` is the input's current text; `set_text(text)` stores it in `self._text` and, when `self.is_mounted`, sets the input's value.
- `show_bar()` sets `self.display = True` and focuses the input; `hide_bar()` sets `self.display = False`.
- `show_result(result)`: update `#filter-result` with `result_line(result)`; update `#filter-caret` with `""` when `result.ok`, else `caret_line(self.value, result.position)`.
- `on_input_submitted(event)`: `event.stop()` and post `FilterSubmitted(event.value)`. `action_close_bar()` posts `FilterClosed()`.
- Imports to add to the stub: `from rich.cells import cell_len`; `Static` next to `Input` in `from textual.widgets import ...`; `from tl_tui.messages import FilterClosed, FilterSubmitted`.

Learnings that apply:
- The provided test lives at `docs/tickets/P0-I4/provided/test_filter_bar.py.txt`; copy it to `packages/tl-tui/tests/test_filter_bar.py` and do not edit the copy. It is already formatted: `diff` the copy against the original in the last acceptance step.
- Remove the `STUB (P0-I4-T60)` paragraph from the module docstring when you implement it.
- Textual: build `Input` in `compose`, never in `__init__` (L-P0-I2-B6); a `Static` shows `[...]` as markup unless `markup=False`; do not name your own attribute after a DOM property (`visible`, `query`, `shown` is fine). Do not add `__init__.py` to the tests directory.
- ruff limits lines to 100 columns, docstrings included; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/P0-I4-T60.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/grid.py
@dataclass(frozen=True)
class FilterResult:
    ok: bool
    count: int | None = None      # matching records; None for a blank filter or a failure
    message: str = ""
    position: int | None = None   # 0-based character offset of a syntax error

# packages/tl-tui/src/tl_tui/messages.py
class FilterSubmitted(Message):   # FilterSubmitted(text: str); .text
class FilterClosed(Message):      # no arguments

# packages/tl-tui/src/tl_tui/widgets/filter_bar.py (the stub: keep every name, signature and class attribute)
INPUT_OFFSET = 1
PLACEHOLDER = "status:open  title~bevel  linked:NCR  psets.nde.method=RT   (Enter applies)"
def result_line(result: FilterResult) -> str
def caret_line(text: str, position: int | None) -> str
class FilterBar(Vertical):  # KEY_HINTS, BINDINGS (escape -> action_close_bar) and DEFAULT_CSS are final
    def compose(self) -> ComposeResult
    @property
    def value(self) -> str
    def set_text(self, text: str) -> None
    def show_bar(self) -> None
    def hide_bar(self) -> None
    def show_result(self, result: FilterResult) -> None
    def on_input_submitted(self, event: Input.Submitted) -> None
    def action_close_bar(self) -> None
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/filter_bar.py` (the stub)
- `packages/tl-tui/tests/test_filter_bar.py` (after you copy it)
- `packages/tl-tui/src/tl_tui/widgets/prompt.py` (an `Input`-based widget in this package, for style)
- `packages/tl-tui/AGENTS.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/filter_bar.py` (edit)
- `packages/tl-tui/tests/test_filter_bar.py` (create: copy of the provided test)
- `docs/reports/P0-I4/P0-I4-T60.md` (create: your report)

## Acceptance
```
cp docs/tickets/P0-I4/provided/test_filter_bar.py.txt packages/tl-tui/tests/test_filter_bar.py
uv run pytest packages/tl-tui/tests/test_filter_bar.py -q
just check
uv run pytest packages/tl-tui -q
diff packages/tl-tui/tests/test_filter_bar.py docs/tickets/P0-I4/provided/test_filter_bar.py.txt
```
Expected: 12 tests pass in the first command; `just check` is clean; the whole TUI suite passes; the diff is empty.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the pass counts of the first and third commands.

## Escalation triggers
- Stop and report *Blocked* if the stub and the specification disagree, or if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
