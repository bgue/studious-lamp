"""The loaders `awp-wbs` and `awp-cwa`: the WBS and the CWA grids of a legacy export (P2-I1-T01)."""

from __future__ import annotations

from tl_mod_legacy.model import LoaderDef

from tl_mod_awp.loaders import read_mapping


def wbs_loader() -> LoaderDef:
    """One row per WBS node: code, title, parent and cost_codes (``CODE:PCT;CODE:PCT``)."""
    return LoaderDef(
        name="awp-wbs",
        system="awp",
        table="wbs",
        target="awp_wbs",
        description="WBS nodes with their cost-code allocations (CSV or workbook).",
        mapping_text=read_mapping("awp-wbs.yaml"),
        file_types=("csv", "xlsx"),
    )


def cwa_loader() -> LoaderDef:
    """One row per control work area: code, title and an optional sequence."""
    return LoaderDef(
        name="awp-cwa",
        system="awp",
        table="cwa",
        target="awp_cwa",
        description="Control work areas, with an optional sequence for the path (CSV or workbook).",
        mapping_text=read_mapping("awp-cwa.yaml"),
        file_types=("csv", "xlsx"),
    )
