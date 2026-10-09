"""Standard Webhooks signing and verification (brief 18.4)."""

from __future__ import annotations

import base64

import pytest
from tl_core.webhooks.signing import (
    SignatureError,
    SigningSecret,
    generate_secret,
    sign,
    sign_headers,
    signature_header,
    verify,
)

# The Standard Webhooks reference example (https://www.standardwebhooks.com).
SECRET = SigningSecret("whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw")
MESSAGE_ID = "msg_p5jXN8AQM9LWM0D4loKWxJek"
TIMESTAMP = 1614265330
BODY = '{"test": 2432232314}'
EXPECTED = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def test_matches_the_published_reference_signature() -> None:
    assert sign(MESSAGE_ID, TIMESTAMP, BODY, SECRET) == EXPECTED


def test_a_generated_secret_has_the_standard_shape() -> None:
    secret = generate_secret()
    assert secret.startswith("whsec_")
    assert len(base64.b64decode(secret[6:])) == 32
    assert generate_secret() != secret


def test_the_secret_value_never_appears_in_repr_or_str() -> None:
    assert SECRET.value not in repr(SECRET)
    assert SECRET.value not in str(SECRET)
    assert "MfKQ9r8G" not in f"{SECRET!r} {SECRET}"


@pytest.mark.parametrize("bad", ["", "nope", "whsec_", "whsec_!!!", "whsec_" + "QQ=="])
def test_malformed_secrets_are_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        SigningSecret(bad)


def test_headers_carry_id_timestamp_and_signature() -> None:
    headers = sign_headers(MESSAGE_ID, TIMESTAMP, BODY, [SECRET])
    assert headers == {
        "webhook-id": MESSAGE_ID,
        "webhook-timestamp": "1614265330",
        "webhook-signature": EXPECTED,
    }


def test_two_active_secrets_give_two_signatures_and_either_verifies() -> None:
    other = SigningSecret(generate_secret())
    headers = sign_headers(MESSAGE_ID, TIMESTAMP, BODY, [SECRET, other])
    assert len(headers["webhook-signature"].split()) == 2
    assert verify(headers, BODY, [SECRET], now=TIMESTAMP) == MESSAGE_ID
    assert verify(headers, BODY, [other], now=TIMESTAMP) == MESSAGE_ID


def test_signing_needs_a_secret() -> None:
    with pytest.raises(ValueError):
        signature_header(MESSAGE_ID, TIMESTAMP, BODY, [])


def test_verify_accepts_a_good_message_and_is_case_insensitive_about_header_names() -> None:
    headers = {k.title(): v for k, v in sign_headers(MESSAGE_ID, TIMESTAMP, BODY, [SECRET]).items()}
    assert verify(headers, BODY.encode(), [SECRET], now=TIMESTAMP + 10) == MESSAGE_ID


@pytest.mark.parametrize(
    "change",
    ["body", "id", "timestamp", "secret", "old", "future", "missing", "garbage", "nosecrets"],
)
def test_verify_fails_closed(change: str) -> None:
    headers = sign_headers(MESSAGE_ID, TIMESTAMP, BODY, [SECRET])
    body, secrets, now = BODY, [SECRET], TIMESTAMP
    if change == "body":
        body = BODY + " "
    elif change == "id":
        headers["webhook-id"] = "msg_other"
    elif change == "timestamp":
        headers["webhook-timestamp"] = str(TIMESTAMP + 1)
    elif change == "secret":
        secrets = [SigningSecret(generate_secret())]
    elif change == "old":
        now = TIMESTAMP + 301
    elif change == "future":
        now = TIMESTAMP - 301
    elif change == "missing":
        del headers["webhook-signature"]
    elif change == "garbage":
        headers["webhook-signature"] = "v1,éé \x00 not-base64 v2,abc"
    elif change == "nosecrets":
        secrets = []
    with pytest.raises(SignatureError):
        verify(headers, body, secrets, now=now)


def test_verify_never_raises_anything_but_signature_error_for_hostile_input() -> None:
    headers = {
        "webhook-id": "x",
        "webhook-timestamp": "not a number",
        "webhook-signature": "\ud800",
    }
    with pytest.raises(SignatureError):
        verify(headers, "{}", [SECRET], now=0)
    headers["webhook-timestamp"] = "0"
    with pytest.raises(SignatureError):
        verify(headers, "{}", [SECRET], now=0)
