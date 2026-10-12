"""The size limits of the module's commands (P1-I1 security review).

A command arrives from a person or an agent over HTTP, so every list and mapping in it has a bound
and every free text a length, before a handler reads it. A request body is also bounded by the
API (`/commands/` allows 1 MiB); these limits are the module's own and hold for the CLI and for
proposals too. Generous for real use (a tag list of 500 ids), small enough that a command cannot
be used to make the ledger work on megabytes.
"""

from __future__ import annotations

MAX_NUMBER = 128  # a tag number, a key, a code
MAX_TEXT = 500  # a label, a title, a service description
MAX_REASON = 2000
MAX_DESCRIPTION = 10_000
MAX_ITEMS = 500  # entries of a list: ids to merge, numbers to split into, mnemonics of a class
MAX_PSETS = 50  # property sets in one request
MAX_PROPERTIES = 200  # properties of one pset, attributes of a value, entries of a segment map
MAX_SEGMENTS = 20  # segments of a numbering pattern
