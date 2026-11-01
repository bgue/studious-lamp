"""Every bound of the materials module's commands and records (m4-materials.md section 2).

A command arrives from a person over HTTP or the CLI, so every text has a length, every list a
bound and every quantity a range before a handler reads it.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

MAX_ITEM_CODE: Final = 40
MAX_LOCATION_CODE: Final = 16
MAX_PO_NUMBER: Final = 30
MAX_SUPPLIER: Final = 120
MAX_DELIVERY_REF: Final = 60
MAX_TITLE: Final = 200
MAX_SPEC_TEXT: Final = 60  # size, rating, material code
MAX_REASON: Final = 500
MAX_LINE_NO: Final = 99_999
MAX_RECEIPT_LINES: Final = 50
MAX_MOVEMENTS: Final = 200
MAX_MTO_LINES: Final = 500
MAX_SERIALS_TEXT: Final = 2_000

MAX_DEPTH: Final = 5  # depth of a location below the root, 0..5
MAX_QTY: Final = Decimal(1_000_000_000)
QTY_PLACES: Final = 3
QTY_STEP: Final = Decimal("0.001")
MAX_VIEW_ROWS: Final = 1_000

ITEM_CODE: Final = re.compile(r"[A-Z0-9][A-Z0-9._\-]{0,39}")
LOCATION_CODE: Final = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,15}")
HEAT_NO: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9./\-]{0,39}")
QTY_TEXT: Final = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,3})?")  # ASCII digits only
ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
#: A value of an extensible code list (``ItemCategory``, ``MaterialCode``) is a lower-case word;
#: the list itself is data in the ledger (the standards edition), never code.
CODE_WORD: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}")

#: Closed code lists of ``co.acme.materials@1.0.0`` (their policy is ``closed``).
LOCATION_KINDS: Final = ("project", "warehouse", "laydown", "toolcrib", "gang_box")
STOCK_UOMS: Final = ("EA", "SET", "BOX", "ROLL", "L", "m", "kg", "lb", "m3")
