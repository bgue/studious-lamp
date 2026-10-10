"""Plans and writes scaffold files.

:class:`Plan` is the whole output of a scaffolder, in memory. :func:`write_plan` checks every path
first and writes nothing if any file exists or any path would leave the root, so a refused run
leaves the tree as it was. A scaffolder never overwrites.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path, PurePosixPath


class ScaffoldError(Exception):
    """A scaffold run was refused; the message says why."""


@dataclass(frozen=True)
class PlannedFile:
    path: str  # posix, relative to the repository root
    content: str


@dataclass
class Plan:
    """Files to create, in order, and one line each of what to do next."""

    files: list[PlannedFile] = field(default_factory=list[PlannedFile])
    next_steps: list[str] = field(default_factory=list[str])

    def add(self, path: str, content: str) -> None:
        if any(existing.path == path for existing in self.files):
            raise ScaffoldError(f"the plan lists {path} twice")
        self.files.append(PlannedFile(path, content))


def render(template: str, **values: str) -> str:
    """The template ``templates/<template>`` with ``${name}`` filled in.

    A missing value raises ``KeyError`` and a stray ``$`` raises ``ValueError``, so a template and
    its caller cannot drift apart silently.
    """
    resource = files("tl_cli.scaffold").joinpath("templates", *template.split("/"))
    return string.Template(resource.read_text(encoding="utf-8")).substitute(values)


def find_root(start: Path | None = None) -> Path:
    """The repository root: the nearest parent with ``AGENTS.md``, ``justfile``, ``packages/``."""
    here = (start if start is not None else Path.cwd()).resolve()
    for parent in (here, *here.parents):
        if (
            (parent / "AGENTS.md").is_file()
            and (parent / "justfile").is_file()
            and (parent / "packages").is_dir()
        ):
            return parent
    raise ScaffoldError("not inside the repository: pass --root PATH")


def use_root(explicit: Path | None) -> Path:
    """``--root`` as given (it must be a directory), else the repository around the current one."""
    if explicit is None:
        return find_root()
    if not explicit.is_dir():
        raise ScaffoldError(f"--root {explicit}: not a directory")
    return explicit.resolve()


def _target(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ScaffoldError(f"refused path {relative!r}")
    target = (root / relative).resolve()
    if root.resolve() not in target.parents:
        raise ScaffoldError(f"refused path {relative!r}: it leaves the repository")
    return target


def check_plan(root: Path, plan: Plan) -> None:
    """Raise :class:`ScaffoldError` if any file exists or any path is unsafe."""
    existing = [item.path for item in plan.files if _target(root, item.path).exists()]
    if existing:
        raise ScaffoldError(
            "refusing to overwrite: "
            + ", ".join(existing[:5])
            + (" ..." if len(existing) > 5 else "")
        )


def write_plan(root: Path, plan: Plan) -> list[str]:
    """Write every file of ``plan`` below ``root``; return the relative paths written.

    All paths are checked before the first write.
    """
    check_plan(root, plan)
    written: list[str] = []
    for item in plan.files:
        target = _target(root, item.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = item.content if item.content.endswith("\n") else item.content + "\n"
        target.write_text(text, encoding="utf-8")
        written.append(item.path)
    return written


def require_module(root: Path, distribution_dir: str, module: str) -> None:
    """Raise unless the module package exists (record types and projectors live inside one)."""
    if not (root / distribution_dir / "pyproject.toml").is_file():
        raise ScaffoldError(f"module {module!r} does not exist: run `tl new module {module}` first")
