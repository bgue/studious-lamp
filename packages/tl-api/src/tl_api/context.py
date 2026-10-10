"""The per-application context that route handlers read from ``request.app.state``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request
from tl_core.files.service import FileService

from tl_api.backend import Backend
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore

if TYPE_CHECKING:
    from tl_api.feed import FeedHub


@dataclass
class ApiContext:
    backend: Backend
    tokens: TokenStore
    authorize: Callable[[str, str, str], None]
    feed: FeedHub
    settings: ApiSettings
    files: FileService | None = None  # None: file routes answer 503 ``unavailable``


def get_ctx(request: Request) -> ApiContext:
    ctx: ApiContext = request.app.state.ctx
    return ctx
