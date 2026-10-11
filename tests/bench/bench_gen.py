"""Deterministic generator of a large project, written through batched units of work (P0-I8 D13).

``seed_database(target, spec)`` fills an empty ledger with ``spec.records`` ``core.Record`` streams,
about ``links_per_record`` ``core.Link`` streams per record and ``PSET_VALUES_PER_RECORD`` pset
values per record. It drives the real ledger and the real default projector registry, so every
current-state table ends up exactly as a production write would leave it, but it skips the command
handlers, the API and the simulator: that is what makes 100k records take minutes, not hours.

Everything is a function of the ``SeedSpec``: ids, timestamps and values come from counters and one
seeded ``random.Random``, so two runs give the same ledger, hash chain included.

Event layout per record ``i`` (in this order, one stream each, appended in one write transaction per
``batch`` records):

* ``Record.Created`` with its psets (``valve_data.*`` and ``inspection.interval_days``);
* for the first ``transition_share`` of the records, one to three ``Workflow.Transitioned``;
* ``Link.Added`` from ``i`` to an earlier record, ``links_per_record`` times on average.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from tl_adapters import db as adapter_db
from tl_adapters import postgres, sqlite
from tl_adapters._unit import BaseUnitOfWork
from tl_core.ledger import NewEvent
from tl_core.projection.defaults import default_registry

GENERATOR_VERSION = 1
SCOPE = "project:P123"
ACTOR = "user:bench"
SOURCE = "bench"
PSET_VALUES_PER_RECORD = 5
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)

KINDS = (
    "Gate valve",
    "Globe valve",
    "Check valve",
    "Ball valve",
    "Butterfly valve",
    "Relief valve",
)
MATERIALS = ("CS", "SS304", "SS316L", "DUPLEX", "other")
FAIL_ACTIONS = ("FC", "FO", "FL")
SIZES = (0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 24.0)
RELATIONS = ("references", "derived_from", "requires", "attached_to", "belongs_to")
CHAINS = (
    (("Draft", "Review", "submit"),),
    (("Draft", "Review", "submit"), ("Review", "Approved", "approve")),
    (
        ("Draft", "Review", "submit"),
        ("Review", "Approved", "approve"),
        ("Approved", "Issued", "issue"),
    ),
)

META_TABLE = "tl_bench_meta"


@dataclass(frozen=True)
class SeedSpec:
    """What to generate. Two equal specs give the same ledger."""

    records: int = 100_000
    links_per_record: int = 2
    transition_share: float = 0.3
    batch: int = 500
    seed: int = 20261010

    def describe(self) -> dict[str, Any]:
        return {**asdict(self), "generator_version": GENERATOR_VERSION}


def record_id(i: int) -> str:
    return f"0REC{i:022d}"


def record_key(i: int) -> str:
    return f"BN-{i:06d}"


def link_id(k: int) -> str:
    return f"0KNK{k:022d}"


class Counters:
    """Deterministic ``clock`` and ``id_gen`` for the ledger: one step per call."""

    def __init__(self) -> None:
        self.events = 0
        self.ticks = 0

    def clock(self) -> datetime:
        self.ticks += 1
        return EPOCH + timedelta(milliseconds=self.ticks)

    def event_id(self) -> str:
        self.events += 1
        return f"0EVT{self.events:022d}"


def record_payload(rng: random.Random, i: int) -> dict[str, Any]:
    kind = rng.choice(KINDS)
    tag = f"V-{i:06d}"
    description = None if i % 2 else f"{kind} {tag} on line {rng.randrange(1, 400)}"
    return {
        "record_type": "core.Record",
        "key": record_key(i),
        "title": f"{kind} {tag}",
        "description": description,
        "psets": {
            "valve_data": {
                "size_in": rng.choice(SIZES),
                "body_material": rng.choice(MATERIALS),
                "fail_action": rng.choice(FAIL_ACTIONS),
                "tag_no": tag,
            },
            "inspection": {"interval_days": rng.choice((30, 90, 180, 365))},
        },
    }


def make_engine_and_uow(
    target: adapter_db.DbTarget, counters: Counters
) -> tuple[Engine, Callable[[], BaseUnitOfWork]]:
    """An engine and a factory of write units of work with the deterministic clock and ids."""
    engine = adapter_db.make_engine(target)
    ledger = adapter_db.make_ledger(engine, clock=counters.clock, id_gen=counters.event_id)
    registry = default_registry()
    if engine.dialect.name == "postgresql":

        def make_pg() -> BaseUnitOfWork:
            return postgres.uow.PostgresUnitOfWork(engine, ledger, registry, None)

        return engine, make_pg

    def make_sqlite() -> BaseUnitOfWork:
        return sqlite.uow.SqliteUnitOfWork(engine, ledger, registry, None)

    return engine, make_sqlite


def _new(event_type: str, payload: dict[str, Any]) -> list[NewEvent]:
    return [NewEvent(event_type=event_type, payload=payload)]


def _append(
    uow: BaseUnitOfWork,
    stream_id: str,
    stream_type: str,
    version: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=SCOPE,
        expected_version=version,
        events=_new(event_type, payload),
        actor=ACTOR,
        source=SOURCE,
        correlation_id="bench",
    )


def seed_database(
    target: adapter_db.DbTarget,
    spec: SeedSpec,
    *,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Create the schema on the empty ``target`` and write the dataset. Returns the facts.

    ``target`` must be empty. The facts (``events``, ``links``, ``transitions``, ``head_hash``)
    are what the caller stores to recognise the same dataset later.
    """
    adapter_db.create_schema(target)
    counters = Counters()
    engine, new_uow = make_engine_and_uow(target, counters)
    rng = random.Random(spec.seed)
    links = 0
    transitions = 0
    try:
        for start in range(0, spec.records, spec.batch):
            with new_uow() as uow:
                for i in range(start, min(start + spec.batch, spec.records)):
                    rid = record_id(i)
                    _append(uow, rid, "core.Record", 0, "Record.Created", record_payload(rng, i))
                    if rng.random() < spec.transition_share:
                        chain = CHAINS[rng.randrange(len(CHAINS))]
                        for step, (src, dst, name) in enumerate(chain, start=1):
                            _append(
                                uow,
                                rid,
                                "core.Record",
                                step,
                                "Workflow.Transitioned",
                                {
                                    "workflow": "core.review",
                                    "workflow_version": 1,
                                    "from_state": src,
                                    "to_state": dst,
                                    "transition": name,
                                    "guards_evaluated": [],
                                    "signature": None,
                                    "reason": None,
                                    "conformance": "ok",
                                    "effective_schema_hash": None,
                                },
                            )
                            transitions += 1
                    if i == 0:
                        continue
                    targets = {rng.randrange(0, i) for _ in range(spec.links_per_record)}
                    for target_index in sorted(targets):
                        lid = link_id(links)
                        links += 1
                        _append(
                            uow,
                            lid,
                            "core.Link",
                            0,
                            "Link.Added",
                            {
                                "link_id": lid,
                                "from_ref": rid,
                                "to_ref": record_id(target_index),
                                "relation": RELATIONS[rng.randrange(len(RELATIONS))],
                                "pin": None,
                                "source": "manual",
                                "note": None,
                            },
                        )
            if on_progress is not None:
                on_progress(min(start + spec.batch, spec.records))
        head = adapter_db.make_ledger(engine).head_seq()
        with engine.connect() as conn:
            head_hash = conn.execute(
                text("SELECT hash FROM events WHERE seq = :seq"), {"seq": head}
            ).scalar_one()
    finally:
        engine.dispose()
    return {
        "events": head,
        "links": links,
        "transitions": transitions,
        "head_hash": head_hash,
        "pset_values": PSET_VALUES_PER_RECORD * spec.records,
    }


def partial_path(path: Path) -> Path:
    return path.with_name(path.name + ".partial")
