"""Scan codes: the one place a code is made, read and hashed is ``tl_core.qr.codes`` (frozen).

This module re-exports those names for the rest of the package and defines none of its own. A code
is never stored, logged, put in an event, an error text or a repr: it exists as the return value
of ``tl_mod_qr.service.issue`` and ``rotate``.
"""

from __future__ import annotations

from tl_core.qr.codes import code_hash, grouped, new_code, normalise_code

__all__ = ["code_hash", "grouped", "new_code", "normalise_code"]
