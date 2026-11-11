"""A ledger with something of every class in it, for the tests that look for leaks (ADR-0016).

``seed_hidden_world`` writes, in project ``P123``: four correspondence items (internal, restricted,
privileged and one whose class nobody knows), each with a clock and a thread; an RFI (internal), a
privileged RFI and a restricted early warning derived from the RFI (P1-I6); a file on an internal
and on a restricted item; a link from the internal item to the restricted one; a feed post that
names each of three items; and a restricted and an internal document. Every hidden thing carries a
token (``TOKENS``) in its text, so a test can search a response for what must not be there.
The accounts named on the privileged item and on the privileged RFI are ``user:amy`` and
``user:ctl``.
"""

from __future__ import annotations

import hashlib
import io
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.auth.queries import find_account
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.services import proposals
from tl_core.services.commands import Command
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.links import AddLink, handle_add_link
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    handle_create_transmittal,
)
from tl_mod_documents.handlers.transmittals import Recipient as Recipient_T
from tl_mod_documents.testing import DocumentsWorld

from tl_mod_correspondence import registry
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.handlers.threads import _join, _open_thread  # pyright: ignore
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_mod_correspondence.names import CORR_CLEARANCE_GRANTED
from tl_mod_correspondence.testing import CorrWorld, frozen_today

TOKENS = {
    "open": "OPENTOKEN",
    "restricted": "RESTOKEN",
    "privileged": "PRIVTOKEN",
    "bogus": "BOGUSTOKEN",
    "document": "DOCTOKEN",
    "file": "FILETOKEN",
    "commercial": "COMMTOKEN",
    "secret_rfi": "SECRETRFITOKEN",
    "loadrun": "LOADTOKEN",
}


@dataclass
class Hidden:
    ids: dict[str, str]  # kind -> record id (open, restricted, privileged, bogus, document, ...)
    numbers: dict[str, str]  # kind -> number or key
    extra_ids: dict[
        str, str
    ]  # "<kind>_clock", "<kind>_thread", "<kind>_file", "<kind>_post", "link"


class Twin(Protocol):
    """The twin-walk hook (tests/confidentiality/test_twin_walk.py): the seed calls ``mark`` before
    each step; ``kind`` names what the step writes (a key of ``TOKENS``, or ``None`` for a step
    nobody is kept from). ``True`` means: leave the step out. Without a twin nothing is left out."""

    def mark(self, kind: str | None) -> bool: ...


def _skip(twin: Twin | None, kind: str | None) -> bool:
    return twin is not None and twin.mark(kind)


class _Cmd(Command):
    """A command carrier for seeding."""


def _seed_domain_items(
    db: DbTarget,
    world: CorrWorld,
    scope: str,
    ids: dict[str, str],
    numbers: dict[str, str],
    extra: dict[str, str],
    twin: Twin | None = None,
) -> None:
    """An answered RFI anybody may read, a privileged RFI, and a restricted early warning derived
    from the RFI, linked to it (the evidence trail of the RFI leads to it, for a controller)."""
    _skip(twin, None)
    word = TOKENS["open"]
    ids["open_rfi"] = world.forge_technical(
        "P123-RFI-0001",
        subject=f"{word} RFI",
        state="Answered",
        scope=scope,
        question=f"{word} question",
        item={"body": f"{word} RFI body"},
        answer={"answer": f"{word} answer", "cost_impact": "yes"},
    )
    numbers["open_rfi"] = "P123-RFI-0001"
    secret = TOKENS["secret_rfi"]
    if not _skip(twin, "secret_rfi"):
        _secret_rfi(world, scope, ids, numbers, secret)
    comm = TOKENS["commercial"]
    if _skip(twin, "commercial"):
        return
    ids["commercial"] = world.forge_commercial(
        "P123-EW-0001",
        subject=f"{comm} subject",
        scope=scope,
        state="Awaiting assessment",
        item={"body": f"{comm} body"},
        derived_from_id=ids["open_rfi"],
        entitlement_basis=f"{comm} basis",
    )
    numbers["commercial"] = "P123-EW-0001"
    with open_uow(db) as uow:
        link = handle_add_link(
            uow,
            AddLink(
                actor="user:ctl",
                source="test",
                scope=scope,
                from_id=ids["commercial"],
                to_id=ids["open_rfi"],
                relation="derived_from",
            ),  # fmt: skip
            by_module=True,
        )
    extra["commercial_link"] = link.stream_id


