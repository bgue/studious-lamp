"""``send_test_webhook``: one signed catalog sample sent to a loopback receiver (brief 25.3, 18.4;
FANOUT D12). It writes nothing to the ledger and needs no subscription."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from tl_core.util import new_ulid
from tl_core.webhooks.base import iso_z, utc_now
from tl_core.webhooks.egress import ResolvedTarget
from tl_core.webhooks.signing import SigningSecret, generate_secret, sign_headers
from tl_core.webhooks.transport import HttpxTransport
from tl_schema import catalog

from tl_mcp.dev.guard import check_loopback_url, redact_url
from tl_mcp.dev.runtime import DevContext, guarded

SEND_ONLY = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
EXCERPT_MAX_CHARS = 512
SHOWN_EVENT_TYPES = 5


class WebhookTestOutput(BaseModel):
    """The answer of ``send_test_webhook``."""

    ok: bool  # the receiver answered 2xx
    status: int | None  # the HTTP status; None when no response arrived
    latency_ms: int
    error: str | None  # the transport's reason when no response arrived
    excerpt: str  # the receiver's answer, at most 512 characters
    event_id: str
    event_type: str
    target: str  # "<ip>:<port>" ("[<ipv6>]:<port>"), the address the request was sent to
    secret: str | None  # set only when the tool generated the secret; a given one is never echoed
    header: str = "webhook-test: 1"


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=SEND_ONLY)
    def send_test_webhook(
        url: Annotated[
            str,
            Field(
                min_length=1,
                max_length=2048,
                description=(
                    "An http(s) URL on this machine: localhost or a 127.x.x.x or ::1 address."
                ),
            ),
        ],
        event_type: Annotated[
            str,
            Field(
                min_length=1,
                max_length=80,
                description="A catalog event type, for example Record.Created.",
            ),
        ] = "Record.Created",
        secret: Annotated[
            str | None,
            Field(
                max_length=200,
                description="The receiver's whsec_ secret. Omit it to get a fresh one back.",
            ),
        ] = None,
        timeout_s: Annotated[
            int, Field(ge=1, le=10, description="Seconds to wait for the receiver.")
        ] = 5,
    ) -> WebhookTestOutput:
        """Send one signed sample event to a receiver on this machine and report the answer.

        Only localhost or a literal loopback address is accepted (no DNS names, no other hosts, no
        redirects followed, proxy variables ignored). The request carries `webhook-test: 1`, so a
        receiver can tell it from a real delivery. Nothing is written to the ledger. Without a
        `secret` a fresh one is generated and returned in `secret` so the receiver can be set up
        with it; a secret you pass is never echoed back.
        """
        with guarded(ctx, "send_test_webhook", {"url": redact_url(url), "event_type": event_type}):
            target = check_loopback_url(url)
            known = catalog.event_types()
            if event_type not in known:
                raise ValueError(
                    f"unknown event type {event_type!r}; the first valid types are "
                    f"{', '.join(known[:SHOWN_EVENT_TYPES])}"
                )
            generated: str | None = None
            if secret is None:
                generated = generate_secret()
                signing = SigningSecret(generated)
            else:
                signing = SigningSecret(secret)

            started = utc_now()
            event_id = new_ulid()
            envelope: dict[str, Any] = dict(catalog.sample(event_type)["envelope"])
            envelope["id"] = event_id
            envelope["time"] = iso_z(started)
            body = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            headers = {
                **sign_headers(event_id, int(started.timestamp()), body, [signing]),
                "Content-Type": "application/json",
                "webhook-test": "1",
            }
            # check_loopback_url only admits http and https; the narrowing is for the type checker.
            scheme: Literal["http", "https"] = "https" if target.scheme == "https" else "http"
            resolved = ResolvedTarget(
                scheme=scheme,
                host=target.ip,
                port=target.port,
                ip=target.ip,
                path_and_query=target.path_and_query,
            )
            result = HttpxTransport().send(
                resolved, headers, body.encode("utf-8"), timeout_s=float(timeout_s)
            )
            return WebhookTestOutput(
                ok=result.ok,
                status=result.status,
                latency_ms=result.latency_ms,
                error=result.error,
                excerpt=result.excerpt[:EXCERPT_MAX_CHARS],
                event_id=event_id,
                event_type=event_type,
                target=f"[{target.ip}]:{target.port}"
                if ":" in target.ip
                else f"{target.ip}:{target.port}",
                secret=generated,
            )
