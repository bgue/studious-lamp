"""The loader `instrument-index`: the instrument index of the incumbent system (P1-I8-T07b)."""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per tag: number, service, type code and the valve data the export carries.

    The mapping template is the data file ``mappings/instrument-index.yaml`` of this package.
    """
    return LoaderDef(
        name="instrument-index",
        system="instr",
        table="index",
        target="tags",
        description="Instrument index of the incumbent system (workbook or CSV).",
        mapping_text=read_mapping("instrument-index.yaml"),
        file_types=("xlsx", "csv"),
    )
