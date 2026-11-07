"""Alias of ``tl_api.preview.cache`` (P2-WEB1-S3): the module object is the moved one."""

import sys

from tl_api.preview import cache as _moved
from tl_api.preview.cache import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]

sys.modules[__name__] = _moved
