"""The change feed (brief 5.3, 18.2): filters, a subscription registry, paged reads, a poller.

Committed events reach subscribers two ways that share one registry: the in-process bus calls
``registry.attach(bus)``; out-of-process readers run a :class:`ChangePoller` over
``Ledger.read_after``. Delivery is at-least-once and resumable from the last ``seq``.
"""

from tl_core.changefeed.filters import ANY, SubscriptionFilter
from tl_core.changefeed.pager import ChangePage, fetch_changes
from tl_core.changefeed.poller import ChangePoller
from tl_core.changefeed.registry import (
    QueueSubscription,
    RegistrySubscription,
    SubscriptionOverflow,
    SubscriptionRegistry,
)

__all__ = [
    "ANY",
    "ChangePage",
    "ChangePoller",
    "QueueSubscription",
    "RegistrySubscription",
    "SubscriptionFilter",
    "SubscriptionOverflow",
    "SubscriptionRegistry",
    "fetch_changes",
]
