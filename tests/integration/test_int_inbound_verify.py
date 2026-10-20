"""Inbound verification (FANOUT D4 step 4): HMAC and HS256 JWT, fail closed with fixed codes."""

from __future__ import annotations

import base64
import hashlib

import jwt
import pytest
from tl_core.integration.contract import INBOUND_JWT_MAX_LIFETIME_S, INBOUND_TOLERANCE_S
from tl_core.integration.inbound.verify import CODES, VerifyError, verify_hmac, verify_jwt
from tl_core.webhooks.signing import SigningSecret, generate_secret, sign_headers

NOW = 1_800_000_000.0
BODY = b'{"a": 1}'
AUD = "/in/erp/orders"


def _secret() -> SigningSecret:
    return SigningSecret(generate_secret())


def _token(
    secret: SigningSecret, *, body: bytes = BODY, algorithm: str = "HS256", **over: object
) -> str:
    claims: dict[str, object] = {
        "iat": int(NOW),
        "exp": int(NOW) + 60,
        "aud": AUD,
        "jti": "j1",
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }
    claims.update(over)
    return jwt.encode(claims, secret.key(), algorithm=algorithm)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _code(call: object) -> str:
    with pytest.raises(VerifyError) as caught:
        call()  # type: ignore[operator]
    assert caught.value.code in CODES
    return caught.value.code


def test_hmac_accepts_a_signed_request_and_returns_the_id() -> None:
    s = _secret()
    headers = sign_headers("msg_1", int(NOW), BODY.decode(), [s])
    assert verify_hmac(headers, BODY, [s], now=NOW) == "msg_1"


def test_hmac_accepts_either_secret_during_a_rotation() -> None:
    old, new = _secret(), _secret()
    headers = sign_headers("msg_1", int(NOW), BODY.decode(), [old])
    assert verify_hmac(headers, BODY, [new, old], now=NOW) == "msg_1"


@pytest.mark.parametrize(
    "case", ["no_secret", "wrong_secret", "other_body", "stale", "future", "missing"]
)
def test_hmac_refuses(case: str) -> None:
    s = _secret()
    headers = sign_headers("msg_1", int(NOW), BODY.decode(), [s])
    secrets = [s]
    body = BODY
    if case == "no_secret":
        secrets = []
    elif case == "wrong_secret":
        secrets = [_secret()]
    elif case == "other_body":
        body = b'{"a": 2}'
    elif case == "stale":
        headers = sign_headers("msg_1", int(NOW) - INBOUND_TOLERANCE_S - 5, BODY.decode(), [s])
    elif case == "future":
        headers = sign_headers("msg_1", int(NOW) + INBOUND_TOLERANCE_S + 5, BODY.decode(), [s])
    else:
        headers = {}
    code = _code(lambda: verify_hmac(headers, body, secrets, now=NOW))
    assert code == ("no_secret" if case == "no_secret" else "bad_signature")


def test_jwt_accepts_a_valid_token_and_returns_the_jti() -> None:
    s = _secret()
    assert verify_jwt(_bearer(_token(s)), BODY, [s], audience=AUD, now=NOW) == "j1"


def test_jwt_accepts_the_old_secret_during_a_rotation() -> None:
    old, new = _secret(), _secret()
    assert verify_jwt(_bearer(_token(old)), BODY, [new, old], audience=AUD, now=NOW) == "j1"


def test_jwt_refuses_another_body() -> None:
    s = _secret()
    code = _code(lambda: verify_jwt(_bearer(_token(s)), b"{}", [s], audience=AUD, now=NOW))
    assert code == "body_mismatch"


def test_jwt_refuses_another_audience() -> None:
    s = _secret()
    code = _code(
        lambda: verify_jwt(_bearer(_token(s, aud="/in/x/y")), BODY, [s], audience=AUD, now=NOW)
    )
    assert code == "bad_claims"


