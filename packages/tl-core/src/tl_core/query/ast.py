"""Query language AST (P0-I4 contract).

Shared by the parser (workstream A), the API and MCP (workstream C) and the TUI filter bar
(workstream D). Changing a node is a contract change and needs an orchestrator decision.

Surface syntax (brief 10.2, 7.5), whitespace-separated terms are ANDed:
    status:open                     Compare("status", "=", "open")
    title~bevel                     Compare("title", "~", "bevel")       contains, case-insensitive
    version>=2                      Compare("version", ">=", 2)
    updated_at<+7d                  Compare("updated_at", "<", RelativeDate(7))
    psets.valve_data.size_in>=2     Compare("psets.valve_data.size_in", ">=", 2)
    -status:void, not status:void   Not(Compare(...))
    a OR b, ( ... )                 Or / grouping
    linked:NCR                      Linked(relation=None, target_type="NCR", where=None)
    linked(raised_against).status:open
                                    Linked("raised_against", None, Compare("status", "=", "open"))
    count(linked:NCR)>0             CountLinked(Linked(None, "NCR", None), ">", 0)
    missing(link:permit)            MissingLink(relation=None, target_type="permit")
    bevel                           Text("bevel")   searches key, title, description
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompareOp = Literal["=", "!=", "<", "<=", ">", ">=", "~"]


@dataclass(frozen=True)
class RelativeDate:
    """A date relative to today in the project time zone: "+7d" is 7, "-3d" is -3, "today" is 0."""

    days: int


Value = str | int | float | bool | None | RelativeDate


@dataclass(frozen=True)
class Compare:
    path: str  # envelope column ("status", "title", ...) or "psets.<pset>[.x].<prop>"
    op: CompareOp
    value: Value


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Linked:
    relation: str | None  # relation code, or None for any relation
    target_type: str | None  # record type or type alias of the other end, or None for any
    where: Expr | None  # condition on the linked record


@dataclass(frozen=True)
class CountLinked:
    linked: Linked
    op: CompareOp
    value: int


@dataclass(frozen=True)
class MissingLink:
    relation: str | None
    target_type: str | None


@dataclass(frozen=True)
class And:
    items: tuple[Expr, ...]


@dataclass(frozen=True)
class Or:
    items: tuple[Expr, ...]


@dataclass(frozen=True)
class Not:
    item: Expr


Expr = Compare | Text | Linked | CountLinked | MissingLink | And | Or | Not
