"""The X-ray criteria language (a subset) in Python, so the skill can run the same element queries as the viewer's 4D
configuration (`tradeQueries`, activity overrides).

    class = 'IfcWallStandardCase' and name like 'Wand-Ext%'
    class in ('IfcBeam', 'IfcMember') and not storey = 'Roof'
    "Pset_WallCommon.IsExternal" = TRUE

Supported: or / and / not, parentheses, = == != <> < <= > >=, [not] like (% and _, case-insensitive), [not] in (...),
is [not] null, a bare column (true test). Columns: class, name, type, storey, material, globalid, zone, or a property
'Pset.Prop' (bare or "quoted"); unknown columns read as null.
"""
from __future__ import annotations

import re
from typing import Any, Callable

TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<qname>\"[^\"]*\")|(?P<num>-?\d+(?:\.\d+)?)|(?P<op><>|!=|==|<=|>=|=|<|>|\(|\)|,)|(?P<id>[A-Za-z_][\w.]*))")
KEYWORDS = {'and', 'or', 'not', 'like', 'in', 'is', 'null', 'true', 'false'}


class QueryError(ValueError):
    pass


def tokenize(text: str) -> list[tuple[str, Any]]:
    out, i = [], 0
    while i < len(text):
        if text[i:].strip() == '':
            break
        m = TOKEN.match(text, i)
        if not m or m.end() == i:
            raise QueryError(f'unexpected character at {i + 1}: {text[i]!r}')
        i = m.end()
        if m.group('str') is not None:
            out.append(('str', m.group('str')[1:-1].replace("''", "'")))
        elif m.group('qname') is not None:
            out.append(('col', m.group('qname')[1:-1]))
        elif m.group('num') is not None:
            out.append(('num', float(m.group('num'))))
        elif m.group('op') is not None:
            out.append(('op', m.group('op')))
        else:
            w = m.group('id')
            out.append(('kw', w.lower()) if w.lower() in KEYWORDS else ('col', w))
    return out


def column(el: dict, name: str) -> Any:
    n = name.lower()
    if n == 'class':
        return el.get('class')
    if n in ('name', 'type', 'storey', 'material'):
        return el.get(n)
    if n == 'globalid':
        return el.get('globalId')
    if n == 'zone':
        z = el.get('zones') or []
        return z[0] if z else None
    props = el.get('props') or {}
    if name in props:
        return props[name]
    for k, v in props.items():  # bare property name: first set that has it
        if k.split('.', 1)[-1].lower() == n:
            return v
    return None


def like(value: Any, pattern: str) -> bool:
    if value is None:
        return False
    rx = '^' + ''.join('.*' if c == '%' else '.' if c == '_' else re.escape(c) for c in pattern) + '$'
    return re.match(rx, str(value), re.IGNORECASE | re.DOTALL) is not None


def compare(a: Any, op: str, b: Any) -> bool:
    if a is None or b is None:
        return False
    if isinstance(b, float):
        try:
            a = float(a)
        except (TypeError, ValueError):
            return False
    elif isinstance(b, bool):
        a = str(a).lower() in ('true', '1', 'yes') if not isinstance(a, bool) else a
    else:
        a, b = str(a).lower(), str(b).lower()
    return {'=': a == b, '==': a == b, '!=': a != b, '<>': a != b, '<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b}[op]


def compile_query(text: str) -> Callable[[dict], bool]:
    toks = tokenize(text)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else ('eof', None)

    def take(kind=None, val=None):
        nonlocal pos
        t = peek()
        if (kind and t[0] != kind) or (val is not None and t[1] != val):
            raise QueryError(f'expected {val or kind}, found {t[1]!r}')
        pos += 1
        return t

    def operand():
        t = take()
        if t[0] == 'col':
            return ('col', t[1])
        if t[0] in ('str', 'num'):
            return ('lit', t[1])
        if t == ('kw', 'true'):
            return ('lit', True)
        if t == ('kw', 'false'):
            return ('lit', False)
        if t == ('kw', 'null'):
            return ('lit', None)
        raise QueryError(f'unexpected {t[1]!r}')

    def value(o, el):
        return column(el, o[1]) if o[0] == 'col' else o[1]

    def primary():
        if peek() == ('op', '('):
            take()
            e = expr_or()
            take('op', ')')
            return e
        left = operand()
        t = peek()
        neg = False
        if t == ('kw', 'not'):
            take()
            neg = True
            t = peek()
        if t[0] == 'op' and t[1] in ('=', '==', '!=', '<>', '<', '<=', '>', '>='):
            take()
            right = operand()
            return lambda el, l=left, r=right, op=t[1]: compare(value(l, el), op, value(r, el))
        if t == ('kw', 'like'):
            take()
            right = operand()
            return lambda el, l=left, r=right, n=neg: like(value(l, el), str(value(r, el))) != n
        if t == ('kw', 'in'):
            take()
            take('op', '(')
            items = [operand()]
            while peek() == ('op', ','):
                take()
                items.append(operand())
            take('op', ')')
            return lambda el, l=left, it=items, n=neg: any(compare(value(l, el), '=', value(i, el)) for i in it) != n
        if t == ('kw', 'is'):
            take()
            isnot = False
            if peek() == ('kw', 'not'):
                take()
                isnot = True
            take('kw', 'null')
            return lambda el, l=left, n=isnot: (value(l, el) is None) != n
        return lambda el, l=left: compare(value(l, el), '=', True)

    def expr_not():
        if peek() == ('kw', 'not'):
            take()
            inner = expr_not()
            return lambda el: not inner(el)
        return primary()

    def expr_and():
        e = expr_not()
        while peek() == ('kw', 'and'):
            take()
            r = expr_not()
            e = (lambda a, b: lambda el: a(el) and b(el))(e, r)
        return e

    def expr_or():
        e = expr_and()
        while peek() == ('kw', 'or'):
            take()
            r = expr_and()
            e = (lambda a, b: lambda el: a(el) or b(el))(e, r)
        return e

    result = expr_or()
    if pos != len(toks):
        raise QueryError(f'unexpected {peek()[1]!r} at the end')
    return result
