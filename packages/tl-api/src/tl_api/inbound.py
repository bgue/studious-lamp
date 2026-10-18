"""``POST /in/{app}/{endpoint}``: the one route family that has no session (FANOUT D4; ADR-0017).

It is an ASGI middleware, outermost, so that nothing before it reads the request: the order of its
answers is the whole security design and no framework step can reorder it.

1. **Not accepting**: the kill switch is on, the app is disabled, the endpoint is unknown or
   disabled, the method is not POST or the path is not exactly ``/in/{app}/{endpoint}``. One fixed
   404 (``INBOUND_NOT_FOUND_BODY``), the same bytes and headers for every reason.
2. **Rate bound**, before the body is read: a source that has failed too often (the last entry of
   ``TL_TRUSTED_PROXY_HEADER``, IPv6 by /64, as ``tl_api.ratelimit``), the endpoint's
   ``rate_per_minute``, the process-wide ``INBOUND_GLOBAL_RATE_PER_MINUTE`` and a full queue
   (``INBOUND_MAX_PENDING_PER_ENDPOINT``) each answer 429 ``rate_limited`` with ``Retry-After``.
3. **Body cap**: ``Content-Length`` first, then while reading (chunked too), at the endpoint's
   ``max_body_bytes``. 413 ``payload_too_large``; the rest of the body is never read.
4. **Verification** (HMAC or JWT, constant time on bytes). Every failure, a replayed message id
   included, is the same 401 (``INBOUND_UNAUTHORIZED_BODY``). The reason is a fixed code in the
   server log and in a per-endpoint counter; never a header value, a claim or the body.
5. **Parse**: UTF-8 JSON of bounded depth; anything else is 422 ``invalid_payload``.
6. **Accept**: the body is stored as an object, then one transaction writes the replay row, the
   delivery row, the job ``inbound.map`` and ``Inbound.Received``. 202 with the delivery id.

A refused request (401, 422) counts against its source. Nothing here is a route of the FastAPI
app, so the route-guard walkers do not see it: ``tests/integration/test_api_inbound.py`` pins that
no FastAPI route sits under ``/in/`` and walks every step above.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable

from fastapi.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tl_core.files.types import ObjectStore
from tl_core.integration.contract import (
    INBOUND_GLOBAL_RATE_PER_MINUTE,
    INBOUND_NOT_FOUND_BODY,
    INBOUND_UNAUTHORIZED_BODY,
)
from tl_core.integration.inbound import gate, store
from tl_core.integration.inbound.limits import WindowCounter
from tl_core.integration.inbound.verify import VerifyError
from tl_core.util import new_ulid, utcnow

from tl_api.context import ApiContext
from tl_api.ratelimit import SourceLimiter, client_key

log = logging.getLogger(__name__)

PREFIX = "/in/"


def _not_found() -> Response:
    return Response(INBOUND_NOT_FOUND_BODY, status_code=404, media_type="application/json")


def _unauthorized() -> Response:
    return Response(INBOUND_UNAUTHORIZED_BODY, status_code=401, media_type="application/json")


def _limited(wait: float) -> Response:
    return JSONResponse(
        {"error": "rate_limited", "message": "too many requests"},
        status_code=429,
        headers={"Retry-After": str(max(1, math.ceil(wait)))},
    )


class _TooLarge(Exception):
    pass


class InboundMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        sources: SourceLimiter,
        trusted_header: str | None = None,
        endpoints: WindowCounter | None = None,
        process: WindowCounter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self._sources = sources
        self._trusted = trusted_header
        self._endpoints = endpoints or WindowCounter(clock=clock)
        self._process = process or WindowCounter(clock=clock)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(PREFIX):
            await self.app(scope, receive, send)
            return
        response = await self._handle(scope, receive)
        await response(scope, receive, send)

    # --- the steps --------------------------------------------------------------------------

    async def _handle(self, scope: Scope, receive: Receive) -> Response:
        ctx: ApiContext = scope["app"].state.ctx
        parts = scope["path"][len(PREFIX) :].split("/")
        if scope["method"] != "POST" or len(parts) != 2 or not all(parts):
            return _not_found()
        endpoint = await run_in_threadpool(self._lookup, ctx, parts[0], parts[1])
        if endpoint is None:
            return _not_found()
        source = client_key(scope, self._trusted)
        wait = self._sources.retry_after(source)
        if wait <= 0:
            wait = self._endpoints.hit(f"endpoint:{endpoint.endpoint_id}", endpoint.rate_per_minute)
        if wait <= 0:
            wait = self._process.hit("process", INBOUND_GLOBAL_RATE_PER_MINUTE)
        if wait <= 0 and await run_in_threadpool(self._full, ctx, endpoint.endpoint_id):
            wait = 30.0
        if wait > 0:
            return _limited(wait)
        try:
            body = await self._read(scope, receive, endpoint.max_body_bytes)
        except _TooLarge:
            return JSONResponse(
                {"error": "payload_too_large", "message": "the request body is too large"},
                status_code=413,
            )
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        try:
            message_id = await run_in_threadpool(self._verify, ctx, endpoint, headers, body)
        except VerifyError as exc:
            return await self._refuse(ctx, endpoint, source, exc.code, _unauthorized())
        try:
            gate.parse_payload(body)
        except gate.InvalidPayload:
            await self._count(ctx, endpoint, source, "invalid_payload")
            return JSONResponse(
                {"error": "invalid_payload", "message": "the body is not acceptable JSON"},
                status_code=422,
            )
        try:
            delivery_id = await run_in_threadpool(self._accept, ctx, endpoint, message_id, body)
        except gate.ReplayError:
            return await self._refuse(ctx, endpoint, source, "replay", _unauthorized())
        except Exception:
            log.exception("inbound %s: could not accept a delivery", endpoint.path)
            return JSONResponse(
                {"error": "internal_error", "message": "internal server error"}, status_code=500
            )
        return JSONResponse({"delivery_id": delivery_id, "state": "queued"}, status_code=202)

    @staticmethod
    async def _read(scope: Scope, receive: Receive, cap: int) -> bytes:
        for name, value in scope["headers"]:
            if name.lower() == b"content-length" and value.isdigit() and int(value) > cap:
                raise _TooLarge
        chunks: list[bytes] = []
        total = 0
        while True:
            message: Message = await receive()
            if message["type"] == "http.disconnect":
                raise _TooLarge  # nothing usable was sent
            total += len(message.get("body", b""))
            if total > cap:
                raise _TooLarge
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                return b"".join(chunks)

    # --- database work (run in a thread) ----------------------------------------------------

    @staticmethod
    def _lookup(ctx: ApiContext, app: str, name: str) -> gate.EndpointView | None:
        with ctx.backend(True) as uow:
            return gate.find_open_endpoint(uow.conn(), app, name)

    @staticmethod
    def _full(ctx: ApiContext, endpoint_id: str) -> bool:
        with ctx.backend(True) as uow:
            try:
                gate.check_pending(uow.conn(), endpoint_id)
            except gate.PendingFull:
                return True
        return False

    @staticmethod
    def _verify(
        ctx: ApiContext, endpoint: gate.EndpointView, headers: dict[str, str], body: bytes
    ) -> str:
        with ctx.backend(True) as uow:
            return gate.verify_request(uow.conn(), endpoint, headers, body, now=utcnow())

    @staticmethod
    def _accept(ctx: ApiContext, endpoint: gate.EndpointView, message_id: str, body: bytes) -> str:
        objects: ObjectStore | None = ctx.objects
        if objects is None:
            raise RuntimeError("no object store is configured for inbound payloads")
        delivery_id = new_ulid()
        key = store.body_key(endpoint.endpoint_id, delivery_id)
        digest = store.put_body(objects, key, body)
        with ctx.backend(False) as uow:
            gate.accept_delivery(
                uow,
                endpoint,
                message_id=message_id,
                delivery_id=delivery_id,
                object_key=key,
                payload_sha256=digest,
                payload_size=len(body),
                now=utcnow(),
            )
        return delivery_id

    @staticmethod
    def _write_count(ctx: ApiContext, endpoint_id: str, code: str) -> None:
        with ctx.backend(False) as uow:
            gate.count_failure(uow.conn(), endpoint_id, code, utcnow())

    async def _count(
        self, ctx: ApiContext, endpoint: gate.EndpointView, source: str, code: str
    ) -> None:
        self._sources.record_failure(source)
        log.info("inbound %s refused: %s", endpoint.path, code)
        try:
            await run_in_threadpool(self._write_count, ctx, endpoint.endpoint_id, code)
        except Exception:  # a counter must never decide the answer
            log.warning("inbound %s: could not count %s", endpoint.path, code)

    async def _refuse(
        self,
        ctx: ApiContext,
        endpoint: gate.EndpointView,
        source: str,
        code: str,
        response: Response,
    ) -> Response:
        await self._count(ctx, endpoint, source, code)
        return response


__all__ = ["PREFIX", "InboundMiddleware"]
