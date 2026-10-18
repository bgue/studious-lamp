"""One check for the text a person, a file or an email gives a record (a copy of ``tl_core.text``).

P1-I4 adds ``tl_core.text.clean_text`` with the same rules; this copy keeps the module independent
of the merge order (the brief: "write a compatible copy if it is not on the trunk"). After P1-I4
is merged the module can import from the core instead; the tests of both pin the same character
sets.

A subject, a name, a reference or a reason is shown on screens, printed in tables and put in file
names. A control character breaks a table (a newline, U+2028), crashes a database (NUL) or spoofs a
screen (a text-direction mark makes ``abc`` look like ``cba``). ``clean_text`` refuses them all; it
does not strip them, because a value that changes on its way in is a value nobody typed. The one
exception is the **body** of an item, which is several lines: ``clean_body`` allows the line break
and the tab and refuses every other control, line-separator and direction character.
"""

from __future__ import annotations

import re
from typing import Final

FORBIDDEN_TEXT: Final = re.compile(r"[\x00-\x1f\x7f-\x9f؜‎‏  ‪-‮⁦-⁩﻿]")
FORBIDDEN_BODY: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f؜‎‏  ‪-‮⁦-⁩﻿]")
MESSAGE: Final = "text must not hold control, line-break or text-direction characters"
BODY_MESSAGE: Final = "text must not hold control or text-direction characters"


def has_forbidden_text(value: str) -> bool:
    return FORBIDDEN_TEXT.search(value) is not None


def clean_text(value: str) -> str:
    """``value`` unchanged, or ``ValueError`` (a pydantic validator turns it into a 422)."""
    if FORBIDDEN_TEXT.search(value) is not None:
        raise ValueError(MESSAGE)
    return value


def clean_optional_text(value: str | None) -> str | None:
    return None if value is None else clean_text(value)


def clean_body(value: str) -> str:
    """Like ``clean_text`` for a text of several lines: ``\\n``, ``\\r`` and tab are allowed."""
    if FORBIDDEN_BODY.search(value) is not None:
        raise ValueError(BODY_MESSAGE)
    return value
