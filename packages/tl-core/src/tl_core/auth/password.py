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
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from tl_core.auth.errors import AuthBusyError, WeakPasswordError

log = logging.getLogger("tl_core.auth")

SCHEME = "scrypt"
MIN_LENGTH = 12
MAX_LENGTH = 128
MAX_CONCURRENT_HASHES = 4
#: Slots a sign-in (public) hash may hold at once; the rest are kept for admin and local operations.
PUBLIC_HASH_SLOTS = 3
#: Seconds a hash waits for a free slot before ``AuthBusyError`` (503, retry shortly).
GATE_TIMEOUT_S = 2.0
MIN_DISTINCT_CHARACTERS = 5
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


class HashGate:
    """At most ``MAX_CONCURRENT_HASHES`` hashes at once, of which ``PUBLIC_HASH_SLOTS`` public ones.

    The slot beyond that is kept for admin and local operations (create, reset, bootstrap), so a
    flood of sign-ins cannot stop an admin from working. ``acquire`` and ``release`` without
    ``public=True`` take any free slot.
    """

    def __init__(self, total: int, public: int) -> None:
        self._total, self._public = total, public
        self._used = 0
        self._used_public = 0
        self._cond = threading.Condition()

    def acquire(self, timeout: float | None = None, *, public: bool = False) -> bool:
        with self._cond:
            ok = self._cond.wait_for(
                lambda: (
                    self._used < self._total and (not public or self._used_public < self._public)
                ),
                timeout,
            )
            if not ok:
                return False
            self._used += 1
            self._used_public += 1 if public else 0
            return True

    def release(self, *, public: bool = False) -> None:
        with self._cond:
            self._used -= 1
            self._used_public -= 1 if public else 0
            self._cond.notify_all()


_gate = HashGate(MAX_CONCURRENT_HASHES, PUBLIC_HASH_SLOTS)


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


#: Which lane the hash in this context uses; ``_scrypt`` keeps the plain three-argument call that
#: tests wrap, so the lane travels in a context variable.
_PUBLIC_LANE: ContextVar[bool] = ContextVar("tl_hash_public_lane", default=True)


def _scrypt(password: str, salt: bytes, params: ScryptParams) -> bytes:
    public = _PUBLIC_LANE.get()
    n = 1 << params.log2_n
    need = 128 * n * params.r + 128 * params.r * params.p
    if not _gate.acquire(timeout=GATE_TIMEOUT_S, public=public):
        raise AuthBusyError("too many sign-ins are being checked; try again in a moment")
    try:
        return hashlib.scrypt(
            normalize_password(password).encode("utf-8"),
            salt=salt,
            n=n,
            r=params.r,
            p=params.p,
            maxmem=2 * need + (1 << 20),
            dklen=HASH_BYTES,
        )
    finally:
        _gate.release(public=public)


def is_clean(text: str, limit: int) -> bool:
    """Whether ``text`` is storable and hashable: at most ``limit`` characters, no NUL, valid UTF-8.

    A lone surrogate does not encode, and a NUL breaks a Postgres parameter; both make a sign-in
    input invalid rather than an error (ADR-0009 section 7).
    """
    if len(text) > limit or "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def hash_password(password: str, params: ScryptParams | None = None, *, public: bool = True) -> str:
    """The stored form of ``password``. The caller has already applied the policy.

    ``public=False`` is for admin and local operations: they may use the slot kept back from
    sign-ins (see :class:`HashGate`).
    """
    use = params if params is not None else _current
    salt = secrets.token_bytes(SALT_BYTES)
    token = _PUBLIC_LANE.set(public)
    try:
        digest = _scrypt(password, salt, use)
    finally:
        _PUBLIC_LANE.reset(token)
    return f"{SCHEME}${use.log2_n}${use.r}${use.p}${_b64(salt)}${_b64(digest)}"


def _ceiling() -> ScryptParams:
    """The most a stored hash may ask for: twice the cost of what this process makes (ADR-0009).

    "Twice" is one more bit of N, and double r and p, of the larger of the configured and the
    production cost, so a tampered row cannot make a sign-in allocate more than that.
    """
    top = ScryptParams(
        max(_current.log2_n, PRODUCTION_PARAMS.log2_n),
        max(_current.r, PRODUCTION_PARAMS.r),
        max(_current.p, PRODUCTION_PARAMS.p),
    )
    return ScryptParams(
        min(top.log2_n + 1, MAX_LOG2_N), min(top.r * 2, MAX_R), min(top.p * 2, MAX_P)
    )


