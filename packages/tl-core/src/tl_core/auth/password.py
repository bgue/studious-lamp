"""Password policy and hashing (ADR-0009 sections 2 and 3). Standard library only.

* ``hash_password`` stores ``scrypt$<log2 N>$<r>$<p>$<salt>$<hash>`` (URL-safe base64, no padding).
* ``verify_password`` always runs one full scrypt, also when there is no stored hash, so the time
  does not tell a caller whether the account exists. It returns ``False`` for a malformed or
  out-of-bounds stored value instead of raising or allocating what the value asks for.
* At most ``MAX_CONCURRENT_HASHES`` hashes run at once in a process.
* The password is NFKC-normalised, then UTF-8 encoded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import unicodedata
from dataclasses import dataclass

from tl_core.auth.errors import WeakPasswordError

log = logging.getLogger("tl_core.auth")

SCHEME = "scrypt"
MIN_LENGTH = 12
MAX_LENGTH = 128
MAX_CONCURRENT_HASHES = 4
#: Bounds a stored hash may ask for. A tampered row cannot make the server allocate more.
MAX_LOG2_N = 20
MAX_R = 16
MAX_P = 16
SALT_BYTES = 16
HASH_BYTES = 32


@dataclass(frozen=True)
class ScryptParams:
    """scrypt cost. The default is the OWASP profile N=2^16, r=8, p=2 (64 MiB)."""

    log2_n: int = 16
    r: int = 8
    p: int = 2

    def weaker_than(self, other: ScryptParams) -> bool:
        return (self.log2_n, self.r, self.p) < (other.log2_n, other.r, other.p)


PRODUCTION_PARAMS = ScryptParams()
_current = PRODUCTION_PARAMS
_gate = threading.BoundedSemaphore(MAX_CONCURRENT_HASHES)


def current_params() -> ScryptParams:
    """The cost new hashes get (and ``needs_rehash`` compares against)."""
    return _current


def configure(params: ScryptParams) -> ScryptParams:
    """Set the cost of new hashes and return the previous one. Tests use this for a cheap cost."""
    global _current
    if not 1 <= params.log2_n <= MAX_LOG2_N or not 1 <= params.r <= MAX_R:
        raise ValueError("scrypt parameters are out of bounds")
    if not 1 <= params.p <= MAX_P:
        raise ValueError("scrypt parameters are out of bounds")
    previous, _current = _current, params
    return previous


def normalize_password(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrypt(password: str, salt: bytes, params: ScryptParams) -> bytes:
    n = 1 << params.log2_n
    need = 128 * n * params.r + 128 * params.r * params.p
    with _gate:
        return hashlib.scrypt(
            normalize_password(password).encode("utf-8"),
            salt=salt,
            n=n,
            r=params.r,
            p=params.p,
            maxmem=2 * need + (1 << 20),
            dklen=HASH_BYTES,
        )


def hash_password(password: str, params: ScryptParams | None = None) -> str:
    """The stored form of ``password``. The caller has already applied the policy."""
    use = params if params is not None else _current
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, use)
    return f"{SCHEME}${use.log2_n}${use.r}${use.p}${_b64(salt)}${_b64(digest)}"


def _parse(stored: str) -> tuple[ScryptParams, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        return None
    try:
        params = ScryptParams(int(parts[1]), int(parts[2]), int(parts[3]))
        salt, digest = _unb64(parts[4]), _unb64(parts[5])
    except ValueError:
        return None
    if not 1 <= params.log2_n <= MAX_LOG2_N or not 1 <= params.r <= MAX_R:
        return None
    if not 1 <= params.p <= MAX_P or len(salt) < 8 or len(digest) != HASH_BYTES:
        return None
    return params, salt, digest


def verify_password(stored: str | None, password: str) -> bool:
    """Whether ``password`` matches ``stored``. Costs one scrypt even when ``stored`` is unusable.

    ``None``, a malformed value, an out-of-bounds one and an over-long password all run one scrypt
    of the current cost with a random salt, and return ``False``.
    """
    parsed = _parse(stored) if stored is not None else None
    if parsed is None or len(normalize_password(password)) > MAX_LENGTH:
        if stored is not None and parsed is None:
            log.warning("a stored password hash is malformed or out of bounds")
        _scrypt(password[:MAX_LENGTH], secrets.token_bytes(SALT_BYTES), _current)
        return False
    params, salt, digest = parsed
    candidate = _scrypt(password, salt, params)
    return hmac.compare_digest(candidate, digest)


def needs_rehash(stored: str) -> bool:
    """True when ``stored`` is weaker than the current cost (or unreadable)."""
    parsed = _parse(stored)
    return parsed is None or parsed[0].weaker_than(_current)


#: Passwords of at least the minimum length that appear in every breach list.
COMMON_PASSWORDS = frozenset(
    {
        "password1234",
        "password12345",
        "passwordpassword",
        "password123456",
        "123456789012",
        "1234567890123",
        "12345678901234",
        "qwertyuiop12",
        "qwertyuiopas",
        "qwertyuiop123",
        "qwertyqwerty",
        "1q2w3e4r5t6y",
        "1qaz2wsx3edc",
        "abcdefghijkl",
        "abcdefghijklmnop",
        "administrator",
        "administrator1",
        "welcome12345",
        "welcomewelcome",
        "letmeinletmein",
        "iloveyou1234",
        "changemechangeme",
        "changeme1234",
        "trustno1trustno1",
        "monkeymonkey",
        "dragondragon",
        "footballfootball",
        "baseballbaseball",
        "superman1234",
        "internet12345",
        "throughline",
        "throughline1",
        "throughline123",
        "throughline1234",
    }
)


def check_policy(password: str, *, username: str | None = None) -> None:
    """Raise ``WeakPasswordError`` listing what is wrong; never echoes the password."""
    text = normalize_password(password)
    issues: list[str] = []
    if len(text) < MIN_LENGTH:
        issues.append(f"must be at least {MIN_LENGTH} characters")
    if len(text) > MAX_LENGTH:
        issues.append(f"must be at most {MAX_LENGTH} characters")
    if any(unicodedata.category(ch) == "Cc" for ch in text):
        issues.append("must not contain control characters")
    if text and len(set(text)) == 1:
        issues.append("must not be one repeated character")
    folded = text.casefold()
    if folded in COMMON_PASSWORDS:
        issues.append("is one of the most common passwords")
    if username is not None and folded == username.casefold():
        issues.append("must not be the username")
    if issues:
        raise WeakPasswordError("password does not meet the policy: " + "; ".join(issues), issues)
