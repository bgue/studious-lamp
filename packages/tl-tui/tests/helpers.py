"""Async test helpers for Textual apps without an async pytest plugin."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from textual.app import App
from textual.pilot import Pilot


def run_pilot(
    app: App[Any],
    scenario: Callable[[Pilot[Any]], Awaitable[None]],
    *,
    size: tuple[int, int] = (120, 40),
) -> None:
    """Run ``app`` headless at ``size`` and await ``scenario(pilot)``."""

    async def main() -> None:
        async with app.run_test(size=size) as pilot:
            await scenario(pilot)

    asyncio.run(main())


def screen_text(app: App[Any]) -> str:
    """The rendered screen as plain text, one line per terminal row (for assertions)."""
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)
