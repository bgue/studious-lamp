"""Helpers shared by the `tl derive` CLI tests (the name is unique on purpose: L-P1-I0A-1).

``derive_env`` gives an initialised ledger whose object store is the test world's; ``seed`` makes
document ISD-001 with a draft revision A and a PDF (the standards and the document pattern are
loaded); ``schema_file`` writes the instrument-index schema as a YAML file ``tl derive schema
register`` reads. The child-process extractors come from the fake registry of ``tl_core``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from auth_support import bootstrap, sign_in
from doccli_support import docs_env, world
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.testing import (
    EXTRACTOR_FACTORY,
    INDEX_MAPPING,
    INDEX_SCHEMA,
    DocumentsWorld,
)

FACTORY = EXTRACTOR_FACTORY
KEY = "ISD-001@A/instrument-index"
ROWS = [
    ("47-FV-1001", "Feed", "CV", "4"),
    ("47-FV-1002", "Return", "HV", "6"),
    ("47-HV-2001", "Vent", "PSV", "2"),
]


def derive_env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = docs_env(new_db, monkeypatch)
    values["TL_OBJECT_ROOT"] = str(tmp_path / "objects")  # the test world's store
    return values


@contextmanager
def runtime(made: DocumentsWorld) -> Iterator[None]:
    """The fake extractors in this process and the world's file service for the module."""
    with use_extractors(make_extractors()), use_files(made.files):
        yield


def seed(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """ISD-001 with revision A and a PDF, over the standards; no schema yet."""
    made = world(env, tmp_path)
    made.load_standards()  # the tag classes; no document pattern, so ISD-001 is a free number
    made.register("ISD-001")
    made.create_revision("ISD-001")
    made.attach("ISD-001", "A")
    return made


def as_admin(env: dict[str, str]) -> bool:
    """Sign an admin in on SQLite (``root``); on Postgres the conftest does. True if it did."""
    if is_postgres(as_target(env["TL_DB"])):
        return False
    assert bootstrap(env).exit_code == 0
    sign_in(env)
    return True


def schema_file(tmp_path: Path, **over: object) -> Path:
    body: dict[str, object] = {
        "code": "instrument-index",
        "semver": "1.0.0",
        "title": "Instrument index",
        "json_schema": INDEX_SCHEMA,
        "key_column": "tag",
        "target_kind": "tags",
        "mapping": INDEX_MAPPING,
        **over,
    }
    path = tmp_path / "schema.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def csv_file(
    tmp_path: Path, rows: list[tuple[str, str, str, str]], name: str = "index.csv"
) -> Path:
    from tl_mod_documents.testing import index_csv

    path = tmp_path / name
    path.write_bytes(index_csv(rows))
    return path


def sign_in_as(env: dict[str, str], tmp_path: Path, name: str, roles: list[str]) -> dict[str, str]:
    """A new account with ``roles``, signed in with a session file of its own; its environment.

    SQLite only: on Postgres the conftest signs one admin in for every command.
    """
    from auth_support import GOOD, separate_session
    from auth_support import sign_in as sign_in_session
    from tl_adapters.db import open_uow
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    other = separate_session(env, tmp_path, name)
    with open_uow(as_target(env["TL_DB"])) as uow:
        accounts.create_account(
            uow,
            username=name,
            display_name=name,
            kind="person",
            roles=roles,
            password=prepare_password(GOOD, username=name),
            by="svc:test",
        )
    sign_in_session(other, name, GOOD)
    return other
