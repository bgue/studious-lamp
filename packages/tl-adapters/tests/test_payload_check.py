"""Append validation: modes, collection, unknown event types."""

from __future__ import annotations

import pytest
from tl_adapters import _payload_check as pc


class _Ev:
    def __init__(self, event_type: str, payload: dict[str, object], version: int = 1) -> None:
        self.event_type, self.payload, self.schema_version = event_type, payload, version


@pytest.fixture(autouse=True)
def _isolate() -> object:
    saved = pc.VIOLATIONS.copy()
    pc.VIOLATIONS.clear()
    yield None
    pc.VIOLATIONS.clear()
    pc.VIOLATIONS.update(saved)


def test_known_event_with_extra_key_is_a_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_PAYLOAD_VALIDATION", "collect")
    pc.validate_events([_Ev("Link.Verified", {"link_id": "x", "bogus": 1})])
    assert any(e == "Link.Verified" and k == "bogus" for (e, k, _r) in pc.VIOLATIONS)


def test_collect_does_not_raise_and_unknown_type_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TL_PAYLOAD_VALIDATION", "collect")
    pc.validate_events([_Ev("No.Such.Event", {})])
    assert ("No.Such.Event", "-", pc.NO_CLASS) in pc.VIOLATIONS


def test_enforce_raises_on_violation_but_not_on_missing_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TL_PAYLOAD_VALIDATION", "enforce")
    pc.validate_events([_Ev("No.Such.Event", {})])
    with pytest.raises(pc.PayloadInvalid, match="Link.Verified"):
        pc.validate_events([_Ev("Link.Verified", {"bogus": 1})])


def test_off_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_PAYLOAD_VALIDATION", "off")
    pc.validate_events([_Ev("Link.Verified", {"bogus": 1})])
    assert not pc.VIOLATIONS


def test_valid_payload_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_PAYLOAD_VALIDATION", "enforce")
    pc.validate_events([_Ev("Link.Verified", {})])
    assert pc.check("Link.Verified", 1, {}) == []
