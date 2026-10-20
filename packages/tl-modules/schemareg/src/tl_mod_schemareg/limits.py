"""The size limits of the schema registry module's commands (the P1-I1 review rule).

A command arrives from a person over HTTP or the CLI, so every text has a length before a handler
reads it.
"""

from __future__ import annotations

MAX_CONTENT_BYTES = 262_144  # the YAML of one package version (256 KiB)
MAX_CHANGELOG = 4_000
MAX_REASON = 1_000
MAX_COMMENT = 1_000
MAX_PATH = 200  # a property path
MAX_PROJECT = 64
WAIVER_MAX_DAYS = 366  # a waiver holds for a year at most (brief 27.5: time-limited)
MAX_OPEN_WAIVERS = 500  # requested or approved waivers of one project
MAX_REPORT_BYTES = 1_048_576  # the classification or impact report as stored (1 MiB)
