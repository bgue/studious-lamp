# P2-X4 S3 — MCP tools registered from the module hook; module tools closed until allowed

kind: piece
review: full
branch: p2/x4-s3-mcp-tools
worktree: /home/user/wt/x4/s3
Depends on: S1 merged (C1, `p2/x4` @9f0bc5ce). Independent of S2 and T01 (disjoint paths). Does not wait for X2.

## Why
`packages/tl-mcp/src/tl_mcp/server.py` (`create_server`, the block `register_write_tools ... register_requisition_tools`) lists every
module's tool registrars by hand and imports each. S1 declared them on `ModuleSpec.tools`. A new module must add tools without an edit
to `tl-mcp`. Authorization stays closed: `tl_mcp/identity.py` `MCP_ACTIONS` is an explicit list ("a new tool is closed until it is
added", AGENTS.md); this piece must not turn it into a prefix rule or derive it from the hook.

## Interfaces (verbatim, `packages/tl-core/src/tl_core/modules.py` on `p2/x4`)
```python
def resolve_hook(spec: ModuleSpec, kind: str) -> tuple[object, ...]:
    """Import and return the objects a spec's hook names (lazily; never at ``ModuleSpec`` build).
    ... Any failure raises ``ModuleHookError`` with a fixed text that carries neither the ref nor the exception."""
class ModuleHookError(ModuleLoadError): ...
def load_modules() -> tuple[ModuleSpec, ...]: ...
# ModuleSpec.tools: Sequence[str]   refs "tl_mcp.<x>_tools:register_<x>_tools", registration order = list order
```
Registrar signature today: `register_<x>_tools(server: MCPServer, ctx: McpContext) -> None` (all module registrars; `register_write_tools`
alone also takes `modes` and is core, it stays hand-called).
Tool refs per module (S1 report): awp `awp_tools:register_awp_tools, iwp_tools:..., awp_week_tools:register_week_tools`; correspondence
`correspondence_tools`; documents `document_tools`, `derivation_tools`; engineering `engineering_tools`; materials `materials_tools`;
quality `punch_tools`; requisitions `requisition_tools`; schedule `schedule_tools`, `schedule_read_tools`; cost, legacy, schemareg: none.
Core registrars that stay hand-called (not module-owned): `register_write_tools`, `register_type_tools`, `register_thread_tools`.

## Goal
1. In `server.py`, delete the imports and calls of the module registrars listed above; after `register_thread_tools` call a helper
   `_register_module_tools(server, ctx)`: for `spec in tables` (see 2) for `register in resolve_hook(spec, "tools")`, call
   `register(server, ctx)`. Module-name order from `load_modules()`; inside a module, declared order.
2. Review F2: resolve the tables once per `create_server` call, before any registration (one `resolve_hook` per spec per call, no
   per-tool re-resolution). Do not cache at import time (`use_modules` must still work in tests).
3. A module whose `tools` hook raises `ModuleHookError` registers none of its tools; the other modules still register. Log
   `str(exc)` once at WARNING on logger `tl_mcp` (the message is fixed text; never log the ref or the cause). Nothing else is opened
   for the failed module.
4. The core tool set is unchanged: the registered tool NAME set after the change equals the set before it. Do not edit the tool modules,
   `identity.py`, `context.py`, `write_tools.py` or anything X2 owns (see Allowed paths).
5. Closed by default (no code change expected, a test proves it): a module tool whose `mcp.<tool>` action is not in `MCP_ACTIONS` is
   refused for an agent token and answers like any denied tool; adding the action to a test authorizer's allow set opens only that tool.

## Context (read these, nothing else; ≤ 10)
`packages/tl-mcp/src/tl_mcp/server.py` (create_server only), `packages/tl-core/src/tl_core/modules.py` (the S1 block at the end),
`packages/tl-mcp/src/tl_mcp/identity.py` (MCP_ACTIONS, read-only), `packages/tl-mcp/tests/mcp_harness.py`,
`packages/tl-mcp/tests/test_mcp_server.py`, `packages/tl-mcp/tests/test_mcp_identity.py`, `tests/services/test_module_hooks.py`,
`docs/reports/P2-X4/S1.md`.

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/server.py`
- `packages/tl-mcp/tests/test_module_tool_hooks.py` (create)
- `docs/reports/P2-X4/S3.md` (create)
Read-only (P2-X2 is rewriting agent scope and proposal wiring on `p2/x2`; stop and report if a change seems to need one):
`tl_mcp/identity.py`, `tl_mcp/context.py`, `tl_mcp/write_tools.py`, every `*_tools.py`, `packages/tl-core/**`.

## Tests to add (`packages/tl-mcp/tests/test_module_tool_hooks.py`, created by this piece)
1. Equality: BEFORE editing `server.py`, list the tool names a harness server registers (use `mcp_harness.py` as `test_mcp_server.py`
   does) and paste them as a literal `frozenset` named `OLD_TOOL_NAMES` in the test; the test asserts the registered set equals it, with
   one comment line saying it was captured before P2-X4 S3. (Names only; order is not pinned.)
2. Every ref of every installed module's `tools` hook resolves (`resolve_hook` for each spec) and each result is callable.
3. A fake in-tree-named module through `use_modules` whose `tools` ref names a registrar adding one tool `fake_probe`: the tool is
   registered; with an agent authorizer that lacks `mcp.fake_probe` the call is refused, with it present the call answers.
4. A module whose `tools` ref names a missing object: its tools absent, the others present, `caplog` shows exactly one fixed message
   `module 'x': hook 'tools' cannot be resolved`, and no ref text in any log record.
5. Resolution happens once per `create_server` call: monkeypatch `tl_core.modules.resolve_hook` (or the name `server.py` imports) with a
   counting wrapper; assert one call per spec with tools, none on the second tool call.
6. Confidentiality is untouched: the existing `test_confidentiality_walk.py` runs in the gate; add nothing.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-mcp/tests/test_module_tool_hooks.py packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_tools.py packages/tl-mcp/tests/test_mcp_identity.py packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_idempotency_walk.py packages/tl-mcp/tests/test_mcp_idempotency.py packages/tl-mcp/tests/test_punch_tools.py packages/tl-mcp/tests/test_requisition_tools.py packages/tl-mcp/tests/test_materials_tools.py packages/tl-mcp/tests/test_awp_tools.py packages/tl-mcp/tests/test_mcp_week_tools.py packages/tl-mcp/tests/test_mcp_document_tools.py packages/tl-mcp/tests/test_mcp_derivation_tools.py packages/tl-mcp/tests/test_mcp_engineering_tools.py packages/tl-mcp/tests/test_mcp_schedule_tools.py packages/tl-mcp/tests/test_mcp_schedule_read_tools.py tests/services/test_module_hooks.py
```
Every path except `test_module_tool_hooks.py` exists on `p2/x4` (checked with `ls`). Name files, never a directory. No `gate-pg`: no
adapter or ledger change. Report the summary lines only.

## Mutation cap
One sentinel plus at most 5 targeted mutants: registration loop skips a module's second registrar; a failed hook aborts `create_server`
instead of skipping that module; a failed hook also skips the other modules; resolution per tool call instead of once; the helper
registers a module's tools only when `identity.MCP_ACTIONS` holds them (this one must NOT be killed by design: it shows closure lives in
`identity.py`; report it as such) . 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; first line: deviations or none; state the order of tool registration before and after
(it may differ; the set may not). Commit `P2-X4-S3: ...` with the session trailers; no model names in committed text.

## Escalation triggers
A registrar needs more than `(server, ctx)`; the tool name set cannot be kept equal; a change to `identity.py` seems needed.
