"""Verifying an inbound request (FANOUT D4 step 4; ADR-0017): HMAC-SHA256 and JWT (HS256 only).

Both kinds check bytes in constant time and fail closed. A failure is a :class:`VerifyError` whose
``code`` is one of a short fixed list; the route answers every one with the same 401 and keeps the
code only in the server log and a per-endpoint counter. A message never holds a header value, a
claim, a signature or the body.

**hmac_sha256** is the Standard Webhooks scheme of the outbound side, verified by
``tl_core.webhooks.signing.verify`` against the endpoint's live secrets (two during a rotation):
HMAC-SHA256 over ``id.timestamp.body``, the timestamp within ``INBOUND_TOLERANCE_S`` either way. The
id it returns is what the route stores for replay detection.

**jwt_hs256** is ``Authorization: Bearer <token>``. The algorithm list is fixed here
(``INBOUND_JWT_ALGORITHMS``), so ``none``, an RSA token and the HS/RS confusion are refused; the
header may hold ``alg``, ``typ`` and ``kid`` and nothing else (no ``jku``, ``jwk``, ``x5u``,
``crit``); the audience is the endpoint path; the claims ``iat``, ``exp``, ``aud``, ``jti`` and
``body_sha256`` are required; ``exp - iat`` is at most ``INBOUND_JWT_MAX_LIFETIME_S``; ``iat`` is
within the tolerance of ``now`` either way and the token is not past ``exp``; ``body_sha256`` must
equal the SHA-256 of the raw body, so a token cannot be replayed on another body. The ``jti`` is
what the route stores.
PyJWT checks the signature, the algorithm and the audience; the time rules are here, so tests can
set the clock.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Mapping, Sequence
from typing import Any

import jwt

from tl_core.integration.contract import (
    INBOUND_JWT_ALGORITHMS,
    INBOUND_JWT_MAX_LIFETIME_S,
    INBOUND_JWT_REQUIRED_CLAIMS,
    INBOUND_TOLERANCE_S,
)
from tl_core.webhooks.signing import SignatureError, SigningSecret
from tl_core.webhooks.signing import verify as verify_webhook

MAX_TOKEN_CHARS = 4096
MAX_ID_CHARS = 128
ALLOWED_HEADER_KEYS = frozenset({"alg", "typ", "kid"})
CODES = (
    "no_secret",
    "bad_signature",
    "bad_token",
    "bad_claims",
    "expired",
    "body_mismatch",
)


class VerifyError(Exception):
    """A request failed verification. ``code`` is one of ``CODES``; the text holds nothing else."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def verify_hmac(
    headers: Mapping[str, str],
    body: bytes,
    secrets: Sequence[SigningSecret],
    *,
    now: float,
) -> str:
    """The ``webhook-id`` of a request signed with one of ``secrets``. Raises ``VerifyError``."""
    if not secrets:
        raise VerifyError("no_secret")
    try:
        message_id = verify_webhook(
            headers, body, secrets, now=now, tolerance_s=INBOUND_TOLERANCE_S
        )
    except SignatureError:
        raise VerifyError("bad_signature") from None
    if not message_id or len(message_id) > MAX_ID_CHARS:
        raise VerifyError("bad_signature")
    return message_id


def _bearer(headers: Mapping[str, str]) -> str:
    lowered = {name.lower(): value for name, value in headers.items()}
    value = lowered.get("authorization", "")
    prefix = "Bearer "
    if not value.startswith(prefix) or len(value) > MAX_TOKEN_CHARS + len(prefix):
        raise VerifyError("bad_token")
    token = value[len(prefix) :]
    if not token or " " in token:
        raise VerifyError("bad_token")
    return token


def verify_jwt(
    headers: Mapping[str, str],
    body: bytes,
    secrets: Sequence[SigningSecret],
    *,
    audience: str,
    now: float,
) -> str:
    """The ``jti`` of a valid token for this endpoint and this body. Raises ``VerifyError``."""
    if not secrets:
        raise VerifyError("no_secret")
    token = _bearer(headers)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise VerifyError("bad_token") from None
    if header.get("alg") not in INBOUND_JWT_ALGORITHMS or not set(header) <= ALLOWED_HEADER_KEYS:
        raise VerifyError("bad_token")
    claims: dict[str, Any] | None = None
    for secret in secrets:
        try:
            claims = jwt.decode(
                token,
                key=secret.key(),
                algorithms=list(INBOUND_JWT_ALGORITHMS),
                audience=audience,
                options={
                    "require": list(INBOUND_JWT_REQUIRED_CLAIMS),
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            break
        except jwt.InvalidAudienceError:
            raise VerifyError("bad_claims") from None
        except jwt.MissingRequiredClaimError:
            raise VerifyError("bad_claims") from None
        except jwt.PyJWTError:
            continue
    if claims is None:
        raise VerifyError("bad_signature")
    return _check_claims(claims, body, now)


def _number(value: Any) -> float:
    """A claim that is a finite number: no bool, NaN, infinity or integer too big for a float."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise VerifyError("bad_claims")
    try:
        number = float(value)
    except OverflowError:
        raise VerifyError("bad_claims") from None
    if not math.isfinite(number):
        raise VerifyError("bad_claims")
    return number


def _check_claims(claims: Mapping[str, Any], body: bytes, now: float) -> str:
    issued = _number(claims.get("iat"))
    expires = _number(claims.get("exp"))
    if expires - issued > INBOUND_JWT_MAX_LIFETIME_S or expires <= issued:
        raise VerifyError("bad_claims")
    if abs(now - issued) > INBOUND_TOLERANCE_S or now > expires:
        raise VerifyError("expired")
    jti = claims.get("jti")
    if not isinstance(jti, str) or not jti or len(jti) > MAX_ID_CHARS:
        raise VerifyError("bad_claims")
    digest = claims.get("body_sha256")
    wanted = hashlib.sha256(body).hexdigest().encode()
    if not isinstance(digest, str) or not hmac.compare_digest(digest.lower().encode(), wanted):
        raise VerifyError("body_mismatch")
    return jti
