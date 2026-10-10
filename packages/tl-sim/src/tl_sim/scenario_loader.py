"""Scenario and template loading from YAML into ``tl_sim.scenario`` models.

Scenarios live in ``<seed dir>/scenarios/<name>.yaml`` and seed templates in
``<seed dir>/templates/<name>.yaml``. The seed directory is ``TL_SEED_DIR`` when set, else
``dev/seed`` in the repository. ``load_scenario`` also takes a path to any YAML file (the CLI).
``load_bundled_scenario`` takes a bundled name only and is what the MCP server uses: a name that
matches ``BUNDLED_NAME`` is resolved inside ``seed_dir()/scenarios`` and refused when the real path
(symlinks followed) is anywhere else.

Every failure is a ``ScenarioError``. ``str(error)`` names the file, so a CLI can print it as it
is; ``error.public`` never holds a path, a file's content or a parser snippet, so a remote caller
(MCP) can be shown it.
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
BUNDLED_NAME = r"[a-z0-9._-]{1,64}"


class ScenarioError(Exception):
    """A scenario or template file cannot be read or is invalid. The message names the file.

    ``public`` is the same problem without any path, file content or parser text.
    """

    def __init__(self, message: str, public: str | None = None) -> None:
        super().__init__(message)
        self.public = public if public is not None else message


def seed_dir() -> Path:
    """The directory holding ``scenarios/`` and ``templates/``: ``TL_SEED_DIR``, else dev/seed."""
    configured = os.environ.get("TL_SEED_DIR", "")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "dev" / "seed"


def bundled_scenarios() -> list[str]:
    """Names of the scenario files in ``seed_dir()/scenarios``, sorted, without ``.yaml``.

    A symlink that leads out of the directory is not a bundled scenario and is not listed.
    """
    directory = seed_dir() / "scenarios"
    if not directory.is_dir():
        return []
    root = directory.resolve()
    return sorted(p.stem for p in directory.glob("*.yaml") if p.resolve().is_relative_to(root))


def load_scenario(source: str | Path) -> Scenario:
    """A scenario from a YAML path, or from a bundled name such as ``north-unit-small``."""
    label: str | None = None
    if isinstance(source, Path) or "/" in source or source.endswith((".yaml", ".yml")):
        path = Path(source)
    else:
        label = f"scenario {source!r}"
        directory = seed_dir() / "scenarios"
        path = directory / f"{source}.yaml"
        if not path.is_file():
            bundled = ", ".join(bundled_scenarios()) or "none"
            raise ScenarioError(
                f"unknown scenario {source!r}: no file {path}; "
                f"searched {directory}; bundled scenarios: {bundled}",
                f"unknown scenario {source!r}; bundled scenarios: {bundled}",
            )
    return _validate(Scenario, _read_mapping(path, label), path)


def load_bundled_scenario(name: str) -> Scenario:
    """The bundled scenario ``name`` and nothing else: never a path (the MCP door).

    ``name`` must match ``BUNDLED_NAME``. The file is ``seed_dir()/scenarios/<name>.yaml``, and its
    real path must lie inside that directory, so a symlink cannot lead out of it. Every refusal
    says only that the scenario is unknown, and lists the bundled names.
    """
    bundled = ", ".join(bundled_scenarios()) or "none"
    unknown = ScenarioError(
        f"unknown scenario {name!r}: not a bundled scenario",
        f"unknown scenario; bundled scenarios: {bundled}",
    )
    if re.fullmatch(BUNDLED_NAME, name) is None:
        raise unknown
    directory = (seed_dir() / "scenarios").resolve()
    path = (directory / f"{name}.yaml").resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise unknown
    return _validate(Scenario, _read_mapping(path, f"scenario {name!r}"), path)


def load_template(name: str) -> Template:
    """The seed template ``seed_dir()/templates/<name>.yaml``."""
    if re.fullmatch(_TEMPLATE_NAME, name) is None:
        raise ScenarioError(
            f"template name {name!r} must be lowercase letters, digits, . _ -",
            "template name must be lowercase letters, digits, . _ -",
        )
    directory = (seed_dir() / "templates").resolve()
    path = (directory / f"{name}.yaml").resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ScenarioError(
            f"template {name!r} not found: no file {directory / f'{name}.yaml'}",
            f"template {name!r} not found",
        )
    return _validate(Template, _read_mapping(path, f"template {name!r}"), path)


def _read_mapping(path: Path, label: str | None = None) -> dict[str, Any]:
    """The top-level mapping of a YAML file, read and parsed with the safe loader only.

    ``label`` is how the file is named in ``ScenarioError.public`` (never the path).
    """
    what = label or "the file"
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ScenarioError(f"{path}: cannot read: {exc}", f"{what}: cannot be read") from exc
    if size > MAX_BYTES:
        raise ScenarioError(
            f"{path}: file is {size} bytes, more than the {MAX_BYTES} allowed",
            f"{what}: file is larger than the {MAX_BYTES} bytes allowed",
        )
    try:
        with path.open("rb") as handle:
            text = handle.read().decode("utf-8")
    except OSError as exc:
        raise ScenarioError(f"{path}: cannot read: {exc}", f"{what}: cannot be read") from exc
    except UnicodeDecodeError as exc:
        raise ScenarioError(f"{path}: not valid YAML: {exc}", f"{what}: not valid YAML") from exc
    try:
        data: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path}: not valid YAML: {exc}", f"{what}: not valid YAML") from exc
    if not isinstance(data, dict):
        raise ScenarioError(
            f"{path}: expected a mapping at the top level",
            f"{what}: expected a mapping at the top level",
        )
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
        raise ScenarioError(f"{path}: {problems}", f"invalid scenario: {problems}") from exc
