"""Bounds of the legacy loaders. The file reader's bounds are the derivation contract's
(``tl_core.derivation.types``: 50 MiB, 20 000 rows, 200 columns, 10 000 characters a cell)."""

from __future__ import annotations

MAX_SYSTEM = 31  # characters of a system or table name
MAX_UNMAPPED_COLUMNS = 60  # columns kept in the source layer of a record
MAX_UNMAPPED_CELL = 500  # characters of a cell kept in the source layer
MAX_PROFILE_VALUES = 5  # most frequent values shown per column
MAX_VALUE_SHOWN = 60  # characters of a value in a profile
MAX_BRONZE_COLUMNS = 200
MAX_PROBLEMS_SHOWN = 50
MAX_RECORD_IDS = 20_000
MAX_REASON = 1_000
