"""An example ``ActionJob``: ``echo`` returns what it was asked (brief §18.7).

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
        return ActionOutcome(
            status="completed",
            result={
                "action": request.action,
                "attempt": request.attempt,
                "parameters": request.parameters,
                "targets": [ref.key or ref.id for ref in request.targets],
            },
            notes=["echo"],
        )
