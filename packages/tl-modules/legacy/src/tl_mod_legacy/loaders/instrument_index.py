# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `instrument-index`: the instrument index of the incumbent system (P1-I8-T07b).

STUB: this file is the interface P1-I8-T07b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per tag: number, service, type code and the valve data the export carries.

    The mapping template is the data file ``mappings/instrument-index.yaml`` of this package.
    """
    # STEPS
    # 1. Return a LoaderDef with name "instrument-index", system "instr", table "index", target
    #    "tags", description "Instrument index of the incumbent system (workbook or CSV).",
    #    mapping_text read_mapping("instrument-index.yaml"), file_types ("xlsx", "csv"). Leave
    #    sheet, header_row and confidentiality at their defaults (the first sheet, header on row 1).
    raise NotImplementedError("STEPS: see the comments")
