"""Where the module schemas are (ADR-0010).

A module's LinkML root is ``schema/modules/<name>/module.yaml``, a sibling of ``schema/core``. The
generators run it after the core root, from inside its own directory, and keep only what the module
itself defines (its ``tl:module`` annotation), because a module root imports core files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT_FILE = "module.yaml"


@dataclass(frozen=True)
class ModuleRoot:
    name: str  # directory name, equal to the ``tl:module`` annotation of the root
    directory: Path
    file: str = ROOT_FILE


def module_roots(schema_dir: Path) -> list[ModuleRoot]:
    """The module roots beside ``schema_dir`` (``schema/core``), sorted by name.

    ``schema_dir.parent / "modules" / <name> / module.yaml``. A directory without that file is
    not a module. Nothing is read from the files here.
    """
    base = schema_dir.parent / "modules"
    if not base.is_dir():
        return []
    return [
        ModuleRoot(name=path.name, directory=path)
        for path in sorted(base.iterdir())
        if path.is_dir() and (path / ROOT_FILE).is_file()
    ]
