"""Parser for the filter language (brief 10.2, 7.5): text to :mod:`tl_core.query.ast`.

Hand-written recursive descent over the characters, so every error carries the 0-based offset of
the offending character. The grammar (whitespace between terms is an implicit AND):

.. code-block:: text

    query    := or_expr?                               blank text parses to None
    or_expr  := and_expr ( "OR" and_expr )*            keywords are case-insensitive
    and_expr := unary ( ["AND"] unary )*
    unary    := ( "-" | "NOT" ) unary | primary
    primary  := "(" or_expr ")" | linked | count | missing | field_term | text
    field_term := FIELD OP VALUE                       FIELD: envelope column or psets.<a>.<b>
    OP       := ":" | "=" | "!=" | "~" | "<" | "<=" | ">" | ">="
    linked   := "linked" [ "(" REL ")" ] [ ":" TYPE ] [ "." unary ]
    count    := "count(" linked ")" OP INTEGER
    missing  := "missing(" ("link" | "linked") [ "(" REL ")" ] [ ":" TYPE ] ")"
    text     := WORD | quoted string                   searches key, title and description

Precedence from tightest: ``-``/``NOT``, implicit/explicit ``AND``, ``OR``. A value is a bare
run of characters (no spaces, parentheses or quotes) or a quoted string with ``\\"`` and ``\\\\``
escapes. What a bare value means depends on the field: text columns always take it as text;
integer and boolean columns check it; date columns take ``2026-10-09``, a date-time, ``+7d``,
``-3d`` or ``today``; pset properties infer ``null``, booleans, numbers and relative dates
and otherwise keep text (quote a value to force text).

The parser never raises anything but :class:`~tl_core.query.api.QuerySyntaxError`, and bounds its
input (length, nesting, node count) so no input can exhaust the stack or build a huge SQL tree.
"""

from __future__ import annotations

import difflib
import re

from tl_core.query.api import QuerySyntaxError
from tl_core.query.ast import (
    And,
    Compare,
    CompareOp,
    CountLinked,
    Expr,
    Linked,
    MissingLink,
    Not,
    Or,
    Text,
    Value,
)
from tl_core.query.fields import (
    ENVELOPE_FIELDS,
    MAX_INT,
    OP_CHARS,
    OPS_BY_KIND,
    PSET_OPS,
    PSET_PATH_RE,
    QUOTES,
    TYPE_RE,
    Field,
)
from tl_core.query.temporal import parse_literal, parse_relative

MAX_QUERY_LENGTH = 2000
MAX_DEPTH = 32
MAX_NODES = 200

_INT_RE = re.compile(r"-?\d+")
_PSET_INT_RE = re.compile(r"-?(?:0|[1-9]\d*)")
_PSET_FLOAT_RE = re.compile(r"-?(?:0|[1-9]\d*)\.\d+")
_REL_RE = re.compile(r"\*|[A-Za-z_][A-Za-z0-9_-]*")
_WORD_STOP = frozenset("()" + QUOTES + OP_CHARS)


def parse_text(text: str) -> Expr | None:
    """Parse query text; blank text gives ``None``. Raises ``QuerySyntaxError``."""
    if len(text) > MAX_QUERY_LENGTH:
        raise QuerySyntaxError(
            f"query is longer than {MAX_QUERY_LENGTH} characters", MAX_QUERY_LENGTH
        )
    for position, char in enumerate(text):
        if (ord(char) < 32 and not char.isspace()) or 0xD800 <= ord(char) <= 0xDFFF:
            raise QuerySyntaxError("control characters are not allowed in a query", position)
    return _Parser(text).parse()


