"""S1 only: a command with a non-null intent answers ``intent_invalid`` and appends nothing.

S2 (the command boundary) removes this file.
"""

from __future__ import annotations

from harness import SCOPE, Harness
from sqlalchemy import text


def count(harness: Harness) -> int:
    with harness.backend(True) as uow:
        return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


def post(harness: Harness, **extra: object) -> object:
    return harness.client.post(
        "/commands/CreateRecord",
        json={
            "scope": SCOPE,
            "record_type": "core.Record",
            "title": "New",
            "key": "R-2",
            **extra,
        },
    )


def test_a_command_with_an_intent_is_refused_and_nothing_is_appended(harness: Harness) -> None:
    harness.create_record("R-1", "Keep")
    before = count(harness)
    response = post(harness, intent={"why": "SECRETWHY"})
    assert response.status_code == 422, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["error"] == "intent_invalid" and body["message"] == "intent not accepted"
    assert "SECRETWHY" not in response.text  # type: ignore[attr-defined]
    assert count(harness) == before


def test_the_same_command_without_an_intent_is_accepted(harness: Harness) -> None:
    before = count(harness)
    assert post(harness).status_code == 200  # type: ignore[attr-defined]
    assert count(harness) == before + 1
