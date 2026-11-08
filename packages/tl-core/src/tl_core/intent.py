"""Event intent (ADR-0025): why a command was run, what comes next, what it moves toward.

``intent_json`` is the one function that turns an intent into the text a ledger stores and the
event hash covers. Adapters, the archive and restore call it or read the stored text; none dumps
the model itself.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class IntentRef(BaseModel):
    """One next item: ``{command, target}`` or ``{text}``."""

    model_config = ConfigDict(extra="forbid")

    command: str | None = None
    target: str | None = None
    text: str | None = None


class IntentToward(BaseModel):
    """What the work moves toward: a target with a state xor a condition."""

    model_config = ConfigDict(extra="forbid")

    target: str
    state: str | None = None
    condition: str | None = None


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why: str | None = None
    next: list[IntentRef] = []
    toward: IntentToward | None = None
    goal_ref: str | None = None


class IntentInvalid(ValueError):
    code = "intent_invalid"


def _dump(intent: Intent) -> dict[str, Any]:
    data: dict[str, Any] = intent.model_dump(mode="json", exclude_none=True)
    if not data.get("next"):
        data.pop("next", None)
    else:
        data["next"] = [item for item in data["next"] if item]
        if not data["next"]:
            del data["next"]
    return data


def intent_json(intent: Intent | None) -> str | None:
    """The stored text of an intent; ``None`` for no intent or an empty one (``{}``, all null)."""
    if intent is None:
        return None
    data = _dump(intent)
    if not data:
        return None
    from tl_core.ledger.hashing import canonical_json  # not at top: ledger.types imports us

    return canonical_json(data)


def check_intent(command: Any) -> None:
    """Refuse any non-null intent until the command boundary validates it (S2 replaces this)."""
    if getattr(command, "intent", None) is not None:
        raise IntentInvalid("intent not accepted")
