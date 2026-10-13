"""Helpers shared by the document control CLI tests (`tl doc`, `tl transmittal`, `tl review`).

The name is unique on purpose (L-P1-I0A-1). ``docs_env`` gives an initialised ledger; ``world``
opens the module's test world on the same ledger (documents, revisions and files made with the
commands of the module, not with the CLI); ``load_standards`` loads the acme standards and the acme
document pattern through the module.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import run as tl
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_mod_documents.testing import DocumentsWorld
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

ROOT = Path(__file__).resolve().parents[3]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"


def docs_env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A fresh initialised ledger of the adapter under test (the default fixtures as schema)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    target = new_db()
    values = {"TL_DB": str(target), "TL_ENV": "dev"}
    assert tl(values, "init").exit_code == 0
    return values


def world(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """The module's test world on ``env``'s ledger (its objects go under ``tmp_path``)."""
    return DocumentsWorld(as_target(env["TL_DB"]), tmp_path / "objects")


def load_document_standards(env: dict[str, str]) -> None:
    """Load the acme standards and the acme document pattern into the ledger, through the module."""
    for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
        with open_uow(as_target(env["TL_DB"])) as uow:
            load_standards(
                uow, load_standards_file(STANDARDS / name), actor="user:seed", source="test"
            )
