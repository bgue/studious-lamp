"""Ed25519 signing for archive manifests (brief 24.3; fanout decision D2).

The dev key is a PKCS#8 PEM private key at ``dev/data/archive-signing.key`` (mode 0600, git-ignored)
with the raw public key as hex beside it (``.pub``). ``key_id`` is the first 16 hex characters of
the SHA-256 of the raw 32-byte public key. Production key custody (KMS, HSM) is a later decision.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DEFAULT_KEY_PATH = Path("dev/data/archive-signing.key")


def key_id_of(public_key: bytes) -> str:
    """The key id of a raw 32-byte Ed25519 public key."""
    return hashlib.sha256(public_key).hexdigest()[:16]


def public_bytes(key: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    """The raw 32 bytes of a key's public half."""
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class Signer(Protocol):
    """Signs manifest bytes. ``key_id`` names the public key that verifies the signature."""

    key_id: str

    def sign(self, data: bytes) -> bytes: ...


class Ed25519Signer:
    """A ``Signer`` backed by an in-memory Ed25519 private key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key
        self.public_key = public_bytes(private_key)
        self.key_id = key_id_of(self.public_key)

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(data)

    def private_pem(self) -> bytes:
        """The private key as an unencrypted PKCS#8 PEM (for ``write_keypair``)."""
        return self._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )


def public_key_path(private_path: Path) -> Path:
    """Where the public key of the private key at ``private_path`` is kept."""
    return private_path.with_suffix(".pub")


def generate_signer() -> Ed25519Signer:
    """A fresh signer with a new random key (tests; ``write_keypair`` for the CLI)."""
    return Ed25519Signer(Ed25519PrivateKey.generate())


def write_keypair(path: Path, *, overwrite: bool = False) -> Ed25519Signer:
    """Create a key pair at ``path`` (private PEM) and ``path.with_suffix('.pub')`` (hex).

    Refuses to replace an existing key unless ``overwrite``: a replaced key makes every sealed
    segment unverifiable with the new public key.
    """
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists; refusing to replace the signing key")
    signer = generate_signer()
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = signer.private_pem()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(
        fd, 0o600
    )  # the mode above applies only to a new file; an overwrite keeps the old one
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
    public_key_path(path).write_text(signer.public_key.hex() + "\n", encoding="utf-8")
    return signer


def load_signer(path: Path) -> Ed25519Signer:
    """The signer for the PEM private key at ``path``."""
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    return Ed25519Signer(loaded)


def load_public_key(path: Path) -> bytes:
    """The raw public key from a ``.pub`` hex file, a public-key PEM, or the private-key PEM."""
    data = path.read_bytes()
    stripped = data.strip()
    if len(stripped) == 64:
        try:
            return bytes.fromhex(stripped.decode("ascii"))
        except ValueError:
            pass
    if b"PRIVATE KEY" in data:
        loaded = serialization.load_pem_private_key(data, password=None)
        if isinstance(loaded, Ed25519PrivateKey):
            return public_bytes(loaded)
    else:
        public = serialization.load_pem_public_key(data)
        if isinstance(public, Ed25519PublicKey):
            return public_bytes(public)
    raise ValueError(f"{path} does not hold an Ed25519 key")


def verify_signature(public_key: bytes, signature_b64: str, data: bytes) -> bool:
    """True when ``signature_b64`` is a valid Ed25519 signature of ``data`` under ``public_key``."""
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(base64.b64decode(signature_b64, validate=True), data)
    except (InvalidSignature, ValueError):
        return False
    return True
