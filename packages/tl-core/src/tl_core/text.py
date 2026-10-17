"""One check for the text a person or a file gives a record: no control or direction characters.

A name, a code, a reason or a note is shown on screens, printed in tables and put in file names.
A control character breaks the table (a newline, U+2028), crashes a database (NUL) or spoofs a
screen (a text-direction mark makes ``abc`` look like ``cba``). ``clean_text`` refuses them all;
it does not strip them, because a value that changes on its way in is a value nobody typed.

Refused: C0 (``U+0000`` to ``U+001F``, tab and newline included: the fields are one line), DEL
and C1
(``U+007F`` to ``U+009F``), the Arabic letter mark, the left-to-right and right-to-left marks, the
line and paragraph separators, the embedding and override controls, the isolates and the byte-order
mark. The message never repeats the value.
"""

from __future__ import annotations

import re
from typing import Final

FORBIDDEN_TEXT: Final = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]"
)
MESSAGE: Final = "text must not hold control, line-break or text-direction characters"


def has_forbidden_text(value: str) -> bool:
    return FORBIDDEN_TEXT.search(value) is not None


def clean_text(value: str) -> str:
    """``value`` unchanged, or ``ValueError`` (a pydantic validator turns it into a 422)."""
    if FORBIDDEN_TEXT.search(value) is not None:
        raise ValueError(MESSAGE)
    return value


def clean_optional_text(value: str | None) -> str | None:
    return None if value is None else clean_text(value)
