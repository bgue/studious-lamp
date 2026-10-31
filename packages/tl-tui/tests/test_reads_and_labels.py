"""Reads shared within one screen refresh; labels kept per client for a while (P2-PERF)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from tl_tui import labels_load
from tl_tui.labels_load import forget_labels, load_labels
from tl_tui.reads import Reads


class Counting:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fail = False

    def history(self, record_id: str) -> list[str]:
        self.calls.append(("history", (record_id,)))
        if self.fail:
            raise RuntimeError("down")
        return [record_id]

    def get_rfi(self, project: str, number: str) -> str:
        self.calls.append(("get_rfi", (project, number)))
        return number

    # what ``load_labels`` asks of a client
    def list_correspondence_domains(self, project: str) -> list[Any]:
        self.calls.append(("domains", (project,)))
        return []

    def list_accounts(self) -> list[Any]:
        self.calls.append(("accounts", ()))
        return []

    def form_metadata(self, scope: str, record_type: str, record_id: str | None = None) -> Any:
        self.calls.append(("meta", (scope, record_type)))
        raise NotImplementedError

    def list_code_lists(self, scope: str) -> dict[str, dict[str, str]]:
        self.calls.append(("lists", (scope,)))
        return {}


def test_a_shared_read_is_made_once_per_arguments() -> None:
    client = Counting()
    reads = Reads(client)
    assert reads.history("A") == reads.history("A") == ["A"]
    assert reads.history("B") == ["B"]
    assert [c for c in client.calls if c[0] == "history"] == [
        ("history", ("A",)),
        ("history", ("B",)),
    ]


def test_other_reads_go_straight_through() -> None:
    client = Counting()
    reads = Reads(client)
    reads.get_rfi("P123", "1")
    reads.get_rfi("P123", "1")
    assert len(client.calls) == 2


def test_an_error_is_not_remembered() -> None:
    client = Counting()
    reads = Reads(client)
    client.fail = True
    with pytest.raises(RuntimeError):
        reads.history("A")
    client.fail = False
    assert reads.history("A") == ["A"]


def test_labels_are_read_once_per_client_scope_and_types() -> None:
    client = Counting()
    first = load_labels(client, "project:P123", ("core.Record",))  # type: ignore[arg-type]
    reads_made = len(client.calls)
    assert reads_made
    assert load_labels(client, "project:P123", ("core.Record",)) is first  # type: ignore[arg-type]
    assert len(client.calls) == reads_made
    load_labels(client, "project:P123", ("documents.Document",))  # type: ignore[arg-type]
    assert len(client.calls) > reads_made  # other types: read
    other = Counting()
    load_labels(other, "project:P123", ("core.Record",))  # type: ignore[arg-type]
    assert len(other.calls) == reads_made  # another client has its own


def test_labels_are_read_again_after_forget_and_after_the_time_is_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Counting()
    load_labels(client, "project:P123", ())  # type: ignore[arg-type]
    reads_made = len(client.calls)
    forget_labels(client)  # type: ignore[arg-type]
    load_labels(client, "project:P123", ())  # type: ignore[arg-type]
    assert len(client.calls) == 2 * reads_made
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + labels_load.LABELS_TTL_S + 1)
    load_labels(client, "project:P123", ())  # type: ignore[arg-type]
    assert len(client.calls) == 3 * reads_made
