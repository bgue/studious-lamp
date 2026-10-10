"""Transport, authentication and error mapping shared by every group of client methods (S5).

``ApiClientBase`` owns one ``httpx2.Client``. Pass your own (``http=``) to share a connection pool
or, in tests, a Starlette ``TestClient`` (an httpx2 client that talks to an app in process).
Every response with status 400 or above is turned back into the exception an embedded call would
have raised (``tl_api.errors.exception_for``): ``RecordNotFoundError``, ``ConcurrencyError``,
``GuardFailedError`` with its ``results``, ``QuerySyntaxError`` with its ``position`` and so on;
a body the table has no class for becomes ``ApiError``. Network failures are not wrapped:
``httpx2.TransportError`` (connection refused, timeout) propagates, so a screen can tell "the server
is unreachable" from "the server refused".
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Mapping
from types import TracebackType
from typing import Any, TypeVar

import httpx2
from pydantic import BaseModel, TypeAdapter
from tl_core.services.commands import Command, CommandResult

from tl_api.errors import ApiError, exception_for

M = TypeVar("M", bound=BaseModel)

DEFAULT_TIMEOUT_S = 30.0


def quote(segment: str) -> str:
    """A path segment with everything escaped, so an id can never add or remove path parts."""
    return urllib.parse.quote(segment, safe="")


def clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop ``None`` values so an unset option is not sent as the text ``None``."""
    return {k: v for k, v in (params or {}).items() if v is not None}


class ApiClientBase:
    """Holds the connection; the method groups (records, links, files, events) build on it."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        http: httpx2.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_http = http is None
        self._http: httpx2.Client = (
            http if http is not None else httpx2.Client(base_url=self.base_url, timeout=timeout)
        )
        self._auth = {"Authorization": f"Bearer {token}"}

    # --- lifecycle -----------------------------------------------------------------------

    def close(self) -> None:
        """Close the connection pool this client created (a client passed in stays open)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> ApiClientBase:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- requests ------------------------------------------------------------------------

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        content: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        """One request. Raises the mapped exception for status 400 and above."""
        response = self._http.request(
            method,
            path,
            params=clean_params(params) or None,
            json=json,
            content=content,
            headers={**self._auth, **(headers or {})},
        )
        if response.status_code >= 400:
            raise self.error_from(response)
        return response

    @staticmethod
    def error_from(response: httpx2.Response) -> Exception:
        """The exception for an error response (also used by the streaming calls)."""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and "error" in body:
            return exception_for(response.status_code, body)  # pyright: ignore[reportUnknownArgumentType]
        text = response.text[:200] if response.content else ""
        return ApiError(
            response.status_code, "http_error", text or f"HTTP {response.status_code}", {}
        )

    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._send("GET", path, params=params).json()

    def _post_json(self, path: str, body: Any, params: Mapping[str, Any] | None = None) -> Any:
        return self._send("POST", path, json=body, params=params).json()

    # --- decoding ------------------------------------------------------------------------

    @staticmethod
    def _model(model: type[M], data: Any) -> M:
        return model.model_validate(data)

    @staticmethod
    def _models(model: type[M], data: Any) -> list[M]:
        adapter: TypeAdapter[list[M]] = TypeAdapter(list[model])  # pyright: ignore[reportInvalidTypeForm]
        return adapter.validate_python(data)

    # --- commands ------------------------------------------------------------------------

    def _command(self, name: str, command: Command) -> CommandResult:
        """``POST /commands/<name>`` with the command minus ``actor`` (the token's actor is used).

        ``source`` is sent as given, so a remote TUI keeps writing ``source="tui"``.
        """
        body = command.model_dump(mode="json", exclude={"actor"})
        return CommandResult.model_validate(self._post_json(f"/commands/{name}", body))
