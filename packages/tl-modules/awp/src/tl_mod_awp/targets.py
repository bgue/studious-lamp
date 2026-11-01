"""Load targets of the awp module (spec m3-wbs-cwp section 6): stubs, filled by ticket T02.

Two targets are found by the entry-point group ``throughline.load_targets``; each entry point names
a zero-argument callable that returns a ``tl_mod_legacy.targets.Target`` with scope ``project``:

* ``awp.wbs`` creates nodes (``code``, ``title``, ``parent``, optional ``cost_codes`` as
  ``CODE:PCT;CODE:PCT``) parents first, and plans a row invalid with a fixed reason when its parent
  is unknown, its depth is over 8 or its percentages do not sum to 100;
* ``awp.cwa`` creates areas and, with a ``sequence`` column, the version-1 path.
"""

from __future__ import annotations

from typing import Any


def wbs_target() -> Any:
    """The ``awp.wbs`` load target."""
    raise NotImplementedError("T02 writes the awp.wbs load target")


def cwa_target() -> Any:
    """The ``awp.cwa`` load target."""
    raise NotImplementedError("T02 writes the awp.cwa load target")