def _parse(stored: str) -> tuple[ScryptParams, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        return None
    try:
        params = ScryptParams(int(parts[1]), int(parts[2]), int(parts[3]))
        salt, digest = _unb64(parts[4]), _unb64(parts[5])
    except ValueError:
        return None
    ceiling = _ceiling()
    if not 1 <= params.log2_n <= ceiling.log2_n or not 1 <= params.r <= ceiling.r:
        return None
    if not 1 <= params.p <= ceiling.p or len(salt) < 8 or len(digest) != HASH_BYTES:
        return None
    return params, salt, digest


def verify_password(stored: str | None, password: str) -> bool:
    """Whether ``password`` matches ``stored``. Costs one scrypt even when ``stored`` is unusable.

    ``None``, a malformed value, an out-of-bounds one, a password that cannot be hashed (NUL, a
    lone surrogate) and an over-long one all run one scrypt of the current cost with a random salt,
    and return ``False``.
    """
    parsed = _parse(stored) if stored is not None else None
    clean = is_clean(password, 4 * MAX_LENGTH) and len(normalize_password(password)) <= MAX_LENGTH
    if parsed is None or not clean:
        if stored is not None and parsed is None:
            log.warning("a stored password hash is malformed or out of bounds")
        _scrypt(password[:MAX_LENGTH] if clean else "", secrets.token_bytes(SALT_BYTES), _current)
        return False
    params, salt, digest = parsed
    try:
        candidate = _scrypt(password, salt, params)
    except ValueError:  # parameters inside the bounds that scrypt itself refuses (N too big for r)
        log.warning("a stored password hash has parameters scrypt refuses")
        _scrypt(password[:MAX_LENGTH], secrets.token_bytes(SALT_BYTES), _current)
        return False
    return hmac.compare_digest(candidate, digest)


def needs_rehash(stored: str) -> bool:
    """True when ``stored`` is weaker than the current cost (or unreadable)."""
    parsed = _parse(stored)
    return parsed is None or parsed[0].weaker_than(_current)


#: Product names and the like, on top of the data file.
EXTRA_COMMON = frozenset({"throughline", "throughline1", "throughline123", "throughline1234"})


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    """The data file ``common_passwords.txt`` (30,000 entries, MIT, see its header) as a set."""
    text = files("tl_core.auth").joinpath("common_passwords.txt").read_text(encoding="utf-8")
    found = {
        line.strip().casefold()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    }
    return frozenset(found) | EXTRA_COMMON


def _is_common(folded: str) -> str | None:
    """Why ``folded`` (case-folded) is a common password, else ``None``.

    Either the whole value is on the list, or it is a listed word of four letters or more with
    only digits and symbols around it ("password1234!").
    """
    common = common_passwords()
    if folded in common:
        return "is one of the most common passwords"
    stripped = folded.strip("".join(ch for ch in set(folded) if not ch.isalpha()))
    if len(stripped) >= 4 and stripped in common:
        return "is a common password with digits or symbols added"
    return None


def check_policy(password: str, *, username: str | None = None) -> None:
    """Raise ``WeakPasswordError`` listing what is wrong; never echoes the password."""
    if not is_clean(password, 4 * MAX_LENGTH):
        raise WeakPasswordError(
            "password does not meet the policy: contains characters that cannot be stored",
            ["contains characters that cannot be stored (NUL or an invalid character)"],
        )
    text = normalize_password(password)
    issues: list[str] = []
    if len(text) < MIN_LENGTH:
        issues.append(f"must be at least {MIN_LENGTH} characters")
    if len(text) > MAX_LENGTH:
        issues.append(f"must be at most {MAX_LENGTH} characters")
    if any(unicodedata.category(ch) == "Cc" for ch in text):
        issues.append("must not contain control characters")
    if text and all(unicodedata.category(ch) in ("Zs", "Zl", "Zp", "Cf") for ch in text):
        issues.append("must not be only spaces or invisible characters")
    elif len(set(text)) < MIN_DISTINCT_CHARACTERS:
        issues.append(f"must use at least {MIN_DISTINCT_CHARACTERS} different characters")
    folded = text.casefold()
    reason = _is_common(folded)
    if reason is not None:
        issues.append(reason)
    if username is not None and folded == username.casefold():
        issues.append("must not be the username")
    if issues:
        raise WeakPasswordError("password does not meet the policy: " + "; ".join(issues), issues)


@dataclass(frozen=True)
class PreparedPassword:
    """A password that has met the policy and been hashed, ready to store in a transaction.

    The services take this, not the password, so the slow hash never runs while a write
    transaction holds the writer lock (ADR-0009 section 2).
    """

    hash: str

    def __repr__(self) -> str:
        return "PreparedPassword(<hidden>)"

    __str__ = __repr__


def prepare_password(
    password: str,
    *,
    username: str | None = None,
    enforce_policy: bool = True,
    public: bool = False,
) -> PreparedPassword:
    """Apply the policy (``WeakPasswordError``) and hash. Call it before opening a transaction.

    By default it counts as an admin or local operation and may use the reserved hash slot;
    ``sessions.change_own_password`` passes ``public=True``: any signed-in person can call it.

    Only the documented demo seed passes ``enforce_policy=False``; the password must still be
    storable.
    """
    if enforce_policy:
        check_policy(password, username=username)
    elif not is_clean(password, 4 * MAX_LENGTH):
        raise WeakPasswordError("password contains characters that cannot be stored")
    return PreparedPassword(hash_password(password, public=public))
