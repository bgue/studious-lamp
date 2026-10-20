"""The size limits of the cost module's commands and import file (the P1-I1 review rule).

A command arrives from a person over HTTP or the CLI, so every list has a bound and every text a
length before a handler reads it.
"""

from __future__ import annotations

MAX_CODE = 64  # a cost code
MAX_TEXT = 500  # a description
MAX_UOM = 20
MAX_ROWS = 20_000  # codes in one snapshot
MAX_IMPORT_BYTES = 10 * 1024 * 1024  # size of one CSV
MAX_SOURCE_NAME = 255
MAX_FIGURE = 1e15  # the largest figure a snapshot may state (hours, quantity or amount)
MAX_DEPTH = 20  # levels of the cost code hierarchy
