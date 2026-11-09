"""Which environments may use development shortcuts (ADR-0009 section 9). Unset fails closed."""

from __future__ import annotations

import os
from collections.abc import Mapping

#: ``TL_ENV`` values that honour the dev token file.
DEV_TOKEN_ENVS = frozenset({"dev", "test", "ci"})
#: ``TL_ENV`` values that may create the ``demo`` account (the contract's ``seed_demo``).
DEMO_ENVS = frozenset({"dev", "demo", "test"})


def current_env(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return source.get("TL_ENV", "").strip().lower()


def dev_tokens_allowed(env: str | Mapping[str, str] | None = None) -> bool:
    name = env if isinstance(env, str) else current_env(env)
    return name.strip().lower() in DEV_TOKEN_ENVS


def demo_allowed(env: str | Mapping[str, str] | None = None) -> bool:
    name = env if isinstance(env, str) else current_env(env)
    return name.strip().lower() in DEMO_ENVS


def prod_like(env: str | Mapping[str, str] | None = None) -> bool:
    """True when ``TL_ENV`` names a real deployment: set, and not a dev, test, ci or demo name.

    Unset is false (it fails closed everywhere else: no dev tokens, no demo account).
    """
    name = (env if isinstance(env, str) else current_env(env)).strip().lower()
    return bool(name) and name not in DEV_TOKEN_ENVS | DEMO_ENVS
