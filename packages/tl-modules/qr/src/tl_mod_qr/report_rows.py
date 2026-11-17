"""The QR module's line-level report (``tl report qr-codes``; V3-P0c).

One row per scan code of the project, oldest first (issue time, then label), through one select
with ``confidentiality.not_hidden`` on the code's subject (``qr.ScanCode`` is in
``SUBJECT_LINKS``): a code whose subject the viewer may not read is not a row. The report checks
the module word ``qr.view`` first, as the register routes do. Columns are the register fields and
the subject's key; never a code, a token, a hash or a salt, and nothing a scan URL can be rebuilt
from (no register id either).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.modules import Report
from tl_core.util import utcnow

from tl_mod_qr import MODULE
from tl_mod_qr.names import SCAN_CODE_TABLE, VIEW
from tl_mod_qr.views import _state

#: The page size the select is read with (a monkeypatched value in the tests).
_PAGE: Final = 500
QR_COLUMNS: Final = (
    "label_text", "size", "state", "subject_key", "issued_by", "issued_at", "expires_on",
    "revoked_at",
)  # fmt: skip


def qr_code_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    require_word(
        conn,
        holder_for_actor(conn, viewer.actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(VIEW),
        what=VIEW,
    )
    today = utcnow().date().isoformat()
    visible, extra = confidentiality.not_hidden("c.target_id", viewer)
    statement = text(
        "SELECT c.label_text, c.size, c.issued_by, c.issued_at, c.expires_on, c.revoked_at, "
        "s.key AS subject_key "
        f"FROM {SCAN_CODE_TABLE} c JOIN cur_core_record s ON s.id = c.target_id "
        f"WHERE c.scope = :scope AND {visible} "
        "ORDER BY c.issued_at, c.label_text, c.id LIMIT :limit OFFSET :offset"
    )
    offset = 0
    while True:
        params: dict[str, Any] = {"scope": scope, "limit": _PAGE, "offset": offset, **extra}
        page = list(conn.execute(statement, params).mappings())
        for raw in page:
            yield {
                "label_text": raw["label_text"],
                "size": raw["size"],
                "state": _state(raw["revoked_at"], raw["expires_on"], today),
                "subject_key": raw["subject_key"],
                "issued_by": raw["issued_by"],
                "issued_at": raw["issued_at"],
                "expires_on": raw["expires_on"],
                "revoked_at": raw["revoked_at"],
            }
        offset += len(page)
        if len(page) < _PAGE:
            return


REPORTS: Final = (Report("qr-codes", "QR scan codes", QR_COLUMNS, qr_code_rows),)
