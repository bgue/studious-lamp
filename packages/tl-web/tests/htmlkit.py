"""A small reader of the HTML the web client answers with (stdlib ``html.parser`` only).

Loaded by the ``htmlkit`` fixture of ``conftest.py`` (``--import-mode=importlib``: no test module
imports a sibling). ``parse(text)`` builds a tree; void elements (``img meta link br input`` and
the other HTML void tags) are never pushed on the open stack, so an ``<img>`` or ``<input>`` cannot
swallow the rest of its parent (T04 learning).

The questions the tests ask: an element by id, the ids in order, the rows and cells of a table, the
links, the text of a region, the buttons of the actions bar, the problems that would break the CSP.
"""

from __future__ import annotations

from collections.abc import Iterator
from html.parser import HTMLParser
from typing import Any

#: The HTML void elements: they have no end tag and no children.
VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
    | {"track", "wbr"}
)  # fmt: skip
#: The seven regions of a log page, in order (spec web-client-i1 section 7).
LOG_REGIONS = (
    "log-crumb",
    "log-filter",
    "log-table",
    "log-panel",
    "log-actions",
    "log-keys",
    "log-status",
)
#: The regions of the record page.
RECORD_REGIONS = ("rec-header", "rec-tabs", "log-actions", "log-panel", "rec-body", "log-status")


class Node:
    """One element: tag, attributes, children (nodes and strings)."""

    def __init__(self, tag: str, attrs: dict[str, str | None], parent: Node | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Node | str] = []

    def __repr__(self) -> str:
        return f"<{self.tag} {self.attrs}>"

    def get(self, name: str, default: str = "") -> str:
        value = self.attrs.get(name)
        return default if value is None else value

    def text(self) -> str:
        """The text of the element and everything under it (script and style bodies included)."""
        out: list[str] = []
        for child in self.children:
            out.append(child if isinstance(child, str) else child.text())
        return "".join(out)

    def descendants(self) -> Iterator[Node]:
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()

    def find_all(self, tag: str | None = None, **attrs: str) -> list[Node]:
        """Descendants of ``tag`` whose attributes equal ``attrs`` (``class_`` is ``class``)."""
        wanted = {k.rstrip("_").replace("_", "-"): v for k, v in attrs.items()}
        return [
            n
            for n in self.descendants()
            if (tag is None or n.tag == tag) and all(n.attrs.get(k) == v for k, v in wanted.items())
        ]

    def find(self, tag: str | None = None, **attrs: str) -> Node | None:
        found = self.find_all(tag, **attrs)
        return found[0] if found else None

    def within(self, ident: str) -> bool:
        node: Node | None = self
        while node is not None:
            if node.attrs.get("id") == ident:
                return True
            node = node.parent
        return False


