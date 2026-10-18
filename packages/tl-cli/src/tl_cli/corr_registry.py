"""The groups `tl corr thread`, `party`, `clause`, `class` and `mail` (brief 9 M10).

Threads group the items of one exchange. Parties and clauses are the controller's register data.
`class` is the confidentiality of an item (ADR-0016): a controller sets it and names who may read a
privileged item. `mail ingest` reads an .eml file (bounded, text only, in a process of its own) into
a received item with the original and the attachments. See the module for the rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_correspondence import registry, views
from tl_mod_correspondence.handlers.clauses import (
    DefineClause,
    RetireClause,
    handle_define_clause,
    handle_retire_clause,
)
from tl_mod_correspondence.handlers.confidentiality import (
    GrantClearance,
    SetCorrespondenceConfidentiality,
    WithdrawClearance,
    handle_grant_clearance,
    handle_set_confidentiality,
    handle_withdraw_clearance,
)
from tl_mod_correspondence.handlers.mail import IngestEmail, ingest_email, read_email
from tl_mod_correspondence.handlers.parties import (
    AddContact,
    ContactIn,
    EndContact,
    RegisterParty,
    RetireParty,
    handle_add_contact,
    handle_end_contact,
    handle_register_party,
    handle_retire_party,
)
from tl_mod_correspondence.handlers.threads import AssignThread, handle_assign_thread

from tl_cli.corr import item_row
from tl_cli.derive_support import configure_files
from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _Reason, _service_errors
from tl_cli.session import require_controller

thread_app = typer.Typer(help="Threads: the items of one exchange.", no_args_is_help=True)
party_app = typer.Typer(help="Parties and their contacts (controller).", no_args_is_help=True)
clause_app = typer.Typer(
    help="Contract clauses and their time bars (controller).", no_args_is_help=True
)
class_app = typer.Typer(
    help="The confidentiality class of an item (controller).", no_args_is_help=True
)
mail_app = typer.Typer(
    help="Email in: read an .eml file into a received item.", no_args_is_help=True
)

MAX_EML_BYTES = 10 * 1024 * 1024


# --- threads ---------------------------------------------------------------------------------


@thread_app.command("ls")
def thread_ls(ctx: typer.Context, project: _Project) -> None:
    """A project's threads: number, state, items, last date, subject key."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.thread_views(uow.conn(), f"project:{project}")
    for t in found:
        typer.echo(f"{t.number} {t.state} {t.item_count} {t.last_item_on or '-'} {t.subject_key}")


@thread_app.command("show")
def thread_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="P123-THR-0001")],
    project: _Project,
) -> None:
    """One thread with its items."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        t = views.thread_view(uow.conn(), f"project:{project}", number)
    typer.echo(f"{t.number} {t.state} {t.item_count} items: {t.subject_key}")
    for line in t.items:
        typer.echo(f"  {line.number} {line.state} {line.direction} {line.on or '-'} {line.subject}")


@thread_app.command("assign")
def thread_assign(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The item number.")],
    project: _Project,
    thread: Annotated[
        str | None, typer.Option("--thread", help="A thread number; default: a new one.")
    ] = None,
    answers: Annotated[
        str | None, typer.Option("--answers", help="The number of the item it answers.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Move an item to a thread (or open a new one) and say what it answers."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        thread_id = None
        if thread is not None:
            found = registry.find_thread(uow.conn(), scope, thread)
            if found is None:
                _fail(f"no thread {thread!r} in project {project!r}")
            thread_id = found.id
        answered = item_row(uow, scope, project, answers).id if answers else None
        handle_assign_thread(
            uow,
            AssignThread(actor=actor, source="cli", scope=scope, stream_id=row.id,
                         thread_id=thread_id, responds_to_id=answered),
        )  # fmt: skip
        after = registry.get_item(uow.conn(), row.id)
        now = (
            registry.get_thread(uow.conn(), after.thread_id) if after and after.thread_id else None
        )
    typer.echo(f"{number} is in thread {now.number if now else '-'}")


# --- parties ---------------------------------------------------------------------------------


def _contact(text: str) -> ContactIn:
    """``Name``, ``Name:email`` or ``Name:email:Title`` as a contact."""
    name, email, title = ([*text.split(":", 2), None, None])[:3]
    return ContactIn(name=name, email=email or None, title=title or None)


@party_app.command("ls")
def party_ls(
    ctx: typer.Context,
    project: _Project,
    all_parties: Annotated[bool, typer.Option("--all", help="Include retired parties.")] = False,
) -> None:
    """Parties: code, role, state, email domains, contacts, name."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.party_views(uow.conn(), f"project:{project}", include_inactive=all_parties)
    for p in found:
        active = [c for c in p.contacts if c.is_active]
        typer.echo(
            f"{p.code} {p.project_role} {'active' if p.is_active else 'retired'} "
            f"{','.join(p.email_domains) or '-'} {len(active)} {p.name}"
        )
        for c in active:
            typer.echo(f"  {c.position} {c.name} {c.email or '-'} {c.title or '-'}")


