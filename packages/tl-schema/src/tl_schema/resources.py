"""One locator for the repository's ``schema/`` data, in a checkout and in an installed wheel."""

from importlib.resources import files
from pathlib import Path

_MARKER = Path("core") / "core.yaml"


def _repo_schema() -> Path | None:
    """``<repo>/schema`` when it sits next to the source tree (checkout, editable install)."""
    candidate = Path(__file__).resolve().parents[4] / "schema"
    return candidate if (candidate / _MARKER).is_file() else None


def schema_root() -> Path:
    """The ``schema`` directory: the repository's if present, else the wheel's packaged copy."""
    repo = _repo_schema()
    if repo is not None:
        return repo
    return Path(str(files("tl_schema") / "_data" / "schema"))
