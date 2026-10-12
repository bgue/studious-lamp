"""Checks a server makes before it listens (ADR-0008 decision 4, ADR-0009 section 9)."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlalchemy.exc import OperationalError, ProgrammingError
from tl_core.auth.env import current_env, demo_allowed
from tl_core.auth.queries import demo_account_enabled
from tl_core.auth.seed import DEMO_WARNING

from tl_api.backend import Backend
from tl_api.settings import is_loopback

log = logging.getLogger("tl_api")


class StartupRefused(Exception):
    """The server must not start in this state; the message says how to fix it."""


def check_demo_account(
    backend: Backend, *, host: str, env: Mapping[str, str] | None = None
) -> bool:
    """Refuse to start while an enabled ``demo`` account is unsafe here; warn while it is not.

    * ``TL_ENV`` is not dev, demo or test: refuse, even on loopback (a reverse proxy makes loopback
      public). The account would not authenticate anyway, but a server that carries it is a mistake
      worth stopping on.
    * the bind address is not loopback: refuse.
    * otherwise log the warning. Returns whether the account exists and is enabled.
    """
    try:
        with backend(True) as uow:
            enabled = demo_account_enabled(uow.conn())
    except (OperationalError, ProgrammingError) as exc:
        raise StartupRefused(
            "the ledger has no account tables yet: run `uv run tl init` (it is safe to repeat)"
        ) from exc
    if not enabled:
        return False
    name = current_env(env)
    if not demo_allowed(name):
        raise StartupRefused(
            f"the demo account is enabled but TL_ENV is {name or 'unset'!r}: disable it with "
            "`tl admin user disable demo` (after creating a real admin with `tl admin bootstrap`)"
        )
    if not is_loopback(host):
        raise StartupRefused(
            f"refusing to bind {host!r} while the demo account (demo/demo) is enabled: disable it "
            "with `tl admin user disable demo`, or bind 127.0.0.1"
        )
    log.warning(DEMO_WARNING)
    return True
