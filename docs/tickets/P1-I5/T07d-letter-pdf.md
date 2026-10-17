# P1-I5-T07d — Letter template filling and a deterministic PDF writer

Status: ready
Tier: haiku
Labels: core, module
Depends on: — (a pure module: no other ticket, no database, no library)
Branch: `p1/i5-t07d-letter-pdf`

## Goal
`tl_mod_correspondence/letter.py` fills a letter template, lays the letter out as lines and writes the lines as a PDF 1.4 file by hand (built-in Helvetica, no library, no date, no random id), so the same letter always gives the same bytes. The constants, `LetterFields` and `LetterError` are written; `fill_template`, `compose_letter`, `_clean`, `_pdf_text` and `render_pdf` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass.

## Brief references (pasted)
> **Issue (brief 9, M10).** An outgoing item is generated from a domain template (letterhead, references, required clauses), approved, then sent. The issued PDF is stored as an immutable rendition. In Phase 1 sending is a stub and the PDF is a deliberately plain rendition: one font, one column, text only. The renderer uses no library, so there is no new dependency and no licence to review.
>
> **Determinism.** The bytes are a function of the lines and the title: no `/CreationDate`, no `/ID`, no producer string. The cross-reference table has exact byte offsets.

### Learnings that apply
> **L-P0-I8A-9.** Hostile text raises errors other than the ones documented: control characters and characters that Windows-1252 cannot show are replaced, never raised on; a letter over the bounds is refused with `LetterError`, not cut.
>
> **L-P1-I3B-5.** If you write a script that rewrites a file in place, compute the new text before opening the file for writing.
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/letter.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""A letter from a template to a PDF, with no library and no clock (brief 9 M10: issue).

``fill_template`` puts the fields of a letter into the text of a domain template, ``compose_letter``
lays the letter out as plain lines, and ``render_pdf`` writes those lines as a PDF 1.4 file with the
built-in Helvetica font. The output is a function of the input alone: no date, no random id, no
metadata other than the title, so the same letter always gives the same bytes (and the same
SHA-256). It is a stub of the letterhead and layout work a real renderer would do: one font, one
column, plain text. Characters that Windows-1252 cannot show become ``?``.

Bounds (a letter is bounded before it is laid out, and an over-long one is refused, not cut):
``MAX_CHARS`` characters, ``MAX_PAGES`` pages.

STUB (P1-I5-T07d): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import re
import textwrap
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

MAX_CHARS: Final = 60_000
MAX_PAGES: Final = 30
LINE_WIDTH: Final = 90  # characters per line (Helvetica 10 pt on an A4 page)
LINES_PER_PAGE: Final = 52
FIELD_NAMES: Final = ("number", "date", "subject", "to", "body")

_FIELD = re.compile(r"\{([a-z_]{1,32})\}")


class LetterError(ValueError):
    """The letter cannot be made: an unknown field, text too long, or a bad template."""


@dataclass(frozen=True)
class LetterFields:
    """The values that go into a letter. Every value is plain text."""

    number: str
    date: str
    subject: str
    to: str
    body: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "number": self.number,
            "date": self.date,
            "subject": self.subject,
            "to": self.to,
            "body": self.body,
        }


def fill_template(text: str, fields: Mapping[str, str]) -> str:
    """``text`` with each ``{name}`` replaced by ``fields[name]``.

    Only the names in ``FIELD_NAMES`` may appear; any other ``{name}`` raises ``LetterError``
    naming it. Braces that do not form ``{lower_case_name}`` stay as they are. A value is inserted
    as it is (it is never searched for further placeholders), and nothing is evaluated: this is
    not ``str.format``.
    """
    # STEPS
    # 1. `unknown = sorted({m for m in _FIELD.findall(text) if m not in FIELD_NAMES})`; when it
    #    is not empty raise `LetterError(f"the template uses {{{unknown[0]}}}, which is not a
    #    letter field")`.
    # 2. `return _FIELD.sub(lambda match: fields.get(match.group(1), ""), text)` (the result of
    #    a replacement function is not searched again, so a value that looks like a placeholder
    #    stays as it is).
    raise NotImplementedError


