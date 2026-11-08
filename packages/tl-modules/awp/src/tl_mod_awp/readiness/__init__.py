"""The readiness engine of the awp module (P2-I2 S4).

``request`` queues the evaluation of IWPs, ``evaluate_now`` runs it inside a request,
``views.readiness`` reads the last evaluation. The checks are plugins (``tl_core.readiness``);
this package imports no other module.
"""

from __future__ import annotations

from tl_mod_awp.readiness.engine import evaluate_now, request
from tl_mod_awp.readiness.views import ReadinessView

__all__ = ["ReadinessView", "evaluate_now", "request"]
