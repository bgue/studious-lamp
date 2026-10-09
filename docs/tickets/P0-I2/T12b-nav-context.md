# P0-I2-T12b — Navigation tree and context panel

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T11 (merged on `p0/i2b`)
Branch: `p0/i2b-t12b-nav-context`

## Goal
The left panel shows a real navigation tree (company, project, its views) that tells the app when the user chooses
"Records", and the right panel shows a summary of the record under the grid cursor: key, version, title, status and
type, conformance, flattened pset values, and the short effective-schema hash. Both exist as stubs with their final
public interface; this ticket replaces their content.

## Brief references (pasted)
> Nav tree (modules, saved views) | Main area | Context panel (links, preview, history, thread, psets, attachments)  (§10.1)
> The context panel follows the cursor: links, psets, file-slot completeness, and the record's feed.  (§10.6 sketch 1)

Sketch 1 left and right panels (§10.6; this increment shows only what exists: no links, files or feed yet):
```text
│ ▾ P123 North Exp│ ... │ 47-1234-W013  v7          │
│   Home          │     │ Welded · BW · CS · Ø6.0   │
│   ...           │     │ ─ Psets ────────────────  │
│  ▶ Welds        │     │  wps      WPS-CS-01       │
│ ★ Saved views   │     │  x.hydro  Y (P123)        │
```
> Meaning never rides on colour alone: pair status with a symbol (§10.3).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns and applies to docstrings and comments. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- Textual `Static` parses `[...]` as markup; record titles can contain brackets. Pass `markup=False` (the stub does).
- Do not name an attribute after a Textual `Widget` attribute (`visible`, `size`, `region`, `id`...).
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text` (importable because `tests/conftest.py`
  adds the directory to `sys.path`).
- Shared display helpers already exist in `tl_tui/text.py`: `short_hash(value)`, `conformance_mark(level)`,
  `format_value(value)`, `EMPTY`. Use them; do not copy their logic.

## Interfaces (verbatim from repo at the branch point, plus the new functions)
```python
# packages/tl-tui/src/tl_tui/widgets/nav_tree.py  (stub today)
class NavTree(Tree[str]):
    def __init__(self, *, company: str, scope: str, id: str | None = None) -> None: ...
    # attributes: company, scope

# packages/tl-tui/src/tl_tui/widgets/context_panel.py  (stub today)
class ContextPanel(VerticalScroll, can_focus=True):
    def __init__(self, *, id: str | None = None) -> None: ...
    # attributes: record (dict | None), text (str, the last rendered text)
    def show_record(self, record: dict[str, Any] | None) -> None: ...
# NEW in context_panel.py
def flatten_psets(psets: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]: ...
def context_text(record: dict[str, Any] | None) -> str: ...

# packages/tl-tui/src/tl_tui/messages.py
class NavSelected(Message):
    def __init__(self, view_id: str) -> None: ...

# packages/tl-tui/src/tl_tui/text.py
def short_hash(value: str | None) -> str: ...        # "#a91f…3c", or "—"
def conformance_mark(value: str | None) -> str: ...  # "✓ ok" | "! warning" | "✗ nonconformant"
def format_value(value: Any) -> str: ...             # None -> "—", float 6.0 -> "6", bool -> yes/no
EMPTY = "—"
```

Rules for the tree: root label is `company` (data `"company"`, expanded). Its child is the project node, labelled with `scope`
minus a leading `project:` (data `"project"`, expanded). Under it two leaves: `"Records"` (data `"records"`) and
`"★ Saved views (none yet)"` (data `"saved-views"`). Choosing (Enter on) the `records` leaf posts `NavSelected("records")`;
no other node posts anything. Build the nodes in `on_mount`.

Rules for `flatten_psets`: depth-first over dict values in sorted key order; a dict value recurses with prefix `path + "."`;
any other value (including an empty list or a list) is a leaf `(dotted_path, value)`; an empty dict contributes nothing.

Rules for `context_text(record)`, lines joined with `"\n"`; `None` returns `"No record under the cursor"`:
```
{key}  v{version}                    <- two spaces between
{title}
{status or "—"} · {type}
{conformance_mark(conformance)}
── Psets ──
{path}  {format_value(value)}        <- one line per flatten_psets pair; the single line "(none)" if there are none
── Schema ──
{short_hash(effective_schema_hash)}
```
`ContextPanel.show_record` stores `record`, sets `text = context_text(record)` and updates its `Static` (`markup=False`).
Initial `text` is `context_text(None)`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/nav_tree.py`
- `packages/tl-tui/src/tl_tui/widgets/context_panel.py`
- `packages/tl-tui/src/tl_tui/text.py`
- `docs/tickets/P0-I2/provided/test_nav_context.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/nav_tree.py` (edit)
- `packages/tl-tui/src/tl_tui/widgets/context_panel.py` (edit)
- `packages/tl-tui/tests/test_nav_context.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_nav_context.py.txt packages/tl-tui/tests/test_nav_context.py`
2. Implement the tree and the panel as specified.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_nav_context.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (the existing shell tests in `test_app_shell.py` must still pass; do not edit them).

## Tests to add
None beyond the provided file. It covers `flatten_psets`, `context_text` for full, sparse and missing records, the tree
labels and the `NavSelected` message, and literal rendering of bracketed text.

## Report requirements
Standard report. State that the provided test file is byte-identical to the `.txt`.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked

## Decision