def _secret_rfi(
    world: CorrWorld, scope: str, ids: dict[str, str], numbers: dict[str, str], secret: str
) -> None:
    ids["secret_rfi"] = world.forge_technical(
        "P123-RFI-0002",
        subject=f"{secret} subject",
        state="Awaiting response",
        scope=scope,
        confidentiality="privileged",
        question=f"{secret} question",
        item={"body": f"{secret} body"},
    )
    numbers["secret_rfi"] = "P123-RFI-0002"
    for account in ("user:amy", "user:ctl"):
        world.forge_item_event(
            ids["secret_rfi"],
            CORR_CLEARANCE_GRANTED,
            {"account": account, "granted_on": "2026-10-19", "reason": "counsel"},
        )


def _ensure_documents_actor(db: DbTarget) -> None:
    """Give ``user:u``, the actor of ``DocumentsWorld``, an account where the ledger needs one.

    On a SQLite dev/test ledger an account-less ``user:`` actor holds the ``user`` role in every
    module (``holder_for_actor``, the dev-ledger rule); on Postgres it holds nothing, so the seed's
    ``AttachFile`` is refused. The seed makes the account itself there (idempotent).
    """
    with open_uow(db) as uow:
        if uow.conn().dialect.name == "sqlite" or find_account(uow.conn(), username="u"):
            return
        accounts.create_account(
            uow,
            username="u",
            display_name="Seed documents actor",
            kind="person",
            roles=["user"],
            password=prepare_password(secrets.token_urlsafe(24)),
            by="svc:test",
        )


