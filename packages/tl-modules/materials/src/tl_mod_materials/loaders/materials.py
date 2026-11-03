"""The loaders ``mat-items``, ``mat-locations`` and ``mat-po-lines`` (P2-I3-T01b).

The targets are hand-written (S2) and read the grid's columns by name, so each mapping text is a
plain YAML description of those columns. The framework only hashes it.
"""

from __future__ import annotations

from tl_mod_legacy.model import LoaderDef

ITEMS_MAPPING = """\
name: mat-items
description: Item master of the incumbent system (CSV export).
delimiter: ","
columns:
  - code
  - description
  - category
  - uom
  - size
  - rating
  - material
  - consumable
"""

LOCATIONS_MAPPING = """\
name: mat-locations
description: Storage and site locations of the incumbent system (CSV export).
delimiter: ","
columns:
  - code
  - title
  - kind
  - parent_code
"""

PO_LINES_MAPPING = """\
name: mat-po-lines
description: Purchase order lines of the incumbent system (CSV export).
delimiter: ","
columns:
  - po_number
  - line_no
  - item_code
  - qty_ordered
  - uom
  - promised_date
  - supplier_text
"""


def items_loader() -> LoaderDef:
    """One row per item of the company library, written to ``materials_item_master``."""
    return LoaderDef(
        name="mat-items",
        system="mat",
        table="items",
        target="materials_item_master",
        description="Item master of the incumbent system (company library).",
        mapping_text=ITEMS_MAPPING,
        file_types=("csv", "xlsx"),
    )


def locations_loader() -> LoaderDef:
    """One row per location, parents first, written to ``materials_location``."""
    return LoaderDef(
        name="mat-locations",
        system="mat",
        table="locations",
        target="materials_location",
        description="Storage and site locations of the incumbent system (project).",
        mapping_text=LOCATIONS_MAPPING,
        file_types=("csv", "xlsx"),
    )


def po_lines_loader() -> LoaderDef:
    """One row per purchase order line, written to ``materials_po_line``."""
    return LoaderDef(
        name="mat-po-lines",
        system="mat",
        table="po_lines",
        target="materials_po_line",
        description="Purchase order lines of the incumbent system (project).",
        mapping_text=PO_LINES_MAPPING,
        file_types=("csv", "xlsx"),
    )
