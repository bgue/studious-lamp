"""The loader `dms-register`: the document register export of the incumbent DMS (P1-I8-T07a)."""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per document: number, title, type, discipline, originator and the old register's
    revision, status and date. Documents are registered ``internal``.

    The mapping template is the data file ``mappings/dms-register.yaml`` of this package.
    """
    return LoaderDef(
        name="dms-register",
        system="dms",
        table="register",
        target="documents",
        description="Document register export of the incumbent DMS (CSV or XLSX).",
        mapping_text=read_mapping("dms-register.yaml"),
        file_types=("csv", "xlsx"),
    )
