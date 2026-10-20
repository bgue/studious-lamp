"""What the correspondence module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``correspondence`` in this package's ``pyproject.toml``
names ``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ChildSource, ConfidentialSource, ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector

from tl_mod_correspondence import MODULE
from tl_mod_correspondence.guards import item_upload, not_void
from tl_mod_correspondence.handlers.triage import ConfirmTriage, handle_confirm_triage
from tl_mod_correspondence.names import (
    CLAUSE,
    CLEARANCE_TABLE,
    CLOCK,
    CLOCK_TABLE,
    COMMERCIAL,
    CORRESPONDENCE,
    CORRESPONDENCE_TABLE,
    ITEM_TYPES,
    PARTY,
    RECORD_TYPES,
    TECHNICAL,
    THREAD,
    THREAD_TABLE,
)
from tl_mod_correspondence.projectors import (
    ClauseProjector,
    ClockProjector,
    CommercialProjector,
    CorrespondenceProjector,
    PartyProjector,
    TechnicalProjector,
    ThreadProjector,
)

#: The generic commands a person may run on each record type (ADR-0010 addendum). Everything else
#: changes through the module's own commands, which check the module's rules:
#:
#: * an item takes property-set values (the psets a domain requires), links, and files in the
#:   slots ``original`` and ``attachment`` (``guards.item_upload`` says when);
#: * a thread, a clause and a party take links; a clock takes nothing.
#:
#: The subject, the register fields, the state, the class and a void are never generic.
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
ITEM_GENERIC_COMMANDS = (
    frozenset({"SetPsetValues", "AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
)
LINKABLE_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE

#: What an agent may propose (ADR-0014 section 8): the triage of a received item. Accepting runs
#: ``ConfirmTriage`` as the accepting person, who needs the access of that command (any signed-in
#: person); the agent only reads what its clearance allows (internal items) and proposes.
PROPOSABLE = (ProposableCommand("propose_triage", ConfirmTriage, handle_confirm_triage, "user"),)

#: The items of the Technical and Commercial domains are records of a type of their own and take the
#: same generic commands as an item (the module's commands do the rest).
#:
#: The class of an item is its `confidentiality` column; a `privileged` item is read by the accounts
#: named in the clearance table (ADR-0016). A thread hangs on its governing item and a clock on its
#: item, so they are readable only when that item is.
CONFIDENTIAL = (
    ConfidentialSource(
        record_types=ITEM_TYPES,
        table=CORRESPONDENCE_TABLE,
        id_column="id",
        class_column="confidentiality",
        clearance_table=CLEARANCE_TABLE,
        children=(
            ChildSource(frozenset({THREAD}), THREAD_TABLE, "id", "governing_item_id"),
            ChildSource(frozenset({CLOCK}), CLOCK_TABLE, "id", "item_id"),
        ),
    ),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        CorrespondenceProjector(),
        ThreadProjector(),
        ClockProjector(),
        ClauseProjector(),
        PartyProjector(),
        TechnicalProjector(),
        CommercialProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            CORRESPONDENCE: ITEM_GENERIC_COMMANDS,
            TECHNICAL: ITEM_GENERIC_COMMANDS,
            COMMERCIAL: ITEM_GENERIC_COMMANDS,
            THREAD: LINKABLE_GENERIC_COMMANDS,
            CLAUSE: LINKABLE_GENERIC_COMMANDS,
            PARTY: LINKABLE_GENERIC_COMMANDS,
        },
        generic_guards={
            **{
                (record_type, command): guard
                for record_type in (CORRESPONDENCE, TECHNICAL, COMMERCIAL)
                for command, guard in (
                    ("AttachFile", item_upload),
                    ("AddLink", not_void),
                    ("SuggestLink", not_void),
                )
            },
        },
        proposable=PROPOSABLE,
        confidential=CONFIDENTIAL,
    )