class Doc(HTMLParser):
    """A parsed answer. ``Doc(text)``; the helpers below read it."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self._stack: list[Node] = [self.root]
        self.feed(text)
        self.close()

    # --- the parser -------------------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, dict(attrs), self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, dict(attrs), self._stack[-1])
        self._stack[-1].children.append(node)  # self-closing: never open

    def handle_endtag(self, tag: str) -> None:
        for pos in range(len(self._stack) - 1, 0, -1):
            if self._stack[pos].tag == tag:
                del self._stack[pos:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)

    # --- the questions ----------------------------------------------------------------------

    def all(self) -> list[Node]:
        return list(self.root.descendants())

    @property
    def ids(self) -> list[str]:
        """Every id in the document, in order."""
        return [n.attrs["id"] for n in self.all() if n.attrs.get("id")]  # type: ignore[misc]

    def regions(self, names: tuple[str, ...] = LOG_REGIONS) -> list[str]:
        """The ids of ``names`` that the page has, in document order."""
        return [i for i in self.ids if i in names]

    def by_id(self, ident: str) -> Node | None:
        return next((n for n in self.all() if n.attrs.get("id") == ident), None)

    def region_text(self, ident: str) -> str:
        node = self.by_id(ident)
        return "" if node is None else node.text()

    def status(self) -> str:
        """The text of ``#log-status``, stripped."""
        return self.region_text("log-status").strip()

    def meta(self, name: str) -> str | None:
        for n in self.all():
            if n.tag == "meta" and n.attrs.get("name") == name:
                return n.attrs.get("content")
        return None

    def pre(self, within: str | None = None) -> str:
        """The text of the first ``<pre>`` (in ``within``); ``""`` when there is none."""
        scope = self.root if within is None else self.by_id(within)
        found = scope.find("pre") if scope is not None else None
        return "" if found is None else found.text()

    def headers(self, within: str | None = None) -> list[str]:
        scope = self.root if within is None else self.by_id(within)
        return [] if scope is None else [th.text() for th in scope.find_all("th")]

    def table_rows(self, within: str | None = None) -> list[Node]:
        """The ``<tr>`` elements that hold ``<td>`` cells (not the header row)."""
        scope = self.root if within is None else self.by_id(within)
        if scope is None:
            return []
        return [tr for tr in scope.find_all("tr") if tr.find("td") is not None]

    @staticmethod
    def cells(row: Node) -> list[str]:
        return [td.text() for td in row.find_all("td")]

    def rows(self, within: str | None = None) -> list[list[str]]:
        """The cell texts of every body row."""
        return [self.cells(r) for r in self.table_rows(within)]

    def log_rows(self) -> list[Node]:
        """The rows of a log table: ``<tr data-number=...>``."""
        return [n for n in self.all() if n.tag == "tr" and "data-number" in n.attrs]

    def buttons(self) -> list[Node]:
        """The action buttons: ``<button data-command=...>``, in order."""
        return [n for n in self.all() if n.tag == "button" and "data-command" in n.attrs]

    def commands(self) -> list[str]:
        return [b.get("data-command") for b in self.buttons()]

    def links(self, within: str | None = None) -> list[tuple[str, str]]:
        """``(href, text)`` of every ``<a>`` (in ``within``, when given)."""
        scope = self.root if within is None else self.by_id(within)
        if scope is None:
            return []
        return [(a.get("href"), a.text()) for a in scope.find_all("a")]

    def images(self, within: str | None = None) -> list[Node]:
        scope = self.root if within is None else self.by_id(within)
        return [] if scope is None else scope.find_all("img")

    def field_names(self) -> list[str]:
        return [
            n.attrs["name"]  # type: ignore[misc]
            for n in self.all()
            if n.tag in ("input", "textarea", "select") and n.attrs.get("name")
        ]

    def visible_text(self) -> str:
        """The text a reader sees: everything outside ``<script>`` and ``<style>``."""
        out: list[str] = []

        def walk(node: Node) -> None:
            for child in node.children:
                if isinstance(child, str):
                    if child.strip():
                        out.append(child.strip())
                elif child.tag not in ("script", "style"):
                    walk(child)

        walk(self.root)
        return "\n".join(out)

    def inline_problems(self) -> list[str]:
        """What the CSP forbids: an inline script or style, a ``style=`` or ``on*=`` attribute."""
        found: list[str] = []
        for n in self.all():
            if n.tag == "script" and "src" not in n.attrs:
                found.append("script without src")
            if n.tag == "script" and n.text().strip():
                found.append("script with a body")
            if n.tag == "style":
                found.append("style element")
            found.extend(f"{n.tag}[{a}]" for a in n.attrs if a == "style" or a.startswith("on"))
        return found


def parse(text: str) -> Doc:
    return Doc(text)


def project_cells(
    headers: list[str], names: tuple[str, ...] | list[str], full: Any
) -> list[list[str]]:
    """``full`` (all columns, ``names`` order) cut to the columns the page shows (``headers``)."""
    positions = [list(names).index(h) for h in headers]
    return [[cells[i] for i in positions] for cells in full]
