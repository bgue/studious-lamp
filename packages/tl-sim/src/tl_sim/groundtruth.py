"""The ground-truth log: what the scenario intended, one JSON line per ``GroundTruth``.

The log is append-only and canonical (sorted keys, compact separators, UTC instants), so two runs
of one seed produce byte-identical files and one digest. It never holds an id the server made up
(ULIDs): a record is named by its key, a link by ``from -> relation -> to`` and a post by the
actor and the day it was written (``Recorder`` builds those names).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tl_sim.types import GroundTruth

# The intents the simulator writes. ``sim_assert`` knows how to check each of them.
RECORD_CREATED = "record.created"
PSET_SET = "pset.set"
LINK_ADDED = "link.added"
WORKFLOW_TRANSITIONED = "workflow.transitioned"
POST_CREATED = "post.created"
PROPOSAL_CREATED = "proposal.created"
PROPOSAL_ACCEPTED = "proposal.accepted"
PROPOSAL_REJECTED = "proposal.rejected"
INTENTS = (
    RECORD_CREATED,
    PSET_SET,
    LINK_ADDED,
    WORKFLOW_TRANSITIONED,
    POST_CREATED,
    PROPOSAL_CREATED,
    PROPOSAL_ACCEPTED,
    PROPOSAL_REJECTED,
)


def to_line(item: GroundTruth) -> str:
    """One canonical JSON line (no trailing newline)."""
    return json.dumps(
        {
            "at": item.at.astimezone(UTC).isoformat(),
            "actor": item.actor,
            "intent": item.intent,
            "ref": item.ref,
            "expect": item.expect,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def from_line(line: str) -> GroundTruth:
    data: dict[str, Any] = json.loads(line)
    return GroundTruth(
        at=datetime.fromisoformat(data["at"]),
        actor=data["actor"],
        intent=data["intent"],
        ref=data["ref"],
        expect=data["expect"],
    )


def digest(items: Iterable[GroundTruth]) -> str:
    """SHA-256 of the canonical lines: equal for two runs that intended the same things."""
    h = hashlib.sha256()
    for item in items:
        h.update(to_line(item).encode())
        h.update(b"\n")
    return h.hexdigest()


class GroundTruthLog:
    """The log file of one run. ``append`` flushes each batch so a crash loses at most one step."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, items: Iterable[GroundTruth]) -> int:
        lines = [to_line(item) for item in items]
        if not lines:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
        return len(lines)

    def read(self) -> list[GroundTruth]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [from_line(line) for line in handle if line.strip()]

    def digest(self) -> str:
        return digest(self.read())
