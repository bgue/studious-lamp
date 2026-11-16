"""What ext_demo gives the platform: a ``ModuleSpec`` that names only its own package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tl_core.modules import ConfidentialSource, ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from . import MODULE, NOTE, NOTE_TABLE
from .commands import ExtDemoAddNote, handle_add_note
from .projector import NoteProjector


@dataclass(frozen=True)
class NoteCommand:
    """A command row: the model, its handler, its access word and its marks."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str
    meta: dict[str, str] = field(default_factory=dict[str, str])


#: ``excluded:reserved``: the module is outside ``IN_TREE_SURFACES``, so the mark lives in the row.
COMMANDS: tuple[NoteCommand, ...] = (
    NoteCommand(
        ExtDemoAddNote,
        handle_add_note,
        "user",
        {"delegation": "excluded:reserved"},
    ),
)

#: Decided by a proposable row that names no agent tool: a person adds notes; an agent does not.
PROPOSABLE = (
    ProposableCommand(
        "propose_ext_demo_note", ExtDemoAddNote, handle_add_note, "user", agent_tool=False
    ),
)


def projectors() -> list[Projector]:
    return [NoteProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=frozenset({NOTE}),
        projectors=projectors,
        proposable=PROPOSABLE,
        confidential=(
            ConfidentialSource(
                record_types=frozenset({NOTE}),
                table=NOTE_TABLE,
                id_column="id",
                class_column="note_class",
            ),
        ),
        command_words={"ExtDemoAddNote": "user"},
        commands="tl_mod_ext_demo.module:COMMANDS",
        read_routers=("tl_mod_ext_demo.routes:router",),
        tools=("tl_mod_ext_demo.tools:register_tools",),
        cli_groups=("tl_mod_ext_demo.cli:ext_demo_app",),
    )
