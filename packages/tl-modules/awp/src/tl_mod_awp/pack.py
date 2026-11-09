"""The IWP work pack: data assembly and the one HTML file a foreman prints (P2-I5-T07a).

Everything shown is read through the viewer's class filter (``tl_core.confidentiality``): a hidden
record is absent, and nothing of it reaches the HTML. Every value that comes from a record goes
through ``_e`` (one escape helper) before it reaches the template; the template holds no record
value, only the slots below. No Jinja2: the template is a package file read with
``importlib.resources`` and filled by ``string.Template.substitute``.

The QR code is optional: ``segno`` is the extra ``pack``. Without it the file is written with no
codes and ``QR_MISSING_NOTE`` says so. A QR code carries the document key (a record key), never a
URL and never a record id.
"""

from __future__ import annotations

import html
import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from importlib import resources
from string import Template
from typing import Any, Final

from sqlalchemy import Connection, text
from tl_core import confidentiality as cf
from tl_core.confidentiality import Viewer, not_hidden
from tl_core.services.errors import RecordNotFoundError

from tl_mod_awp import iwp_views
from tl_mod_awp.common import has_table
from tl_mod_awp.progress import engine

#: The materials take-off line table (the materials module owns it; awp names it, never imports).
MTO_TABLE: Final = "cur_materials_mto_line"
TEMPLATE_NAME: Final = "pack_template.html"
NO_SAFETY: Final = "No safety plan attached yet."
NO_QUALITY: Final = "No inspection and test plan attached yet."
NOT_TRACKED: Final = "not tracked yet"
QR_MISSING_NOTE: Final = "QR codes not drawn: the pack extra is not installed."
EMPTY: Final = "-"


@dataclass(frozen=True)
class Cover:
    number: str
    title: str
    state: str
    discipline: str | None
    foreman: str | None
    cwp_number: str | None
    planned_start: str | None
    planned_finish: str | None
    estimated_hours: Decimal | None
    crew_text: str | None


@dataclass(frozen=True)
class ScopeLine:
    key: str | None  # None for a tag (tags have no number)
    type: str
    description: str | None
    qty: Decimal | None
    uom: str | None
    pct: Decimal | None  # None for a tag
    steps: tuple[str, ...]


@dataclass(frozen=True)
class Drawing:
    key: str
    title: str
    pin: str


@dataclass(frozen=True)
class MtoLine:
    line_no: int
    item_key: str | None
    qty: Decimal | None
    uom: str | None
    reserved: Decimal | None
    issued: Decimal | None


@dataclass(frozen=True)
class Signoff:
    who: str
    role: str
    day: str


@dataclass(frozen=True)
class PackData:
    iwp_id: str  # never printed; the caller names the IWP to the file service with it
    cover: Cover
    scope: tuple[ScopeLine, ...]
    drawings: tuple[Drawing, ...]
    mto: tuple[MtoLine, ...]
    signoffs: tuple[Signoff, ...]
    safety: str
    quality: str
    permits: str
    generated_on: date
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Rendered:
    html: str
    qr: bool  # True when the QR codes were drawn
    notes: tuple[str, ...]


def _e(value: object) -> str:
    """The one escape of a value that reaches the page (``None`` shows as a dash)."""
    return EMPTY if value is None else html.escape(str(value), quote=True)


