"""Reconciliation when the store changes underneath it (P0-I4-B, from the T25 report)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import BinaryIO

from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.files import ObjectNotFound, object_key
from tl_core.files.reconcile import reconcile_objects

BODY = b"vanishing"
DIGEST = hashlib.sha256(BODY).hexdigest()


class Vanishing:
    """exists() says yes, then the object is gone by the time it is read."""

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        raise AssertionError("not used")

    def get(self, key: str) -> BinaryIO:
        raise ObjectNotFound(key)

    def exists(self, key: str) -> bool:
        return True

    def presign_put(self, key: str, *, expires_s: int) -> str:
        raise AssertionError("not used")

    def presign_get(self, key: str, *, expires_s: int) -> str:
        raise AssertionError("not used")


def test_an_object_that_vanishes_during_verification_is_reported_missing(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    with open_uow(db) as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_files (file_id, scope, record_id, slot, revision, sha256, size, "
                "content_type, filename, status, deduplicated, uploaded_by, uploaded_at, "
                "updated_at, version, last_seq) VALUES ('F-1', 'project:P123', 'REC', NULL, 1, "
                ":sha, :size, 'text/plain', 'f.txt', 'available', FALSE, 'user:t', "
                "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 1, 1)"
            ),
            {"sha": DIGEST, "size": len(BODY)},
        )
    with open_uow(db, readonly=True) as uow:
        report = reconcile_objects(uow, Vanishing(), verify=True)
    assert not report.ok and report.corrupt == []
    (problem,) = report.missing
    assert problem.key == object_key(DIGEST) and problem.file_ids == ["F-1"]
