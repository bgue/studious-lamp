"""File routes: the upload flow, downloads and the HTTP side of the security rules (O2)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, BinaryIO

from harness import ALICE, BOB, SCOPE, Harness
from tl_api.routes.files import content_disposition
from tl_core.files.scan import ScanResult

PDF = b"%PDF-1.7 api test body"


def declare(record_id: str, body: bytes = PDF, **over: Any) -> dict[str, Any]:
    return {
        "scope": SCOPE,
        "record_id": record_id,
        "slot": "report",
        "filename": "mtr.pdf",
        "content_type": "application/pdf",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        **over,
    }


def upload(h: Harness, record_id: str, body: bytes = PDF, actor: str = ALICE, **over: Any) -> Any:
    client = h.client_for(actor)
    ticket = client.post("/uploads", json=declare(record_id, body, **over))
    assert ticket.status_code == 200, ticket.text
    return client.put(
        f"/uploads/{ticket.json()['upload_id']}/content", params={"scope": SCOPE}, content=body
    )


def test_register_send_bytes_list_and_download(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    done = upload(harness, record.stream_id)
    assert done.status_code == 200, done.text
    info = done.json()
    assert info["status"] == "available" and info["revision"] == 1 and info["size"] == len(PDF)

    listed = harness.client.get(f"/records/{record.stream_id}/files", params={"scope": SCOPE})
    assert [f["file_id"] for f in listed.json()] == [info["file_id"]]
    one = harness.client.get(f"/files/{info['file_id']}", params={"scope": SCOPE}).json()
    assert one["filename"] == "mtr.pdf" and one["uploaded_by"] == ALICE

    content = harness.client.get(f"/files/{info['file_id']}/content", params={"scope": SCOPE})
    assert content.status_code == 200 and content.content == PDF
    assert content.headers["x-content-sha256"] == hashlib.sha256(PDF).hexdigest()


def test_downloads_are_attachments_that_must_not_be_sniffed(harness: Harness) -> None:
    """The content type is client-declared, so hostile HTML must never be rendered inline."""
    record = harness.create_record("REC-1")
    body = b"<html><script>alert(1)</script></html>"
    done = upload(
        harness,
        record.stream_id,
        body,
        slot=None,
        filename='"><script>x.html',
        content_type="text/html",
    )
    assert done.status_code == 200, done.text
    response = harness.client.get(
        f"/files/{done.json()['file_id']}/content", params={"scope": SCOPE}
    )
    headers = response.headers
    assert headers["content-type"] == "application/octet-stream"
    assert headers["content-disposition"].startswith("attachment;")
    assert '"><' not in headers["content-disposition"]
    assert headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in headers["content-security-policy"]
    assert "no-store" in headers["cache-control"]
    assert response.content == body


def test_content_disposition_is_safe_for_any_file_name() -> None:
    for name in ['a"b.pdf', "a\r\nSet-Cookie: x=1", "ü ñ.pdf", "../../etc/passwd", "", "..", "x;y"]:
        value = content_disposition(name)
        assert value.startswith("attachment; filename=")
        assert "\r" not in value and "\n" not in value
        assert value.count('"') == 2  # only the two that wrap the ASCII fallback
        assert "../" not in value.split("filename*=")[0]
    assert content_disposition("ü.pdf").endswith("filename*=UTF-8''%C3%BC.pdf")


def test_a_quarantined_file_is_served_to_its_uploader_only(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, scan_inline=False)
    try:
        record = h.create_record("REC-1")
        done = upload(h, record.stream_id)
        assert done.json()["status"] == "quarantined"
        path = f"/files/{done.json()['file_id']}/content"
        refused = h.client_for(BOB).get(path, params={"scope": SCOPE})
        assert refused.status_code == 403 and refused.json()["error"] == "file_quarantined"
        assert PDF not in refused.content
        assert h.client_for(ALICE).get(path, params={"scope": SCOPE}).content == PDF
    finally:
        h.close()


class RejectAll:
    def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
        return ScanResult(clean=False, reason="test verdict")


def test_a_rejected_file_is_gone_for_everyone(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, scanner=RejectAll())
    try:
        record = h.create_record("REC-1")
        done = upload(h, record.stream_id)
        assert done.json()["status"] == "rejected"
        gone = h.client.get(f"/files/{done.json()['file_id']}/content", params={"scope": SCOPE})
        assert gone.status_code == 410 and gone.json()["error"] == "file_rejected"
    finally:
        h.close()


def test_the_server_checks_the_bytes_against_the_declaration(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    client = harness.client
    ticket = client.post("/uploads", json=declare(record.stream_id)).json()
    wrong = client.put(
        f"/uploads/{ticket['upload_id']}/content", params={"scope": SCOPE}, content=b"%PDF-other!!"
    )
    assert wrong.status_code == 400 and wrong.json()["error"] == "upload_verification"
    listed = client.get(f"/records/{record.stream_id}/files", params={"scope": SCOPE}).json()
    assert listed == []


def test_an_upload_id_is_not_transferable(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    ticket = harness.client.post("/uploads", json=declare(record.stream_id)).json()
    stolen = harness.client_for(BOB).put(
        f"/uploads/{ticket['upload_id']}/content", params={"scope": SCOPE}, content=PDF
    )
    assert stolen.status_code == 400 and stolen.json()["error"] == "upload_token"
    garbage = harness.client.put(
        "/uploads/not-a-token/content", params={"scope": SCOPE}, content=PDF
    )
    assert garbage.status_code == 400


def test_a_body_over_the_server_limit_is_413(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    big = b"x" * (harness.settings.max_upload_bytes + 1)
    ticket = harness.client.post(
        "/uploads", json=declare(record.stream_id, big, slot=None, content_type="text/plain")
    ).json()
    response = harness.client.put(
        f"/uploads/{ticket['upload_id']}/content", params={"scope": SCOPE}, content=big
    )
    assert response.status_code == 413 and response.json()["error"] == "file_too_large"


def test_known_bytes_are_attached_without_sending_them_again(harness: Harness) -> None:
    first = harness.create_record("REC-1")
    second = harness.create_record("REC-2")
    assert upload(harness, first.stream_id).status_code == 200
    ticket = harness.client.post("/uploads", json=declare(second.stream_id)).json()
    assert ticket["exists"] is True and ticket["upload_url"] is None
    done = harness.client.post(f"/uploads/{ticket['upload_id']}/complete", params={"scope": SCOPE})
    assert done.status_code == 200 and done.json()["deduplicated"] is True
    attached = harness.client.post("/files/attach", json=declare(second.stream_id, slot=None))
    assert attached.status_code == 200, attached.text


def test_a_slot_the_record_does_not_declare_is_422(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    response = harness.client.post("/uploads", json=declare(record.stream_id, slot="nonesuch"))
    assert response.status_code == 422 and response.json()["error"] == "unknown_slot"


def test_a_file_in_another_scope_is_not_found(harness: Harness) -> None:
    record = harness.create_record("REC-1")
    done = upload(harness, record.stream_id).json()
    other = harness.client.get(f"/files/{done['file_id']}", params={"scope": "project:P999"})
    assert other.status_code == 404 and other.json()["error"] == "file_not_found"


def test_without_file_storage_the_routes_answer_503(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, files=False)
    try:
        record = h.create_record("REC-1")
        response = h.client.post("/uploads", json=declare(record.stream_id))
        assert response.status_code == 503 and response.json()["error"] == "unavailable"
        listed = h.client.get(f"/records/{record.stream_id}/files", params={"scope": SCOPE})
        assert listed.status_code == 200  # metadata needs no store
    finally:
        h.close()