@party_app.command("add")
def party_add(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The party code, for example MER.")],
    project: _Project,
    name: Annotated[str, typer.Option("--name")],
    role: Annotated[str, typer.Option("--role", help="client, engineer, contractor, ...")],
    domains: Annotated[list[str] | None, typer.Option("--email-domain", help="Repeat.")] = None,
    contacts: Annotated[
        list[str] | None, typer.Option("--contact", help="NAME[:EMAIL[:TITLE]]. Repeat.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Register a party (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        made = handle_register_party(
            uow,
            RegisterParty.model_validate(
                {"actor": actor, "source": "cli", "scope": scope, "code": code, "name": name,
                 "project_role": role, "email_domains": domains or [],
                 "contacts": [_contact(c) for c in contacts or []]}
            ),
        )  # fmt: skip
    typer.echo(f"registered party {made.key}")


@party_app.command("contact-add")
def party_contact_add(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The party code.")],
    project: _Project,
    contact: Annotated[str, typer.Option("--contact", help="NAME[:EMAIL[:TITLE]]")],
    domain: Annotated[
        str | None, typer.Option("--domain", help="Limit to a correspondence domain.")
    ] = None,
    authorised: Annotated[bool, typer.Option("--authorised")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Add a contact to a party (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    person = _contact(contact).model_copy(update={"domain": domain, "is_authorised": authorised})
    with _service_errors(), open_uow(db) as uow:
        party = registry.find_party(uow.conn(), scope, code)
        if party is None:
            _fail(f"no party {code!r} in project {project!r}")
        handle_add_contact(
            uow,
            AddContact(actor=actor, source="cli", scope=scope, party_id=party.id, contact=person),
        )
    typer.echo(f"added contact {person.name} to {code}")


@party_app.command("contact-end")
def party_contact_end(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The party code.")],
    project: _Project,
    position: Annotated[int, typer.Option("--position", min=1)],
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End a contact of a party (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        party = registry.find_party(uow.conn(), scope, code)
        if party is None:
            _fail(f"no party {code!r} in project {project!r}")
        handle_end_contact(
            uow,
            EndContact(actor=actor, source="cli", scope=scope, party_id=party.id,
                       position=position, reason=reason),
        )  # fmt: skip
    typer.echo(f"ended contact {position} of {code}")


@party_app.command("retire")
def party_retire(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The party code.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retire a party (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        party = registry.find_party(uow.conn(), scope, code)
        if party is None:
            _fail(f"no party {code!r} in project {project!r}")
        handle_retire_party(
            uow,
            RetireParty(actor=actor, source="cli", scope=scope, party_id=party.id, reason=reason),
        )
    typer.echo(f"retired party {code}")


# --- clauses ---------------------------------------------------------------------------------


@clause_app.command("ls")
def clause_ls(
    ctx: typer.Context,
    project: _Project,
    all_clauses: Annotated[bool, typer.Option("--all", help="Include retired clauses.")] = False,
) -> None:
    """Clauses: contract/number, state, time bar, service method."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.clause_views(uow.conn(), f"project:{project}", include_inactive=all_clauses)
    for c in found:
        bar = f"{c.time_bar_days} {c.time_bar_day_type}" if c.time_bar_days else "-"
        typer.echo(
            f"{c.contract}/{c.clause_number} {'active' if c.is_active else 'retired'} "
            f"{bar} {c.service_method or '-'}"
        )


@clause_app.command("add")
def clause_add(
    ctx: typer.Context,
    contract: Annotated[str, typer.Argument(help="The contract, for example CT-1.")],
    number: Annotated[str, typer.Argument(help="The clause number, for example 20.1.")],
    project: _Project,
    days: Annotated[int | None, typer.Option("--days", min=1, help="The time bar in days.")] = None,
    day_type: Annotated[str | None, typer.Option("--type", help="calendar or working.")] = None,
    notice: Annotated[
        str | None, typer.Option("--notice", help="What the notice must contain.")
    ] = None,
    recipients: Annotated[
        list[str] | None, typer.Option("--recipient", help="A contact role. Repeat.")
    ] = None,
    service: Annotated[
        str | None, typer.Option("--service", help="email, letter, portal, hand.")
    ] = None,
    domains: Annotated[
        list[str] | None, typer.Option("--domain", help="A domain that cites it.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Register a contract clause (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        made = handle_define_clause(
            uow,
            DefineClause.model_validate(
                {"actor": actor, "source": "cli", "scope": scope, "contract": contract,
                 "clause_number": number, "time_bar_days": days, "time_bar_day_type": day_type,
                 "notice_requirements": notice, "required_recipients": recipients or [],
                 "service_method": service, "domains": domains or []}
            ),
        )  # fmt: skip
    typer.echo(f"registered clause {made.key}")


@clause_app.command("retire")
def clause_retire(
    ctx: typer.Context,
    contract: Annotated[str, typer.Argument()],
    number: Annotated[str, typer.Argument()],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retire a clause (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        found = registry.find_clause(uow.conn(), scope, contract, number)
        if found is None:
            _fail(f"no clause {contract}/{number} in project {project!r}")
        handle_retire_clause(
            uow,
            RetireClause(actor=actor, source="cli", scope=scope, clause_id=found.id, reason=reason),
        )
    typer.echo(f"retired clause {contract}/{number}")


# --- confidentiality -------------------------------------------------------------------------


@class_app.command("set")
def class_set(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The item number.")],
    project: _Project,
    to: Annotated[str, typer.Option("--to", help="internal, restricted or privileged.")],
    reason: _Reason,
    grant: Annotated[
        list[str] | None,
        typer.Option("--grant", help="For privileged: an account user:NAME. Repeat."),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Set the class of an item (controller). Privileged names who may read it, you too."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_set_confidentiality(
            uow,
            SetCorrespondenceConfidentiality.model_validate(
                {"actor": actor, "source": "cli", "scope": scope, "stream_id": row.id,
                 "to_class": to, "reason": reason, "grant": grant or []}
            ),
        )  # fmt: skip
    typer.echo(f"{number} is now {to}")


@class_app.command("ls")
def class_ls(
    ctx: typer.Context, number: Annotated[str, typer.Argument()], project: _Project
) -> None:
    """The class of an item and the accounts named on it."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = item_row(uow, scope, project, number)
        named = registry.clearances_of(uow.conn(), row.id)
    typer.echo(f"{number} {row.confidentiality}")
    for c in named:
        typer.echo(f"named {c.account} since {c.granted_on} by {c.granted_by}")


@class_app.command("grant")
def class_grant(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument()],
    project: _Project,
    account: Annotated[str, typer.Option("--account", help="user:NAME")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Name an account that may read a privileged item (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_grant_clearance(
            uow,
            GrantClearance(actor=actor, source="cli", scope=scope, stream_id=row.id,
                           account=account, reason=reason),
        )  # fmt: skip
    typer.echo(f"{account} may read {number}")


@class_app.command("withdraw")
def class_withdraw(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument()],
    project: _Project,
    account: Annotated[str, typer.Option("--account", help="user:NAME")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Remove an account from the readers of a privileged item (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_withdraw_clearance(
            uow,
            WithdrawClearance(actor=actor, source="cli", scope=scope, stream_id=row.id,
                              account=account, reason=reason),
        )  # fmt: skip
    typer.echo(f"{account} may no longer read {number}")


# --- email in --------------------------------------------------------------------------------


@mail_app.command("ingest")
def mail_ingest(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="An .eml file.", exists=True, dir_okay=False)],
    project: _Project,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Read an .eml file into a received item: the original, the attachments, the thread.

    The message is untrusted: it is read in a process of its own with a clock and a memory limit,
    every size and count is bounded, and a message over a bound or with a hostile character is
    refused whole (nothing is cut short). Nothing in it is fetched, rendered or run.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if path.stat().st_size > MAX_EML_BYTES:
        _fail("the email was refused: the message is larger than the limit")
    data = path.read_bytes()
    configure_files()
    with _service_errors():
        parsed = read_email(data)
        with open_uow(db) as uow:
            made = ingest_email(
                uow,
                IngestEmail(actor=actor, source="cli", scope=scope, original_name=path.name),
                parsed,
                data,
            )
    typer.echo(f"ingested {made.key}")
    typer.echo(f"attachments {len(parsed.attachments)}")
