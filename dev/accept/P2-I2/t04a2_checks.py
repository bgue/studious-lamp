"""The checks of T04a2.py (owner filter and review groups); kept here so the script stays short."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import c2_checks as c2
from awp_world import SCOPE, hidden_record
from tl_core.constraints import queries, review_groups

ok = c2.ok


def shape(groups: Any) -> list[tuple[Any, ...]]:
    return [(g.label, g.count, g.blocking, g.aging, g.keys) for g in groups]


def owner_checks(w: c2.C2) -> None:
    everyone = w.read(queries.list_constraints, "default", SCOPE)
    mine = w.read(queries.list_constraints, "default", SCOPE, owner="user:user")
    n = w.read(queries.count_constraints, "default", SCOPE, owner="user:user")
    expect = {v.key for v in everyone if v.owner == "user:user"}
    ok(
        "owner filter returns only that owner's rows",
        len(everyone) == 3
        and all(v.owner == "user:user" for v in mine)
        and {v.key for v in mine} == expect
        and len(mine) == 2,
    )
    ok("count_constraints agrees with the owner filter", n == len(mine) == 2)
    uma = w.read(queries.list_constraints, "default", SCOPE, owner="user:uma")
    ok("an assigned owner finds its one constraint", [v.owner for v in uma] == ["user:uma"])
    refused = []
    for fn in (queries.list_constraints, queries.count_constraints):
        try:
            w.read(fn, "default", SCOPE, owner="")
        except ValueError:
            refused.append(fn.__name__)
    ok("owner='' raises ValueError", refused == ["list_constraints", "count_constraints"])


def group_checks(w: c2.C2) -> None:
    base = w.read(queries.list_constraints, "default", SCOPE)[0]

    def view(key: str, owner: str | None, cat: str, age: int, aging: bool, sev: str) -> Any:
        return replace(
            base, key=key, owner=owner, category=cat, age_days=age, aging=aging, severity=sev
        )

    views = [
        view("P-0003", "user:uma", "permit", 3, False, "blocking"),
        view("P-0001", "user:user", "materials", 30, True, "advisory"),
        view("P-0002", None, "materials", 10, False, "blocking"),
        view("P-0004", "user:user", "permit", 15, True, "blocking"),
    ]
    by_owner = shape(review_groups(list(reversed(views)), "owner"))
    ok(
        "groups by owner: label, count, blocking, aging, keys; unowned last",
        by_owner
        == [
            ("user:uma", 1, 1, 0, ("P-0003",)),
            ("user:user", 2, 1, 2, ("P-0001", "P-0004")),
            ("-", 1, 1, 0, ("P-0002",)),
        ],
    )
    ok(
        "groups by category",
        shape(review_groups(views, "category"))
        == [
            ("materials", 2, 1, 1, ("P-0001", "P-0002")),
            ("permit", 2, 2, 1, ("P-0003", "P-0004")),
        ],
    )
    ok(
        "groups by age band with aging and keys",
        shape(review_groups(views, "age"))
        == [
            ("0-7", 1, 1, 0, ("P-0003",)),
            ("8-14", 1, 1, 0, ("P-0002",)),
            ("15-28", 1, 1, 1, ("P-0004",)),
            ("29+", 1, 0, 1, ("P-0001",)),
        ],
    )
    ok(
        "empty age bands are kept with count 0",
        shape(review_groups([views[0], views[1]], "age"))
        == [
            ("0-7", 1, 1, 0, ("P-0003",)),
            ("8-14", 0, 0, 0, ()),
            ("15-28", 0, 0, 0, ()),
            ("29+", 1, 0, 1, ("P-0001",)),
        ],
    )
    ok(
        "no views: owner and category give no groups, age gives every band",
        review_groups([], "owner") == []
        and review_groups([], "category") == []
        and [g.count for g in review_groups([], "age")] == [0, 0, 0, 0],
    )
    refused = False
    try:
        review_groups(views, "x")
    except ValueError:
        refused = True
    ok("by='x' raises ValueError", refused)


def hidden_checks(w: c2.C2) -> None:
    secret = hidden_record(w)
    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    for who in ("default", "user", "agent"):
        rows = w.read(queries.list_constraints, who, SCOPE, owner="user:controller")
        n = w.read(queries.count_constraints, who, SCOPE, owner="user:controller")
        none = w.read(queries.count_constraints, who, SCOPE, owner="user:nobody")
        ok(
            f"hidden looks like missing below the class ({who})",
            rows == [] and n == none == 0 and not any(v.subject_id == secret for v in rows),
        )
    above = w.read(queries.count_constraints, "controller", SCOPE, owner="user:controller")
    got = w.read(queries.get_constraint, "controller", made.stream_id)
    ok("controller sees the restricted constraint under its owner", above == 1 and got is not None)


def checks(w: c2.C2, docs: dict[str, str]) -> None:
    owner_checks(w)
    group_checks(w)
    hidden_checks(w)
