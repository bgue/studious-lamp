"""Transport, authentication and error mapping shared by every group of client methods (S5).

``ApiClientBase`` owns one ``httpx2.Client``. Pass your own (``http=``) to share a connection pool
or, in tests, a Starlette ``TestClient`` (an httpx2 client that talks to an app in process).

Errors. Every response with status 400 or above is turned back into the exception an embedded call
would have raised (``tl_api.errors.exception_for``): ``RecordNotFoundError``, ``ConcurrencyError``,
``GuardFailedError`` with its ``results``, ``QuerySyntaxError`` with its ``position`` and so on; a
body the table has no class for becomes ``ApiError``.

Network failures. A failure to reach the server (connection refused or reset, timeout, protocol
error) in a plain request becomes ``ApiUnavailableError`` (status 0, original exception as
``__cause__``), so a screen can tell "the server is unreachable" from "the server refused". It is
also an ``httpx2.TransportError``, so code that catches the transport error keeps working. The
streaming calls (``stream_events``, ``download_to``) use the connection pool directly and raise the
raw ``httpx2.TransportError``.

Retries. A GET that fails because a reused connection was reset (``ReadError``, ``WriteError``,
``CloseError``, ``RemoteProtocolError``) is sent once more on a fresh connection; a GET timeout is
not. A ``POST /commands/<name>`` (P2-X1-T02) gets an idempotency key (the caller's, or a fresh one)
and is sent a second time with that same key when it fails with a reset or a timeout; server replay
makes that safe. A refused connection, an error answer and every other POST are never retried,
because the POST may have been applied.
"""

from __future__ import annotations

import urllib.parse
import uuid
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
    """A path segment with everything escaped, so an id can never add or remove path parts.

    ``.`` and ``..`` are refused with ``ValueError``: they are not ids, and servers and proxies
    resolve them as path steps even when they are the whole segment.
    """
    if segment in (".", ".."):
        raise ValueError(f"{segment!r} cannot be used as an id in a request path")
    return urllib.parse.quote(segment, safe="")


def clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop ``None`` values so an unset option is not sent as the text ``None``."""
    return {k: v for k, v in (params or {}).items() if v is not None}


class ApiUnavailableError(ApiError, httpx2.TransportError):
    """The server could not be reached or did not answer (status 0). See ``__cause__``."""

    def __init__(self, cause: httpx2.TransportError) -> None:
        message = f"cannot reach the server: {cause.__class__.__name__}: {cause}"
        ApiError.__init__(self, 0, "unreachable", message, {})  # also runs TransportError's


#: Failures that mean "the pooled connection died", the only case a GET is sent again.
_RESET = (httpx2.ReadError, httpx2.WriteError, httpx2.CloseError, httpx2.RemoteProtocolError)


def _keyed(method: str, path: str, json: Any) -> bool:
    """A command POST: it carries an idempotency key and is sent twice on a reset or a timeout."""
    return method.upper() == "POST" and path.startswith("/commands/") and isinstance(json, dict)


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
        keyed = _keyed(method, path, json)
        if keyed and json.get("idempotency_key") is None:
            # One key per call, made before the first attempt, so the retry carries the same one.
            json = {**json, "idempotency_key": uuid.uuid4().hex}
        attempts = 2 if method.upper() == "GET" or keyed else 1
        response = self._attempt(attempts, method, path, params, json, content, headers)
        if response.status_code >= 400:
            raise self.error_from(response)
        return response

    def _attempt(
        self,
        attempts: int,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        json: Any,
        content: Any,
        headers: Mapping[str, str] | None,
    ) -> httpx2.Response:
        """Send the request; a reset connection is tried again while ``attempts`` remain.

        A timeout is tried again only for a keyed command POST (its key makes the second send safe).
        """
        keyed = _keyed(method, path, json)
        last: httpx2.TransportError | None = None
        for _ in range(attempts):
            try:
                return self._http.request(
                    method,
                    path,
                    params=clean_params(params) or None,
                    json=json,
                    content=content,
                    headers={**self._auth, **(headers or {})},
                )
            except _RESET as exc:
                last = exc  # a pooled connection died: try once more on a fresh one
            except httpx2.TimeoutException as exc:
                if not keyed:
                    raise ApiUnavailableError(exc) from exc
                last = exc  # a keyed command: the same key makes the second send safe
            except httpx2.TransportError as exc:
                raise ApiUnavailableError(exc) from exc
        assert last is not None
        raise ApiUnavailableError(last) from last

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
