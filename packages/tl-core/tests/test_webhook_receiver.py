"""The dev webhook receiver: verifies signatures, dedupes, fails on request (P0-I5-T23)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from tl_core.webhooks.receiver import DevReceiver
from tl_core.webhooks.signing import SigningSecret, generate_secret, sign_headers

SECRET = generate_secret()
BODY = json.dumps({"id": "evt_1", "tlseq": 7, "type": "tl.core.Record.Created.v1"})


def post(
    receiver: DevReceiver,
    *,
    message_id: str = "evt_1",
    body: str = BODY,
    secret: str = SECRET,
    timestamp: int | None = None,
    path: str = "/hook",
) -> httpx.Response:
    stamp = int(time.time()) if timestamp is None else timestamp
    headers = sign_headers(message_id, stamp, body, [SigningSecret(secret)])
    url = f"http://127.0.0.1:{receiver.port}{path}"
    return httpx.post(url, content=body, headers=headers, timeout=5)


@pytest.fixture
def receiver() -> Iterator[DevReceiver]:
    with DevReceiver([SECRET]) as running:
        yield running


def test_it_listens_on_loopback_on_a_free_port_and_stops_cleanly() -> None:
    server = DevReceiver([SECRET])
    with pytest.raises(RuntimeError):
        _ = server.port  # not running yet
    server.start()
    try:
        port = server.port
        assert port > 0
        assert server.url == f"http://127.0.0.1:{port}/hook"
        with pytest.raises(RuntimeError):
            server.start()
    finally:
        server.stop()
    server.stop()  # a second stop is harmless
    with pytest.raises(httpx.ConnectError):
        httpx.post(f"http://127.0.0.1:{port}/", timeout=1)


def test_a_correctly_signed_message_is_accepted_and_recorded(receiver: DevReceiver) -> None:
    response = post(receiver, path="/custom/path")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "duplicate": False}
    (message,) = receiver.messages()
    assert message.path == "/custom/path"
    assert message.webhook_id == "evt_1"
    assert message.verified and not message.duplicate
    assert message.event()["tlseq"] == 7
    assert message.headers["webhook-id"] == "evt_1"
    assert receiver.rejected() == []


def test_a_bad_signature_is_refused_with_401_and_not_counted(receiver: DevReceiver) -> None:
    assert post(receiver, secret=generate_secret()).status_code == 401
    assert (
        post(receiver, timestamp=int(time.time()) - 10_000).status_code == 401
    )  # replayed too late
    tampered = httpx.post(
        f"http://127.0.0.1:{receiver.port}/hook",
        content=BODY + " ",
        headers=sign_headers("evt_1", int(time.time()), BODY, [SigningSecret(SECRET)]),
        timeout=5,
    )
    assert tampered.status_code == 401
    assert (
        httpx.post(f"http://127.0.0.1:{receiver.port}/hook", content=BODY, timeout=5).status_code
        == 401
    )
    assert receiver.messages() == []
    assert len(receiver.rejected()) == 4
    assert not any(m.verified for m in receiver.rejected())


def test_the_same_event_id_twice_is_answered_200_and_flagged_as_a_duplicate(
    receiver: DevReceiver,
) -> None:
    assert post(receiver).json()["duplicate"] is False
    assert post(receiver).json() == {"ok": True, "duplicate": True}
    assert post(receiver, message_id="evt_2").json()["duplicate"] is False
    assert [m.duplicate for m in receiver.messages()] == [False, True, False]
    assert [m.webhook_id for m in receiver.unique()] == ["evt_1", "evt_2"]


def test_fail_next_answers_the_next_requests_with_the_given_statuses(receiver: DevReceiver) -> None:
    receiver.fail_next([500, 429])
    assert post(receiver).status_code == 500
    assert post(receiver).status_code == 429
    assert post(receiver).status_code == 200
    assert len(receiver.messages()) == 1  # failed requests are not deliveries
    assert len(receiver.rejected()) == 2  # but they are logged


def test_a_rotation_overlap_accepts_either_secret(receiver: DevReceiver) -> None:
    newer = generate_secret()
    receiver.set_secrets([SECRET, newer])
    assert post(receiver, secret=SECRET).status_code == 200
    assert post(receiver, secret=newer, message_id="evt_2").status_code == 200
    receiver.set_secrets([newer])
    assert post(receiver, secret=SECRET, message_id="evt_3").status_code == 401


def test_wait_for_returns_when_enough_messages_arrived_or_times_out(receiver: DevReceiver) -> None:
    assert receiver.wait_for(1, timeout_s=0.1) is False
    threading.Timer(0.2, lambda: post(receiver)).start()
    assert receiver.wait_for(1, timeout_s=5) is True


def test_clear_forgets_messages_failures_and_seen_ids(receiver: DevReceiver) -> None:
    post(receiver)
    receiver.fail_next([500])
    receiver.clear()
    assert receiver.messages() == [] and receiver.rejected() == []
    assert post(receiver).json() == {"ok": True, "duplicate": False}


def test_concurrent_posts_are_all_recorded(receiver: DevReceiver) -> None:
    def send(n: int) -> None:
        post(receiver, message_id=f"evt_{n}")

    threads = [threading.Thread(target=send, args=(n,), daemon=True) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(receiver.messages()) == 20
    assert len({m.webhook_id for m in receiver.messages()}) == 20
