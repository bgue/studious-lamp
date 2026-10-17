"""The size limits of the module's commands (the P1-I1 security review rule applies here too).

A command arrives from a person or an agent over HTTP, so every list and mapping in it has a bound
and every free text a length, before a handler reads it. A request body is also bounded by the API
(`/commands/` allows 1 MiB); these limits are the module's own and hold for the CLI, for email
ingest and for proposals too.
"""

from __future__ import annotations

MAX_NUMBER = 128  # an item number, an external reference, a code
MAX_TEXT = 500  # a subject, a name, a label
MAX_REASON = 2000
MAX_BODY = 20_000  # the text of one item, in characters
MAX_RECIPIENTS = 100  # to and cc of one item, each
MAX_CONTACTS = 100  # contacts of one party
MAX_REFERENCES = 50  # records one item may refer to at triage
MAX_CLOCKS_PER_ITEM = 20  # clocks one item may carry
MAX_DURATION_DAYS = 3650  # the longest clock
MAX_WARNINGS = 10  # warning thresholds on one clock
MAX_CLOCK_EVENTS = 500  # events one clock may have; the engine refuses more
MAX_EMAIL = 254  # an email address
MAX_DOMAINS = 20  # email domains of one party
CLASSES_NOTE = (
    "Confidentiality is enforced (ADR-0016): a person sees an item only if their clearance "
    "covers its class; an unknown class is hidden from everyone."
)
