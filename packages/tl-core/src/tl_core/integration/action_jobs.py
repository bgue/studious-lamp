# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""An example ``ActionJob``: ``echo`` returns what it was asked (brief §18.7).

STUB (P1-I7-T02a): ``EchoJob.run`` raises NotImplementedError. Remove this paragraph, the STEPS
comment, the two lint-silencing lines above and `NotImplementedError` when you implement it.

Registered as ``echo`` under ``throughline.action_jobs``. It exists so an admin can define a job
action without writing code, and so the executor and the action screens have a job to run in the
demo and in tests.
"""

from __future__ import annotations

from tl_core.integration.contract import ActionOutcome, ActionRequest, SideEffectClass


class EchoJob:
    name = "echo"
    version = "1"
    side_effect_class: SideEffectClass = "read"

    def run(self, request: ActionRequest) -> ActionOutcome:
        # STEPS
        # 1. Return ActionOutcome(status="completed", result={...}, notes=["echo"]) where the
        #    result has exactly four keys:
        #    "action": request.action; "attempt": request.attempt;
        #    "parameters": request.parameters;
        #    "targets": for each target, its `key` or, when it has none, its `id`.
        raise NotImplementedError
