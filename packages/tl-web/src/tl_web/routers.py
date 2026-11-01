"""The page routers, in match order (their paths are all more specific than the 404 catch-all).

Each module named here exposes ``router``, an ``APIRouter(prefix="/web", include_in_schema=False)``.
A module that does not exist yet is skipped, so the pieces that add pages never edit ``app.py``;
the tests piece pins the full list.
"""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec

from fastapi import APIRouter

PAGE_MODULES: tuple[str, ...] = (
    "tl_web.files",
    "tl_web.actions",
    "tl_web.pages.rfis",
    "tl_web.pages.correspondence",
    "tl_web.pages.documents",
    "tl_web.pages.record",
    "tl_web.pages.viewer",
)


def _exists(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except ModuleNotFoundError:  # the parent package is not there yet
        return False


def page_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []
    for name in PAGE_MODULES:
        if _exists(name):
            routers.append(import_module(name).router)  # a module without ``router`` is an error
    return routers
