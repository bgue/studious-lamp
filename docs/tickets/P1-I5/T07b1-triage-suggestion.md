# P1-I5-T07b1 — The triage suggestion engine

Status: ready
Tier: haiku
Labels: module
Depends on: — (a pure module: no database)
Branch: `p1/i5-t07b1-triage-suggestion`

## Goal
`suggest.py` proposes the domain and subtype of a received item from its text and the domain definitions. `Suggestion`, the constants and `_found` are written; `suggest` raises `NotImplementedError`. You implement it by its STEPS comment. The function is pure and deterministic: no database, no clock, no model, and the answer never depends on the order of the definitions. One provided test file must pass.

## Brief references (pasted)
> **Triage (brief 9, M10).** The module proposes the domain from the content: keywords and patterns defined in the domain files. A person confirms it; an agent's call is only a proposal. Matching is on whole words or phrases, ignoring case; a keyword in the subject counts double; each distinct keyword counts once; ties go to the domain `general`, otherwise to the lowest code. Only the first 500 characters of the subject and 20 000 of the body are read.
>
> **Rules of this module.** Domain definitions are data; nothing in them is run or used as SQL. Build every regular expression with `re.escape` on the keyword (the file does, in `_found`).

### Learnings that apply
> **L-P1-I3B-8.** A regular expression with a group or alternation under a repeat can use gigabytes on a long string; `_found` uses a single escaped keyword between two look-arounds. Do not build other expressions here.
>
> **Rule of this ticket.** The test runs `suggest` on the two committed domain files; do not hard-code domain names in `suggest` except the constant `DOMAIN_GENERAL`.
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/suggest.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""The triage suggestion engine: which domain and subtype a received item probably belongs to.

A pure function of the item's text and the domain definitions: no database, no clock, no model.
Each domain and each subtype lists the words and phrases that point to it (``triage_keywords`` and
``keywords`` in the domain file); the engine counts how many *different* keywords occur in the
subject and the body and picks the best. The suggestion is only a suggestion: a person confirms it
(``ConfirmTriage``) and an agent's call is a proposal a person accepts.

Matching is on whole words or phrases, ignoring case; a keyword in the subject counts double
(a letter's subject is what its writer thought it was about). Ties go to the domain named
``general`` when it is among the best, otherwise to the lowest code, so the answer never depends on
the order of the files. A text with no keyword at all gets the ``general`` domain (or the first
domain when there is none) with a score of 0 and says so.

STUB (P1-I5-T07b1): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.names import DOMAIN_GENERAL

#: Only this much of the subject and the body is read.
MAX_SUBJECT_CHARS: Final = 500
MAX_BODY_CHARS: Final = 20_000
SUBJECT_WEIGHT: Final = 2


@dataclass(frozen=True)
class Suggestion:
    """The proposed domain and subtype, how sure the engine is, and why."""

    domain: str | None
    subtype: str | None
    score: int  # the winning domain's score; 0 means no keyword matched
    reasons: tuple[str, ...] = ()
    scores: dict[str, int] = field(default_factory=lambda: {})  # domain code to score


def _found(keyword: str, subject: str, body: str) -> int:
    """How much a keyword counts: ``SUBJECT_WEIGHT`` in the subject, 1 in the body only, else 0."""
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])")
    if pattern.search(subject):
        return SUBJECT_WEIGHT
    return 1 if pattern.search(body) else 0


