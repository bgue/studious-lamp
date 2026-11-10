"""Where the terminal opens after sign-in (P2-I5 T06c2; W3-6 as decided, D7).

There is no foreman account role. The user-scope setting ``tui.landing`` decides. While nobody
has set it (origin ``default``), a person who is foreman on any IWP of the project lands on the
IWP log filtered to their own IWPs; anyone else lands on the usual start screen. A value set at
company, project or user level is honoured as it is. A failed read never blocks the app: the
landing is ``default``.

This module does not import ``textual``; the app asks ``landing`` and pushes the screen itself.
"""

from __future__ import annotations

from typing import Literal

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.settings_text import user_of

SETTING_KEY = "tui.landing"


def landing(client: ClientInterface, project: str, actor: str) -> Literal["default", "iwp_mine"]:
    """The screen to open after sign-in: ``"iwp_mine"`` or ``"default"``."""
    try:
        view = client.get_setting(SETTING_KEY, user=user_of(actor))
        origin = view.effective.origin
        value = view.effective.value
        if origin != "default":
            # someone chose the value (company, project or the person): it is the answer
            return "iwp_mine" if value == "iwp_mine" else "default"
        # nobody chose it: a foreman on any IWP of the project lands on their IWPs
        if client.list_iwps(project, foreman=actor, limit=1):
            return "iwp_mine"
        return "default"
    except CLIENT_ERRORS:
        return "default"
