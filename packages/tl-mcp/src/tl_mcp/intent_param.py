"""The optional ``intent`` parameter of the proposing tools (P2-INT-T03; ADR-0025 d6, ADR-0027 F9).

An agent gives the reason with a proposal exactly as a person does. The tool only passes the
object on: ``proposals.submit`` checks it (``tl_core.intent.validate_intent``) and stores it in the
Created event's ``intent`` column. An intent grants no authority, and there is no ``evidence`` key.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from tl_core.intent import Intent

IntentParam = Annotated[
    Intent | None,
    Field(
        description="Why you propose this: why (<= 500 chars), next (<= 5 items: {command,target} "
        "or {text}), toward ({target,state} or {target,condition}), goal_ref. Recorded with the "
        "event; it grants no authority."
    ),
]
