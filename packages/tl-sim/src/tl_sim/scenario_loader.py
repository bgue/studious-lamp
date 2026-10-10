"""Scenario and template loading from YAML into ``tl_sim.scenario`` models.

Scenarios live in ``<seed dir>/scenarios/<name>.yaml`` and seed templates in
``<seed dir>/templates/<name>.yaml``. The seed directory is ``TL_SEED_DIR`` when set, else
``dev/seed`` in the repository. ``load_scenario`` also takes a path to any YAML file. Every failure
is a ``ScenarioError`` whose message names the file, so a CLI can print it as it is.
"""

from __future__ import annotations

from pathlib import Path

from tl_sim.scenario import Scenario, Template

MAX_BYTES = 256 * 1024


class ScenarioError(Exception):
    """A scenario or template file cannot be read or is invalid. The message names the file."""


def seed_dir() -> Path:
    """The directory holding ``scenarios/`` and ``templates/``: ``TL_SEED_DIR``, else dev/seed."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def bundled_scenarios() -> list[str]:
    """Names of the scenario files in ``seed_dir()/scenarios``, sorted, without ``.yaml``."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def load_scenario(source: str | Path) -> Scenario:
    """A scenario from a YAML path, or from a bundled name such as ``north-unit-small``."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def load_template(name: str) -> Template:
    """The seed template ``seed_dir()/templates/<name>.yaml``."""
    raise NotImplementedError("STUB (P0-I6-T43)")
