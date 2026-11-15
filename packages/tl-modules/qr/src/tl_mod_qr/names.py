"""Names the QR module shares: record type, table, event types, access words."""

from __future__ import annotations

from typing import Final

SCAN_CODE: Final = "qr.ScanCode"
RECORD_TYPES: Final = frozenset({SCAN_CODE})

SCAN_CODE_TABLE: Final = "cur_qr_scan_code"
SCAN_CODE_VIEW: Final = "v_qr_scan_code"

SCAN_CODE_ISSUED: Final = "ScanCode.Issued"
SCAN_CODE_REVOKED: Final = "ScanCode.Revoked"
SCAN_CODE_EVENTS: Final = frozenset({SCAN_CODE_ISSUED, SCAN_CODE_REVOKED})

#: Access words (``schema/settings/access-words.yaml``).
VIEW: Final = "qr.view"
ISSUE: Final = "qr.issue"
REVOKE: Final = "qr.revoke"

DEFAULT_SIZE: Final = "tag"
FEED_NONE: Final = "none"
