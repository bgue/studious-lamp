"""One in-process writer: the real command handlers, one unit of work per command.

``World`` is to the demo project what the acceptance ``World`` helpers are to their checks. It runs
a command model through its handler inside ``open_uow`` (never raw SQL inserts) and uploads a file
through the file service. ``on(day)`` makes ``day`` today for the modules **and** for the ledger,
so the events of a section fall on the project's own timeline (the demo clock, not the wall clock).
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore import make_object_store, object_secret
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.services.commands import Command, CommandResult
from tl_mod_correspondence.testing import at
from tl_mod_documents.derivation import store

PROJECT_ID = "P200"
PROJECT = f"project:{PROJECT_ID}"
SOURCE = "demo-project"
START = date(2026, 9, 1)
TODAY = date(2026, 11, 6)  # the fixed "today" of the demo project

Handler = Callable[[Any, Any], CommandResult]


def actor_of(username: str) -> str:
    return f"user:{username}"


class World:
    def __init__(self, target: DbTarget, objects: Path | None = None) -> None:
        self.target = target
        objects_store = (
            FsObjectStore(objects, secret=object_secret())
            if objects is not None
            else make_object_store()
        )
        self.files = FileService(objects_store, secret=object_secret())
        store.configure(self.files)  # the modules that render a letter use the same service

    # --- the timeline ------------------------------------------------------------------------

    def on(self, day: date) -> AbstractContextManager[None]:
        """Today is ``day`` (noon UTC) for the handlers and for the ledger inside the block."""
        return at(day)

    @contextmanager
    def today(self) -> Iterator[None]:
        with at(TODAY):
            yield

    # --- commands -------------------------------------------------------------------------------

    def run(
        self,
        handler: Handler,
        model: type[Command],
        *,
        by: str,
        scope: str = PROJECT,
        **fields: Any,
    ) -> CommandResult:
        """One command, in its own unit of work, as ``by`` (a username)."""
        command = model(actor=actor_of(by), source=SOURCE, scope=scope, **fields)  # type: ignore[call-arg]
        with open_uow(self.target) as uow:
            return handler(uow, command)

    def upload(
        self,
        record_id: str,
        *,
        slot: str,
        filename: str,
        data: bytes,
        by: str,
        content_type: str = "application/pdf",
        scope: str = PROJECT,
    ) -> FileResult:
        """Put ``data`` in ``slot`` of the record through the file service."""
        base = {"actor": actor_of(by), "source": SOURCE, "scope": scope}
        declared = RegisterUpload(
            **base,
            record_id=record_id,
            slot=slot,
            filename=filename,
            content_type=content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        with open_uow(self.target) as uow:
            ticket = self.files.register_upload(uow, declared)
        with open_uow(self.target) as uow:
            return self.files.complete_upload(
                uow, CompleteUpload(**base, upload_id=ticket.upload_id), io.BytesIO(data)
            )

    # --- reads ----------------------------------------------------------------------------------

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.target, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.target, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def record_count(self) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM cur_core_record"))

    def event_count(self) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM events"))

    def id_of(self, key: str, scope: str = PROJECT) -> str:
        return str(
            self.scalar(
                "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k", s=scope, k=key
            )
        )

    def version(self, record_id: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record_id))
