"""Fine access words as data (specs/wave0.md section 2; plan check F1).

A module names its commands' access with a fine word (``awp.cwp.release``); the role table knows
three words (``read``, ``user``, ``controller``). ``schema/settings/access-words.yaml`` maps every
fine word to the table word it needs::

    version: 1
    words: {awp.view: read, awp.cwp.edit: user, awp.cwp.release: controller, ...}

The file is read whole and checked whole: an unknown table word, a repeated word, a word that is
not dotted lower-case or a file of another shape is an :class:`AccessWordError`, so a bad table
stops start-up rather than letting a command through (fail closed).
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import yaml
from tl_schema.resources import schema_root

#: The words of the role table, weakest first.
TABLE_WORDS = ("read", "user", "controller")
DEFAULT_ACCESS_WORDS_FILE = schema_root() / "settings" / "access-words.yaml"
_VERSION = 1
_FINE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")


class AccessWordError(Exception):
    """The access-word table is not acceptable, or a word is not in it."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping key written twice (PyYAML keeps the last one)."""


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key: Any = loader.construct_object(key_node, deep=deep)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        try:
            repeated = key in seen
        except TypeError:
            raise AccessWordError("an access-word key is not text") from None
        if repeated:
            raise AccessWordError(f"the access word {key!r} is listed twice")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)  # pyright: ignore[reportUnknownMemberType]


def parse_access_words(text: str, *, source: str = "<string>") -> Mapping[str, str]:
    """The table in a YAML document, checked; raises :class:`AccessWordError`."""
    try:
        document: Any = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506  (safe subclass)
    except AccessWordError as exc:
        raise AccessWordError(f"{source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise AccessWordError(f"{source}: invalid YAML") from exc
    if not isinstance(document, dict):
        raise AccessWordError(f"{source}: expected a mapping with `version` and `words`")
    shape = cast("dict[Any, Any]", document)
    if shape.get("version") != _VERSION or isinstance(shape.get("version"), bool):
        raise AccessWordError(f"{source}: version must be {_VERSION}")
    unknown_top = sorted(str(k) for k in shape if k not in ("version", "words"))
    if unknown_top:
        raise AccessWordError(f"{source}: unknown top-level keys {unknown_top}")
    listed = shape.get("words")
    if not isinstance(listed, dict) or not listed:
        raise AccessWordError(f"{source}: `words` must be a non-empty mapping")
    words: dict[str, str] = {}
    for word, table in cast("dict[Any, Any]", listed).items():
        if not isinstance(word, str) or _FINE.fullmatch(word) is None:
            raise AccessWordError(f"{source}: {word!r} is not a dotted lower-case access word")
        if word in TABLE_WORDS:
            raise AccessWordError(f"{source}: {word!r} is a table word, not a fine word")
        if not isinstance(table, str) or table not in TABLE_WORDS:
            raise AccessWordError(
                f"{source}: {word!r} maps to {table!r}, which is not one of {list(TABLE_WORDS)}"
            )
        words[word] = table
    return MappingProxyType(words)


def load_access_words(path: Path | None = None) -> Mapping[str, str]:
    """Fine word -> table word, from ``path`` (default ``schema/settings/access-words.yaml``).

    Raises :class:`AccessWordError` when the file is unreadable or breaks a rule of the table.
    """
    target = DEFAULT_ACCESS_WORDS_FILE if path is None else path
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise AccessWordError(f"{target.name}: cannot read the file: {exc.strerror}") from exc
    return parse_access_words(text, source=target.name)


_lock = threading.Lock()
_default: Mapping[str, str] | None = None


def table_word(word: str) -> str:
    """The table word a fine ``word`` needs; a table word returns itself.

    Raises :class:`AccessWordError` for a word that is neither (fail closed). The default file is
    read once per process; a failure is raised again on the next call, never cached as empty.
    """
    global _default
    if word in TABLE_WORDS:
        return word
    with _lock:
        if _default is None:
            _default = load_access_words()
        words = _default
    found = words.get(word)
    if found is None:
        raise AccessWordError(f"there is no access word {word!r}")
    return found
