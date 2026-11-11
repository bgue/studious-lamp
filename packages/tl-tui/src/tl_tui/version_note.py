"""The version line of the sign-in screen: a server whose ``major.minor`` differs from this app's.

``version_pair_note`` is the whole rule. The sign-in screen only displays what it returns. A
version that does not start with ``major.minor`` numbers (``dev``, ``unknown``) cannot be compared,
so it gives no line: the note never claims a mismatch it cannot see.
"""

from __future__ import annotations

import importlib.metadata
import re

_MAJOR_MINOR = re.compile(r"([0-9]+)\.([0-9]+)(?:\.|$)")


def _major_minor(version: str) -> tuple[int, int] | None:
    match = _MAJOR_MINOR.match(version)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def version_pair_note(server: str | None, app: str) -> str | None:
    """The sign-in line when the server's ``major.minor`` differs from the app's, else ``None``.

    ``None`` when the server is unknown, when either version has no numeric ``major.minor``, or
    when they agree (a patch difference is not a mismatch).
    """
    if server is None:
        return None
    theirs, ours = _major_minor(server), _major_minor(app)
    if theirs is None or ours is None or theirs == ours:
        return None
    return (
        f"server is {theirs[0]}.{theirs[1]}.x, this app is {ours[0]}.{ours[1]}.x: "
        "not a supported pair"
    )


def app_version() -> str:
    """This app's version from its package metadata (``unknown`` when it is not installed)."""
    try:
        return importlib.metadata.version("tl-tui")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
