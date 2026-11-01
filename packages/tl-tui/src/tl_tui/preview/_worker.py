"""Alias of ``tl_api.preview._worker`` (P2-WEB1-S3): the module object is the moved one."""

import sys

from tl_api.preview import _worker as _moved
from tl_api.preview._worker import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]
from tl_api.preview._worker import _limit_resources as _limit_resources  # noqa: PLC0414

sys.modules[__name__] = _moved
