"""Fake record actions, record files and module command runners (P1-UX2-S1).

The default is the quiet one: no record offers an action and no record has a file. A test sets
what a record offers with ``set_actions`` and what it holds with ``add_record_file``; the module
command runners record what they were asked to run and refuse, like the real client, a name the
module's table does not hold and an access the signed-in person lacks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tl_api.client.files import save_download
from tl_core.actions import ActionOffer, RecordActions
from tl_core.auth.errors import ForbiddenError
from tl_core.files.queries import FileInfo
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError, UnknownFileError
from tl_mod_documents.commands import API_COMMANDS as DOCUMENT_COMMANDS
from tl_mod_engineering.commands import API_COMMANDS as ENGINEERING_COMMANDS

SCOPE = "project:P123"


class FakeActionsSupport:
    """Mixin for `FakeClient`: call `_init_actions()` from its `__init__`."""

    def _init_actions(self) -> None:
        self._offers: dict[str, RecordActions] = {}
        self._hidden_records: set[str] = set()
        self._record_files: dict[str, list[FileInfo]] = {}
        self._file_bytes: dict[str, bytes] = {}
        self._known_files: set[str] = set()  # file ids this client listed (their scope is known)
        self.module_commands: list[tuple[str, str, Command]] = []  # (module, name, command)
        self.is_module_controller = True  # False: a controller's command raises ForbiddenError

    # --- seeding -----------------------------------------------------------------------------

    def set_actions(
        self, record_id: str, *offers: tuple[str, str], state: str | None = None
    ) -> None:
        """What ``record_id`` offers: ``(command, label)`` pairs, in order."""
        self._offers[record_id] = RecordActions(
            record_id=record_id,
            state=state,
            actions=[ActionOffer(command=c, label=label) for c, label in offers],
        )

    def hide_record(self, record_id: str) -> None:
        """Make ``record_id`` one the viewer may not read: it answers like a missing record."""
        self._hidden_records.add(record_id)

    def add_record_file(
        self, record_id: str, filename: str, data: bytes, *, sha256: str | None = None, **more: Any
    ) -> FileInfo:
        """A current file of a record; ``sha256`` overrides the recorded digest (a tampered one)."""
        n = len(self._file_bytes) + 1
        info = FileInfo(
            file_id=f"01FILE{n:020d}",
            scope=SCOPE,
            record_id=record_id,
            slot=more.pop("slot", "attachment"),
            revision=1,
            sha256=sha256 or hashlib.sha256(data).hexdigest(),
            size=len(data),
            content_type=more.pop("content_type", "application/pdf"),
            filename=filename,
            status="available",
            deduplicated=False,
            superseded_by=None,
            reason=None,
            uploaded_by="user:t",
            uploaded_at="2026-10-21T09:00:00Z",
            processed_at=None,
            version=1,
        )
        self._record_files.setdefault(record_id, []).append(info)
        self._file_bytes[info.file_id] = data
        return info

    # --- the interface -----------------------------------------------------------------------

    def allowed_actions(self, record_id: str) -> RecordActions:
        self.calls.append("allowed_actions")  # type: ignore[attr-defined]
        if record_id in self._hidden_records:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return self._offers.get(
            record_id, RecordActions(record_id=record_id, state=None, actions=[])
        )

    def list_record_files(self, record_id: str) -> list[FileInfo]:
        self.calls.append("list_record_files")  # type: ignore[attr-defined]
        if record_id in self._hidden_records:
            return []
        found = list(self._record_files.get(record_id, []))
        self._known_files.update(info.file_id for info in found)
        return found

    def fetch_file(self, file_id: str, dest_dir: Path) -> Path:
        self.calls.append("fetch_file")  # type: ignore[attr-defined]
        info = next(
            (
                i
                for infos in self._record_files.values()
                for i in infos
                if i.file_id == file_id and i.record_id not in self._hidden_records
            ),
            None,
        )
        if info is None or file_id not in self._known_files:
            raise UnknownFileError(f"no file {file_id!r}")
        data = self._file_bytes[file_id]
        return save_download(dest_dir, info, lambda out: out.write(data))

    def document_command(self, name: str, cmd: Command) -> CommandResult:
        return self._module_command("documents", DOCUMENT_COMMANDS, name, cmd)

    def engineering_command(self, name: str, cmd: Command) -> CommandResult:
        return self._module_command("engineering", ENGINEERING_COMMANDS, name, cmd)

    def _module_command(self, module: str, table: Any, name: str, cmd: Command) -> CommandResult:
        self.calls.append(f"{module}_command")  # type: ignore[attr-defined]
        spec = next((c for c in table if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a {module} command")
        if spec.access != "user" and not self.is_module_controller:
            raise ForbiddenError("this action needs the document_controller or admin role")
        self.module_commands.append((module, name, cmd))
        return CommandResult(
            stream_id=getattr(cmd, "stream_id", "") or "", key=None, version=1, events=[]
        )
