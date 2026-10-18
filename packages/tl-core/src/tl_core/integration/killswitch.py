"""The kill switch of the integration layer (FANOUT D11).

``integration.kill_switch`` is a platform and company setting. Every engine reads it **per batch or
per delivery**, never once at start: a worker that has run for a day obeys a change at the next
event (L-P1-I0A-22). A read that fails is not an answer: the error propagates, the batch is
retried, and nothing runs meanwhile.
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.integration.contract import KILL_SWITCH_SETTING
from tl_core.settings.resolver import value_of


def kill_switch_on(conn: Connection) -> bool:
    """Whether the company has stopped rules, inbound endpoints, action executors and enrichers."""
    return value_of(conn, KILL_SWITCH_SETTING) is True
