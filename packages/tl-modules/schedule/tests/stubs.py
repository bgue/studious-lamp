"""Tests that need a ticket's code skip while that code is still a stub (P1-I4).

Remove the marks of a ticket when it has merged.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest
from tl_mod_schedule import lookahead, resolver


def is_stub(function: Callable[..., Any]) -> bool:
    return "raise NotImplementedError" in inspect.getsource(function)


needs_t07 = pytest.mark.skipif(
    is_stub(resolver.resolve_snapshot), reason="P1-I4-T07 (the resolver) has not merged"
)
needs_t08 = pytest.mark.skipif(
    is_stub(lookahead.build_look_ahead), reason="P1-I4-T08 (the look-ahead) has not merged"
)
