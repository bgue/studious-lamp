# P2-X4-T05b — demo driver, part B: `ext_demo` through API, CLI and MCP (clauses 3, 4, 5)

Status: ready (T02b, S5 merged)
Tier: haiku
review: full
Labels: tests
Depends on: S5 merged. Disjoint from T04, T05a, T06 (own file). T05c waits for T05a and T05b.
Branch: `p2/x4-t05b-driver-ext-demo`
Worktree: `/home/user/wt/x4/t05b`

## Goal
`dev/demos/p2_x4_ext_demo.py` is a Python driver with modes `clause3`, `clause4`, `clause5`, same style as `dev/demos/p2_x2_demo.py` (`ok ...` lines or `FAIL ...` and exit 1; env `TL_DB` and
`P2_X4_WORKDIR` from the shell; a ledger made by `tl init --dev`). Each mode is one process: it enters `use_modules([*load_modules(), ext_demo_spec()])`, imports `tl_api.app` and `tl_api.commands` inside
the block (or reloads `tl_api.commands` there, `test_ext_demo_api.py:55-69`), runs `create_schema(target)` inside the block (the module's projector makes `ext_demo_note`), builds `create_app` over
`open_backend(target)`, and seeds idempotently (`find_account` first): people `bob` (role user), `ctl` (document_controller), `boss` (admin), `vic` (user account with only a `viewer` `GrantModuleRole` for
module `ext_demo` on `project:P123`), the agent `bot` with an agent token, notes `N-OPEN` (internal, "words anyone may read") and `N-HIDDEN` (restricted, "words only a clearance may read"). Scope is
`project:P123`. Copy the seeding from `packages/tl-api/tests/test_ext_demo_api.py` lines 62-139 (`person`, `seed_note`, `world`); the loader is `tests/ext_demo/load.py` (`sys.path.insert(0, tests/ext_demo)`,
`from load import ext_demo_spec`). Tokens: `sessions.sign_in(backend, username=, password=)[1]`; plain `fastapi.testclient.TestClient(app)` with `Authorization: Bearer`.

## Brief references (pasted)
Demo clauses 3 to 5 as built by S5 (`docs/reports/P2-X4/S5.md`); D14: the demo's tool is the read tool `ext_demo_get_note`, since `ExtDemoAddNote` is excluded from proposals (`excluded:reserved`), so clause 4
shows closed-until-allowed and an allowed read, not a filed proposal.
- clause3: `POST /commands/ExtDemoAddNote` body `{"scope","key","title","body"}`: `bob` 200; `vic` 403 and the text names the module `ext_demo`; the agent `bot` 403 `agent_must_propose`. The CLI adds a note:
  Typer root with `_add_module_groups(root, load_modules())`, `CliRunner().invoke(root, ["ext_demo","add","N-CLI","--project","P123","--title","Cli","--body","x"], obj=as_target(TL_DB),
  env={"TL_ENV":"test","TL_SESSION_FILE":<workdir>/session.json})` gives exit 0 and `added N-CLI` (pattern: `tests/services/test_ext_demo_conformance.py:114-165`).
- clause4: `build_server(make_uow_factory(target), actor="agent:bot", authorize_hook=hook)` where `hook` raises `tl_api.auth.Forbidden("closed")` for any action not in a local `allowed` set
  (`packages/tl-mcp/tests/test_ext_demo_mcp.py:60-80`): `ext_demo_get_note` is listed; calling it raises ToolError matching `not allowed`; after `allowed.add("mcp.ext_demo_get_note")` it returns the open
  note; the core tool `get_record` is still refused; a hidden and a missing key raise one identical text containing `no such note` and neither the key nor the note text.
- clause5: the five readers of `GET /modules/ext_demo/notes/{key}?scope=project:P123`: anonymous, `bot`, `bob`, `ctl`, `boss`. Keys N-OPEN, N-HIDDEN, N-NONE. Expected readable sets: anonymous none (401 for
  all three, same text); bot and bob `{N-OPEN}`; ctl and boss `{N-OPEN, N-HIDDEN}`. Where N-HIDDEN is not readable its (status, text) equals N-NONE's, the text holds neither the key nor the note words, and the
  status is 401 for anonymous, 404 otherwise. Print one `ok reader <name>: reads <n> of 3` line per reader.

## Interfaces (verbatim from the merged tree)
`tests/ext_demo/load.py`: `def ext_demo_spec() -> ModuleSpec`. `tl_mod_ext_demo.commands`: `ExtDemoAddNote(actor, source, scope, key, title, body, note_class="internal"|"restricted")`,
`handle_add_note(uow, command)`. Route `GET /modules/ext_demo/notes/{key}` (query `scope`); tool `ext_demo_get_note(scope, key)`; CLI group `ext_demo` with `add` and `get`.

## Provided test (copy byte-identical; checked ruff format, ruff check, pyright at the target path)
`docs/tickets/P2-X4/provided/test_demo_p2_x4_drivers.py` to `tests/services/test_demo_p2_x4_drivers.py`, unless T05a already merged it (then it is on the branch: leave it). The driver defines
`MODES = ("clause3", "clause4", "clause5")` as a plain module-level tuple. Run only `-k p2_x4_ext_demo.py`.

## Context (read these, nothing else)
- `dev/demos/p2_x2_demo.py` (lines 1-130)
- `packages/tl-api/tests/test_ext_demo_api.py`
- `packages/tl-mcp/tests/test_ext_demo_mcp.py`
- `tests/services/test_ext_demo_conformance.py` (lines 110-165)
- `docs/reports/P2-X4/S5.md`
may explore: (none)

## Allowed paths
- `dev/demos/p2_x4_ext_demo.py` (create)
- `tests/services/test_demo_p2_x4_drivers.py` (create, provided)
- `docs/reports/P2-X4/T05b.md` (create)

## Acceptance
```
just check
just gate tests/services/test_demo_p2_x4_drivers.py   # only the p2_x4_ext_demo.py cases must pass
d=$(mktemp -d); TL_DB=$d/a.db uv run tl init --dev
TL_DB=$d/a.db P2_X4_WORKDIR=$d uv run python dev/demos/p2_x4_ext_demo.py clause3   # then clause4, clause5, same ledger
```
Expected: each mode prints `ok` lines only and exits 0 (SQLite; Postgres runs in T05c). Modes must also pass on a repeat run on the same ledger (idempotent seeding).

## Tests to add
The provided file only.

## Report requirements
Standard report; one pasted `ok` output per mode (≤ 5 lines each).

## Escalation triggers
- Stop and report *Blocked* if a check fails because the platform differs from the text (name the line), or the seeding needs more than the pasted pattern.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
