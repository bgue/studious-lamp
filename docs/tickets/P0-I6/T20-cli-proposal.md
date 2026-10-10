# P0-I6-T20 — `tl proposal ls|show|accept|reject`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the proposals service is on the base)
Branch: `p0/i6b-t20-cli-proposal`

## Goal
The `tl proposal` command group exists: `ls` lists the review queue, `show` prints one proposal and the command it would run, `accept` runs
that command as the person at the keyboard, `reject` closes it with a reason. Each subcommand parses options, makes one call into
`tl_core.services.proposals`, and prints. The module has the option declarations, the helpers and the wiring in `main.py`; `queue_line`,
`show_lines` and the four commands raise `NotImplementedError`. A provided test file (14 tests) must pass.

## Brief references (pasted)
> **11.3** AI agents get MCP tools. Record-changing tools are propose-only in Phase 0: a call records a proposal, a person accepts or rejects
> it in a review queue, and only accepting changes anything. The change is made by the person, tagged with the agent that proposed it.
> **18.12** Agent writes are labelled `source=mcp:<agent>`; an agent has a daily proposal budget.
> Build spec 02: the CLI contains no rules. Errors print `error: <message>` on stderr and exit 1 (see `tl_cli/feed.py`).

### Specification
The stub's docstrings give the exact output of each command; `queue_line` and `show_lines` format the lines. The provided test checks all
of it. `ctx.obj` is the ledger path (`Path`), set by the root callback. A project `P123` means scope `project:P123`; `--company` is scope
`company`. The default actor is `user:dev`, the source is `cli`. A proposal is created by an agent through MCP; the tests create them with
`proposals.submit(...)`. Only a person (`user:<id>`) can accept or reject: the service refuses an agent and the CLI prints that refusal.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T20.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from every docstring you fill in and the `STUB` line in the module docstring.
- `typer.testing.CliRunner` catches exceptions and returns them on the result: a CLI test that only checks "nothing changed" passes against a crash. The provided tests assert `exit_code` and `exception`.
- ruff's autofix removed the imports the stub does not use; add back `import json`, `cast` (from `typing`) and `ProposalStatus` (from `tl_core.proposals.types`).

