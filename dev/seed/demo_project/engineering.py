"""engineering section: the company standards, then 300+ tags over the six areas.

The standards file (``data/standards.yaml``) is North Refinery's edition: the six areas, the
disciplines, document types, mnemonics, the tag and document number patterns and the tag classes.
A tag number that fits the pattern (``200-P-1023``) is made with ``CreateTag``. Legacy numbers that
cannot fit it (line numbers ``6"-P-200-1045-A1A``, spares ``200-P-1023A``) are kept by the admin
with ``RecordTag`` as pattern violations, as a brownfield register has them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from tl_adapters.db import open_uow
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RecordTag,
    handle_create_tag,
    handle_record_tag,
)
from tl_mod_engineering.loader import load_standards

from dev.seed.demo_project.core import ADMIN, AREAS
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import START, World

STANDARDS = Path(__file__).resolve().parent / "data" / "standards.yaml"
ENGINEER = "lhartmann"


@dataclass(frozen=True)
class Kind:
    mnemonic: str
    tag_class: str
    services: tuple[str, ...]
    per_area: dict[str, int]  # area code -> how many tags of this kind


KINDS: tuple[Kind, ...] = (
    Kind(
        "P",
        "Pump",
        (
            "Reactor feed pump",
            "Charge pump",
            "Reflux pump",
            "Bottoms pump",
            "Cooling water pump",
            "Product transfer pump",
            "Condensate pump",
        ),
        {"100": 0, "200": 9, "300": 7, "400": 8, "500": 0, "600": 2},
    ),
    Kind(
        "E",
        "HeatExchanger",
        (
            "Feed/effluent exchanger",
            "Overhead condenser",
            "Reboiler",
            "Product cooler",
            "Trim cooler",
        ),
        {"100": 0, "200": 9, "300": 0, "400": 5, "500": 0, "600": 1},
    ),
    Kind(
        "V",
        "Vessel",
        (
            "Reactor",
            "Separator",
            "Reflux drum",
            "Fractionator",
            "Surge drum",
            "Knock-out drum",
            "Storage tank",
        ),
        {"100": 0, "200": 8, "300": 6, "400": 2, "500": 0, "600": 0},
    ),
    Kind(
        "K",
        "Compressor",
        ("Recycle gas compressor", "Make-up gas compressor", "Instrument air compressor"),
        {"100": 0, "200": 2, "300": 0, "400": 3, "500": 0, "600": 0},
    ),
    Kind(
        "M",
        "Motor",
        ("Pump motor", "Compressor motor", "Fan motor", "Agitator motor"),
        {"100": 0, "200": 9, "300": 6, "400": 8, "500": 2, "600": 0},
    ),
    Kind(
        "HV",
        "ManualValve",
        (
            "Isolation valve",
            "Block valve",
            "Drain valve",
            "Vent valve",
            "Bypass valve",
            "Sample valve",
        ),
        {"100": 12, "200": 22, "300": 14, "400": 14, "500": 0, "600": 12},
    ),
    Kind(
        "XV",
        "ControlValve",
        ("Emergency shutdown valve", "Isolation actuated valve", "Inlet shutoff valve"),
        {"100": 2, "200": 9, "300": 5, "400": 4, "500": 0, "600": 4},
    ),
    Kind(
        "FV",
        "ControlValve",
        ("Feed flow control valve", "Reflux flow control valve", "Quench flow control valve"),
        {"100": 0, "200": 8, "300": 3, "400": 4, "500": 0, "600": 0},
    ),
    Kind(
        "PV",
        "ControlValve",
        ("Pressure control valve", "Backpressure control valve", "Letdown valve"),
        {"100": 0, "200": 7, "300": 2, "400": 4, "500": 0, "600": 0},
    ),
    Kind(
        "PSV",
        "SafetyValve",
        ("Relief valve", "Thermal relief valve", "Vessel relief valve"),
        {"100": 0, "200": 9, "300": 5, "400": 4, "500": 0, "600": 0},
    ),
    Kind(
        "FT",
        "Transmitter",
        ("Flow transmitter", "Feed flow transmitter", "Product flow transmitter"),
        {"100": 0, "200": 9, "300": 4, "400": 6, "500": 0, "600": 2},
    ),
    Kind(
        "PT",
        "Transmitter",
        ("Pressure transmitter", "Header pressure transmitter", "Suction pressure transmitter"),
        {"100": 2, "200": 12, "300": 4, "400": 6, "500": 0, "600": 4},
    ),
    Kind(
        "LT",
        "Transmitter",
        ("Level transmitter", "Interface level transmitter", "Tank level transmitter"),
        {"100": 0, "200": 9, "300": 7, "400": 4, "500": 0, "600": 0},
    ),
    Kind(
        "TT",
        "Transmitter",
        ("Temperature transmitter", "Bed temperature transmitter", "Skin temperature transmitter"),
        {"100": 0, "200": 11, "300": 3, "400": 5, "500": 2, "600": 2},
    ),
)

LINE_SIZES = ('1"', '2"', '3"', '4"', '6"', '8"', '10"', '12"', '16"')
LINE_SERVICES = {
    "100": ("P", "HC", "FG"),
    "200": ("P", "H2", "HC", "FG"),
    "300": ("P", "HC"),
    "400": ("CW", "ST", "N2", "IA"),
    "500": ("IA",),
    "600": ("P", "HC", "FG", "ST"),
}
LINE_SPECS = ("A1A", "A1B", "B1A", "B1C", "D2A", "D2C", "F3A")
LINES_PER_AREA = {"100": 10, "200": 14, "300": 8, "400": 10, "500": 2, "600": 8}


def tag_numbers(rng: random.Random) -> list[tuple[str, Kind, str]]:
    """(number, kind, service) for every pattern tag: unique, sequences 1001 upwards with gaps."""
    found: list[tuple[str, Kind, str]] = []
    for code, _ in AREAS:
        for kind in KINDS:
            sequence = 1000
            for _ in range(kind.per_area[code]):
                sequence += rng.randint(1, 4)
                found.append(
                    (f"{code}-{kind.mnemonic}-{sequence:04d}", kind, rng.choice(kind.services))
                )
    return found


def line_numbers(rng: random.Random) -> list[tuple[str, str]]:
    """(number, service) of the legacy line numbers, ``6"-P-200-1045-A1A``."""
    found: list[tuple[str, str]] = []
    for code, _ in AREAS:
        sequence = 1000
        for _ in range(LINES_PER_AREA[code]):
            sequence += rng.randint(1, 9)
            service = rng.choice(LINE_SERVICES[code])
            size, spec = rng.choice(LINE_SIZES), rng.choice(LINE_SPECS)
            found.append(
                (f"{size}-{service}-{code}-{sequence:04d}-{spec}", f"Line {service} area {code}")
            )
    return found


def build(world: World, rng: random.Random) -> None:
    standards = load_standards_file(STANDARDS)
    with open_uow(world.target) as uow:
        load_standards(uow, standards, actor=f"user:{ADMIN}", source="demo-project")
    day = START + timedelta(days=7)
    numbers = tag_numbers(rng)
    for position, (number, kind, service) in enumerate(numbers):
        if position % 20 == 0:
            day += timedelta(days=1 + (day.weekday() == 4) * 2)
        with world.on(day):
            world.run(
                handle_create_tag,
                CreateTag,
                by=ENGINEER,
                number=number,
                class_code=kind.tag_class,
                service=service,
            )
    with world.on(day):
        for number, service in line_numbers(rng):
            world.run(
                handle_record_tag,
                RecordTag,
                by=ADMIN,
                number=number,
                class_code="Line",
                service=service,
            )
        # spares of existing pumps: a suffix letter breaks the pattern, so they are kept as recorded
        pumps = [n for n, k, _ in numbers if k.mnemonic == "P"]
        for number in rng.sample(pumps, 8):
            world.run(
                handle_record_tag,
                RecordTag,
                by=ADMIN,
                number=f"{number}A",
                class_code="Pump",
                service="Installed spare",
            )


register("engineering", build)
