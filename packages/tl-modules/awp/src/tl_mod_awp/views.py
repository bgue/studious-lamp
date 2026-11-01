"""Reads of the awp module (spec m3-wbs-cwp section 5): stubs, filled by ticket T10.

Every function takes a connection and a project scope and reads through the viewer's class filter
(ADR-0016). Nothing here writes and nothing checks an access word: the entry points do.
"""

from __future__ import annotations

from sqlalchemy import Connection


def cwp_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    discipline: str | None = None,
    cwa: str | None = None,
) -> list[object]:
    raise NotImplementedError("T10 writes the awp views")


def cwp_detail(conn: Connection, scope: str, number: str) -> object | None:
    raise NotImplementedError("T10 writes the awp views")


def cwa_list(conn: Connection, scope: str) -> list[object]:
    raise NotImplementedError("T10 writes the awp views")


def wbs_tree(conn: Connection, scope: str, *, depth: int | None = None) -> list[object]:
    raise NotImplementedError("T10 writes the awp views")


def wbs_detail(conn: Connection, scope: str, code: str) -> object | None:
    raise NotImplementedError("T10 writes the awp views")


def path(conn: Connection, scope: str, version: int | None = None) -> object | None:
    raise NotImplementedError("T10 writes the awp views")


def path_versions(conn: Connection, scope: str) -> list[object]:
    raise NotImplementedError("T10 writes the awp views")


def package_list(conn: Connection, scope: str, *, kind: str | None = None) -> list[object]:
    raise NotImplementedError("T10 writes the awp views")
