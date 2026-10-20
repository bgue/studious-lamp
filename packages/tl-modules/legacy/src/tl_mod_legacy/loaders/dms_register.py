# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `dms-register`: the document register export of the incumbent DMS (P1-I8-T07a).

STUB: this file is the interface P1-I8-T07a implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per document: number, title, type, discipline, originator and the old register's
    revision, status and date. Documents are registered ``internal``.

    The mapping template is the data file ``mappings/dms-register.yaml`` of this package.
    """
    # STEPS
    # 1. Return a LoaderDef with name "dms-register", system "dms", table "register", target
    #    "documents", description "Document register export of the incumbent DMS (CSV or XLSX).",
    #    mapping_text read_mapping("dms-register.yaml"), file_types ("csv", "xlsx"). Leave the
    #    other fields at their defaults.
    raise NotImplementedError("STEPS: see the comments")
