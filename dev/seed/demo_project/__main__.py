"""``python -m dev.seed.demo_project``: build the demo project in a fresh ledger.

``dev`` is not an installed package; run it from the repository root (``just demo-project`` does).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tl_adapters.db import DbTarget, as_target, create_schema, display_target, is_postgres
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_schema.registry import default_schema_dir

from dev.seed.demo_project import ORDER, SECTIONS
from dev.seed.demo_project.overlay import OVERLAY, ROOT, use_overlay
from dev.seed.demo_project.registry import missing_types
from dev.seed.demo_project.rng import section_rng
from dev.seed.demo_project.world import PROJECT, World

DEFAULT_DB = "dev/data/demo-project.db"


class AlreadySeededError(Exception):
    """The ledger already holds project P200."""


@dataclass(frozen=True)
class Done:
    section: str
    records: int
    events: int
    seconds: float
    note: str = ""


def parse_sections(raw: str | None) -> list[str]:
    if raw is None:
        return list(ORDER)
    wanted = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in wanted if name not in SECTIONS]
    if unknown:
        raise ValueError(f"unknown section {', '.join(unknown)}; sections are {', '.join(ORDER)}")
    return [name for name in ORDER if name in wanted]  # always in the fixed order


def prepare(target: DbTarget) -> None:
    """Create the ledger (``tl init`` without the dev account) unless it holds P200 already."""
    if not is_postgres(target):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    create_schema(target)


def run(
    target: DbTarget,
    *,
    seed: int | str = 2026,
    sections: Sequence[str] | None = None,
    objects: Path | None = None,
) -> list[Done]:
    """Build the project; returns one ``Done`` per section, in order."""
    use_overlay()
    prepare(target)
    world = World(target, objects)
    if world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE scope = :s", s=PROJECT):
        raise AlreadySeededError(
            f"{display_target(target)} already holds project P200; "
            "use a new database (the generator builds a fresh ledger, it never adds to one)"
        )
    done: list[Done] = []
    with use_provider(DirectorySchemaProvider(default_schema_dir())):
        for name in sections if sections is not None else ORDER:
            section = SECTIONS[name]
            absent = missing_types(section)
            if absent:
                print(f"{name}: skipped, {', '.join(absent)} not installed")
                done.append(Done(name, 0, 0, 0.0, "skipped"))
                continue
            records, events, started = world.record_count(), world.event_count(), time.monotonic()
            section.build(world, section_rng(seed, name))
            took = time.monotonic() - started
            done.append(
                Done(
                    name,
                    world.record_count() - records,
                    world.event_count() - events,
                    took,
                )
            )
            print(f"{name}: {done[-1].records} records, {done[-1].events} events, {took:.1f}s")
    return done


def summary(done: Sequence[Done]) -> str:
    lines = ["section          records   events  seconds"]
    for item in done:
        note = f"  ({item.note})" if item.note else ""
        lines.append(
            f"{item.section:<15} {item.records:>8} {item.events:>8} {item.seconds:>8.1f}{note}"
        )
    lines.append(
        f"{'total':<15} {sum(d.records for d in done):>8} {sum(d.events for d in done):>8} "
        f"{sum(d.seconds for d in done):>8.1f}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dev.seed.demo_project",
        description="Build the demo project P200 (North Refinery, HT-2) in a new ledger.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite path or postgresql:// URL")
    parser.add_argument("--seed", default="2026", help="seed of the random draws (default 2026)")
    parser.add_argument("--sections", help=f"comma list of {', '.join(ORDER)} (default all)")
    parser.add_argument(
        "--objects", type=Path, help="directory of the file store (default: TL_OBJECT_ROOT)"
    )
    args = parser.parse_args(argv)
    try:
        chosen = parse_sections(args.sections)
        target = as_target(args.db)
        done = run(target, seed=args.seed, sections=chosen, objects=args.objects)
    except (ValueError, AlreadySeededError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print()
    print(summary(done))
    print(f"\nclients of this ledger read it with TL_SCHEMA_DIR={OVERLAY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
