"""Resolve a typed or scanned code to a status card (P2-QR S2).

One exit for every miss: a malformed code, an unknown one, a revoked one, an expired one, a code
whose target the viewer may not read, a viewer without the provider's view word, a record type with
no provider and a provider that fails all answer ``None``. Nothing tells them apart. It never
writes and never logs the code.

Order: normalise (a malformed code runs no statement at all), the hash lookup (the first statement,
before any other work; the class filter is part of it), state and expiry, the provider, the view
word, the card.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, holds_word, normalise_word
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.qr import registry
from tl_core.qr.types import ScanCard

from tl_mod_qr.codes import code_hash, normalise_code
from tl_mod_qr.names import SCAN_CODE_TABLE

_LOOKUP = (
    "SELECT c.scope, c.target_id, c.target_type, c.expires_on, c.revoked_at "
    f"FROM {SCAN_CODE_TABLE} c WHERE c.code_hash = :h AND "
)


def _view_word_held(conn: Connection, viewer: Viewer, word: str, scope: str) -> bool:
    """Whether ``viewer`` holds the provider's ``view_word`` in ``scope`` (fail closed)."""
    if not viewer.actor:
        return False
    try:
        return holds_word(
            conn,
            holder_for_actor(conn, viewer.actor),
            scope=scope,
            module=word.partition(".")[0],
            word=normalise_word(word),
        )
    except Exception:
        return False


def resolve(
    conn: Connection, code: str, viewer: Viewer = LOWEST, now: datetime | None = None
) -> ScanCard | None:
    """The card for ``code`` as ``viewer`` sees it, or ``None`` (every miss alike)."""
    plain = normalise_code(code)
    if plain is None:
        return None
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    clause, params = confidentiality.not_hidden_each("c.id", viewer)
    row = conn.execute(text(_LOOKUP + clause), {"h": code_hash(plain), **params}).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_on is not None and str(row.expires_on)[:10] < moment.date().isoformat():
        return None
    try:
        provider = registry.load_scan_cards().get(str(row.target_type))
    except registry.ScanCardLoadError:
        return None
    if provider is None or not _view_word_held(conn, viewer, provider.view_word, str(row.scope)):
        return None
    try:
        card = provider.card(conn, str(row.target_id), viewer, moment)
    except Exception:
        return None
    return card if isinstance(card, ScanCard) else None  # pyright: ignore[reportUnnecessaryIsInstance]
