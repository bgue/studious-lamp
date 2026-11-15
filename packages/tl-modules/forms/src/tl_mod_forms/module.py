"""What the forms module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``forms`` names ``spec``. This slice holds the record
types and their projectors only: no commands (S3 and S7c add them), no hook fields, and no
``confidential`` declaration (the confidentiality rows add it with the subject rows, before any read
path ships).
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_forms import MODULE
from tl_mod_forms.names import RECORD_TYPES
from tl_mod_forms.projectors import (
    IntakeCodeProjector,
    IntakeItemProjector,
    SubmissionProjector,
    TemplateProjector,
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        TemplateProjector(),
        SubmissionProjector(),
        IntakeCodeProjector(),
        IntakeItemProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        command_words={},
        proposable=(),
    )
