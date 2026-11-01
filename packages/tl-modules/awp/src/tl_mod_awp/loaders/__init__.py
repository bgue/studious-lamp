"""The loaders the awp package ships: a name, a mapping template and the kind of record they write.

Each loader is a function returning a :class:`tl_mod_legacy.model.LoaderDef`, named in the
``throughline.loaders`` entry-point group of ``pyproject.toml`` (the entry-point name is the
loader's name). The mapping template is a data file in ``mappings/`` next to this package. The
awp targets only hash it; they read the grid by column name.
"""

from __future__ import annotations

from importlib.resources import files


def read_mapping(filename: str) -> str:
    """The text of the mapping template ``mappings/<filename>`` of this package."""
    return files(__package__).joinpath("mappings", filename).read_text(encoding="utf-8")
