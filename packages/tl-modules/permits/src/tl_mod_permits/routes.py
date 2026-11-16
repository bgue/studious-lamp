"""The read routes of the permits module: none yet (T05 adds them in this file).

A route that returns record text reads through the viewer's class filter
(`tl_core.confidentiality`), and a hidden record answers as a missing one.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["permits"])
