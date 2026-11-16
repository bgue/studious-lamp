"""The read routes of the QR module (ADR-0029): none yet; a later piece adds them.

A route that returns record text reads through the viewer's class filter
(`tl_core.confidentiality`), and a hidden record answers as a missing one.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["qr"])
