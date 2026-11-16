"""Intake and scan codes: make one, read one a person typed, hash it, print it in groups (P2-FORMS
S7c, decision D15). Frozen: the QR module imports these and defines none of its own.

A code is 16 symbols of a 32-symbol alphabet (80 random bits). The server keeps only
``code_hash(code)``; the code itself is printed once and never logged, stored or put in an event.
Pure: imports ``hashlib``, ``secrets`` and ``re`` only.
"""

from __future__ import annotations

import hashlib
import re
import secrets

#: 32 symbols: no ``I``, ``O``, ``0`` or ``1`` (they are mistaken for one another when printed).
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 16
GROUP = 4

_SEPARATORS = re.compile(r"[ \-]")
_SHAPE = re.compile(rf"[{ALPHABET}]{{{CODE_LENGTH}}}")


def new_code() -> str:
    """A fresh code: 16 symbols of ``ALPHABET`` from ``secrets``. Never log it."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(text: str) -> str | None:
    """``text`` with spaces and hyphens removed and upper-cased, or ``None`` unless that is exactly
    16 symbols of ``ALPHABET`` (also ``None`` for anything that is not text)."""
    if not isinstance(text, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        return None
    plain = _SEPARATORS.sub("", text).upper()
    return plain if _SHAPE.fullmatch(plain) else None


def code_hash(code: str) -> str:
    """SHA-256 of the normalised code: 64 lower-case hex characters. ``ValueError`` (with no text
    of the input) when ``code`` is not a code."""
    plain = normalise_code(code)
    if plain is None:
        raise ValueError("not an intake code")
    return hashlib.sha256(plain.encode("ascii")).hexdigest()


def grouped(code: str) -> str:
    """The printed form, four groups of four (``7KQ2-M9XA-4TTC-P0HV``). ``ValueError`` when
    ``code`` is not a code."""
    plain = normalise_code(code)
    if plain is None:
        raise ValueError("not an intake code")
    return "-".join(plain[i : i + GROUP] for i in range(0, CODE_LENGTH, GROUP))


__all__ = ["ALPHABET", "CODE_LENGTH", "code_hash", "grouped", "new_code", "normalise_code"]
