"""The rules-of-credit engine: earned progress of an IWP from the states of its scope items.

Pure apart from the connection it is handed. The four math rules (P2-I5 S2, F9):

1. *Computed unfiltered, filtered on read.* The figure is computed over every non-void item
   whatever the reader may open, so it never depends on who asks. ``viewer`` only narrows the
   ``items`` list (and adds one note); the percent is the same.
2. *Null hours.* An item with no ``est_hours`` weighs the mean of the weights set; when none is
   set every item weighs 1.
3. *Rounding.* Sums are exact (``Fraction``); a figure is rounded once, half-up, at its output.
   ``largest_remainder`` splits one rounded total into parts that sum to it.
4. *PPC.* A count of IWPs done over IWPs committed (``ppc``).

Every refusal has a fixed text, never a cell of the input.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.confidentiality import Viewer
from tl_core.schema_provider import get_provider
from tl_core.services.errors import RecordNotFoundError
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_schema.packages import CreditStep
from tl_schema.registry import PackageError, default_schema_dir, load_package

from tl_mod_awp.errors import RulesOfCreditError
from tl_mod_awp.names import (
    DEFAULT_COMMODITY,
    DEFAULT_EDITION,
    EDITION_SETTING,
    IWP,
    IWP_PROGRESS_TABLE,
    RULE_LINK_SOURCE,
    SCI_VOID,
    SCOPE_ITEM,
    SCOPE_RELATION,
    SCOPE_STATE_ORDER,
)

MSG_NO_EDITION = "the edition of the rules of credit is not adopted"
MSG_NO_RULES = "the edition of the rules of credit holds no rules"
NOTE_HIDDEN = "some items not shown"
NOTE_NO_TYPE = "type not recorded yet"
HUNDRED = Fraction(100)
TENTH = Decimal("0.1")

_ITEMS_SQL = text(
    "SELECT r.id AS id, r.key AS key, r.status AS status, s.commodity AS commodity, "
    "s.est_hours AS est_hours FROM cur_links l JOIN cur_core_record r ON r.id = l.from_id "
    "LEFT JOIN cur_awp_scope_item s ON s.id = r.id "
    "WHERE l.to_id = :iwp AND l.relation = :relation AND l.source = :source "
    "AND l.status = 'active' AND r.type = :item_type AND r.voided = :voided "
    "ORDER BY r.key, r.id"
)
_IWP_SQL = text("SELECT id, scope FROM cur_core_record WHERE id = :id AND type = :type")
_ROW_SQL = text(
    f"SELECT earned_pct, edition, manual_json FROM {IWP_PROGRESS_TABLE} WHERE iwp_id = :id"
)
_TYPE_SQL = text("SELECT 1 FROM cur_core_record WHERE type = :type LIMIT 1")
_RELATED_SQL = text(
    "SELECT x.status AS status FROM cur_links l JOIN cur_core_record x ON x.id = l.to_id "
    "WHERE l.from_id = :item AND l.status = 'active' AND x.type = :type AND x.voided = :voided "
    "UNION ALL "
    "SELECT x.status AS status FROM cur_links l JOIN cur_core_record x ON x.id = l.from_id "
    "WHERE l.to_id = :item AND l.status = 'active' AND x.type = :type AND x.voided = :voided"
)


@dataclass(frozen=True)
class Rules:
    """One edition of the rules of credit: ``edition`` is ``package@version``; ``by_commodity``
    maps a commodity to its steps. A commodity without an entry uses ``piping``."""

    edition: str
    by_commodity: dict[str, tuple[CreditStep, ...]]

    def steps_for(self, commodity: str | None) -> tuple[CreditStep, ...]:
        found = self.by_commodity.get(commodity or "")
        if found is None:
            found = self.by_commodity.get(DEFAULT_COMMODITY)
        return found if found is not None else ()


@dataclass(frozen=True)
class ItemEarned:
    item_id: str
    key: str
    commodity: str
    pct: Decimal  # 1 dp, half-up
    steps: tuple[str, ...]  # the names of the steps earned
    hours: Decimal | None  # the estimate as recorded


@dataclass(frozen=True)
class Earned:
    pct: Decimal  # 1 dp, at most 100.0
    edition: str
    items: list[ItemEarned]
    notes: list[str] = field(default_factory=lambda: [])


@dataclass(frozen=True)
class StoredProgress:
    pct: str
    edition: str
    manual: list[dict[str, str]]


# --- rounding and allocation (rule 3) and PPC (rule 4) -----------------------------------------


def round_half_up(value: Fraction | Decimal | int) -> Decimal:
    """``value`` to one decimal, half-up (the one rounding of a figure)."""
    exact = Fraction(value)
    tenths = math.floor(exact * 10 + Fraction(1, 2))
    return Decimal(tenths) * TENTH


def largest_remainder(total: Decimal, percents: Sequence[Decimal]) -> list[Decimal]:
    """Split ``total`` (rounded to 1 dp first) over ``percents`` into parts of 1 dp that sum to the
    rounded total: each part gets its share rounded down, the leftover tenths go to the largest
    remainders (the earlier line first on a tie)."""
    if not percents:
        return []
    units = int(round_half_up(total) * 10)
    weights = [Fraction(p) for p in percents]
    whole = sum(weights, Fraction(0))
    if whole <= 0:
        raise ValueError("the percents must sum to more than zero")
    shares = [Fraction(units) * w / whole for w in weights]
    floors = [math.floor(s) for s in shares]
    spare = units - sum(floors)
    order = sorted(range(len(shares)), key=lambda i: (-(shares[i] - floors[i]), i))
    for i in order[:spare]:
        floors[i] += 1
    return [Decimal(n) * TENTH for n in floors]


def ppc(done: int, committed: int) -> tuple[Decimal | None, list[str]]:
    """Plan percent complete: IWPs done over IWPs committed, as a count, 1 dp. Nothing committed
    is ``None`` with the note ``nothing committed`` (never ``0.0``)."""
    if committed <= 0:
        return None, ["nothing committed"]
    return round_half_up(Fraction(done * 100, committed)), []


# --- the edition -------------------------------------------------------------------------------

_SHIPPED: dict[str, Any] = {}


def _package_doc(key: str) -> Any:
    name, _, version = key.partition("@")
    provider = get_provider()
    registry = getattr(provider, "registry", None)
    if registry is not None:
        try:
            return registry().get(name, version)
        except PackageError:
            pass
    if key == DEFAULT_EDITION:  # the shipped standard (schema/fixtures/packages)
        if key not in _SHIPPED:
            path = default_schema_dir() / "packages" / f"{key}.yaml"
            _SHIPPED[key] = load_package(path) if path.is_file() else None
        if _SHIPPED[key] is not None:
            return _SHIPPED[key]
    raise RulesOfCreditError(MSG_NO_EDITION)


def package_doc(key: str) -> Any:
    """The schema package behind the edition ``key`` (``package@version``), as ``_package_doc``
    returns it: its ``rules_of_credit`` carry each rule's ``kind``. ``RulesOfCreditError`` when the
    edition is unknown or not adopted."""
    return _package_doc(key)


def rules_for(key: str) -> Rules:
    """The rules of the edition ``key`` (``package@version``). ``RulesOfCreditError`` when it is
    unknown, not adopted, or holds no rules."""
    doc = _package_doc(key)
    if not doc.rules_of_credit:
        raise RulesOfCreditError(MSG_NO_RULES)
    return Rules(
        edition=key,
        by_commodity={rule.commodity: tuple(rule.steps) for rule in doc.rules_of_credit},
    )


def edition_key(conn: Connection, scope: str) -> str:
    """The ``package@version`` in force for the project of ``scope``: the setting, else the
    company standard."""
    value = value_of(conn, EDITION_SETTING, project=project_of_scope(scope))
    return str(value) if value else DEFAULT_EDITION


def edition_for(conn: Connection, scope: str) -> Rules:
    """The rules in force for ``scope`` (setting ``awp.rules_of_credit.set``, else
    ``co.acme.awp@1.1.0``). ``RulesOfCreditError`` when the edition is unknown or not adopted."""
    return rules_for(edition_key(conn, scope))


# --- reading the stored figure -----------------------------------------------------------------


def manual_entries(value: Any) -> list[dict[str, str]]:
    """The entries of a ``manual_json`` cell (text on SQLite, a list on Postgres)."""
    if value is None:
        return []
    found = json.loads(value) if isinstance(value, str | bytes) else value
    return [{"scope_item_id": str(e["scope_item_id"]), "step": str(e["step"])} for e in found]


def stored_progress(conn: Connection, iwp_id: str) -> StoredProgress | None:
    row = conn.execute(_ROW_SQL, {"id": iwp_id}).first()
    if row is None:
        return None
    return StoredProgress(
        pct=str(row.earned_pct), edition=str(row.edition), manual=manual_entries(row.manual_json)
    )


# --- the computation ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeItemRow:
    id: str
    key: str
    state: str
    commodity: str
    hours: Fraction | None
    hours_text: Decimal | None


@dataclass(frozen=True)
class Figure:
    """The unfiltered result: the exact percent, every item and whether a type was missing."""

    pct: Decimal
    edition: str
    items: list[ItemEarned]
    missing_type: bool
    item_hours_missing: dict[str, bool]


def scope_items(conn: Connection, iwp_id: str) -> list[ScopeItemRow]:
    rows = conn.execute(
        _ITEMS_SQL,
        {
            "iwp": iwp_id,
            "relation": SCOPE_RELATION,
            "source": RULE_LINK_SOURCE,
            "item_type": SCOPE_ITEM,
            "voided": False,
        },
    ).all()
    found: list[ScopeItemRow] = []
    for row in rows:
        state = str(row.status or SCOPE_STATE_ORDER[0])
        if state == SCI_VOID:
            continue
        hours = None if row.est_hours in (None, "") else Decimal(str(row.est_hours))
        found.append(
            ScopeItemRow(
                id=str(row.id),
                key=str(row.key or ""),
                state=state,
                commodity=str(row.commodity or ""),
                hours=None if hours is None else Fraction(hours),
                hours_text=hours,
            )
        )
    return found


def _weights(items: Sequence[ScopeItemRow]) -> list[Fraction]:
    """Rule 2: a null weighs the mean of the set weights; none set, every item weighs 1."""
    set_weights = [i.hours for i in items if i.hours is not None]
    if not set_weights or sum(set_weights, Fraction(0)) == 0:
        return [Fraction(1)] * len(items)
    mean = sum(set_weights, Fraction(0)) / len(set_weights)
    return [mean if i.hours is None else i.hours for i in items]


def _earned_steps(
    conn: Connection,
    rules: Rules,
    item: ScopeItemRow,
    manual: set[tuple[str, str]],
    known_types: dict[str, bool],
) -> tuple[Fraction, list[str], bool]:
    """``(percent, names of the steps earned, a record type was missing)`` of one item."""
    pct = Fraction(0)
    names: list[str] = []
    missing = False
    for step in rules.steps_for(item.commodity):
        evidence = step.evidence
        earned = False
        if evidence == "manual":
            earned = (item.id, step.name) in manual
        elif evidence.startswith("scope_state:"):
            wanted = evidence.split(":", 1)[1]
            if wanted in SCOPE_STATE_ORDER and item.state in SCOPE_STATE_ORDER:
                earned = SCOPE_STATE_ORDER.index(item.state) >= SCOPE_STATE_ORDER.index(wanted)
        elif evidence.startswith("record_state:"):
            _, record_type, wanted = evidence.split(":", 2)
            if record_type not in known_types:
                known_types[record_type] = (
                    conn.execute(_TYPE_SQL, {"type": record_type}).first() is not None
                )
            if not known_types[record_type]:
                missing = True  # skipped, never an error
            else:
                states = conn.execute(
                    _RELATED_SQL, {"item": item.id, "type": record_type, "voided": False}
                ).all()
                earned = any(str(s.status) == wanted for s in states)
        if earned:
            pct += step.weight
            names.append(step.name)
    return min(pct, HUNDRED), names, missing


def compute_figure(
    conn: Connection,
    iwp_id: str,
    rules: Rules,
    manual: Sequence[dict[str, str]] = (),
) -> Figure:
    """The earned figure of ``iwp_id`` over every non-void item (rule 1: no viewer is applied)."""
    items = scope_items(conn, iwp_id)
    weights = _weights(items)
    held = {(e["scope_item_id"], e["step"]) for e in manual}
    known: dict[str, bool] = {}
    total_weight = sum(weights, Fraction(0))
    weighted = Fraction(0)
    out: list[ItemEarned] = []
    missing_type = False
    for item, weight in zip(items, weights, strict=True):
        pct, names, missing = _earned_steps(conn, rules, item, held, known)
        missing_type = missing_type or missing
        weighted += weight * pct
        out.append(
            ItemEarned(
                item_id=item.id,
                key=item.key,
                commodity=item.commodity,
                pct=round_half_up(pct),
                steps=tuple(names),
                hours=item.hours_text,
            )
        )
    whole = weighted / total_weight if total_weight else Fraction(0)
    return Figure(
        pct=min(round_half_up(whole), Decimal("100.0")),
        edition=rules.edition,
        items=out,
        missing_type=missing_type,
        item_hours_missing={i.id: i.hours is None for i in items},
    )


def iwp_scope(conn: Connection, iwp_id: str) -> str:
    """The scope of the IWP (``RecordNotFoundError`` when there is none)."""
    row = conn.execute(_IWP_SQL, {"id": iwp_id, "type": IWP}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {iwp_id!r}")
    return str(row.scope)


def figure_of(
    conn: Connection, iwp_id: str, *, manual: Sequence[dict[str, str]] | None = None
) -> Figure:
    """The unfiltered figure the stored row would hold now: the edition of the stored row when
    there is one (a recorded figure keeps its edition), else the one in force; the stored manual
    credit unless ``manual`` is given."""
    scope = iwp_scope(conn, iwp_id)
    stored = stored_progress(conn, iwp_id)
    rules = rules_for(stored.edition) if stored is not None else edition_for(conn, scope)
    held = manual if manual is not None else (stored.manual if stored is not None else [])
    return compute_figure(conn, iwp_id, rules, held)


def earned_fraction(conn: Connection, iwp_id: str, *, viewer: Viewer | None = None) -> Earned:
    """Earned progress of an IWP. ``pct`` is the stored figure whoever reads (rule 1). With a
    ``viewer`` the IWP must be one it may open (one not-found otherwise) and ``items`` lists only
    the items it may open, with the note ``some items not shown`` when any are hidden (no count)."""
    if viewer is not None:
        confidentiality.require_visible(conn, iwp_id, viewer)
    figure = figure_of(conn, iwp_id)
    items = figure.items
    notes: list[str] = []
    if viewer is not None:
        hidden = confidentiality.hidden_among(conn, [i.item_id for i in items], viewer)
        if hidden:
            items = [i for i in items if i.item_id not in hidden]
            notes.append(NOTE_HIDDEN)
    missing = sum(1 for i in items if figure.item_hours_missing[i.item_id])
    if missing:
        notes.append(f"hours missing on {missing} items")
    if figure.missing_type:
        notes.append(NOTE_NO_TYPE)
    return Earned(pct=figure.pct, edition=figure.edition, items=list(items), notes=notes)


def figure_text(value: Decimal) -> str:
    """The figure as the events and the table carry it (``"42.5"``)."""
    return f"{value:.1f}"