def _table(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    head = "".join(f"<th>{_e(c)}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _num(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _cover(data: PackData) -> str:
    c = data.cover
    pairs: list[tuple[str, object]] = [
        ("IWP", c.number),
        ("Title", c.title),
        ("State", c.state),
        ("Discipline", c.discipline),
        ("Foreman", c.foreman),
        ("CWP", c.cwp_number),
        ("Planned start", c.planned_start),
        ("Planned finish", c.planned_finish),
        ("Estimated hours", _num(c.estimated_hours)),
        ("Crew", c.crew_text),
    ]
    cells = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in pairs)
    return f"<h1>{_e(c.title)}</h1><dl>{cells}</dl>"


def _scope(data: PackData) -> str:
    rows = [
        (
            line.key,
            line.type,
            line.description,
            _num(line.qty),
            line.uom,
            _num(line.pct),
            ", ".join(line.steps) if line.steps else None,
        )
        for line in data.scope
    ]
    return _table(("Key", "Type", "Description", "Qty", "UoM", "Pct", "Steps"), rows)


def _drawings(data: PackData, qr_svg: Callable[[str], str] | None) -> str:
    if not data.drawings:
        return "<p>No drawings pinned.</p>"
    parts: list[str] = []
    for d in data.drawings:
        code = qr_svg(d.key) if qr_svg is not None else ""
        parts.append(
            f'<div class="drawing">{code}<div>{_e(d.key)}</div>'
            f"<div>{_e(d.title)}</div><div>pin {_e(d.pin)}</div></div>"
        )
    notes = "".join(f'<p class="note">{_e(n)}</p>' for n in data.notes)
    return "".join(parts) + notes


def _mto(data: PackData) -> str:
    rows = [
        (m.line_no, m.item_key, _num(m.qty), m.uom, _num(m.reserved), _num(m.issued))
        for m in data.mto
    ]
    return _table(("Line", "Item", "Qty", "UoM", "Reserved", "Issued"), rows)


def _signoff(data: PackData) -> str:
    return _table(("Who", "Role", "Day"), [(s.who, s.role, s.day) for s in data.signoffs])


@cache
def _template() -> Template:
    source = resources.files("tl_mod_awp").joinpath(TEMPLATE_NAME).read_text(encoding="utf-8")
    return Template(source)


def _qr_drawer(segno: Any) -> Callable[[str], str]:
    """A function that draws one key as an inline SVG code, from the imported ``segno``."""

    def draw(key: str) -> str:
        return str(segno.make(key, error="m").svg_inline(scale=2, border=1))

    return draw


def render_html(data: PackData) -> Rendered:
    """The pack as one HTML page. The QR codes are drawn only when ``segno`` is importable; a
    missing library is a note, never an error (the page is still written)."""
    notes = [*data.notes]
    qr_svg: Callable[[str], str] | None = None
    try:
        segno: Any = importlib.import_module("segno")  # the optional extra `pack`
    except ImportError:
        notes.append(QR_MISSING_NOTE)
    else:
        qr_svg = _qr_drawer(segno)

    page = _template().substitute(
        cover=_cover(data),
        scope=_scope(data),
        drawings=_drawings(data, qr_svg),
        mto=_mto(data),
        safety=_e(data.safety),
        quality=_e(data.quality),
        permits=_e(data.permits),
        signoff=_signoff(data),
        generated=_e(data.generated_on.isoformat()),
    )
    return Rendered(html=page, qr=qr_svg is not None, notes=tuple(notes))


def _drawing_rows(conn: Connection, iwp_id: str, viewer: Viewer) -> tuple[Drawing, ...]:
    visible, extra = not_hidden("l.to_id", viewer)
    rows = conn.execute(
        text(
            "SELECT d.key, d.title, l.pin FROM cur_links l "
            "JOIN cur_core_record d ON d.id = l.to_id "
            "WHERE l.from_id = :iwp AND l.pin IS NOT NULL AND l.status = 'active' "
            f"AND {visible} ORDER BY d.key, l.link_id"
        ),
        {"iwp": iwp_id, **extra},
    ).mappings()
    return tuple(Drawing(key=str(r["key"]), title=str(r["title"]), pin=str(r["pin"])) for r in rows)


def _mto_rows(conn: Connection, iwp_id: str, viewer: Viewer) -> tuple[MtoLine, ...]:
    if not has_table(conn, MTO_TABLE):
        return ()
    vis_line, extra_line = not_hidden("m.id", viewer)
    vis_item, extra_item = not_hidden("r.id", viewer)
    rows = conn.execute(
        text(
            f"SELECT m.line_no, r.key, m.qty, m.uom, m.reserved_qty, m.issued_qty "
            f"FROM {MTO_TABLE} m LEFT JOIN cur_core_record r ON r.id = m.project_item_id "
            f"WHERE m.work_package_id = :iwp AND {vis_line} "
            f"AND (r.id IS NULL OR {vis_item}) ORDER BY m.line_no, m.id"
        ),
        {"iwp": iwp_id, **extra_line, **extra_item},
    ).mappings()
    return tuple(
        MtoLine(
            line_no=int(r["line_no"]),
            item_key=None if r["key"] is None else str(r["key"]),
            qty=_dec(r["qty"]),
            uom=None if r["uom"] is None else str(r["uom"]),
            reserved=_dec(r["reserved_qty"]),
            issued=_dec(r["issued_qty"]),
        )
        for r in rows
    )


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def build_pack_data(
    conn: Connection,
    scope: str,
    number: str,
    viewer: Viewer | None = None,
    *,
    generated_on: date | None = None,
) -> PackData:
    """The data of the pack of one IWP, read through ``viewer``. Raises ``RecordNotFoundError``
    for a missing, hidden or void IWP (the same answer for each)."""
    who = viewer if viewer is not None else cf.current_viewer()
    with cf.use_viewer(who):
        detail = iwp_views.iwp_detail(conn, scope, number)
        if detail is None:
            raise RecordNotFoundError(f"no IWP {number}")
        scope_rows = iwp_views.iwp_scope(conn, scope, number) or []
        earned = engine.earned_fraction(conn, detail.id, viewer=who)
        by_item = {item.item_id: item for item in earned.items}
        lines = tuple(
            ScopeLine(
                key=row.number,
                type=row.type,
                description=row.description,
                qty=row.qty,
                uom=row.uom,
                pct=by_item[row.id].pct if row.id in by_item else None,
                steps=by_item[row.id].steps if row.id in by_item else (),
            )
            for row in scope_rows
        )
        return PackData(
            iwp_id=detail.id,
            cover=Cover(
                number=detail.number,
                title=detail.title,
                state=detail.state,
                discipline=detail.discipline,
                foreman=detail.foreman,
                cwp_number=detail.cwp_number,
                planned_start=detail.planned_start,
                planned_finish=detail.planned_finish,
                estimated_hours=detail.estimated_hours,
                crew_text=detail.crew_text,
            ),
            scope=lines,
            drawings=_drawing_rows(conn, detail.id, who),
            mto=_mto_rows(conn, detail.id, who),
            signoffs=tuple(
                Signoff(
                    who=str(s.get("by", EMPTY)),
                    role=str(s.get("role", EMPTY)),
                    day=str(s.get("at", EMPTY))[:10],
                )
                for s in detail.signoffs
            ),
            safety=NO_SAFETY,
            quality=NO_QUALITY,
            permits=NOT_TRACKED,
            generated_on=generated_on if generated_on is not None else date.today(),
            notes=tuple(earned.notes),
        )


__all__ = [
    "MTO_TABLE",
    "NOT_TRACKED",
    "NO_QUALITY",
    "NO_SAFETY",
    "QR_MISSING_NOTE",
    "PackData",
    "Rendered",
    "build_pack_data",
    "render_html",
]
