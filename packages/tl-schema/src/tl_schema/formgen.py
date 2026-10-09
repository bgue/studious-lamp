"""Form and grid metadata from an effective schema (brief 27.3, 10.2).

STUB: the body below is implemented by P0-I2-T04b. Signature and docstring are the contract.
"""

from __future__ import annotations

from tl_schema.effective import EffectiveSchema
from tl_schema.forms import FormMetadata


def form_metadata(schema: EffectiveSchema, record_type: str) -> FormMetadata:
    """Metadata a client needs to render and edit ``record_type`` under ``schema``.

    ``core_fields`` are the four envelope fields, then ``psets`` lists the psets that apply to the
    record type, standard psets first and then project psets, each by name. See the ticket for
    the exact mapping.
    """
    raise NotImplementedError