def compose_letter(header: str | None, footer: str | None, fields: LetterFields) -> list[str]:
    """The lines of the letter: header, number and date, recipient, subject, body, footer.

    Layout: the filled header (if any), a blank line, ``Our ref: <number>`` and ``Date: <date>``,
    a blank line, ``To: <to>``, a blank line, ``Subject: <subject>``, a blank line, the body, a
    blank line, the filled footer (if any). Every line is wrapped at ``LINE_WIDTH`` and the
    text is cleaned (tabs become four spaces, other control characters a space). Raises
    ``LetterError`` when the whole letter holds more than ``MAX_CHARS`` characters.
    """
    # STEPS
    # 1. `mapping = fields.as_mapping()`; `parts: list[str] = []`. When `header` is not empty
    #    `parts += [fill_template(header, mapping), ""]`.
    # 2. Then `parts += [f"Our ref: {fields.number}", f"Date: {fields.date}", "", f"To:
    #    {fields.to}", "", f"Subject: {fields.subject}", "", fields.body]`.
    # 3. When `footer` is not empty `parts += ["", fill_template(footer, mapping)]`.
    # 4. `raw = "\n".join(parts)`; when `len(raw) > MAX_CHARS` raise `LetterError(f"the letter
    #    has {len(raw)} characters; the limit is {MAX_CHARS}")`.
    # 5. `lines: list[str] = []`; for each `paragraph` of `_clean(raw).split("\n")`: `wrapped =
    #    textwrap.wrap(paragraph, width=LINE_WIDTH, replace_whitespace=False,
    #    drop_whitespace=True)`; `lines.extend(wrapped or [""])` (an empty paragraph is one
    #    empty line). Return `lines`.
    raise NotImplementedError


def _clean(text: str) -> str:
    # STEPS
    # 1. `text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")`.
    # 2. Replace each character other than "\n" whose `unicodedata.category` starts with "C" by
    #    a space; return the joined text.
    raise NotImplementedError


def _pdf_text(line: str) -> bytes:
    # STEPS
    # 1. `data = line.encode("cp1252", errors="replace")`.
    # 2. Escape with a backslash, in this order: `\` (`b"\\"` becomes `b"\\\\"`), `(` and `)`.
    #    Return the bytes.
    raise NotImplementedError


def render_pdf(lines: Sequence[str], title: str) -> bytes:
    """A PDF 1.4 file with ``lines`` in Helvetica 10 pt, ``LINES_PER_PAGE`` to a page.

    The file has a catalog, a page tree, one page and one content stream per page, a Type1
    Helvetica font, an info dictionary with only ``/Title``, a cross-reference table with exact
    offsets and a trailer; it holds no date and no random id. An empty ``lines`` gives one empty
    page. Raises ``LetterError`` for more than ``MAX_PAGES`` pages.
    """
    # STEPS
    # 1. `pages = [list(lines[i : i + LINES_PER_PAGE]) for i in range(0, len(lines),
    #    LINES_PER_PAGE)]`; `pages = pages or [[]]`; when `len(pages) > MAX_PAGES` raise
    #    `LetterError(f"the letter needs {len(pages)} pages; the limit is {MAX_PAGES}")`.
    # 2. Object bodies (bytes), in this order, numbered from 1: (1) `<< /Type /Catalog /Pages 2
    #    0 R >>`; (2) `<< /Type /Pages /Kids [<refs>] /Count <n> >>` where the refs are `f"{5 +
    #    2 * i} 0 R"` for page i joined by one space and n is `len(pages)`, written as `b"<<
    #    /Type /Pages /Kids [" + refs + f"] /Count {n} >>".encode()`; (3) `<< /Type /Font
    #    /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>`; (4) `<< /Title (`
    #    + `_pdf_text(title[:200])` + `) >>`.
    # 3. For page `index` (objects 5 + 2 * index and 6 + 2 * index): the content stream is `b"BT
    #    /F1 10 Tf 12 TL 50 790 Td\n"` followed, for each line, by `b"(" + _pdf_text(line) + b")
    #    Tj T*\n"`, then `b"ET"`. The page object is `<< /Type /Page /Parent 2 0 R /MediaBox [0
    #    0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents <6 + 2 * index> 0 R >>`.
    #    The content object is `<< /Length <len(stream)> >>\nstream\n` + stream + `\nendstream`.
    # 4. Write the file: `out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")`. For each object
    #    `number, body` (from 1) remember `len(out)` as its offset and append `f"{number} 0
    #    obj\n".encode() + body + b"\nendobj\n"`.
    # 5. `xref_at = len(out)`; append `f"xref\n0 {len(objects) + 1}\n"` and `b"0000000000 65535
    #    f \n"`, then for each object `f"{offset:010d} 00000 n \n"` (exactly 20 bytes each).
    # 6. Append `f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 4 0 R
    #    >>\nstartxref\n{xref_at}\n%%EOF\n"` and return `bytes(out)`. The file has no date and
    #    no random id: the same lines and title always give the same bytes.
    raise NotImplementedError
```


## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/letter.py`
- `docs/tickets/P1-I5/provided/t07d-test_letter.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/letter.py`
- `packages/tl-modules/correspondence/tests/test_letter.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T07d.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t07d-test_letter.py.txt packages/tl-modules/correspondence/tests/test_letter.py`. Do not edit the copy.
2. Implement the five functions by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T07d: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_letter.py -q
```
Expected: `just check` clean; 23 passed on SQLite.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_letter.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T07d.md` and committed. State the count you got and whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone.

## Escalation triggers
- A STEPS line contradicts the docstring of its function or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
