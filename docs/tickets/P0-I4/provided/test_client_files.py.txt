"""HTTP client: files (P0-I4-T48)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import BinaryIO

import httpx2
import pytest
from harness import BOB, SCOPE, Harness
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_core.files.scan import ScanResult
from tl_core.files.service import AttachFile, RegisterUpload
from tl_core.services.errors import (
    FileQuarantinedError,
    FileRejectedError,
    UnknownFileError,
    UploadVerificationError,
)

PDF = b"%PDF-1.7 client test body"


def pdf_file(tmp_path: Path, body: bytes = PDF, name: str = "mtr.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(body)
    return path


def declare(record_id: str, body: bytes = PDF, **over: object) -> RegisterUpload:
    fields: dict[str, object] = {
        "actor": "user:ignored",
        "source": "tui",
        "scope": SCOPE,
        "record_id": record_id,
        "slot": "report",
        "filename": "mtr.pdf",
        "content_type": "application/pdf",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        **over,
    }
    return RegisterUpload(**fields)  # type: ignore[arg-type]


def test_upload_file_list_info_and_download(harness: Harness, tmp_path: Path) -> None:
    record = harness.create_record("REC-1")
    api = harness.api()
    result = api.upload_file(SCOPE, record.stream_id, pdf_file(tmp_path), slot="report")
    assert result.status == "available" and result.revision == 1 and result.size == len(PDF)
    (listed,) = api.list_files(SCOPE, record.stream_id)
    assert listed.file_id == result.file_id and listed.filename == "mtr.pdf"
    assert api.list_files(SCOPE, record.stream_id, slot="other") == []
    assert api.get_file_info(SCOPE, result.file_id) == listed
    assert api.download_file(SCOPE, result.file_id) == PDF
    sink = io.BytesIO()
    assert api.download_to(SCOPE, result.file_id, sink) == len(PDF)
    assert sink.getvalue() == PDF


def test_the_same_bytes_for_another_record_skip_the_upload(
    harness: Harness, tmp_path: Path
) -> None:
    first = harness.create_record("REC-1")
    second = harness.create_record("REC-2")
    api = harness.api()
    path = pdf_file(tmp_path)
    api.upload_file(SCOPE, first.stream_id, path, slot="report")
    ticket = api.register_upload(declare(second.stream_id))
    assert ticket.exists is True and ticket.upload_url is None
    done = api.upload_file(SCOPE, second.stream_id, path, slot="report")
    assert done.deduplicated is True and done.record_id == second.stream_id
    attached = api.attach_file(AttachFile(**declare(second.stream_id, slot=None).model_dump()))
    assert attached.record_id == second.stream_id


def test_the_manual_flow_and_its_refusals(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    api = harness.api()
    ticket = api.register_upload(declare(record.stream_id))
    assert ticket.exists is False and ticket.upload_id
    with pytest.raises(UploadVerificationError):
        api.upload_content(ticket.upload_id, SCOPE, b"%PDF-other bytes!!!!!!")
    done = api.upload_content(ticket.upload_id, SCOPE, io.BytesIO(PDF))
    assert done.status == "available"
    with pytest.raises(UnknownFileError):
        api.get_file_info(SCOPE, "01NOSUCHFILE")
    with pytest.raises(UnknownFileError):
        api.download_file(SCOPE, "01NOSUCHFILE")
    other = harness.api(BOB)
    ticket2 = api.register_upload(declare(record.stream_id, slot=None))
    with pytest.raises(Exception, match="someone else|token"):
        other.upload_content(ticket2.upload_id, SCOPE, PDF)


def test_a_quarantined_file_is_the_uploaders_only(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, scan_inline=False)
    try:
        record = h.create_record("REC-1")
        result = h.api().upload_file(SCOPE, record.stream_id, pdf_file(tmp_path), slot="report")
        assert result.status == "quarantined"
        with pytest.raises(FileQuarantinedError):
            h.api(BOB).download_file(SCOPE, result.file_id)
        with pytest.raises(FileQuarantinedError):
            h.api(BOB).download_to(SCOPE, result.file_id, io.BytesIO())
        assert h.api().download_file(SCOPE, result.file_id) == PDF
    finally:
        h.close()


class RejectAll:
    def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
        return ScanResult(clean=False, reason="test verdict")


def test_a_rejected_file_raises_file_rejected(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, scanner=RejectAll())
    try:
        record = h.create_record("REC-1")
        result = h.api().upload_file(SCOPE, record.stream_id, pdf_file(tmp_path), slot="report")
        assert result.status == "rejected"
        with pytest.raises(FileRejectedError):
            h.api().download_file(SCOPE, result.file_id)
    finally:
        h.close()


def test_without_file_storage_the_calls_raise_api_error_503(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, files=False)
    try:
        record = h.create_record("REC-1")
        with pytest.raises(ApiError) as caught:
            h.api().upload_file(SCOPE, record.stream_id, pdf_file(tmp_path), slot="report")
        assert caught.value.status == 503 and caught.value.error == "unavailable"
    finally:
        h.close()


def mock_client(body: bytes, sha: str | None) -> ApiClient:
    headers = {} if sha is None else {"x-content-sha256": sha}
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, content=body, headers=headers)
    )
    return ApiClient("http://x", "t", http=httpx2.Client(transport=transport, base_url="http://x"))


def test_a_download_that_does_not_match_the_servers_digest_is_refused() -> None:
    good = hashlib.sha256(b"hello").hexdigest()
    assert mock_client(b"hello", good).download_file(SCOPE, "f") == b"hello"
    assert mock_client(b"hello", None).download_file(SCOPE, "f") == b"hello"  # no header, no check
    with pytest.raises(ValueError, match="SHA-256"):
        mock_client(b"tampered", good).download_file(SCOPE, "f")
    with pytest.raises(ValueError, match="SHA-256"):
        mock_client(b"tampered", good).download_to(SCOPE, "f", io.BytesIO())
