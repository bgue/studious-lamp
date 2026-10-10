"""Driver for dev/demos/P0-I6.sh: the simulated project as a remote TUI feed shows it.

Reads TL_DEMO_URL, TL_DEMO_TOKEN and TL_DEMO_SCOPE from the environment (the script starts the API
and plays the simulation first). It opens the TUI in remote mode under Textual's Pilot (headless),
presses `F` to open the project feed and checks that the crew's and the document controller's
posts are on the screen. Every expectation is an assert, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from tl_tui.app import TlApp
from tl_tui.remote import RemoteClient

ROWS = 45


def screen_text(app: TlApp) -> str:
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


async def main() -> None:
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # Textual routes INFO lines to stdout
    url, token = os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_TOKEN"]
    scope = os.environ["TL_DEMO_SCOPE"]
    client = RemoteClient.connect(url, token)
    app = TlApp(client.as_client(), scope=scope, mode="remote", feed=client.change_feed(scope))
    async with app.run_test(size=(140, ROWS)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("F")
        deadline = time.monotonic() + 10
        text = ""
        while time.monotonic() < deadline:
            await pilot.pause(0.2)
            text = screen_text(app)
            if "Installed" in text and "Registered" in text:
                break
        print(text)
        assert "Installed" in text, "the crew's post is not on the remote feed screen"
        assert "Registered" in text, "the document controller's post is not on the screen"
        assert "user:sim-crew" in text or "sim-crew" in text, "the author is not shown"
    client.close()


asyncio.run(main())
