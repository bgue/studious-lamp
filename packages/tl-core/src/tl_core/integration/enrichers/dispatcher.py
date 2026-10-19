"""The enrichment dispatcher: follows the ledger and runs the enrichers (FANOUT D6, D11).

Like the rules worker it reads ``outbox_events`` off the write path, in batches from the
operational cursor ``enrich_cursor``, so an enricher never blocks or fails a person's write. For
each event it finds the enabled enrichers whose *when* matches (the scope, the moment the enricher
was switched on, the filter and its record selector) and runs each in a unit of work of its own;
a crash re-reads the batch, and the pipeline does not propose the same value twice.

* **Kill switch.** Read inside every run. When on, the event is passed over (counted ``killed``)
  and the cursor moves past it: it is not replayed when the switch is turned off.
* **Never on its own work.** An event whose source starts with ``enricher:`` is not offered to
  any enricher, so a layer write cannot start another run.
* **A failure** (a plugin that raised, a record the layer refuses) rolls back that run and is
  counted ``failed``; the next event goes on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Connection, text

from tl_core.integration.contract import RULE_BATCH_EVENTS, Enricher
from tl_core.integration.enrichers.pipeline import (
    RunStats,
    StoredEnricher,
    in_scope,
    load_live_enricher,
    load_live_enrichers,
    load_subject,
    run_enricher,
)
from tl_core.integration.enrichers.registry import load_enricher
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.rules.engine import read_outbox
from tl_core.services.errors import RetryableTransactionError
from tl_core.webhooks.base import Clock, UowFactory, utc_now
from tl_core.webhooks.dispatch import record_matches
from tl_core.webhooks.rows import OutboxRow

log = logging.getLogger(__name__)

CURSOR_NAME = "enrichers"
ENRICHER_SOURCE_PREFIX = "enricher:"


@dataclass
class EnrichStats(RunStats):
    read: int = 0
    killed: int = 0
    cursor: int = 0


def applies(enricher: StoredEnricher, row: OutboxRow) -> bool:
    """The row-level part of *when*: scope, the moment it was switched on, the filter."""
    if not in_scope(enricher, row.scope) or row.seq <= enricher.enabled_from_seq:
        return False
    return enricher.when.matches_row(row)


class EnrichmentDispatcher:
    """Follows the ledger and runs the enrichers. One instance per process; safe to run twice."""

    def __init__(
        self,
        open_uow: UowFactory,
        *,
        clock: Clock = utc_now,
        plugins: Callable[[str], Enricher | None] = load_enricher,
    ) -> None:
        self._open = open_uow
        self._clock = clock
        self._plugins = plugins

    def run_once(self, *, limit: int = RULE_BATCH_EVENTS) -> EnrichStats:
        with self._open() as uow:
            cursor = self._cursor(uow.conn())
            rows = read_outbox(uow.conn(), cursor, limit)
            enrichers = load_live_enrichers(uow.conn())
        stats = EnrichStats(read=len(rows), cursor=cursor)
        for row in rows:
            if not row.source.startswith(ENRICHER_SOURCE_PREFIX):
                for enricher in enrichers:
                    if applies(enricher, row):
                        stats.add(self._run(enricher, row, stats))
            stats.cursor = row.seq
        if stats.cursor != cursor:
            with self._open() as uow:
                self._set_cursor(uow.conn(), stats.cursor)
        return stats

    def run_until_idle(self, *, limit: int = RULE_BATCH_EVENTS) -> EnrichStats:
        total = EnrichStats()
        while True:
            stats = self.run_once(limit=limit)
            total.add(stats)
            total.read += stats.read
            total.killed += stats.killed
            total.cursor = max(total.cursor, stats.cursor)
            if stats.read == 0:
                return total

    def _run(self, enricher: StoredEnricher, row: OutboxRow, counts: EnrichStats) -> RunStats:
        none = RunStats()
        try:
            with self._open() as uow:
                if kill_switch_on(uow.conn()):
                    counts.killed += 1
                    return none
                # the batch loaded its enrichers once: ask again, so switching one off (or
                # revising it) takes effect at the next event, as it does for a rule
                live = load_live_enricher(uow.conn(), enricher.name)
                if live is None or live.enricher_id != enricher.enricher_id:
                    return none
                if not applies(live, row):
                    return none
                enricher = live
                selector = enricher.when.record_selector
                if selector is not None and not record_matches(uow, row, selector):
                    return none
                subject = load_subject(uow.conn(), row.subject_id)
                plugin = self._plugins(enricher.name)
                if subject is None or plugin is None or subject.record.id != row.subject_id:
                    return none
                stats, _ = run_enricher(
                    uow,
                    enricher,
                    plugin,
                    subject,
                    now=self._clock(),
                    correlation_id=row.correlation_id,
                    causation_id=row.event_id,
                )
                return stats
        except RetryableTransactionError:
            raise
        except Exception:  # rolled back with the unit of work; the next event goes on
            log.warning(
                "enricher %s failed on event %s", enricher.name, row.event_id, exc_info=True
            )
            failed = RunStats()
            failed.failed += 1
            return failed

    @staticmethod
    def _cursor(conn: Connection) -> int:
        row = conn.execute(
            text("SELECT last_seq FROM enrich_cursor WHERE name = :n"), {"n": CURSOR_NAME}
        ).first()
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO enrich_cursor (name, last_seq) VALUES (:n, 0) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"n": CURSOR_NAME},
            )
            return 0
        return int(row.last_seq)

    @staticmethod
    def _set_cursor(conn: Connection, seq: int) -> None:
        conn.execute(
            text("UPDATE enrich_cursor SET last_seq = :seq WHERE name = :n AND last_seq < :seq"),
            {"seq": seq, "n": CURSOR_NAME},
        )


__all__ = ["CURSOR_NAME", "EnrichStats", "EnrichmentDispatcher", "applies"]
