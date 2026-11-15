"""A slot tagged ``tl:webhook: omit`` is removed from a webhook body (P2-FORMS S2w).

Delta and full lose the key (absent, not null) for every subscriber; thin never had a detail. The
tag is read from the generated catalog (``tl_schema.catalog.webhook_omit``). The lint half checks
that the tag only sits on event payload slots.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_core.webhooks import envelope
from tl_core.webhooks.envelope import build_envelope, to_body
from tl_core.webhooks.rows import OutboxRow
from tl_core.webhooks.uris import UriConfig
from tl_schema import catalog

STAMP = "2026-11-14T00:00:00+00:00"
SECRET = "SECRET-MARKER-41"
REPO = Path(__file__).resolve().parents[3]


def _row(event_type: str = "Record.Created") -> OutboxRow:
    detail = {"keep": 1, "hush": SECRET, "other": None}
    return OutboxRow(
        seq=1,
        event_id="01EVENT00000000000000000",
        scope="project:P1",
        event_type=event_type,
        stream_id="01S",
        stream_type="core.Record",
        stream_version=1,
        subject_id="01S",
        actor="user:x",
        recorded_at=STAMP,
        correlation_id="c1",
        data={"origin": {"id": "01S"}, "changes": {}, "links": [], "detail": detail},
    )


@pytest.fixture
def tagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        envelope,
        "webhook_omit",
        lambda t: frozenset({"hush"}) if t == "Record.Created" else frozenset(),
    )


@pytest.mark.parametrize("mode", ["delta", "full"])
def test_a_tagged_slot_is_removed_not_nulled(tagged: None, mode: str) -> None:
    body = to_body(build_envelope(_row(), mode, UriConfig("https://x.example")))  # type: ignore[arg-type]
    detail = json.loads(body)["data"]["detail"]
    assert detail == {"keep": 1, "other": None}  # the key is gone; an untagged null stays
    assert SECRET not in body and "hush" not in body


def test_an_untagged_event_is_unchanged(tagged: None) -> None:
    row = _row("Record.Updated")
    body = to_body(build_envelope(row, "delta", UriConfig("https://x.example")))
    assert json.loads(body)["data"]["detail"] == row.data["detail"]


def test_thin_has_no_detail(tagged: None) -> None:
    body = to_body(build_envelope(_row(), "thin", UriConfig("https://x.example")))
    assert "detail" not in json.loads(body)["data"] and SECRET not in body


def test_the_catalog_lists_the_forms_slots() -> None:
    assert catalog.webhook_omit("Submission.DraftSaved") == {"answers"}
    assert catalog.webhook_omit("Submission.Submitted") == {"answers"}
    assert catalog.webhook_omit("IntakeItem.Accepted") == {"on_behalf_of_claim"}
    assert catalog.webhook_omit("Template.Created") == {"form_fields"}
    assert catalog.webhook_omit("Template.Edited") == {"changes"}
    assert catalog.webhook_omit("IntakeCode.Issued") == {"heading"}
    assert catalog.webhook_omit("Record.Created") == frozenset()


def test_the_tag_only_sits_on_event_payload_slots() -> None:
    tagged: list[str] = []
    for path in sorted(
        [*(REPO / "schema" / "core").glob("*.yaml"), *(REPO / "schema" / "modules").rglob("*.yaml")]
    ):
        loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        doc: dict[str, Any] = loaded
        for cname, cls in ((doc or {}).get("classes") or {}).items():
            for sname, slot in ((cls or {}).get("attributes") or {}).items():
                value = ((slot or {}).get("annotations") or {}).get("tl:webhook")
                if value is None:
                    continue
                tagged.append(f"{cname}.{sname}")
                assert value == "omit", (cname, sname, value)
                assert "tl:event_type" in (cls.get("annotations") or {}), (cname, sname)
            assert "tl:webhook" not in (cls or {}).get("annotations", {}), cname
        for sname, slot in ((doc or {}).get("slots") or {}).items():
            assert "tl:webhook" not in ((slot or {}).get("annotations") or {}), sname
    assert len(tagged) == 6  # the catalog test above names the same six
