"""The ``webhook`` action executor: one signed POST, the answer is the result (FANOUT D8).

An action of this kind sends the canonical request (what ``ActionRequest`` holds, never a secret)
to the URL of its config and takes the receiver's answer as the result. Synchronous only: async
result callbacks are not built (§18.7 follow-up).

**Egress.** Every attempt goes through ``tl_core.webhooks.egress.EgressPolicy`` *before* any
connection: ``https`` only unless the host is allow-listed (``webhooks.egress.allowlist``); private,
loopback, link-local (169.254.169.254 among them), carrier-grade NAT, multicast, reserved and
IPv4-mapped addresses refused; the host resolved **once** and the connection pinned to that
address; credentials and fragments refused. A refusal is ``egress_denied`` and is not retried.

**Signing.** The body is signed with the Standard Webhooks headers using the action's live secrets
(``int_secret``, newest first; two during a rotation). The secret is read here, inside the attempt,
through the injected ``SecretSource``; it is not in ``ActionRequest``, the outcome, a message or a
log. The ``webhook-id`` is the invocation id, so a retry is recognisable as one.

**Answer.** 2xx completed; the body, when it is JSON, is the stored result (an object as it is, any
other JSON value under ``value``), else the text under ``text``; an answer past
``ACTION_MAX_RESULT_BYTES`` fails (it is never cut). 3xx is a failure (redirects are not followed).
408, 425, 429 and 5xx and a network error are retryable; any other 4xx is not. No message carries
the receiver's address, its error text or a header value.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from tl_core.integration.contract import (
    ACTION_MAX_RESULT_BYTES,
    ActionOutcome,
    ActionRequest,
    ExecutorKind,
    Problem,
    WebhookExecutorConfig,
)
from tl_core.webhooks.egress import EgressDenied, EgressPolicy, ResolutionFailed
from tl_core.webhooks.signing import SigningSecret, sign_headers
from tl_core.webhooks.transport import Transport

#: Live signing secrets of the action that owns ``secret_id``, newest first (empty: none).
SecretSource = Callable[[str], list[SigningSecret]]
RETRYABLE_STATUSES = frozenset({408, 425, 429})
JSON_TYPE = "application/json"


def failed(
    code: str, message: str, *, retryable: bool = False, status: int | None = None
) -> ActionOutcome:
    return ActionOutcome(
        status="failed",
        http_status=status,
        retryable=retryable,
        problems=[Problem(code=code, message=message)],
    )


def canonical_body(request: ActionRequest) -> str:
    """The text that is signed and sent: the request without its config, as sorted compact JSON."""
    body: dict[str, Any] = {
        "invocation_id": request.invocation_id,
        "action": request.action,
        "action_version": request.action_version,
        "scope": request.scope,
        "targets": [ref.model_dump(mode="json") for ref in request.targets],
        "parameters": request.parameters,
        "invoked_by": request.invoked_by,
        "attempt": request.attempt,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def result_of(text: str) -> dict[str, Any]:
    """The stored result of an answer: its JSON object, another JSON value as ``value``, else the
    text as ``text``. Never raises."""
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return {"text": text}
    if isinstance(parsed, dict):
        return parsed  # pyright: ignore[reportUnknownVariableType]
    return {"value": parsed}


class WebhookExecutor:
    kind: ExecutorKind = "webhook"

    def __init__(
        self,
        *,
        policy: EgressPolicy,
        transport: Transport,
        secrets: SecretSource,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._policy = policy
        self._transport = transport
        self._secrets = secrets
        self._clock = clock

    def execute(self, request: ActionRequest) -> ActionOutcome:
        config = request.config
        if not isinstance(config, WebhookExecutorConfig):
            return failed("wrong_executor", "This is not a webhook action.")
        if config.secret_id is None:
            return failed("no_secret", "The action has no signing secret.")
        try:
            secrets = self._secrets(config.secret_id)
        except Exception:
            return failed(
                "secret_unavailable", "The signing secret could not be read.", retryable=True
            )
        if not secrets:
            return failed("no_secret", "The action has no live signing secret.")
        try:
            target = self._policy.check(config.url)
        except EgressDenied:
            return failed("egress_denied", "The receiver's address is not allowed.")
        except ResolutionFailed:
            return failed(
                "unresolvable", "The receiver's name could not be resolved.", retryable=True
            )
        body = canonical_body(request)
        headers = {
            "Content-Type": JSON_TYPE,
            **sign_headers(request.invocation_id, int(self._clock()), body, secrets),
        }
        sent = self._transport.send(target, headers, body.encode(), timeout_s=config.timeout_s)
        status = sent.status
        if status is None:
            return failed("network_error", "The request did not get an answer.", retryable=True)
        if 200 <= status < 300:
            if sent.truncated or len(sent.excerpt.encode()) > ACTION_MAX_RESULT_BYTES:
                return failed(
                    "result_too_large",
                    f"The answer is over {ACTION_MAX_RESULT_BYTES} bytes.",
                    status=status,
                )
            return ActionOutcome(
                status="completed", http_status=status, result=result_of(sent.excerpt)
            )
        if 300 <= status < 400:
            return failed("redirect", "The receiver answered with a redirect.", status=status)
        retryable = status >= 500 or status in RETRYABLE_STATUSES
        return failed(
            "http_error", f"The receiver answered {status}.", retryable=retryable, status=status
        )
