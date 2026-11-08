"""Liveness: the one route that needs no token. It answers the server's version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


def _server_version() -> str:
    try:
        return version("tl-api")
    except PackageNotFoundError:  # running from a tree that was never installed
        return "unknown"


SERVER_VERSION = _server_version()


class Health(BaseModel):
    status: str
    version: str


@router.get("/health", operation_id="health")
def health() -> Health:
    """The server is up and its version. Does not touch the database."""
    return Health(status="ok", version=SERVER_VERSION)