## Interfaces (verbatim from the repo at the branch point)
```python
"""The `tl proposal` group: the review queue of agent proposals (P0-I6-T20; brief 11.3, 18.12).

STUB (P0-I6-T20): ``queue_line``, ``show_lines`` and the four commands raise NotImplementedError.

Each subcommand parses options, makes one call into `tl_core.services.proposals`, and prints. The
rules (who may decide, what accepting runs, what a failure records) live in the service. A proposal
is named by the id that `ls` prints. Agents propose through MCP; only a person decides here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork

app = typer.Typer(
    help="Review what agents proposed: list, show, accept, reject.", no_args_is_help=True
)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="The person deciding (user:<id>).")]
_STATUSES = ("pending", "accepted", "rejected", "failed")
#: Command fields `show` leaves out: they restate who proposed it, which `show` prints already.
_HIDDEN_FIELDS = frozenset({"actor", "source", "correlation_id", "causation_id", "idempotency_key"})


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _factory(db: Path) -> proposals.Factory:
    """``factory(readonly)`` for the service functions that open their own units of work."""

    def open_one(readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return open_uow(db, readonly=readonly)

    return open_one


def _scope(project: str | None, company: bool) -> str:
    if company == (project is not None):
        _fail("give exactly one of --project and --company")
    return "company" if company else f"project:{project}"


def queue_line(view: ProposalView) -> str:
    """``<id>  pending  agent:triage  create_record  Create the weld NCR`` (two-space columns).

    The columns are ``view.proposal_id``, ``view.status``, ``view.agent``, ``view.tool`` and
    ``view.summary``, joined by two spaces.

    STUB (P0-I6-T20): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")


def show_lines(view: ProposalView) -> list[str]:
    """The lines `show` prints for ``view``, in this order:

    ``proposal <id>``, ``scope <scope>``, ``status <status>``, ``agent <agent>``,
    ``tool <tool>``, ``summary <summary>``, ``command <command_type>``; then one line
    ``  <name> <json>`` for each field of ``view.command`` in sorted name order, leaving out the
    names in ``_HIDDEN_FIELDS`` and the fields whose value is ``None`` (the json is
    ``json.dumps(value, sort_keys=True, ensure_ascii=False)``, so a string keeps its quotes);
    then, only when set, ``decided by <view.decided_by>``, ``reason <view.reason>`` and
    ``result <view.result_stream_id>``.

    STUB (P0-I6-T20): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project", help="Project ID.")] = None,
    company: Annotated[bool, typer.Option("--company", help="The company scope.")] = False,
    status: Annotated[
        str, typer.Option("--status", help="pending, accepted, rejected, failed or all.")
    ] = "pending",
    agent: Annotated[str | None, typer.Option("--agent", help="Only this proposer.")] = None,
    n: Annotated[int, typer.Option("-n", min=1, help="How many (oldest first).")] = 50,
) -> None:
    """List proposals, oldest first. Nothing is printed for an empty queue.

    ``scope = _scope(project, company)`` first. A ``status`` that is not ``all`` and not in
    ``_STATUSES``: ``_fail`` with ``--status must be pending, accepted, rejected, failed or all,
    not 'x'``. In a read-only unit of work (``open_uow(db, readonly=True)`` inside
    ``_service_errors``) call ``proposals.list_proposals(uow.conn(), scope, status=..., agent=agent,
    limit=n)`` (``status=None`` for ``all``). Print ``queue_line(view)`` for each.

    STUB (P0-I6-T20): remove this paragraph when you implement the command.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")


@app.command("show")
def show(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Proposal id from `tl proposal ls`.")],
) -> None:
    """Print one proposal and the command it would run.

    Read-only unit of work, ``proposals.get_proposal(uow.conn(), proposal_id)`` inside
    ``_service_errors``; print each of ``show_lines(view)``.

    STUB (P0-I6-T20): remove this paragraph when you implement the command.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")


@app.command("accept")
def accept(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Proposal id from `tl proposal ls`.")],
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="A workflow role you hold (for a transition); repeatable."),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Run the proposal's command as you. Prints `accepted <id>` and `result <stream id>`.

    ``proposals.accept_or_fail(_factory(db), proposal_id=..., by=actor, roles=role or [],
    source="cli")`` inside ``_service_errors`` (it opens its own units of work; do not open one).
    When the returned view has ``status == "failed"`` nothing of the command was kept: print
    ``failed <id>`` to stdout, then ``_fail(view.reason or "the command was refused")``
    (``error: ...`` on stderr, exit code 1). Otherwise print ``accepted <id>`` and then
    ``result <view.result_stream_id>``.

    STUB (P0-I6-T20): remove this paragraph when you implement the command.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")


@app.command("reject")
def reject(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Proposal id from `tl proposal ls`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why; the agent and the ledger keep it.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Reject a pending proposal. The command never runs. Prints `rejected <id>`.

    Write unit of work (``open_uow(db)``) inside ``_service_errors``,
    ``proposals.reject_proposal(uow, proposal_id=..., by=actor, reason=reason, source="cli")``.
    Print ``rejected <id>``.

    STUB (P0-I6-T20): remove this paragraph when you implement the command.
    """
    raise NotImplementedError("STUB (P0-I6-T20)")
```
```python
# tl_core.proposals.types.ProposalView (pydantic): proposal_id, scope, tool, agent, command_type, command: dict[str, Any], summary,
#   status: "pending"|"accepted"|"rejected"|"failed", decided_by: str|None, reason: str|None, result_stream_id: str|None, seq: int
# tl_core.services.proposals:
#   list_proposals(conn, scope, *, status: ProposalStatus | None = "pending", agent: str | None = None, limit: int = 200) -> list[ProposalView]
#   get_proposal(conn, proposal_id, *, scope=None) -> ProposalView                       # ProposalNotFoundError
#   accept_or_fail(factory, *, proposal_id, by, roles=(), source="review") -> ProposalView   # status "accepted" or "failed" (reason = the error)
#   reject_proposal(uow, *, proposal_id, by, reason, source="review") -> ProposalView
#   Errors (all ServiceError): ProposalNotFoundError, ProposalNotPendingError, ProposalDeciderError ("only a person ..."), InvalidProposalError
# tl_adapters.sqlite.uow.open_uow(path, *, readonly=False) -> context manager yielding a UnitOfWork (uow.conn() is the connection)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/proposal.py`
- `packages/tl-cli/src/tl_cli/feed.py` (style: `_service_errors`, `_fail`, `open_uow`, options)
- `docs/tickets/P0-I6/provided/b-test_cli_proposal.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/proposal.py` (edit)
- `packages/tl-cli/tests/test_cli_proposal.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T20.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/b-test_cli_proposal.py.txt packages/tl-cli/tests/test_cli_proposal.py`
2. Implement `queue_line` and `show_lines`, then `ls`, `show`, `accept`, `reject`; delete the STUB paragraphs; add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_proposal.py -q
just check
just test
```
Expected: 14 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the output of `uv run tl proposal ls --project P123` and `uv run tl proposal show <id>` for a proposal you create in a scratch ledger (`TL_DB=/tmp/x.db uv run tl init`, then a small Python snippet that calls `proposals.submit`).

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
