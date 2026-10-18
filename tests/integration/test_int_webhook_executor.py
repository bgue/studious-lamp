"""The ``webhook`` executor: egress before any connect, signing, and what the answer becomes.

Nothing leaves the machine: the transport is a scripted one, the resolver a table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from tl_core.integration.contract import (
    ACTION_MAX_RESULT_BYTES,
    ActionRequest,
    JobExecutorConfig,
    RecordRef,
    WebhookExecutorConfig,
)
from tl_core.integration.executors.webhook import WebhookExecutor, canonical_body
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.signing import SigningSecret, generate_secret, verify
from tl_core.webhooks.testing import ScriptedTransport
from tl_core.webhooks.transport import TransportResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))

from test_integration_contract import check_executor_contract  # noqa: E402

SECRET = SigningSecret(generate_secret())
OLD_SECRET = SigningSecret(generate_secret())
HOSTS = {
    "nde.example.net": ["93.184.216.34"],
    "internal.example.net": ["10.1.2.3"],
    "rebind.example.net": ["93.184.216.34", "127.0.0.1"],
    "mixed.example.net": ["93.184.216.34", "169.254.169.254"],
    "dev.example.net": ["127.0.0.1"],
}


def resolver(host: str, port: int) -> list[str]:
    return HOSTS.get(host, [])


def request(url: str = "https://nde.example.net/hooks/request", **changes: Any) -> ActionRequest:
    base: dict[str, Any] = {
        "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
        "action": "send_to_nde",
        "action_version": 2,
        "scope": "project:P123",
        "targets": [RecordRef(id="r1", key="47-1234-W012", record_type="core.Record", version=3)],
        "parameters": {"method": "RT"},
        "invoked_by": "user:jsmith",
        "attempt": 1,
        "config": WebhookExecutorConfig(url=url, secret_id="S" * 26),
    }
    return ActionRequest.model_validate({**base, **changes})


def make(
    transport: ScriptedTransport | None = None,
    allowlist: tuple[str, ...] = (),
    secrets: list[SigningSecret] | None = None,
    clock: float = 1_800_000_000.0,
) -> tuple[WebhookExecutor, ScriptedTransport]:
    sent = transport if transport is not None else ScriptedTransport()
    live = [SECRET] if secrets is None else secrets
    executor = WebhookExecutor(
        policy=EgressPolicy(allowlist, resolver),
        transport=sent,
        secrets=lambda secret_id: live,
        clock=lambda: clock,
    )
    return executor, sent


def code(outcome: Any) -> str:
    assert outcome.status == "failed" and outcome.problems
    return outcome.problems[0].code


def test_it_passes_the_shared_executor_contract_checks() -> None:
    executor, _ = make()
    check_executor_contract(
        executor,
        [
            request(),
            request(url="http://nde.example.net/h"),
            request(url="https://internal.example.net/h"),
            request(config=JobExecutorConfig(job="echo")),
        ],
    )


# --- egress: refused before any connect --------------------------------------------------------

REFUSED_URLS = [
    "https://10.0.0.1/h",
    "https://172.16.0.1/h",
    "https://192.168.1.1/h",
    "https://127.0.0.1/h",
    "https://[::1]/h",
    "https://169.254.169.254/latest/meta-data/",
    "https://[fe80::1]/h",
    "https://100.64.0.1/h",
    "https://100.100.100.200/h",
    "https://224.0.0.1/h",
    "https://240.0.0.1/h",
    "https://0.0.0.0/h",
    "https://[::ffff:10.0.0.1]/h",
    "https://[::ffff:169.254.169.254]/h",
    "https://[fd00::1]/h",
    "https://internal.example.net/h",
    "https://rebind.example.net/h",
    "https://mixed.example.net/h",
    "https://metadata.google.internal/h",
    "http://nde.example.net/h",
    "https://user:pass@nde.example.net/h",
    "https://nde.example.net/h#frag",
    "ftp://nde.example.net/h",
    "https:///h",
    "nde.example.net/h",
    "",
]


@pytest.mark.parametrize("url", REFUSED_URLS)
def test_a_refused_target_is_never_connected_to(url: str) -> None:
    executor, transport = make()
    outcome = executor.execute(request(url=url))
    assert code(outcome) in ("egress_denied", "unresolvable"), url
    assert outcome.retryable is (code(outcome) == "unresolvable")
    assert transport.sent == [], "nothing is sent before the check passes"


def test_the_refusal_does_not_echo_the_address() -> None:
    executor, _ = make()
    outcome = executor.execute(request(url="https://169.254.169.254/latest"))
    message = outcome.problems[0].message
    assert "169.254" not in message and "http" not in message


def test_an_allow_listed_host_may_use_plain_http_and_a_private_address() -> None:
    executor, transport = make(allowlist=("dev.example.net",))
    outcome = executor.execute(request(url="http://dev.example.net:8080/h"))
    assert outcome.status == "completed"
    assert transport.sent[0].target.ip == "127.0.0.1" and transport.sent[0].target.port == 8080


def test_the_metadata_address_is_refused_even_when_it_is_allow_listed() -> None:
    executor, transport = make(allowlist=("169.254.169.254", "169.254.0.0/16", "mixed.example.net"))
    for url in ("https://169.254.169.254/h", "https://mixed.example.net/h"):
        assert code(executor.execute(request(url=url))) == "egress_denied"
    assert transport.sent == []


def test_the_host_is_resolved_once_and_the_connection_is_pinned() -> None:
    calls: list[str] = []

    def counting(host: str, port: int) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    transport = ScriptedTransport()
    executor = WebhookExecutor(
        policy=EgressPolicy((), counting),
        transport=transport,
        secrets=lambda _: [SECRET],
    )
    assert executor.execute(request()).status == "completed"
    assert calls == ["nde.example.net"]
    assert transport.sent[0].target.ip == "93.184.216.34"
    assert transport.sent[0].target.host == "nde.example.net"


def test_a_name_that_does_not_resolve_is_retried_later() -> None:
    executor, transport = make()
    outcome = executor.execute(request(url="https://nowhere.example.net/h"))
    assert code(outcome) == "unresolvable" and outcome.retryable
    assert transport.sent == []


# --- signing ----------------------------------------------------------------------------------


def test_the_body_is_signed_so_the_receiver_can_verify_it() -> None:
    executor, transport = make()
    executor.execute(request())
    sent = transport.sent[0]
    assert verify(sent.headers, sent.body, [SECRET], now=1_800_000_000.0) == (
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"
    )
    assert sent.headers["Content-Type"] == "application/json"


def test_during_a_rotation_both_secrets_sign() -> None:
    executor, transport = make(secrets=[SECRET, OLD_SECRET])
    executor.execute(request())
    sent = transport.sent[0]
    assert len(sent.headers["webhook-signature"].split()) == 2
    for secret in (SECRET, OLD_SECRET):
        verify(sent.headers, sent.body, [secret], now=1_800_000_000.0)


def test_the_request_carries_no_secret_and_no_config() -> None:
    executor, transport = make()
    executor.execute(request())
    text = transport.sent[0].body.decode()
    body = json.loads(text)
    assert set(body) == {
        "invocation_id", "action", "action_version", "scope", "targets", "parameters",
        "invoked_by", "attempt",
    }  # fmt: skip
    assert SECRET.value not in text and "whsec_" not in text and "secret" not in text
    assert text == canonical_body(request()), "sorted compact JSON, the same text every attempt"


def test_an_action_without_a_live_secret_does_not_send_unsigned() -> None:
    executor, transport = make(secrets=[])
    assert code(executor.execute(request())) == "no_secret"
    no_id = request(config=WebhookExecutorConfig(url="https://nde.example.net/h"))
    assert code(make()[0].execute(no_id)) == "no_secret"
    assert transport.sent == []


def test_a_failure_to_read_the_secret_is_a_retry_with_no_detail() -> None:
    def broken(secret_id: str) -> list[SigningSecret]:
        raise RuntimeError("password=hunter2 at /srv/db")

    transport = ScriptedTransport()
    executor = WebhookExecutor(
        policy=EgressPolicy((), resolver), transport=transport, secrets=broken
    )
    outcome = executor.execute(request())
    assert code(outcome) == "secret_unavailable" and outcome.retryable
    assert "hunter2" not in outcome.problems[0].message and transport.sent == []


def test_the_timeout_comes_from_the_config() -> None:
    seen: list[float] = []

    def responder(sent: Any) -> TransportResult:
        return TransportResult(status=200, latency_ms=1, excerpt="{}")

    transport = ScriptedTransport(responder=responder)
    original = transport.send

    def spy(target: Any, headers: Any, body: Any, *, timeout_s: float) -> TransportResult:
        seen.append(timeout_s)
        return original(target, headers, body, timeout_s=timeout_s)

    transport.send = spy  # type: ignore[method-assign]
    config = WebhookExecutorConfig(
        url="https://nde.example.net/h", secret_id="S" * 26, timeout_s=3.5
    )
    executor, _ = make(transport)
    executor.execute(request(config=config))
    assert seen == [3.5]


# --- the answer --------------------------------------------------------------------------------


def answering(status: int | None, text: str = "", **extra: Any) -> ScriptedTransport:
    return ScriptedTransport(
        default=TransportResult(status=status, latency_ms=1, excerpt=text, **extra)
    )


def test_a_json_answer_is_the_result() -> None:
    executor, _ = make(answering(200, '{"accepted": true, "ticket": "NDE-9"}'))
    outcome = executor.execute(request())
    assert outcome.status == "completed" and outcome.http_status == 200
    assert outcome.result == {"accepted": True, "ticket": "NDE-9"}


def test_an_answer_that_is_not_an_object_or_not_json_is_still_stored() -> None:
    executor, _ = make(answering(200, "[1, 2]"))
    assert executor.execute(request()).result == {"value": [1, 2]}
    executor, _ = make(answering(202, "queued, thanks"))
    assert executor.execute(request()).result == {"text": "queued, thanks"}
    executor, _ = make(answering(200, "{" * 50_000))
    assert executor.execute(request()).result == {"text": "{" * 50_000}


def test_an_answer_past_the_limit_fails_and_is_not_cut() -> None:
    executor, _ = make(answering(200, "x" * 100, truncated=True))
    outcome = executor.execute(request())
    assert code(outcome) == "result_too_large" and not outcome.retryable
    big = "x" * (ACTION_MAX_RESULT_BYTES + 1)
    executor, _ = make(answering(200, big))
    assert code(executor.execute(request())) == "result_too_large"


@pytest.mark.parametrize("status", [500, 502, 503, 429, 408, 425])
def test_a_server_side_or_busy_answer_is_retried(status: int) -> None:
    outcome = make(answering(status))[0].execute(request())
    assert code(outcome) == "http_error" and outcome.retryable and outcome.http_status == status


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_a_client_error_is_final(status: int) -> None:
    outcome = make(answering(status))[0].execute(request())
    assert code(outcome) == "http_error" and not outcome.retryable and outcome.http_status == status


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_a_redirect_is_a_failure_and_is_not_followed(status: int) -> None:
    executor, transport = make(answering(status))
    outcome = executor.execute(request())
    assert code(outcome) == "redirect" and not outcome.retryable
    assert len(transport.sent) == 1


def test_no_answer_is_a_retry_and_the_error_text_is_not_kept() -> None:
    executor, _ = make(answering(None, error="ConnectError: connect to 10.0.0.9 failed"))
    outcome = executor.execute(request())
    assert code(outcome) == "network_error" and outcome.retryable
    assert "10.0.0.9" not in outcome.problems[0].message


def test_a_wrong_config_is_not_for_this_executor() -> None:
    executor, transport = make()
    assert code(executor.execute(request(config=JobExecutorConfig(job="echo")))) == "wrong_executor"
    assert transport.sent == []
