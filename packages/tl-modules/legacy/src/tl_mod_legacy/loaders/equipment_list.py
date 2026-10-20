# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `equipment-list`: the equipment list of the incumbent system (P1-I8-T07b).

STUB: this file is the interface P1-I8-T07b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per equipment tag: number, description and the type that names the tag class.

    The workbook has the sheet ``Equipment List`` and two title rows above the header, so the
    header is on row 3. The mapping template is ``mappings/equipment-list.yaml``.
    """
    # STEPS
    # 1. Return a LoaderDef with name "equipment-list", system "equip", table "list", target
    #    "tags", description "Equipment list of the incumbent system (workbook).", mapping_text
    #    read_mapping("equipment-list.yaml"), file_types ("xlsx",), sheet "Equipment List",
    #    header_row 3. Leave confidentiality at its default.
    raise NotImplementedError("STEPS: see the comments")
