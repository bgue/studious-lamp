"""Scenario and template loading from YAML into ``tl_sim.scenario`` models.

Scenarios live in ``<seed dir>/scenarios/<name>.yaml`` and seed templates in
``<seed dir>/templates/<name>.yaml``. The seed directory is ``TL_SEED_DIR`` when set, else
``dev/seed`` in the repository. ``load_scenario`` also takes a path to any YAML file. Every failure
is a ``ScenarioError`` whose message names the file, so a CLI can print it as it is.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from tl_sim.scenario import Scenario, Template

MAX_BYTES = 256 * 1024

_TEMPLATE_NAME = r"[a-z0-9][a-z0-9._-]*"


class ScenarioError(Exception):
    """A scenario or template file cannot be read or is invalid. The message names the file."""


def seed_dir() -> Path:
    """The directory holding ``scenarios/`` and ``templates/``: ``TL_SEED_DIR``, else dev/seed."""
    configured = os.environ.get("TL_SEED_DIR", "")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "dev" / "seed"


def bundled_scenarios() -> list[str]:
    """Names of the scenario files in ``seed_dir()/scenarios``, sorted, without ``.yaml``."""
    directory = seed_dir() / "scenarios"
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.yaml"))


def load_scenario(source: str | Path) -> Scenario:
    """A scenario from a YAML path, or from a bundled name such as ``north-unit-small``."""
    if isinstance(source, Path) or "/" in source or source.endswith((".yaml", ".yml")):
        path = Path(source)
    else:
        directory = seed_dir() / "scenarios"
        path = directory / f"{source}.yaml"
        if not path.is_file():
            bundled = ", ".join(bundled_scenarios()) or "none"
            raise ScenarioError(
                f"unknown scenario {source!r}: no file {path}; "
                f"searched {directory}; bundled scenarios: {bundled}"
            )
    return _validate(Scenario, _read_mapping(path), path)


def load_template(name: str) -> Template:
    """The seed template ``seed_dir()/templates/<name>.yaml``."""
    if re.fullmatch(_TEMPLATE_NAME, name) is None:
        raise ScenarioError(f"template name {name!r} must be lowercase letters, digits, . _ -")
    path = seed_dir() / "templates" / f"{name}.yaml"
    if not path.is_file():
        raise ScenarioError(f"template {name!r} not found: no file {path}")
    return _validate(Template, _read_mapping(path), path)


def _read_mapping(path: Path) -> dict[str, Any]:
    """The top-level mapping of a YAML file, read and parsed with the safe loader only."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ScenarioError(f"{path}: cannot read: {exc}") from exc
    if size > MAX_BYTES:
        raise ScenarioError(f"{path}: file is {size} bytes, more than the {MAX_BYTES} allowed")
    try:
        with path.open("rb") as handle:
            text = handle.read().decode("utf-8")
    except OSError as exc:
        raise ScenarioError(f"{path}: cannot read: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ScenarioError(f"{path}: not valid YAML: {exc}") from exc
    try:
        data: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ScenarioError(f"{path}: expected a mapping at the top level")
    return data  # pyright: ignore[reportUnknownVariableType]


def _validate[M: BaseModel](model: type[M], data: dict[str, Any], path: Path) -> M:
    """``data`` as a ``model``; a validation failure names the file and each dotted field."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '(top level)'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ScenarioError(f"{path}: {problems}") from exc
