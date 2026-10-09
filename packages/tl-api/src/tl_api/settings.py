"""Process settings for the API server, read from the environment and the command line."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = "./dev/data/tl.db"
DEFAULT_TOKENS = "./dev/data/tokens.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
#: Largest body ``PUT /uploads/{id}/content`` accepts (the unslotted attachment limit, 5 GiB).
DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024**3


@dataclass(frozen=True)
class ApiSettings:
    """What ``create_app`` and the server entry point need to know."""

    db_path: Path = Path(DEFAULT_DB)
    tokens_path: Path = Path(DEFAULT_TOKENS)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    #: Allow a non-loopback bind (ADR-0005). Every request then logs a warning.
    insecure_dev: bool = False
    poll_interval_s: float = 0.25  # how often the feed looks for events written by other processes
    sse_keepalive_s: float = 15.0  # idle seconds before an SSE comment line is sent
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @staticmethod
    def from_env(env: Mapping[str, str] | None = None) -> ApiSettings:
        """``TL_DB``, ``TL_TOKENS``, ``TL_API_HOST`` and ``TL_API_PORT`` override the defaults."""
        source = os.environ if env is None else env
        return ApiSettings(
            db_path=Path(source.get("TL_DB", DEFAULT_DB)),
            tokens_path=Path(source.get("TL_TOKENS", DEFAULT_TOKENS)),
            host=source.get("TL_API_HOST", DEFAULT_HOST),
            port=int(source.get("TL_API_PORT", str(DEFAULT_PORT))),
        )


def is_loopback(host: str) -> bool:
    """True for ``localhost`` and loopback IP literals. Any other name may resolve anywhere."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_bind(host: str, *, insecure_dev: bool) -> None:
    """Refuse a non-loopback bind unless ``insecure_dev`` (ADR-0005). Raises ``ValueError``."""
    if not is_loopback(host) and not insecure_dev:
        raise ValueError(
            f"refusing to bind {host!r}: the Phase 0 API has no real authentication. "
            "Bind 127.0.0.1, or pass --insecure-dev to accept the risk."
        )
