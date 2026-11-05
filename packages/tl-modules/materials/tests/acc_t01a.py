"""Checks of the sample files (T01a)."""

import csv
import io
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import NoReturn

SAMPLES = (
    Path(__file__).resolve().parents[4]
    / "packages/tl-modules/materials/src/tl_mod_materials/samples"
)

ITEM_HEADER = [
    "code",
    "description",
    "category",
    "uom",
    "size",
    "rating",
    "material",
    "consumable",
]
LOCATION_HEADER = ["code", "title", "kind", "parent_code"]
PO_HEADER = [
    "po_number",
    "line_no",
    "item_code",
    "qty_ordered",
    "uom",
    "promised_date",
    "supplier_text",
]

CATEGORIES = frozenset(
    "pipe fitting flange valve bolting structural plate cable instrument electrical "
    "insulation paint consumable concrete other".split()
)
UOMS = frozenset("EA SET BOX ROLL L m kg lb m3".split())
MATERIALS = frozenset("CS SS304 SS316L DUPLEX other".split())
KINDS = frozenset("project warehouse laydown toolcrib gang_box".split())

ITEM_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9._\-]{0,39}")
LOCATION_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,15}")
LINE_NO_RE = re.compile(r"[0-9]+")
QTY_RE = re.compile(r"[0-9]+(?:\.[0-9]{1,3})?")
ISO_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MAX_QTY = Decimal("1000000000")


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def fail(message: str) -> NoReturn:
    raise Failure(message)


def _read_text(name: str) -> str:
    raw = (SAMPLES / name).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        fail(f"{name} starts with a UTF-8 byte order mark")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"{name} is not UTF-8")
    if "\r" in text:
        fail(f"{name} contains CR characters (LF endings required)")
    if not text.endswith("\n"):
        fail(f"{name} does not end with a newline")
    return text


def _rows(name: str) -> list[list[str]]:
    """All rows of the file, after checking they are in the RFC 4180 minimal-quoting form."""
    text = _read_text(name)
    rows = list(csv.reader(io.StringIO(text, newline="")))
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    if buffer.getvalue() != text:
        fail(f"{name} is not in the RFC 4180 minimal quoting form")
    return rows


def _header(name: str, header: list[str]) -> None:
    rows = _rows(name)
    if not rows or rows[0] != header:
        fail(f"{name} header is {rows[0] if rows else []}, want {header}")


def _table(name: str, header: list[str]) -> list[dict[str, str]]:
    _header(name, header)
    body = _rows(name)[1:]
    for number, row in enumerate(body, start=2):
        if len(row) != len(header):
            fail(f"{name} line {number} has {len(row)} fields, want {len(header)}")
    return [dict(zip(header, row, strict=True)) for row in body]


def items() -> list[dict[str, str]]:
    return _table("items.csv", ITEM_HEADER)


def locations() -> list[dict[str, str]]:
    return _table("locations.csv", LOCATION_HEADER)


def po_lines() -> list[dict[str, str]]:
    return _table("po_lines.csv", PO_HEADER)


def _item(code: str) -> dict[str, str]:
    for row in items():
        if row["code"] == code:
            return row
    fail(f"item {code} is not in items.csv")


# Items


def check_items_format() -> None:
    _rows("items.csv")


def check_items_header() -> None:
    _header("items.csv", ITEM_HEADER)


def check_items_count() -> None:
    count = len(items())
    if count != 50:
        fail(f"{count} item rows, want 50")


def check_items_codes() -> None:
    codes = [row["code"] for row in items()]
    duplicates = sorted(code for code, n in Counter(codes).items() if n > 1)
    if duplicates:
        fail(f"duplicate codes {duplicates}")
    bad = [code for code in codes if not ITEM_CODE_RE.fullmatch(code)]
    if bad:
        fail(f"codes outside the pattern: {bad}")


def check_items_values() -> None:
    for row in items():
        if row["category"] not in CATEGORIES:
            fail(f"{row['code']} category {row['category']!r} not in the list")
        if row["uom"] not in UOMS:
            fail(f"{row['code']} uom {row['uom']!r} not in the list")
        if row["material"] and row["material"] not in MATERIALS:
            fail(f"{row['code']} material {row['material']!r} not in the list")


def check_items_consumable_flag() -> None:
    bad = sorted({row["consumable"] for row in items()} - {"true", "false"})
    if bad:
        fail(f"consumable values {bad} are not true or false")


def check_items_mix() -> None:
    consumables = sum(1 for row in items() if row["consumable"] == "true")
    categories = {row["category"] for row in items()}
    if consumables < 3:
        fail(f"{consumables} consumable rows, want at least 3")
    if len(categories) < 8:
        fail(f"{len(categories)} categories used, want at least 8")


def check_demo_flange() -> None:
    row = _item("FLG-WN-6-150-A105")
    want = {
        "description": 'Flange WN 6" 150# A105',
        "category": "flange",
        "uom": "EA",
        "size": '6"',
        "rating": "150#",
        "material": "CS",
        "consumable": "false",
    }
    for key, value in want.items():
        if row[key] != value:
            fail(f"FLG-WN-6-150-A105 {key} is {row[key]!r}, want {value!r}")