@pytest.mark.parametrize("claim", ["iat", "exp", "aud", "jti", "body_sha256"])
def test_jwt_requires_every_claim(claim: str) -> None:
    s = _secret()
    claims = {
        "iat": int(NOW),
        "exp": int(NOW) + 60,
        "aud": AUD,
        "jti": "j1",
        "body_sha256": hashlib.sha256(BODY).hexdigest(),
    }
    del claims[claim]
    token = jwt.encode(claims, s.key(), algorithm="HS256")
    assert (
        _code(lambda: verify_jwt(_bearer(token), BODY, [s], audience=AUD, now=NOW)) == "bad_claims"
    )


def test_jwt_refuses_a_long_lifetime_an_expired_token_and_a_stale_iat() -> None:
    s = _secret()
    long_ = _token(s, exp=int(NOW) + INBOUND_JWT_MAX_LIFETIME_S + 1)
    assert (
        _code(lambda: verify_jwt(_bearer(long_), BODY, [s], audience=AUD, now=NOW)) == "bad_claims"
    )
    assert (
        _code(lambda: verify_jwt(_bearer(_token(s)), BODY, [s], audience=AUD, now=NOW + 120))
        == "expired"
    )
    iat = int(NOW) - INBOUND_TOLERANCE_S - 10
    stale = _token(s, iat=iat, exp=iat + 60)
    assert _code(lambda: verify_jwt(_bearer(stale), BODY, [s], audience=AUD, now=NOW)) == "expired"


def test_jwt_refuses_a_wrong_secret() -> None:
    code = _code(
        lambda: verify_jwt(_bearer(_token(_secret())), BODY, [_secret()], audience=AUD, now=NOW)
    )
    assert code == "bad_signature"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_jwt_refuses_alg_none_and_other_algorithms() -> None:
    s = _secret()
    claims = b'{"iat":%d,"exp":%d,"aud":"%s","jti":"j","body_sha256":"%s"}' % (
        int(NOW),
        int(NOW) + 60,
        AUD.encode(),
        hashlib.sha256(BODY).hexdigest().encode(),
    )
    none = f"{_b64(b'{"alg":"none","typ":"JWT"}')}.{_b64(claims)}."
    assert _code(lambda: verify_jwt(_bearer(none), BODY, [s], audience=AUD, now=NOW)) == "bad_token"
    hs512 = _token(s, algorithm="HS512")
    assert (
        _code(lambda: verify_jwt(_bearer(hs512), BODY, [s], audience=AUD, now=NOW)) == "bad_token"
    )


def test_jwt_refuses_extra_header_keys() -> None:
    s = _secret()
    token = jwt.encode(
        {
            "iat": int(NOW),
            "exp": int(NOW) + 60,
            "aud": AUD,
            "jti": "j",
            "body_sha256": hashlib.sha256(BODY).hexdigest(),
        },
        s.key(),
        algorithm="HS256",
        headers={"jku": "https://evil.example/keys"},
    )
    assert (
        _code(lambda: verify_jwt(_bearer(token), BODY, [s], audience=AUD, now=NOW)) == "bad_token"
    )


@pytest.mark.parametrize(
    "header", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}]
)
def test_jwt_refuses_a_missing_or_malformed_bearer(header: dict[str, str]) -> None:
    s = _secret()
    assert _code(lambda: verify_jwt(header, BODY, [s], audience=AUD, now=NOW)) == "bad_token"


def test_jwt_with_no_secret_fails_closed() -> None:
    assert (
        _code(lambda: verify_jwt(_bearer("x.y.z"), BODY, [], audience=AUD, now=NOW)) == "no_secret"
    )


def test_an_error_text_holds_only_the_code() -> None:
    s = _secret()
    token = _token(s)
    try:
        verify_jwt(_bearer(token), b"{}", [s], audience=AUD, now=NOW)
    except VerifyError as exc:
        assert str(exc) == exc.code
        assert token not in str(exc)
