"""The size limits of the module's commands (the P1-I1 security review rule applies here too).

A command arrives from a person or an agent over HTTP, so every list and mapping in it has a bound
and every free text a length, before a handler reads it. A request body is also bounded by the API
(`/commands/` allows 1 MiB); these limits are the module's own and hold for the CLI and for
proposals too.
"""

from __future__ import annotations

MAX_NUMBER = 128  # a document or transmittal number, a revision code, a code
MAX_TEXT = 500  # a title, a subject, a name, an originator
MAX_REASON = 2000
MAX_DESCRIPTION = 10_000
MAX_ITEMS = 200  # revisions on one transmittal
MAX_RECIPIENTS = 100  # recipients of one transmittal
MAX_REVIEWERS = 50  # reviewers of one review cycle
MAX_PAGES = 100_000  # the page count a rendition may state
MAX_IMPORT_ROWS = 1000  # data rows of one legacy register file
MAX_IMPORT_BYTES = 5 * 1024 * 1024  # size of one legacy register file
MAX_LEGACY_CELL = 64  # a legacy revision, status or date kept in a note
MAX_MARKUPS = 20  # current markup renditions of one revision (markup is additive)

#: Said wherever confidentiality is set or shown, so nobody takes the class for access control.
CONFIDENTIALITY_NOTE = (
    "Confidentiality is enforced (ADR-0016): a person reads a document only when their "
    "clearance covers its class (internal or restricted); a document of any other class is "
    "hidden from everyone."
)
