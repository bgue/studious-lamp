"""Reading and writing the files of the derivation pipeline: extracted rows and validation reports.

The rows an extractor read and the report of their validation are files in the file service (slots
``extracted`` and ``report`` of the derived document), never event payloads (ADR-0014). A command
handler has the signature ``(uow, command)`` and no object store, so a process that runs derivation
commands says which file service to use once, at start-up: :func:`configure` (the API server and
the CLI do it), or :func:`use_files` for the length of a block (tests). A process that did not
configure one answers ``DerivationNotConfiguredError`` the first time a command needs bytes; the
job runner is given its file service directly and does not use the global.

Files written here go through the service's ``by_module`` path: the upload guard of the derived
document refuses these slots to a person.
"""

from __future__ import annotations

import hashlib
import io
import threading
from collections import OrderedDict
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from pydantic import BaseModel
from tl_core.derivation.types import ExtractionResult
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.uow import UnitOfWork

from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.errors import DerivationNotConfiguredError, InvalidSourceError
from tl_mod_documents.names import SLOT_EXTRACTED, SLOT_REPORT

ACTOR = "svc:derivation"
SOURCE = "svc:derivation"
JSON_TYPE = "application/json"

_lock = threading.Lock()
_files: FileService | None = None

#: Parsed results and reports, by (file id, sha256, model): a few, newest last. A read of the same
#: pass again (a screen paging through rows) then costs a permission check and no parse.
CACHE_ENTRIES = 4
#: ...and at most this many bytes of stored JSON in all (the parsed objects are several times the
#: size of their JSON, so this keeps the cache to a few hundred megabytes at worst). A file bigger
#: than the budget is parsed for the call and not kept.
CACHE_BYTES = 32 * 1024 * 1024
_parsed: OrderedDict[tuple[str, str, str], tuple[BaseModel, int]] = OrderedDict()
_parsed_lock = threading.Lock()


def forget_parsed() -> None:
    """Empty the cache of parsed files (tests)."""
    with _parsed_lock:
        _parsed.clear()


def configure(files: FileService | None) -> None:
    """Set (or clear, with ``None``) the file service derivation commands use in this process."""
    global _files
    with _lock:
        _files = files


@contextmanager
def use_files(files: FileService | None) -> Generator[None]:
    """Use ``files`` for the length of the block (tests, embedders)."""
    global _files
    with _lock:
        previous, _files = _files, files
    try:
        yield
    finally:
        with _lock:
            _files = previous


def configured() -> FileService | None:
    with _lock:
        return _files


def result_files() -> ResultFiles:
    """The reader/writer over the configured file service, or ``DerivationNotConfiguredError``."""
    files = configured()
    if files is None:
        raise DerivationNotConfiguredError(
            "this process has no file service for derived data; the server or command that runs "
            "it must configure one (tl_mod_documents.derivation.store.configure)"
        )
    return ResultFiles(files)


@dataclass(frozen=True)
class Stored:
    file_id: str
    sha256: str
    size: int


class ResultFiles:
    def __init__(self, files: FileService) -> None:
        self._files = files

    def read(
        self, uow: UnitOfWork, scope: str, file_id: str, *, expect_sha256: str | None = None
    ) -> bytes:
        """The bytes of an available file; ``InvalidSourceError`` if they differ from the hash."""
        opened = self._files.open_file(uow, scope, file_id, actor=ACTOR)
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
        digest = hashlib.sha256(data).hexdigest()
        wanted = expect_sha256 or opened.info.sha256
        if digest != wanted or len(data) != opened.info.size:
            raise InvalidSourceError(f"file {file_id} does not match the hash the ledger holds")
        return data

    def _parsed_as[M: BaseModel](
        self,
        uow: UnitOfWork,
        scope: str,
        file_id: str,
        sha256: str | None,
        model: type[M],
    ) -> M:
        """The file parsed as ``model``. The file is opened every time, so a file that was
        rejected or is quarantined is refused even when its parse is cached; the bytes are read
        and parsed only on a miss."""
        opened = self._files.open_file(uow, scope, file_id, actor=ACTOR)
        key = (file_id, sha256 or opened.info.sha256, model.__name__)
        with _parsed_lock:
            hit = _parsed.get(key)
            if hit is not None:
                _parsed.move_to_end(key)
        if hit is not None:
            opened.data.close()
            assert isinstance(hit[0], model)
            return hit[0]
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
        digest = hashlib.sha256(data).hexdigest()
        wanted = sha256 or opened.info.sha256
        if digest != wanted or len(data) != opened.info.size:
            raise InvalidSourceError(f"file {file_id} does not match the hash the ledger holds")
        parsed = model.model_validate_json(data)
        size = len(data)
        if size <= CACHE_BYTES:
            with _parsed_lock:
                _parsed[key] = (parsed, size)
                while (
                    len(_parsed) > CACHE_ENTRIES
                    or sum(n for _, n in _parsed.values()) > CACHE_BYTES
                ):
                    _parsed.popitem(last=False)
        return parsed

    def read_result(
        self, uow: UnitOfWork, scope: str, file_id: str, sha256: str | None
    ) -> ExtractionResult:
        """The stored ``ExtractionResult`` (columns, rows, profiles, problems, metadata)."""
        return self._parsed_as(uow, scope, file_id, sha256, ExtractionResult)

    def read_report(
        self, uow: UnitOfWork, scope: str, file_id: str, sha256: str | None
    ) -> ValidationReport:
        """The stored ``ValidationReport`` of a pass."""
        return self._parsed_as(uow, scope, file_id, sha256, ValidationReport)

    def write(
        self,
        uow: UnitOfWork,
        *,
        scope: str,
        record_id: str,
        slot: str,
        filename: str,
        data: bytes,
        correlation_id: str,
    ) -> Stored:
        """Store ``data`` as a JSON file in a module-written slot of the derived document."""
        if slot not in (SLOT_EXTRACTED, SLOT_REPORT):
            raise ValueError(f"the module writes only {SLOT_EXTRACTED} and {SLOT_REPORT}")
        digest = hashlib.sha256(data).hexdigest()
        base = {
            "actor": ACTOR,
            "source": SOURCE,
            "scope": scope,
            "correlation_id": correlation_id,
        }
        ticket = self._files.register_upload(
            uow,
            RegisterUpload(
                **base,
                record_id=record_id,
                slot=slot,
                filename=filename,
                content_type=JSON_TYPE,
                size=len(data),
                sha256=digest,
            ),
            by_module=True,
        )
        done: FileResult = self._files.complete_upload(
            uow,
            CompleteUpload(**base, upload_id=ticket.upload_id),
            io.BytesIO(data),
            by_module=True,
        )
        return Stored(file_id=done.file_id, sha256=digest, size=len(data))
