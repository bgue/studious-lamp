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
