"""Where services get the relation vocabulary (brief 7.1).

The vocabulary is extensible, but company and module relations are not declared anywhere yet, so
the default is the built-in thirteen. Tests and embedders install their own with ``use_vocabulary``.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from tl_core.links.vocabulary import RelationVocabulary, default_vocabulary

_vocabulary: RelationVocabulary | None = None


def get_vocabulary() -> RelationVocabulary:
    """The installed vocabulary, else a fresh built-in one."""
    return _vocabulary if _vocabulary is not None else default_vocabulary()


@contextmanager
def use_vocabulary(vocabulary: RelationVocabulary) -> Generator[None]:
    global _vocabulary
    previous, _vocabulary = _vocabulary, vocabulary
    try:
        yield
    finally:
        _vocabulary = previous