def seed_hidden_world(
    db: DbTarget,
    service: FileService,
    objects: Path,
    *,
    scope: str = "project:P123",
    twin: Twin | None = None,
) -> Hidden:
    cmd = _Cmd(actor="user:ctl", source="test", scope=scope)
    world = CorrWorld(db, objects / "corr")
    ids: dict[str, str] = {}
    numbers: dict[str, str] = {}
    extra: dict[str, str] = {}
    with frozen_today("2026-10-19"), cf.system_view():
        for kind, klass in (
            ("open", "internal"),
            ("restricted", "restricted"),
            ("privileged", "privileged"),
            ("bogus", "bogus"),
        ):
            if _skip(twin, kind if kind != "open" else None):
                continue
            with open_uow(db) as uow:
                made = create_item(
                    uow,
                    cmd,
                    subject=f"{TOKENS[kind]} subject",
                    direction="in",
                    medium="letter",
                    received_via="manual",
                    to=[Recipient(name=f"{TOKENS[kind]} recipient")],
                    body=f"{TOKENS[kind]} body",
                    confidentiality=klass,
                    received_on="2026-10-19",
                    received=True,
                )
            ids[kind], numbers[kind] = made.stream_id, made.key or ""
        if not _skip(twin, "privileged"):
            for account in ("user:amy", "user:ctl"):
                world.forge_item_event(
                    ids["privileged"],
                    CORR_CLEARANCE_GRANTED,
                    {"account": account, "granted_on": "2026-10-19", "reason": "counsel"},
                )
        _seed_domain_items(db, world, scope, ids, numbers, extra, twin)
        for kind in ("open", "restricted", "privileged"):
            if _skip(twin, kind if kind != "open" else None):
                continue
            clock = world.start_clock(ids[kind], label=f"{TOKENS[kind]} clock")
            extra[f"{kind}_clock"] = clock.stream_id
            with open_uow(db) as uow:
                row = registry.get_item(uow.conn(), ids[kind])
                assert row is not None
                thread_id, _ = _open_thread(uow, cmd, row)
                _join(uow, cmd, thread_id, row, None, "manual", first=True)
            extra[f"{kind}_thread"] = thread_id
        for kind in ("open", "restricted"):
            if _skip(twin, "file" if kind == "restricted" else None):
                continue
            word = TOKENS["file"] if kind == "restricted" else "OPENFILETEXT"
            data = f"{word} the original letter".encode()
            with open_uow(db) as uow:
                ticket = service.register_upload(
                    uow,
                    RegisterUpload(
                        actor="user:ctl",
                        source="test",
                        scope=scope,
                        record_id=ids[kind],
                        slot="original",
                        filename=f"{kind}.pdf",
                        content_type="application/pdf",
                        size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    ),  # fmt: skip
                    by_module=True,
                )
            with open_uow(db) as uow:
                done = service.complete_upload(
                    uow,
                    CompleteUpload(
                        actor="user:ctl", source="test", scope=scope, upload_id=ticket.upload_id
                    ),
                    io.BytesIO(data),
                    by_module=True,
                )
            extra[f"{kind}_file"] = done.file_id
        if not _skip(twin, "restricted"):
            with open_uow(db) as uow:
                link = handle_add_link(
                    uow,
                    AddLink(
                        actor="user:ctl",
                        source="test",
                        scope=scope,
                        from_id=ids["open"],
                        to_id=ids["restricted"],
                        relation="references",
                    ),  # fmt: skip
                    by_module=True,
                )
            extra["link"] = link.stream_id
        for kind in ("open", "restricted", "privileged"):
            if _skip(twin, kind if kind != "open" else None):
                continue
            with open_uow(db) as uow:
                post = handle_post(
                    uow,
                    PostToFeed(
                        actor="user:ctl",
                        source="test",
                        scope=scope,
                        body=f"{TOKENS[kind]} note on #{numbers[kind]}",
                    ),
                )
            extra[f"{kind}_post"] = post.stream_id
        for kind in ("open", "restricted"):  # an agent's pending proposal that names the item
            if _skip(twin, kind if kind != "open" else None):
                continue
            with open_uow(db) as uow:
                proposal = proposals.propose(
                    uow,
                    tool="propose_triage",
                    agent="agent:bot",
                    command=ConfirmTriage(
                        actor="agent:bot",
                        source="agent:bot",
                        scope=scope,
                        stream_id=ids[kind],
                        domain="general",
                        subtype="letter",
                    ),
                    summary=f"{TOKENS[kind]} triage",
                )
            extra[f"{kind}_proposal"] = proposal.proposal_id
    _ensure_documents_actor(db)
    docs = DocumentsWorld(db, objects / "docs")
    with cf.system_view():
        for kind, klass in (("document", "restricted"), ("open_document", None)):
            if _skip(twin, kind if kind == "document" else None):
                continue
            number = "ISO-9001" if kind == "document" else "ISO-9002"
            title = f"{TOKENS['document']} drawing" if kind == "document" else "OPENTOKEN drawing"
            made = docs.register(number, title=title, confidentiality=klass)
            ids[kind], numbers[kind] = made.stream_id, number
            docs.create_revision(number)
            docs.attach(number, "A")
            docs.issue(number, "A", "IFR")
        # one transmittal that lists a revision of each: the restricted one is left out for a
        # reader who may not read it, the transmittal itself is not hidden
        _skip(twin, None)
        revisions = [
            docs.revision(n, "A").id for n in ("ISO-9001", "ISO-9002") if n in numbers.values()
        ]
        with open_uow(db) as uow:
            sent = handle_create_transmittal(
                uow,
                CreateTransmittal(
                    actor="user:ctl",
                    source="test",
                    scope=scope,
                    subject="OPENTOKEN transmittal",
                    purpose="for_information",
                    recipients=[Recipient_T(name="Site", organisation=None, email=None)],
                    revision_ids=revisions,
                ),
            )
        extra["transmittal"] = sent.stream_id
        numbers["transmittal"] = sent.key or ""
    return Hidden(ids, numbers, extra)
