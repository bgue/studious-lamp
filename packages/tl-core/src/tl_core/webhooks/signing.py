"""Standard Webhooks signing (https://www.standardwebhooks.com), brief 18.4.

Three headers accompany every delivery:

* ``webhook-id``: the message id. Here it is the ledger event id, so a receiver that stores the ids
  it
  has processed dedupes retries and replays.
* ``webhook-timestamp``: Unix seconds when this attempt was signed. Each attempt is signed afresh so
  a
  retry hours later is still inside the receiver's tolerance window.
* ``webhook-signature``: space-separated ``v1,<base64 HMAC-SHA256>`` entries, one per active secret
  (two during a rotation overlap), over ``"<id>.<timestamp>.<body>"``.

A secret is ``whsec_`` followed by the base64 of its key bytes. Secrets are never logged: ``repr``
of
:class:`SigningSecret` hides the value, and nothing in this module formats one into a message.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets as _secrets
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

SECRET_PREFIX = "whsec_"
SIGNATURE_VERSION = "v1"
HEADER_ID = "webhook-id"
HEADER_TIMESTAMP = "webhook-timestamp"
HEADER_SIGNATURE = "webhook-signature"
#: Default window in which a receiver accepts a timestamp, per the Standard Webhooks guidance.
DEFAULT_TOLERANCE_S = 300


class SignatureError(Exception):
    """A webhook failed verification. The message never contains a secret or a signature."""


@dataclass(frozen=True)
class SigningSecret:
    """A signing secret in its ``whsec_<base64>`` form. ``repr`` and ``str`` hide the value."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        self.key()  # validate early

    def key(self) -> bytes:
        """The raw key bytes."""
        if not self.value.startswith(SECRET_PREFIX):
            raise ValueError(f"a signing secret starts with {SECRET_PREFIX!r}")
        try:
            raw = base64.b64decode(self.value[len(SECRET_PREFIX) :], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("a signing secret is whsec_ followed by base64") from exc
        if len(raw) < 16:
            raise ValueError("a signing secret needs at least 16 bytes of key")
        return raw

    def __repr__(self) -> str:
        return "SigningSecret(<hidden>)"

    __str__ = __repr__


def generate_secret() -> str:
    """A new secret: ``whsec_`` plus the base64 of 32 random bytes."""
    return SECRET_PREFIX + base64.b64encode(_secrets.token_bytes(32)).decode("ascii")


def signed_content(message_id: str, timestamp: int, body: str) -> bytes:
    """The bytes that are signed: ``<id>.<timestamp>.<body>`` in UTF-8."""
    return f"{message_id}.{timestamp}.{body}".encode()


def sign(message_id: str, timestamp: int, body: str, secret: SigningSecret) -> str:
    """One ``v1,<base64>`` signature entry."""
    digest = hmac.new(secret.key(), signed_content(message_id, timestamp, body), hashlib.sha256)
    return f"{SIGNATURE_VERSION},{base64.b64encode(digest.digest()).decode('ascii')}"


def signature_header(
    message_id: str, timestamp: int, body: str, secrets: Iterable[SigningSecret]
) -> str:
    """The ``webhook-signature`` value: one entry per secret, space-separated. Needs one secret."""
    entries = [sign(message_id, timestamp, body, secret) for secret in secrets]
    if not entries:
        raise ValueError("at least one signing secret is needed to sign a delivery")
    return " ".join(entries)


def sign_headers(
    message_id: str, timestamp: int, body: str, secrets: Iterable[SigningSecret]
) -> dict[str, str]:
    """The three Standard Webhooks headers for one attempt."""
    return {
        HEADER_ID: message_id,
        HEADER_TIMESTAMP: str(timestamp),
        HEADER_SIGNATURE: signature_header(message_id, timestamp, body, secrets),
    }


def verify(
    headers: Mapping[str, str],
    body: str | bytes,
    secrets: Iterable[SigningSecret],
    *,
    now: float | None = None,
    tolerance_s: int = DEFAULT_TOLERANCE_S,
) -> str:
    """Check a received webhook; return its ``webhook-id`` or raise :class:`SignatureError`.

    Header names are matched case-insensitively. The timestamp must be within ``tolerance_s`` of
    ``now`` (either direction). The signature matches when **any** entry equals the signature made
    with **any** of ``secrets``; comparisons are constant-time and on bytes, so hostile header text
    cannot raise or leak timing. Fails closed: no secrets, a missing header or a malformed entry is
    an error.
    """
    lowered = {name.lower(): value for name, value in headers.items()}
    try:
        message_id = lowered[HEADER_ID]
        stamp_text = lowered[HEADER_TIMESTAMP]
        presented = lowered[HEADER_SIGNATURE]
    except KeyError as exc:
        raise SignatureError(f"missing header {exc.args[0]}") from None
    try:
        timestamp = int(stamp_text)
    except ValueError:
        raise SignatureError("the webhook timestamp is not a number") from None
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance_s:
        raise SignatureError("the webhook timestamp is outside the tolerance window")
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    keys = list(secrets)
    if not keys:
        raise SignatureError("no signing secret to verify with")
    expected = [sign(message_id, timestamp, text, secret).encode() for secret in keys]
    for entry in presented.split():
        candidate = entry.encode("utf-8", errors="replace")
        for want in expected:
            if hmac.compare_digest(candidate, want):
                return message_id
    raise SignatureError("no signature matches")