class _Parser:
    def __init__(self, text: str) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.depth = 0
        self.nodes = 0

    # --- helpers ------------------------------------------------------------------------------

    def err(self, message: str, position: int | None = None) -> QuerySyntaxError:
        return QuerySyntaxError(message, self.i if position is None else position)

    def count(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise self.err(f"query is too complex (more than {MAX_NODES} terms)")

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise self.err(f"query is nested more than {MAX_DEPTH} levels deep")

    def leave(self) -> None:
        self.depth -= 1

    def ws(self) -> None:
        while self.i < self.n and self.s[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    def at_keyword(self, keyword: str) -> bool:
        end = self.i + len(keyword)
        if self.s[self.i : end].lower() != keyword:
            return False
        return end >= self.n or self.s[end].isspace() or self.s[end] == "("

    def expect(self, char: str, what: str) -> None:
        if self.peek() != char:
            raise self.err(f"expected {char!r} {what}")
        self.i += 1

    # --- grammar ------------------------------------------------------------------------------

    def parse(self) -> Expr | None:
        self.ws()
        if self.i >= self.n:
            return None
        expr = self.or_expr()
        self.ws()
        if self.i < self.n:
            if self.s[self.i] == ")":
                raise self.err("unmatched ')'")
            raise self.err(f"unexpected {self.s[self.i]!r}")
        return expr

    def or_expr(self) -> Expr:
        items = [self.and_expr()]
        while True:
            self.ws()
            if not self.at_keyword("or"):
                break
            self.i += 2
            self.ws()
            if self.i >= self.n or self.peek() == ")":
                raise self.err("expected a term after OR")
            items.append(self.and_expr())
        if len(items) == 1:
            return items[0]
        self.count()
        flat: list[Expr] = []
        for item in items:
            flat.extend(item.items if isinstance(item, Or) else (item,))
        return Or(tuple(flat))

    def and_expr(self) -> Expr:
        items = [self.unary()]
        while True:
            self.after_term()
            self.ws()
            if self.i >= self.n or self.peek() == ")" or self.at_keyword("or"):
                break
            if self.at_keyword("and"):
                self.i += 3
                self.ws()
                if self.i >= self.n or self.peek() == ")" or self.at_keyword("or"):
                    raise self.err("expected a term after AND")
                if self.at_keyword("and"):
                    raise self.err("expected a term after AND")
            items.append(self.unary())
        if len(items) == 1:
            return items[0]
        self.count()
        flat: list[Expr] = []
        for item in items:
            flat.extend(item.items if isinstance(item, And) else (item,))
        return And(tuple(flat))

    def after_term(self) -> None:
        if self.i < self.n and not self.s[self.i].isspace() and self.s[self.i] != ")":
            raise self.err(f"expected a space before {self.s[self.i]!r}")

    def unary(self) -> Expr:
        self.enter()
        try:
            if self.peek() == "-":
                self.i += 1
                if self.i >= self.n or self.s[self.i].isspace() or self.s[self.i] == ")":
                    raise self.err("expected a term after '-'")
                self.count()
                return Not(self.unary())
            if self.at_keyword("not"):
                self.i += 3
                self.ws()
                if self.i >= self.n or self.peek() == ")":
                    raise self.err("expected a term after NOT")
                self.count()
                return Not(self.unary())
            return self.primary()
        finally:
            self.leave()

    def primary(self) -> Expr:
        char = self.peek()
        if char == "":
            raise self.err("expected a term")
        if char == "(":
            return self.group()
        if char == ")":
            raise self.err("unmatched ')'")
        if self.at_keyword("or") or self.at_keyword("and"):
            raise self.err("expected a term, found a keyword; quote the word to search for it")
        if char in QUOTES:
            start = self.i
            quoted = self.read_quoted()
            if self.peek() != "" and self.peek() in OP_CHARS:
                raise self.err("a quoted text cannot be a field name", self.i)
            if not quoted.strip():
                raise self.err("empty search text", start)
            self.count()
            return Text(quoted)
        start = self.i
        while self.i < self.n and not self.s[self.i].isspace() and self.s[self.i] not in _WORD_STOP:
            self.i += 1
        word = self.s[start : self.i]
        if not word:
            raise self.err(f"unexpected {char!r}; a field name must come before an operator")
        lower = word.lower()
        following = self.peek()
        if lower.startswith("linked.") or (
            lower == "linked" and (following == "" or following.isspace() or following in "():.)")
        ):
            self.i = start + len("linked")
            return self.linked(allow_where=True)
        if lower == "count" and following == "(":
            return self.count_term()
        if lower == "missing" and following == "(":
            return self.missing_term()
        if lower == "path" and following == "(":
            raise self.err("path(...) is not supported yet", start)
        if following != "" and following in OP_CHARS:
            return self.field_term(word, start)
        self.count()
        return Text(word)

    def group(self) -> Expr:
        opened = self.i
        self.i += 1
        self.ws()
        if self.peek() == ")":
            raise self.err("empty parentheses", opened)
        inner = self.or_expr()
        self.ws()
        if self.peek() != ")":
            raise self.err(f"missing ')' for the '(' at position {opened}")
        self.i += 1
        return inner

    # --- quoted strings and values ------------------------------------------------------------

    def read_quoted(self) -> str:
        quote = self.s[self.i]
        start = self.i
        self.i += 1
        out: list[str] = []
        while self.i < self.n:
            char = self.s[self.i]
            if char == "\\" and self.i + 1 < self.n and self.s[self.i + 1] in (quote, "\\"):
                out.append(self.s[self.i + 1])
                self.i += 2
                continue
            if char == quote:
                self.i += 1
                return "".join(out)
            out.append(char)
            self.i += 1
        raise self.err("unterminated quoted string", start)

    def read_op(self, allow_tilde: bool = True) -> tuple[CompareOp, int]:
        position = self.i
        char = self.s[self.i]
        nxt = self.s[self.i + 1] if self.i + 1 < self.n else ""
        op: CompareOp
        if char in ":=":
            op, width = "=", 1
        elif char == "~":
            op, width = "~", 1
        elif char == "!":
            if nxt != "=":
                raise self.err("expected '=' after '!'")
            op, width = "!=", 2
        elif char == "<":
            op, width = ("<=", 2) if nxt == "=" else ("<", 1)
        elif char == ">":
            op, width = (">=", 2) if nxt == "=" else (">", 1)
        else:
            raise self.err(f"expected an operator, found {char!r}")
        if op == "~" and not allow_tilde:
            raise self.err("'~' cannot be used here", position)
        self.i += width
        return op, position

    def read_value(self) -> tuple[str, bool, int]:
        """The raw value text, whether it was quoted, and where it starts."""
        position = self.i
        if self.i >= self.n or self.s[self.i].isspace() or self.s[self.i] == ")":
            raise self.err("expected a value after the operator")
        char = self.s[self.i]
        if char in QUOTES:
            return self.read_quoted(), True, position
        if char == "(":
            raise self.err("a value cannot start with '('; quote it")
        if char in OP_CHARS:
            raise self.err(f"unexpected {char!r} in the value; quote the value to use it as text")
        while (
            self.i < self.n and not self.s[self.i].isspace() and self.s[self.i] not in "()" + QUOTES
        ):
            self.i += 1
        return self.s[position : self.i], False, position

    # --- field terms --------------------------------------------------------------------------

    def resolve_field(self, word: str, position: int) -> tuple[str, Field | None]:
        lower = word.lower()
        if lower == "psets" or lower.startswith("psets."):
            path = "psets" + word[5:]
            if PSET_PATH_RE.match(path) is None:
                raise self.err(
                    "a pset path looks like psets.<pset>.<property> (letters, digits, _ and -)",
                    position,
                )
            return path, None
        found = ENVELOPE_FIELDS.get(lower)
        if found is None:
            close = difflib.get_close_matches(lower, list(ENVELOPE_FIELDS), n=1)
            hint = f"; did you mean {close[0]!r}?" if close else ""
            raise self.err(
                f"unknown field {word!r}{hint} (quote the text to search for it)", position
            )
        return found.name, found

    def field_term(self, word: str, start: int) -> Expr:
        path, field = self.resolve_field(word, start)
        op, op_position = self.read_op()
        raw, quoted, value_position = self.read_value()
        value = self.coerce(path, field, op, raw, quoted, op_position, value_position)
        self.count()
        return Compare(path, op, value)

    def coerce(
        self,
        path: str,
        field: Field | None,
        op: CompareOp,
        raw: str,
        quoted: bool,
        op_position: int,
        value_position: int,
    ) -> Value:
        kind = field.kind if field is not None else "pset"
        allowed = PSET_OPS if field is None else OPS_BY_KIND[field.kind]
        if op not in allowed:
            raise self.err(f"operator {op!r} cannot be used with {path} ({kind})", op_position)
        if not quoted and raw.lower() == "null":
            if op in ("=", "!="):
                return None
            raise self.err("null can only be compared with ':', '=' or '!='", value_position)
        if kind == "text":
            return raw
        if kind == "int":
            if _INT_RE.fullmatch(raw) is None or abs(int(raw)) > MAX_INT:
                raise self.err(f"{path} takes a whole number", value_position)
            return int(raw)
        if kind == "bool":
            if raw.lower() not in ("true", "false"):
                raise self.err(f"{path} takes true or false", value_position)
            return raw.lower() == "true"
        if kind == "datetime":
            return self.coerce_date(raw, value_position)
        # pset property: infer unless the value was quoted or is a "contains" pattern
        if quoted or op == "~":
            return raw
        try:
            relative = parse_relative(raw)
        except ValueError as exc:
            raise self.err(str(exc), value_position) from exc
        if relative is not None:
            return relative
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        if _PSET_INT_RE.fullmatch(raw) is not None:
            if abs(int(raw)) > MAX_INT:
                raise self.err("number out of range", value_position)
            return int(raw)
        if _PSET_FLOAT_RE.fullmatch(raw) is not None:
            number = float(raw)
            if number != number or number in (float("inf"), float("-inf")):
                raise self.err("number out of range", value_position)
            return number
        return raw

    def coerce_date(self, raw: str, position: int) -> Value:
        try:
            relative = parse_relative(raw)
            if relative is not None:
                return relative
            literal = parse_literal(raw)
        except ValueError as exc:
            raise self.err(f"not a valid date: {exc}", position) from exc
        if literal is None:
            raise self.err(
                "expected a date such as 2026-10-09, a date-time, +7d, -3d or today", position
            )
        return raw

    # --- link operators -----------------------------------------------------------------------

    def linked(self, *, allow_where: bool) -> Linked:
        """After the word ``linked`` (or ``link`` inside ``missing``): relation, type, condition."""
        relation = self.relation_group()
        target: str | None = None
        where: Expr | None = None
        if self.peek() == ":":
            self.i += 1
            target, where = self.target_type(allow_where=allow_where)
        if where is None and self.peek() == ".":
            if not allow_where:
                raise self.err("missing(...) does not take a condition")
            self.i += 1
            if self.i >= self.n or self.s[self.i].isspace():
                raise self.err("expected a condition after '.'")
            where = self.unary()
        self.count()
        return Linked(relation, target, where)

    def relation_group(self) -> str | None:
        if self.peek() != "(":
            return None
        self.i += 1
        self.ws()
        match = _REL_RE.match(self.s, self.i)
        if match is None:
            raise self.err("expected a relation code, or * for any relation")
        self.i = match.end()
        self.ws()
        self.expect(")", "after the relation code")
        return None if match.group() == "*" else match.group()

    def target_type(self, *, allow_where: bool) -> tuple[str, Expr | None]:
        """A record type after ``:``; ``NCR.status:open`` splits into ``NCR`` and a condition."""
        match = TYPE_RE.match(self.s, self.i)
        if match is None:
            raise self.err("expected a record type after ':'")
        word = match.group()
        following = self.s[match.end()] if match.end() < self.n else ""
        if following == "" or following not in OP_CHARS:
            self.i = match.end()
            return word, None
        segments = word.split(".")
        if len(segments) == 1:
            raise self.err(f"unexpected {following!r} after the record type", match.end())
        if not allow_where:
            raise self.err("missing(...) does not take a condition", match.end())
        cut = next(
            (k for k, seg in enumerate(segments) if k >= 1 and seg.lower() == "psets"),
            len(segments) - 1,
        )
        target = ".".join(segments[:cut])
        self.i = self.i + len(target) + 1
        return target, self.unary()

    def count_term(self) -> Expr:
        self.i += 1  # (
        self.ws()
        if self.s[self.i : self.i + 6].lower() != "linked":
            raise self.err("count(...) takes a linked term, for example count(linked:NCR)>0")
        self.i += 6
        linked = self.linked(allow_where=True)
        self.ws()
        self.expect(")", "to close count(")
        if self.i >= self.n or self.s[self.i] not in OP_CHARS:
            raise self.err("expected a comparison after count(...), for example >0")
        op, _ = self.read_op(allow_tilde=False)
        raw, _quoted, value_position = self.read_value()
        if _INT_RE.fullmatch(raw) is None or abs(int(raw)) > MAX_INT:
            raise self.err("count(...) is compared with a whole number", value_position)
        self.count()
        return CountLinked(linked, op, int(raw))

    def missing_term(self) -> Expr:
        self.i += 1  # (
        self.ws()
        lowered = self.s[self.i : self.i + 6].lower()
        if lowered == "linked":
            self.i += 6
        elif lowered[:4] == "link":
            self.i += 4
        else:
            raise self.err("missing(...) takes a link term, for example missing(link:permit)")
        linked = self.linked(allow_where=False)
        self.ws()
        self.expect(")", "to close missing(")
        self.count()
        return MissingLink(linked.relation, linked.target_type)
