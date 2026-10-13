"""What the documents module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``documents`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_documents import MODULE
from tl_mod_documents.guards import revision_upload, transmittal_draft_only
from tl_mod_documents.names import DOCUMENT, RECORD_TYPES, REVISION, TRANSMITTAL
from tl_mod_documents.projectors import (
    DocumentProjector,
    RenditionProjector,
    ReviewCycleProjector,
    RevisionProjector,
    TransmittalProjector,
)

#: The generic commands a person may run on each record type (ADR-0010 addendum). Everything else
#: changes through the module's own commands, which check the module's rules:
#:
#: * a document takes property-set values (custom fields) and links;
#: * a revision takes links and file uploads into its four slots (an upload becomes a controlled
#:   rendition only when ``AttachRendition`` registers it);
#: * a transmittal takes links and attachments (a cover letter);
#: * a rendition and a review cycle allow none: they change only through ``AttachRendition`` and
#:   the review commands.
#:
#: The title, the register fields, the workflow state and a void are never generic.
#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract) is
#: allowed too; a link a rule of this module wrote is kept by the module (core refuses a generic
#: FlagLink or RetractLink on it).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
DOCUMENT_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "SuggestLink"}) | LINK_LIFE
REVISION_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
TRANSMITTAL_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        DocumentProjector(),
        RevisionProjector(),
        RenditionProjector(),
        TransmittalProjector(),
        ReviewCycleProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            DOCUMENT: DOCUMENT_GENERIC_COMMANDS,
            REVISION: REVISION_GENERIC_COMMANDS,
            TRANSMITTAL: TRANSMITTAL_GENERIC_COMMANDS,
        },
        generic_guards={
            (REVISION, "AttachFile"): revision_upload,
            (TRANSMITTAL, "AttachFile"): transmittal_draft_only,
            (TRANSMITTAL, "AddLink"): transmittal_draft_only,
            (TRANSMITTAL, "SuggestLink"): transmittal_draft_only,
            (TRANSMITTAL, "FlagLink"): transmittal_draft_only,
            (TRANSMITTAL, "RetractLink"): transmittal_draft_only,
        },
    )
