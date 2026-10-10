# P0-I4-T61 — `tl serve` and `tl tui`

Status: merged
Tier: haiku
Labels: cli
Depends on: — (`tl_tui.main.run` and `tl_api.main.main` are on the base branch; `main.py` already registers both commands)
Branch: `p0/i4d-t61-cli-serve-tui`

## Goal
`tl serve` runs the REST API and event stream on the dev ledger; `tl tui` opens the TUI, embedded by default or remote with `--remote URL --token T`. `packages/tl-cli/src/tl_cli/serve.py` and `tui.py` have final signatures and help text; the bodies raise `NotImplementedError`. Implement them as thin wrappers (the root `--db` option is `ctx.obj`, a `Path`). One provided test file (8 tests) must pass.

## Brief references (pasted)
> **4 (Architecture):** the TUI works embedded (in process, a SQLite file) and remote (API client) through one client interface. **ADR-0005:** the dev API binds to loopback unless `--insecure-dev`; identity is a static dev token (`tl dev token add`). **29.4:** each CLI subcommand parses options, makes one call, and prints; no rules live in the CLI.

### Specification (the provided tests check it)
- `serve`: `from tl_api import main as api_main` (inside the function, so a test can replace `tl_api.main.main`); `argv = ["--db", str(ctx.obj), "--tokens", str(tokens), "--host", host, "--port", str(port)]`, append `"--insecure-dev"` when set; `raise typer.Exit(code=api_main.main(argv))`.
- `tui`: `from tl_tui import main as tui_main` (inside the function); call `tui_main.run(remote=remote, token=token, db=ctx.obj, project=project, actor=actor)`; on `ValueError` print `error: <message>` to stderr with `typer.echo(..., err=True)` and `raise typer.Exit(code=2) from exc`. Never print the token.
- Imports to add: inside `serve`: `from tl_api import main as api_main`; inside `tui`: `from tl_tui import main as tui_main` (both already named in the lines above).

Learnings that apply:
- The provided test lives at `docs/tickets/P0-I4/provided/test_cli_serve_tui.py.txt`; copy it to `packages/tl-cli/tests/test_cli_serve_tui.py` and do not edit the copy. It is already formatted: `diff` the copy against the original in the last acceptance step.
- `CliRunner.invoke` catches exceptions and returns them on the result, so a CLI test must assert `exit_code` and that `result.exception` is `None` or `SystemExit` (L-P0-I4-B8); the provided test does. Do the same for any check you run by hand.
- Remove the `STUB (P0-I4-T61)` paragraph from both module docstrings when you implement them.
- ruff limits lines to 100 columns, docstrings included; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`. Do not add `__init__.py` to the tests directory.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/P0-I4-T61.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/main.py (already edited on the base)
app.command("serve")(serve.serve)
app.command("tui")(tui.tui)
# packages/tl-cli/src/tl_cli/serve.py and tui.py: keep every signature, option name, envvar and help text of the stubs.
# packages/tl-tui/src/tl_tui/main.py
def run(*, remote: str | None = None, token: str | None = None, db: str | Path | None = None,
        project: str | None = None, actor: str | None = None) -> None   # raises ValueError for a bad remote/token
# packages/tl-api/src/tl_api/main.py
def main(argv: Sequence[str] | None = None) -> int     # serves until stopped; returns an exit code
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/serve.py`, `packages/tl-cli/src/tl_cli/tui.py` (the stubs)
- `packages/tl-cli/tests/test_cli_serve_tui.py` (after you copy it)
- `packages/tl-cli/src/tl_cli/dev.py` (a command in the same style)
- `packages/tl-cli/AGENTS.md` if it exists
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/serve.py` (edit)
- `packages/tl-cli/src/tl_cli/tui.py` (edit)
- `packages/tl-cli/tests/test_cli_serve_tui.py` (create: copy of the provided test)
- `docs/reports/P0-I4/P0-I4-T61.md` (create: your report)

## Acceptance
```
cp docs/tickets/P0-I4/provided/test_cli_serve_tui.py.txt packages/tl-cli/tests/test_cli_serve_tui.py
uv run pytest packages/tl-cli/tests/test_cli_serve_tui.py -q
just check
uv run pytest packages/tl-cli -q
diff packages/tl-cli/tests/test_cli_serve_tui.py docs/tickets/P0-I4/provided/test_cli_serve_tui.py.txt
```
Expected: 8 tests pass in the first command; `just check` is clean; the whole CLI suite passes; the diff is empty.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the pass counts of the first and third commands.

## Escalation triggers
- Stop and report *Blocked* if `tl_api.main.main` or `tl_tui.main.run` does not have the signature above.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
