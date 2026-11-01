"""The MTO seam: S4 fills these (publishing take-offs, assigning lines, the compensation refusals).

S2 leaves them empty so ``commands.py`` and ``actions.py`` can splat them today and S4 changes only
this file and ``handlers/mto.py``. The MTO events (``MTO.Defined``, ``MTOLine.Defined``,
``MTOLine.Assigned``) already project (``projectors/mto.py``).
"""

from __future__ import annotations

from tl_mod_materials.common import CommandSpec

MTO_COMMANDS: tuple[CommandSpec, ...] = ()
MTO_RULES: tuple[()] = ()
