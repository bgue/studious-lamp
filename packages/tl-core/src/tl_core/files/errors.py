"""Errors raised by object store backends (P0-I4).

They sit beside ``files/types.py`` (the frozen contract) so that ``tl_core`` can catch what
``tl_adapters`` raises without importing an adapter. Both derive from ``ValueError``.
"""

from __future__ import annotations


class ObjectIntegrityError(ValueError):
    """The bytes handed to ``ObjectStore.put`` do not match the declared size or SHA-256.

    Nothing was stored: the object never became visible.
    """


class InvalidObjectKey(ValueError):
    """A key that a backend refuses: empty, absolute, or containing ``..`` or unusual characters."""


class PresignError(ValueError):
    """A presigned URL (fs backend) that cannot be redeemed."""


class PresignInvalid(PresignError):
    """The URL is malformed, for another operation, or its signature does not verify."""


class PresignExpired(PresignError):
    """The URL's expiry time has passed."""
