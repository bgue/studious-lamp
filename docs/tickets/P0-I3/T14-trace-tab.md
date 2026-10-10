# P0-I3-T14 — Trace tab

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (the record view hosts `TraceTab`; `TlApp.action_trace`, `ClientInterface.trace`, the stub); `FakeClient.trace` stands in for the trace query
Branch: `p0/i3-t14-trace-tab`

## Goal
The record view's Trace tab shows the records reachable from the open record through links as a tree, to a depth the user changes with `+` and `-`,
following outbound, inbound or both directions (`o`); Enter on a record opens it as a followed reference. `t` anywhere in the record view switches
to the tab (the app part is written). `tl_tui/widgets/trace_tab.py` has the layout (`compose`), constructor, attributes, key bindings, `head_text` and
the `on_mount` that stops Enter from folding nodes; the two pure functions and the methods marked `raise NotImplementedError` (plus one line marked
`STUB`) are the work. A provided test file (11 tests) must pass.

## Brief references (pasted)
> **7.5 Trace view (`t`):** n-hop tree or graph, e.g. deficiency → inspection → weld → spool → line → test package → subsystem → system. `Enter` on a link row opens the target; back/forward history works like a browser across every followed reference.
> **10.2 Trace view:** Tree/graph of linked records with expand/collapse. Meaning never rides on colour alone: a stale or broken link, a voided record, hidden further links are written in the label.

### Specification (the provided test checks it)
- `node_text(node)`: `base = f"{node.key or EMPTY}  {node.title}"`; `text = f"{node.label}: {base}" if node.label else base`; then append `"  ! stale"` if `node.link_status == "stale"`, else `"  ✗ broken"` if it is `"broken"`; then `"  (voided)"` if `node.voided`; then `f"  +{node.more} more"` if `node.more`.
- `tree_lines(root)`: a list: `"  " * root.depth + node_text(root)`, followed by the lines of each child (recursively, in the given order).
- `TraceTab` (a `Vertical`; `compose` yields `Static#trace-head` and `Tree#trace-tree`):
  - `show_record(record)` (**edit the `STUB` line**): store `record`, then `self.reload()`.
  - `reload()`: return if there is no record. `root = self.client.trace(record["id"], depth=self.depth, direction=self.direction)`. On `NotImplementedError` set `#trace-head` to `"Trace unavailable: the link services are not installed yet"` and return. On `CLIENT_ERRORS` post `StatusMessage(describe_error(exc), "error")` and return (keep what is shown). Then: `#trace-head` ← `head_text(self.depth, self.direction)`; `tree.clear()`; `tree.root.set_label(Text(node_text(root)))`; `tree.root.data = root.key`; fill the tree (`_fill`); `tree.root.expand()`; `self.lines = tree_lines(root)`. (Annotate the tree variable as `Tree[str]`: `tree: Tree[str] = self.query_one("#trace-tree", Tree)`; do not subscript inside `query_one`.)
  - `_fill(parent, node)`: for each child: `branch = parent.add(Text(node_text(child)), data=child.key, expand=True)` (**labels must be `rich.text.Text`**: `[...]` in a plain string is markup), then `_fill(branch, child)`.
  - `action_depth(delta)`: `depth = max(MIN_DEPTH, min(MAX_DEPTH, self.depth + delta))`; only when it differs from `self.depth`, store it and `reload()`.
  - `action_direction()`: `self.direction` becomes the next entry of `DIRECTIONS` (wrapping), then `reload()`.
  - `on_tree_node_selected(event)`: `event.stop()`; `key = event.node.data`; unless the node is the root (`event.node.is_root`) or `key is None`, `self.post_message(OpenRecord(self.scope, key, follow=True))`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. Do not name an attribute after a Textual DOM property.
- `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `CLIENT_ERRORS`, `describe_error`, `OpenRecord`, `StatusMessage`, `EMPTY`, `TreeNode`).
- Remove the `STUB (P0-I3-T14)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/trace_tab.py (existing stub; keep every name and signature)
Direction = Literal["both", "out", "in"]; DIRECTIONS = ("both", "out", "in"); DIRECTION_WORDS: dict[str, str]; MIN_DEPTH = 1; MAX_DEPTH = 6
def node_text(node: TraceNode) -> str; def tree_lines(root: TraceNode) -> list[str]; def head_text(depth: int, direction: str) -> str   # head_text is written
class TraceTab(Vertical, can_focus=True):
    def __init__(self, client, scope, *, id=None)    # .client .scope .record (dict | None) .depth (2) .direction ("both") .lines (list[str])
    def show_record(self, record: dict[str, Any]) -> None; def reload(self) -> None
    def action_depth(self, delta: int) -> None; def action_direction(self) -> None
```
```python
# existing
# TraceNode (tl_core.services.link_trace): record_id, key (str | None), title, type, status, voided, depth, link_id, link_status, relation,
#   direction, label (how it was reached, e.g. "raised against"), children: list[TraceNode], more: int
# ClientInterface.trace(record_id, *, depth=2, direction="both") -> TraceNode
# tl_tui.messages: OpenRecord(scope, key, *, follow=False), StatusMessage(text, severity);  tl_tui.errors: CLIENT_ERRORS, describe_error;  tl_tui.text.EMPTY == "—"
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/trace_tab.py`
- `packages/tl-tui/src/tl_tui/widgets/nav_tree.py` (style of a `Tree` widget)
- `packages/tl-tui/tests/fakes.py` and `packages/tl-tui/tests/fakes_links.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_trace_tab.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/trace_tab.py` (edit)
- `packages/tl-tui/tests/test_trace_tab.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T14.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_trace_tab.py.txt packages/tl-tui/tests/test_trace_tab.py`
2. Implement the two functions, the methods and the `STUB` line; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_trace_tab.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_trace_tab.py.txt packages/tl-tui/tests/test_trace_tab.py
```
Expected: 11 tests pass, `just check` and `just test` exit 0 (all record-view and snapshot tests must still pass), `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `record_view.py`, `app.py`, the fakes or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
