"""JSON Schema for a record type's psets, and a validator over it (brief 27.3).

STUB: the bodies below are implemented by P0-I2-T04. Signatures and docstrings are the contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tl_schema.effective import EffectiveSchema


@dataclass(frozen=True)
class ValueIssue:
    """One violation found in a ``psets`` object."""

    path: str  # "psets.valve_data.size_in", "psets.valve_data.x.nope", "psets.valve_data"
    # The JSON Schema keyword: type, minimum, maximum, pattern, enum, additionalProperties.
    keyword: str
    message: str


def record_json_schema(schema: EffectiveSchema, record_type: str) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of the ``psets`` object of ``record_type``.

    Built only from ``schema``; cached by ``schema.hash`` and ``record_type``; the returned
    dict must not be mutated by callers. See the ticket for the exact shape.
    """
    raise NotImplementedError


def validate_psets(
    schema: EffectiveSchema, record_type: str, psets: Mapping[str, Any]
) -> list[ValueIssue]:
    """Every violation of ``psets`` against ``record_json_schema``, sorted by ``(path, keyword)``.

    An ``additionalProperties`` violation yields one issue per unknown key, with that key at the
    end of ``path``. An empty list means the object is valid.
    """
    raise NotImplementedError