def suggest(
    domains: Sequence[DomainDefinition], *, subject: str, body: str | None = None
) -> Suggestion:
    """The best domain and subtype for the text, or an empty suggestion when there are no domains.

    A domain's score is the sum of the weights of its distinct ``triage_keywords`` and of the
    distinct keywords of all its subtypes. Its subtype is the one with the highest keyword score;
    a tie, or no match, gives the domain's ``default_subtype``.
    """
    # STEPS
    # 1. `if not domains:` return `Suggestion(domain=None, subtype=None, score=0, reasons=("no
    #    domain is defined",))`.
    # 2. `low_subject = subject[:MAX_SUBJECT_CHARS].lower()`; `low_body = (body or
    #    "")[:MAX_BODY_CHARS].lower()`. Three dicts keyed by domain code: `scores` (int),
    #    `reasons` (list of str) and `subtype_scores` (a dict subtype code to int).
    # 3. For each `domain`: `total = 0`, `why = []`. For each `word` in
    #    `domain.triage_keywords`: `weight = _found(word, low_subject, low_body)`; when it is
    #    not 0 add it to `total` and append `f"{domain.code}: '{word}'"` to `why`.
    # 4. For each `subtype` of `domain.subtypes`: `own = 0`; for each `word` in
    #    `subtype.keywords` add `_found(...)` the same way (and append
    #    `f"{domain.code}/{subtype.code}: '{word}'"` to `why`); record `by_subtype[subtype.code]
    #    = own` and add `own` to `total`. Store `total`, `why` and `by_subtype` under the domain
    #    code.
    # 5. `best = max(scores.values())`; `leaders = sorted(code for code, score in scores.items()
    #    if score == best)`; `code = DOMAIN_GENERAL if DOMAIN_GENERAL in leaders else
    #    leaders[0]`. When `best == 0 and DOMAIN_GENERAL not in scores`: `code =
    #    sorted(scores)[0]`. (Sorting makes the answer independent of the order of the
    #    definitions.)
    # 6. `chosen` is the definition with that code. `own = subtype_scores[code]`; `top =
    #    max(own.values()) if own else 0`; `winners = [s for s, n in own.items() if n == top]`;
    #    `subtype = winners[0] if top > 0 and len(winners) == 1 else chosen.default_subtype`.
    # 7. `why_not = ("no keyword matched; the default domain",) if best == 0 else ()`. Return
    #    `Suggestion(domain=code, subtype=subtype, score=best, reasons=tuple(reasons[code]) or
    #    why_not, scores=dict(sorted(scores.items())))`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/domains.py` (read-only; names and signatures):
```python
class DomainSubtype: ...  # see the file
class DomainDefinition: ...  # see the file
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/suggest.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/domains.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `docs/tickets/P1-I5/provided/t07b1-test_suggest.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/suggest.py`
- `packages/tl-modules/correspondence/tests/test_suggest.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T07b1.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t07b1-test_suggest.py.txt packages/tl-modules/correspondence/tests/test_suggest.py`. Do not edit the copy.
2. Implement `suggest` by its STEPS comment.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T07b1: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_suggest.py -q
```
Expected: `just check` clean; 14 passed on SQLite (the 10 provided tests plus 4 the supervisor appended after the merge, see *Decision*).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_suggest.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T07b1.md` and committed. State the count you got and whether the `STUB` paragraph, the STEPS comment and the `ruff: noqa` line are gone.

## Escalation triggers
- A STEPS line contradicts the docstring of `suggest` or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
Supervisor, 2026-10-18, after the merge (73e9dce). The implementer's code followed STEPS 4, which counted a keyword that two
subtypes share once per subtype, while the docstring of `suggest` said *distinct* keywords. The code now follows the docstring:
- **Shared word.** A keyword that two subtypes of one domain share counts once for the domain's score and once for each of the
  two subtypes' own scores (the subtype is still chosen by its own score).
- **Repeated triage keyword.** A word listed twice in a domain's `triage_keywords` counts once.
- **Docstring.** `suggest` now says so in words.
- **STEPS 5 fallback removed.** The branch that picked the lowest code when nothing matched and no `general` domain exists was
  dead: the sorted leaders already give the lowest code. The mutation run showed no test could tell it from the plain line.
- **Tests.** Four tests were appended to the provided file (shared word and repeated keyword, word edges, order independence
  and the lowest code, the subject limit). The copy in `tests/test_suggest.py` is therefore **not** byte-identical to the
  provided text, by design; the first 10 tests are.
- **Known and intended: a word in both lists.** A word that is in a domain's `triage_keywords` *and* in one of its subtype lists
  counts twice (the provided test pins `transmittal` at 2 + 2). `triage_keywords` say "this domain"; a subtype keyword says
  "this kind of letter in this domain"; both agree for a word such as `transmittal`. It is documented in the `suggest`
  docstring and not forbidden by the domain file check.
