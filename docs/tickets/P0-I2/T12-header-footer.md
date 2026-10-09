# P0-I2-T12 — Header and footer widgets

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T11 (merged on `p0/i2b`)
Branch: `p0/i2b-t12-header-footer`

## Goal
The shell's header bar and two-line footer render what the sketch shows: a breadcrumb on the left and the connection
and user on the right of one header line; key hints, a status line, and a right-aligned selection count in the footer.
The widgets exist as stubs with their final public interface; this ticket replaces their rendering and adds the pure
layout functions `header_line` and `footer_lines`.

## Brief references (pasted)
> Header: Company ▸ Project ▸ Module ▸ View        [sync ● live] [user] [inbox 3]  (§10.1)
> Footer: context key hints │ status / job progress │ selection count  (§10.1)
> Accessibility: ... no meaning by colour alone (status also as text/symbol) (§10.3)

Sketch 1 (§10.6), top and bottom lines:
```text
┌─ ACME ▸ P123 ▸ Piping ▸ Welds ───────────────────────────── ● live · jsmith · ✉ 3 · ⏱ 2 at risk ─┐
│ Enter open  l link  d deficiency  b bulk  w workflow  F feed  : palette  ? help                  │
│ 2 selected · RT request draft ▸ [b]                       sync ✓ seq 48,211,933                  │
```

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns and applies to docstrings and comments. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui` (the second sorts imports).
- Textual `Static` parses `[...]` as markup. The stubs already pass `markup=False`; keep it, because key hints contain `[ ]`.
- Do not name an attribute after a Textual `Widget` attribute (`visible`, `size`, `region`, `id`, `parent`...).
- Tests have no async plugin: drive apps with `helpers.run_pilot` and read the screen with `helpers.screen_text`
  (`from helpers import run_pilot, screen_text` works because `tests/conftest.py` adds the directory to `sys.path`).
  Test helpers type apps as `App[Any]`.

## Interfaces (verbatim from repo at the branch point, plus the new functions)
```python
# packages/tl-tui/src/tl_tui/widgets/header.py  (stub today)
class TlHeader(Static):
    def __init__(self, *, company: str, scope: str, view: str = "Records",
                 mode: str = "embedded", actor: str = "user:dev", id: str | None = None) -> None: ...
    # attributes: company, scope, view, mode, actor
    def set_view(self, view: str) -> None: ...        # changes the last breadcrumb element and redraws

# NEW in header.py
def header_line(company: str, scope: str, view: str, mode: str, actor: str, width: int) -> str: ...

# packages/tl-tui/src/tl_tui/widgets/footer.py  (stub today; keep DEFAULT_HINTS and hints_for unchanged)
DEFAULT_HINTS = "F2 nav  F3 context  F6 panels  Ctrl+Q quit"
def hints_for(widget: Widget | None) -> str: ...
class TlFooter(Static):
    def __init__(self, *, id: str | None = None) -> None: ...
    # attributes: hints, status, severity, selection_count
    def set_hints(self, text: str) -> None: ...
    def show_status(self, text: str, severity: Severity = "info") -> None: ...
    def set_selection_count(self, count: int) -> None: ...

# NEW in footer.py
def footer_lines(hints: str, status: str, severity: Severity, selection_count: int,
                 width: int) -> tuple[str, str]: ...

# packages/tl-tui/src/tl_tui/messages.py
Severity = Literal["info", "warning", "error"]
```

Rules for `header_line(...)` (all lengths are terminal cells: use `rich.cells.cell_len` and `set_cell_size`):
1. `project` is `scope` without a leading `project:` (scope `company` stays `company`).
2. `left = f" {company} ▸ {project} ▸ {view}"`; `right = f"● {mode} · {user} "` where `user` is `actor` without a leading `user:` (other prefixes such as `svc:` stay).
3. If `cell_len(left) + 1 + cell_len(right) <= width`: return `left`, then spaces, then `right`, exactly `width` cells.
4. Else if `cell_len(left) <= width`: return `left` padded with spaces to `width` (the right part is dropped).
5. Else: return `set_cell_size(left, width - 1) + "…"` (exactly `width` cells).

Rules for `footer_lines(...)` returns `(first, second)`:
1. `first = f" {hints}"`; if longer than `width`, cut to `set_cell_size(first, width - 1) + "…"`. It is not padded.
2. `left = f" {prefix}{status}"` when `status` is non-empty, else `""`. `prefix` is `""` for `info`, `"! "` for `warning`, `"✗ "` for `error`.
3. `right = f"{selection_count} selected "` when `selection_count > 0`, else `""`.
4. Both empty: `second = ""`. Only `left`: `second = left`, cut with an ellipsis as in rule 1 if longer than `width`. Otherwise (a `right` exists): cut `left` to `width - cell_len(right) - 1` cells with an ellipsis if longer, then `second = left + spaces + right`, exactly `width` cells.

`TlHeader` and `TlFooter` call these functions with the widget's current width (`self.size.width`, fallback 80 before the first layout), `update(...)` themselves, and redraw on mount, on `events.Resize`, and whenever their state changes. The footer content is `first + "\n" + second`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/header.py`
- `packages/tl-tui/src/tl_tui/widgets/footer.py`
- `packages/tl-tui/tests/helpers.py`
- `docs/tickets/P0-I2/provided/test_header_footer.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/header.py` (edit)
- `packages/tl-tui/src/tl_tui/widgets/footer.py` (edit)
- `packages/tl-tui/tests/test_header_footer.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_header_footer.py.txt packages/tl-tui/tests/test_header_footer.py`
2. Implement `header_line` and `footer_lines`, then make the two widgets use them.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_header_footer.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (the existing shell tests in `test_app_shell.py` must still pass; do not edit them).

## Tests to add
None beyond the provided file. It covers: `header_line` widths, prefixes, right-part drop, ellipsis; `footer_lines` hints
truncation, severity symbols, right-aligned count, status truncation; both widgets rendering and reflowing on resize.

## Report requirements
Standard report. Paste the final test counts. State that the provided test file is byte-identical to the `.txt`.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.
- Stop if `test_app_shell.py` fails for a reason you cannot trace to your two files.

## Blocked

## Decision
