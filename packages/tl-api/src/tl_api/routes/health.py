"""Liveness: the one route that needs no token."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/health", operation_id="health")
def health() -> Health:
    """The server is up. Does not touch the database."""
    return Health(status="ok")