def check_blind_flange() -> None:
    row = _item("FLG-BL-6-150-A105")
    if row["category"] != "flange" or row["uom"] != "EA":
        fail(f"FLG-BL-6-150-A105 is {row['category']}/{row['uom']}, want flange/EA")


# Locations


def check_locations_format() -> None:
    _rows("locations.csv")


def check_locations_header() -> None:
    _header("locations.csv", LOCATION_HEADER)


def check_locations_codes() -> None:
    codes = [row["code"] for row in locations()]
    duplicates = sorted(code for code, n in Counter(codes).items() if n > 1)
    if duplicates:
        fail(f"duplicate location codes {duplicates}")
    bad = [code for code in codes if not LOCATION_CODE_RE.fullmatch(code)]
    if bad:
        fail(f"location codes outside the pattern: {bad}")


def check_locations_kinds() -> None:
    bad = sorted({row["kind"] for row in locations()} - KINDS)
    if bad:
        fail(f"location kinds {bad} not in the list")


def check_locations_one_root() -> None:
    roots = [row["code"] for row in locations() if row["parent_code"] == ""]
    if len(roots) != 1:
        fail(f"{len(roots)} roots {roots}, want exactly one")


def check_locations_parents_first() -> None:
    seen: set[str] = set()
    for row in locations():
        parent = row["parent_code"]
        if parent and parent not in seen:
            fail(f"{row['code']} has parent {parent!r} that is missing or comes later")
        seen.add(row["code"])


def check_locations_depths() -> None:
    depth: dict[str, int] = {}
    for row in locations():
        parent = row["parent_code"]
        depth[row["code"]] = 0 if not parent else depth[parent] + 1
    deepest = max(depth.values())
    if deepest != 4:
        fail(f"deepest location is at depth {deepest}, want 4 (never deeper)")
    present = {row["kind"] for row in locations()}
    if not KINDS <= present:
        fail(f"kinds missing from the tree: {sorted(KINDS - present)}")


# PO lines


def check_po_format() -> None:
    _rows("po_lines.csv")


def check_po_header() -> None:
    _header("po_lines.csv", PO_HEADER)


def check_po_count_and_pos() -> None:
    lines = po_lines()
    if len(lines) < 12:
        fail(f"{len(lines)} PO lines, want at least 12")
    pos = {row["po_number"] for row in lines}
    if not {"4471", "4472"} <= pos:
        fail(f"POs {sorted(pos)} do not cover 4471 and 4472")


def check_po_keys() -> None:
    keys = [(row["po_number"], row["line_no"]) for row in po_lines()]
    duplicates = sorted(key for key, n in Counter(keys).items() if n > 1)
    if duplicates:
        fail(f"duplicate (po_number, line_no) keys {duplicates}")


def check_po_text_bounds() -> None:
    for row in po_lines():
        if not 1 <= len(row["po_number"]) <= 30:
            fail(f"po_number {row['po_number']!r} is not 1 to 30 characters")
        if len(row["supplier_text"]) > 120:
            fail(f"supplier_text on {row['po_number']}-{row['line_no']} is over 120 characters")


def check_po_line_numbers() -> None:
    for row in po_lines():
        if not LINE_NO_RE.fullmatch(row["line_no"]) or int(row["line_no"]) < 1:
            fail(f"line_no {row['line_no']!r} on PO {row['po_number']} is not a positive integer")


def check_po_items_and_uom() -> None:
    for row in po_lines():
        item = _item(row["item_code"])
        if row["uom"] != item["uom"]:
            fail(
                f"{row['po_number']}-{row['line_no']} uom {row['uom']!r} differs from "
                f"{row['item_code']} uom {item['uom']!r}"
            )


def check_po_quantities() -> None:
    for row in po_lines():
        qty = row["qty_ordered"]
        if not QTY_RE.fullmatch(qty):
            fail(f"qty_ordered {qty!r} on {row['po_number']}-{row['line_no']} is malformed")
        if not 0 < Decimal(qty) <= MAX_QTY:
            fail(f"qty_ordered {qty!r} on {row['po_number']}-{row['line_no']} is out of bounds")


def check_po_dates() -> None:
    for row in po_lines():
        text = row["promised_date"]
        if not ISO_DATE_RE.fullmatch(text):
            fail(f"promised_date {text!r} is not YYYY-MM-DD")
        try:
            date.fromisoformat(text)
        except ValueError:
            fail(f"promised_date {text!r} is not a valid date")


def check_po_demo_line() -> None:
    matches = [row for row in po_lines() if (row["po_number"], row["line_no"]) == ("4471", "3")]
    if len(matches) != 1:
        fail(f"found {len(matches)} rows for PO 4471 line 3, want 1")
    row = matches[0]
    if row["item_code"] != "FLG-WN-6-150-A105" or row["supplier_text"] != "Acme Valves":
        fail(f"4471-3 is {row['item_code']} from {row['supplier_text']!r}")
