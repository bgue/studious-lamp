# P0-I4-T45 — `tl dev token add`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the token store is `tl_api.tokens`, on the base branch; the `dev` group and its registration exist)
Branch: `p0/i4c-t45-dev-token-cli`

## Goal
`tl dev token add <actor>` creates a static bearer token for an actor in the dev token file, prints the token on stdout and a confirmation on
stderr. `packages/tl-cli/src/tl_cli/dev.py` exists with the `dev` and `token` groups, the option declarations and the registration in
`main.py`; the `add` body raises `NotImplementedError`. A provided test file (6 tests) must pass. This is the whole of the dev identity
tooling (ADR-0005); it is not an account system and creates no roles.

## Brief references (pasted)
> **ADR-0005** Phase 0 servers use a dev-only identity stub: static bearer tokens read from a local file (`dev/data/tokens.json`, created by `tl dev token add <actor>`), mapping token to an actor string (`user:<id>` or `agent:<id>`). A missing or unknown token is HTTP 401. There is no authorisation and no password storage.

### Specification (the provided test checks it)
- Call `add_token(tokens, actor)` from `tl_api.tokens` (it validates the actor, creates the file with mode 0600, adds a fresh random token and returns it).
- On success: `typer.echo(token)` (stdout, the token alone on one line), then `typer.echo(f"added token for {actor} to {tokens}", err=True)`.
- `add_token` raises `ValueError` for an invalid actor (not `user:<id>` or `agent:<id>`) or for a token file that does not hold a JSON object. Catch `ValueError`: `typer.echo(f"error: {exc}", err=True)` and `raise typer.Exit(code=1) from exc`. Nothing is printed on stdout then.
- Do not read the token file yourself and do not print existing tokens. The `--tokens` option and its `TL_TOKENS` environment variable are already declared in the stub.
- Add the import `from tl_api.tokens import add_token`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. A `.py.txt` is outside `ruff format`, so the supervisor formatted it already; `diff` it against the original in the last acceptance step.
- The package `tl-api` has a test harness (`packages/tl-api/tests/conftest.py`, `harness.py`): a real app over a real SQLite file. Tests import it with `from harness import ...`. Do not edit it and do not add `__init__.py` to the test directory.
- `just check` includes an OpenAPI drift check (`uv run python -m tl_api.openapi --check`). The stub's signatures, decorators, parameters and response models are final and already in the committed document. If `just check` reports the document out of date, you changed a signature: put it back. Never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages/tl-api` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.
- `typer.testing.CliRunner.invoke` catches exceptions and returns them on the result, so a CLI test that only asserts "nothing changed" passes against a command that crashes. Every provided test asserts `exit_code` and `result.exception`; do not weaken them.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-api/src/tl_api/tokens.py (final)
def add_token(path: str | Path, actor: str) -> str      # ValueError: bad actor, or a token file that is not a JSON object
# packages/tl-cli/src/tl_cli/dev.py (the stub; keep every name and option)
@token_app.command("add")
def add(actor: Annotated[str, typer.Argument(...)], tokens: Annotated[Path, typer.Option("--tokens", envvar="TL_TOKENS", ...)] = Path(DEFAULT_TOKENS)) -> None
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/dev.py` (the stub)
- `packages/tl-cli/src/tl_cli/events.py` (the pattern for a small command group)
- `docs/tickets/P0-I4/provided/test_cli_dev_token.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/dev.py` (edit)
- `packages/tl-cli/tests/test_cli_dev_token.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T45.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_cli_dev_token.py.txt packages/tl-cli/tests/test_cli_dev_token.py`
2. Implement `add`; delete the `STUB (P0-I4-T45)` paragraph from the module docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_dev_token.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_cli_dev_token.py.txt packages/tl-cli/tests/test_cli_dev_token.py
```
Expected: 6 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (`tl_api/tokens.py` and `main.py` are not yours).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
