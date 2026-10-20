"""Test support other packages share: a ledger, a file service, two loaders and a load service.

``LegacyWorld`` wraps a ledger target and a file store; every call opens its own unit of work like
a real command. The two loaders are built from the seed mapping templates
(``dev/seed/templates``) and the sample files are in ``dev/seed/legacy``. It is not registered
anywhere and never runs in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import FileService
from tl_lake import LakeConfig
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

from tl_mod_legacy import registry
from tl_mod_legacy.model import LoaderDef
from tl_mod_legacy.registry import RunRow
from tl_mod_legacy.service import LoadService

ROOT = Path(__file__).resolve().parents[5]
SEED = ROOT / "dev" / "seed"
PROJECT = "project:P123"
ADMIN = "user:admin"
TAG_FILE = SEED / "legacy" / "instrument-index.csv"
DOC_FILE = SEED / "legacy" / "dms-document-register.csv"


def tag_loader(name: str = "test-tags") -> LoaderDef:
    return LoaderDef(
        name=name,
        system="plantx",
        table="tags",
        target="tags",
        description="Instrument index of the incumbent system.",
        mapping_text=(SEED / "templates" / "tag-list-instrument-index.yaml").read_text("utf-8"),
        file_types=("csv", "xlsx"),
    )


def document_loader(name: str = "test-docs", confidentiality: str | None = None) -> LoaderDef:
    return LoaderDef(
        name=name,
        system="dms",
        table="register",
        target="documents",
        description="Document register of the incumbent DMS.",
        mapping_text=(SEED / "templates" / "document-register-dms-export.yaml").read_text("utf-8"),
        file_types=("csv",),
        confidentiality=confidentiality,
    )


class LegacyWorld:
    def __init__(self, db: DbTarget, objects: Path, lake: LakeConfig | None = None) -> None:
        self.db = db
        self.store = FsObjectStore(objects, secret=b"s")
        self.files = FileService(self.store, secret=b"s")
        self.service = LoadService(db, self.files, lake=lake)

    def load_standards(self) -> None:
        """The sample company's tag classes and document patterns, into the ledger."""
        for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
            path = ROOT / "schema" / "fixtures" / "standards" / name
            with open_uow(self.db) as uow:
                load_standards(uow, load_standards_file(path), actor="user:seed", source="test")

    # --- reads ------------------------------------------------------------------------------

    def run(self, key_or_id: str) -> RunRow:
        return self.service.get(PROJECT, key_or_id)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def events_of(self, record_id: str) -> list[str]:
        return [
            str(r["event_type"])
            for r in self.rows(
                "SELECT event_type FROM events WHERE stream_id = :i ORDER BY seq", i=record_id
            )
        ]

    def runs(self) -> list[RunRow]:
        with open_uow(self.db, readonly=True) as uow:
            return registry.list_runs(uow.conn(), PROJECT)

    # --- writes -----------------------------------------------------------------------------

    def open(self, loader: str, name: str, data: bytes, actor: str = ADMIN) -> RunRow:
        return self.service.open(PROJECT, loader, name, data, actor=actor)

    def through_plan(self, loader: str, name: str, data: bytes) -> RunRow:
        """Open, extract, profile and plan a file; the planned run."""
        run = self.open(loader, name, data)
        self.service.extract(PROJECT, run.id, actor=ADMIN)
        self.service.profile(PROJECT, run.id, actor=ADMIN)
        planned, _ = self.service.plan(PROJECT, run.id, actor=ADMIN)
        return planned

    def loaded(self, loader: str, name: str, data: bytes) -> RunRow:
        """The whole way to Loaded."""
        run = self.through_plan(loader, name, data)
        self.service.load(PROJECT, run.id, actor=ADMIN)
        return self.run(run.id)


def tag_csv(count: int, start: int = 1) -> bytes:
    """A valid instrument index of ``count`` control valves, numbered ``47-FV-<1000+n>``."""
    header = "TAG NO,SERVICE,TYPE,SIZE (IN),MATERIAL,MFR,FAIL,FAT WITNESS,P&ID,REMARKS,ISSUED"
    rows = [
        f"47-FV-{1000 + n},Service {n},CV,4,316,Acme Valves,FC,,PID-4701,,2024-03-01"
        for n in range(start, start + count)
    ]
    return ("\n".join([header, *rows]) + "\n").encode()
