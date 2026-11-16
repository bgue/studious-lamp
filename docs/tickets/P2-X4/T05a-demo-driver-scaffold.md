# P2-X4-T05a — demo driver, part A: the scaffolded module and the failing hook (clauses 1, 2, 6)

Status: ready (T02b, S5 merged)
Tier: haiku
review: full
Labels: tests
Depends on: T02b, S5 merged. Disjoint from T04, T05b, T06 (own file). T05c (the shell script) waits for T05a and T05b.
Branch: `p2/x4-t05a-driver-scaffold`
Worktree: `/home/user/wt/x4/t05a`

## Goal
`dev/demos/p2_x4_demo.py` is a Python driver with three modes, `clause1`, `clause2`, `clause6`, in the style of `dev/demos/p2_x2_demo.py` (read its first 70 lines): each mode prints `ok ...` lines or
`FAIL ...` and exits 1; env `TL_DB` (a SQLite path or a postgresql:// URL, a ledger made by `tl init --dev`) and `P2_X4_WORKDIR` (a temp dir) come from the shell. The demo script (T05c) calls it as
`uv run python dev/demos/p2_x4_demo.py clauseN`. It runs no pytest and no gate.

## Brief references (pasted)
Demo clauses (README of P2-X4), as amended by D7 (the scaffold has no example command, so `/commands/<Name>` belongs to `ext_demo`, T05b) and D13 (clauses 1 and 2 show the scaffold's route, tool and CLI group):
- clause1: the shell has run `tl new module probe --root $P2_X4_WORKDIR/scaf`. The driver puts `$P2_X4_WORKDIR/scaf/packages/tl-modules/probe/src` on `sys.path`, imports `tl_mod_probe.module`, takes `spec()`.
  Checks: the spec has no `commands` rows, three hooks `read_routers == ("tl_mod_probe.routes:router",)`, `tools == ("tl_mod_probe.tools:register_tools",)`, `cli_groups == ("tl_mod_probe.cli:probe_app",)`,
  all resolve through `resolve_hook`; no file under `packages/*/src` and `packages/tl-modules/*/src` of the repository contains the text `probe` as a module name: check that `tl_mod_probe` and `"probe"` do not occur in
  `packages/tl-api/src`, `packages/tl-mcp/src`, `packages/tl-cli/src` (no platform edit).
- clause2: inside `use_modules([*load_modules(), spec])`: `hook_failures() == {}`; `create_app` over a backend from `tl_adapters.backend.open_backend(as_target(TL_DB))` has the path `/modules/probe/ping`
  in `openapi()["paths"]` (import `tl_api.app` and `tl_api.commands` inside the block; if `ExtDemoAddNote`-style reload is needed see below); `build_server(make_uow_factory(target), actor="agent:probe",
  authorize_hook=<allow all>)` lists the tool `probe_ping`; a Typer root with `_add_module_groups(root, [spec])` answers `probe ping` with exit 0 and `probe\n` (copy the three lines of
  `test_the_cli_group_prints_the_module_name`).
- clause6: a fake module `ghost` (`ModuleSpec(name="ghost", record_types=frozenset(), projectors=list, commands="tl_mod_ghost.commands:COMMANDS")`, no such package): inside
  `use_modules([*load_modules(), ghost])`, `hook_failures() == {"ghost": "module 'ghost': hook 'commands' cannot be resolved"}`, the message holds no `tl_mod_ghost`, and
  `module_commands()` equals the rows without the fake (same names, count printed); `create_app` still builds and its `openapi()` path count equals the count without the fake.

## Interfaces (verbatim from the merged tree)
```python
# tl_core.modules
def use_modules(specs: Sequence[ModuleSpec]) -> Generator[None]: ...
def load_modules() -> tuple[ModuleSpec, ...]: ...
def resolve_hook(spec: ModuleSpec, hook: str) -> tuple[object, ...]: ...
def hook_failures() -> dict[str, str]: ...
def module_commands() -> tuple[ModuleCommand, ...]: ...
# tl_cli.main: def _add_module_groups(root: typer.Typer, specs: Iterable[ModuleSpec]) -> None
# tl_api.app: def create_app(backend, *, settings=None, tokens=None, ...) -> FastAPI   (see Harness.build, packages/tl-api/tests/harness.py:110-151, for the minimum arguments)
# tl_mcp.server: def build_server(factory, *, actor, authorize_hook=authorize, tool_modes=None, lake_dir=None, object_store=None, files=None) -> MCPServer
```
The command table is made once per import of `tl_api.commands`: import it inside the `use_modules` block of a fresh process, or `importlib.reload` it there (pattern: `reimport` fixture,
`packages/tl-api/tests/test_ext_demo_api.py:55-69`). Each mode is one process, so nothing is restored.

## Provided test (copy byte-identical; checked ruff format, ruff check, pyright at the target path)
`docs/tickets/P2-X4/provided/test_demo_p2_x4_drivers.py` to `tests/services/test_demo_p2_x4_drivers.py`. The driver defines `MODES = ("clause1", "clause2", "clause6")` as a plain module-level tuple. (The `p2_x4_ext_demo.py`
cases of that file stay red until T05b merges; run only `-k p2_x4_demo.py`.)

## Context (read these, nothing else)
- `dev/demos/p2_x2_demo.py` (lines 1-130: style, `ok`, `miss`, `check`, `MODES`)
- `packages/tl-api/tests/harness.py` (lines 110-151)
- `packages/tl-cli/tests/test_new_module_surfaces.py` (the CLI and hook checks to reuse)
- `packages/tl-api/tests/test_ext_demo_api.py` (lines 40-70, the reload)
may explore: (none)

## Allowed paths
- `dev/demos/p2_x4_demo.py` (create)
- `tests/services/test_demo_p2_x4_drivers.py` (create, provided)
- `docs/reports/P2-X4/T05a.md` (create)

## Acceptance
```
just check
just gate tests/services/test_demo_p2_x4_drivers.py   # only the p2_x4_demo.py cases must pass
d=$(mktemp -d); TL_DB=$d/a.db uv run tl init --dev; uv run tl new module probe --root $d/scaf
TL_DB=$d/a.db P2_X4_WORKDIR=$d uv run python dev/demos/p2_x4_demo.py clause1   # and clause2, clause6
```
Expected: each mode prints `ok` lines only and exits 0 (SQLite). Postgres runs in T05c.

## Tests to add
The provided file only; the modes are the checks.

## Report requirements
Standard report; one pasted `ok` output per mode (≤ 5 lines each).

## Escalation triggers
- Stop and report *Blocked* if `create_app` needs an argument the Harness lines do not show, or a check above fails because the platform differs from the text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
