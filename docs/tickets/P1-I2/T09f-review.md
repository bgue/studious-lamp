# P1-I2-T09f — `tl review`: open, answer, on-behalf, close, override, ls

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket (T08b, the review commands, is merged)
Branch: `p1/i2-t09f-cli-review`

## Goal
A reviewer and a document controller run reviews from the shell. `packages/tl-cli/src/tl_cli/review.py` has the group, its helper and the six commands' signatures, options and docstrings final; the six bodies raise `NotImplementedError`. The group is already registered as `tl review` in `tl_cli/main.py`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `ReviewCycle`: a revision, its reviewers, a date, an outcome from each reviewer; closing returns the revision to Draft with the overall outcome. A revision is In Review exactly while a cycle on it is open.
>
> **ADR-0011.** A reviewer records their own answer only (the command passes the caller; it has no reviewer option). Recording an answer on someone's behalf (`RecordReviewOutcomeOnBehalf`, with a mandatory comment) and closing with an outcome milder than the worst answer (`OverrideReviewOutcome`, with a reason) are the admin's acts; the CLI calls `require_admin` for `on-behalf` and `override`. Opening, answering and closing are open to any signed-in person.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (do not change the default text; the root replaces it by the signed-in person). `answer` passes that actor as the reviewer by passing no reviewer at all.
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure and turns an input-validation failure into `error: <field>: <message>`.
- A cycle is looked up by its key with `_cycle(...)` (final); a revision by `registry.find_revision`.
- `on-behalf` and `override` call `require_admin(db)` before anything else.
- `close` is open to the cycle's opener and the revision's author only (the module refuses anyone else with `not_your_review`); a round nobody answered closes as `withdrawn`, which is not a rejection.
- Reads (`ls`) open the unit of work with `readonly=True`; writes use `open_uow(db)`.
- The test makes accounts for the reviewers with the module's test world (`world.people(..., password=...)`) and runs `answer` with `--actor user:<name>`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/review.py` (the stub you complete):
```python
"""The `tl review` group: open a review of a revision, answer it, close it (brief 9 M1).

A review cycle asks named reviewers to review one draft revision by a date and collects an outcome
from each. Each subcommand parses options, makes one call into `tl_mod_documents` and prints. The
rules live in the module: reviewers are people with an account and not only the author; a reviewer
answers for themselves; a person cannot close milder than the worst answer; only the opener or the
revision's author closes. A cycle is named by its key (`ISO-1234@A/RC1`, as `tl review open` prints
it); the project comes from `--project`. Recording an answer on someone's behalf and overriding an
outcome are an admin's acts (ADR-0011).

STUB (P1-I2-T09f): the bodies of the six commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.handlers.reviews import (
    CloseReviewCycle,
    OpenReviewCycle,
    OverrideReviewOutcome,
    RecordReviewOutcome,
    RecordReviewOutcomeOnBehalf,
    ReviewerRequest,
    handle_close_review_cycle,
    handle_open_review_cycle,
    handle_override_review_outcome,
    handle_record_review_outcome,
    handle_record_review_outcome_on_behalf,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Open, answer and close reviews of revisions.", no_args_is_help=True)

_Cycle = Annotated[str, typer.Argument(help="The review cycle key, for example ISO-1234@A/RC1.")]
_Outcome = Annotated[
    str, typer.Option("--outcome", help="approved, approved_with_comments or rejected.")
]


def _cycle(uow: UnitOfWork, scope: str, project: str, key: str) -> registry.ReviewCycleRow:
    """The review cycle ``key``; exits `error: no review cycle 'X' in project 'P'`."""
    record = get_record(uow, scope, key)
    found = registry.get_review_cycle(uow.conn(), record["id"]) if record is not None else None
    if found is None:
        _fail(f"no review cycle {key!r} in project {project!r}")
    return found


@app.command("open")
def open_cycle(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    code: Annotated[str, typer.Argument(help="The draft revision to review, for example A.")],
    project: _Project,
    reviewers: Annotated[
        list[str],
        typer.Option("--reviewer", help="A reviewer, written user:<username>. Repeat it."),
    ],
    due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Open a review round on a draft revision. The revision moves to In Review."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` doc = _document(uow, scope, project,
    #    number); rev = registry.find_revision(uow.conn(), doc.id, code); if it is None,
    #    _fail(f"no revision {code!r} of {number}"). made = handle_open_review_cycle(uow,
    #    OpenReviewCycle(actor=actor, source="cli", scope=scope, revision_id=rev.id,
    #    reviewers=[ReviewerRequest(reviewer=r) for r in reviewers], due_date=due)).
    # 3. Print `opened <made.key> round <n>` where n is the number after "RC" in made.key, and
    #    then `reviewers <len(reviewers)>`.
    raise NotImplementedError


@app.command("answer")
def answer(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: _Outcome,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record your own answer to a review: approved, approved with comments, or rejected."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_record_review_outcome(uow, RecordReviewOutcome.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "comment": comment})). The answer is the caller's own: do not pass a reviewer. A bad
    #    `--outcome` is reported by _service_errors as `error: outcome: ...`.
    # 3. Print `answered <cycle>: <outcome> by <actor>`.
    raise NotImplementedError


@app.command("on-behalf")
def on_behalf(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    reviewer: Annotated[str, typer.Option("--reviewer", help="Whose answer this is.")],
    outcome: _Outcome,
    comment: Annotated[str, typer.Option("--comment", help="How the answer reached you.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record a reviewer's answer for them (admin). The comment is required and kept."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_record_review_outcome_on_behalf(uow, RecordReviewOutcomeOnBehalf.model_validate(
    #    {"actor": actor, "source": "cli", "scope": scope, "review_cycle_id": row.id,
    #    "reviewer": reviewer, "outcome": outcome, "comment": comment})).
    # 3. Print `recorded <cycle>: <outcome> for <reviewer> by <actor>`.
    raise NotImplementedError


@app.command("close")
def close(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: Annotated[
        str | None,
        typer.Option("--outcome", help="Default: the worst answer. Never milder than it."),
    ] = None,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Required while a reviewer has not answered.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close a review cycle (its opener or the revision's author). The revision returns to Draft."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_close_review_cycle(uow, CloseReviewCycle.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "reason": reason})); after = _cycle(uow, scope, project, cycle).
    # 3. Print `closed <cycle>: <after.outcome>`.
    raise NotImplementedError


@app.command("override")
def override(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: _Outcome,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close a cycle with a stated outcome, even a milder one than the answers (admin)."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_override_review_outcome(uow, OverrideReviewOutcome.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "reason": reason})).
    # 3. Print `closed <cycle>: <outcome> (overridden)`.
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    code: Annotated[str, typer.Argument(help="The revision code.")],
    project: _Project,
) -> None:
    """List the review cycles of a revision, each followed by its reviewers."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc = _document(uow,
    #    scope, project, number); rev = registry.find_revision(uow.conn(), doc.id, code) (exit
    #    `error: no revision 'X' of N` when it is None); cycles =
    #    registry.review_cycles_of(uow.conn(), rev.id); and for each cycle its reviewers =
    #    registry.reviewers_of(uow.conn(), cycle.id).
    # 3. For each cycle print, joined by two spaces: cycle.key, f"round={round}", state,
    #    f"due={due_date or '-'}", f"outcome={outcome or '-'}". Under it one line per reviewer:
    #    two spaces, then joined by two spaces: reviewer, outcome or "pending", responded_on or
    #    "-", comment or "-".
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` (excerpts; read-only, do not edit):
```python
class ReviewerRequest(BaseModel):
    """A reviewer and, when it differs from the cycle's, the date by which they should answer."""

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=MAX_TEXT)
    due_date: str | None = None


class OpenReviewCycle(Command):
    """Open a review round on a draft revision. The revision moves to In Review."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    reviewers: list[ReviewerRequest] = Field(min_length=1, max_length=MAX_REVIEWERS)
    due_date: str | None = None


class RecordReviewOutcome(Command):
    """A reviewer's own answer: approved, approved with comments, or rejected. Given once.

    ``reviewer`` may be left out (it is the caller); if given it must be the caller. To record an
    answer for someone else an admin uses ``RecordReviewOutcomeOnBehalf``.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    reviewer: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    outcome: Outcome
    comment: str | None = Field(default=None, max_length=MAX_DESCRIPTION)


class RecordReviewOutcomeOnBehalf(Command):
    """Admin: record a reviewer's answer for them (they replied by mail, say). A comment says how.

    The event keeps who recorded it (``recorded_by``) next to the reviewer it is for.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    reviewer: str = Field(min_length=1, max_length=MAX_TEXT)
    outcome: Outcome
    comment: str = Field(min_length=1, max_length=MAX_DESCRIPTION)


class CloseReviewCycle(Command):
    """Close a cycle. The outcome is the worst answer unless the command states a stricter one.

    Only the person who opened the cycle or the revision's author may close it (an admin closes
    any cycle with ``OverrideReviewOutcome``). A person cannot close with an outcome milder than
    the worst answer. If a reviewer has not answered, ``reason`` is required (why the cycle closes
    early). If nobody has answered, the round is ``withdrawn``: that is the only outcome, and the
    default.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    outcome: CloseOutcome | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class OverrideReviewOutcome(Command):
    """Admin: close a cycle with a stated outcome, even a milder one than the answers given.

    ``reason`` is required; the event keeps the worst recorded answer (``worst_answer``) so the
    record shows what was overruled.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    outcome: Outcome
    reason: str = Field(min_length=1, max_length=MAX_REASON)
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class ReviewCycleRow:
    id: str
    scope: str
    key: str
    title: str
    voided: bool
    version: int
    revision_id: str
    document_id: str
    round: int
    state: str  # open | closed
    due_date: str | None
    outcome: str | None
    opened_on: str | None
    closed_on: str | None


@dataclass(frozen=True)
class ReviewerRow:
    review_cycle_id: str
    revision_id: str
    document_id: str
    reviewer: str
    due_date: str | None
    outcome: str | None
    comment: str | None
    responded_on: str | None


def find_revision(conn: Connection, document_id: str, code: str) -> RevisionRow | None:
    ...


def get_review_cycle(conn: Connection, cycle_id: str) -> ReviewCycleRow | None:
    ...


def review_cycles_of(conn: Connection, revision_id: str) -> list[ReviewCycleRow]:
    """The review cycles of a revision, round by round."""
    ...


def reviewers_of(conn: Connection, cycle_id: str) -> list[ReviewerRow]:
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/review.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` (read the docstrings: they list what each command refuses)
- `docs/tickets/P1-I2/provided/t09f-test_cli_review.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-cli`, `packages/tl-mcp` and `packages/tl-api`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- On Postgres the tl-cli `conftest.py` signs a test admin in for you (L-P1-I0B-8); a command that needs the admin role runs as that admin there, and the test skips the refusal part (`doccli_support.admin_session` returns False).
- A signed-in person is needed for the admin commands of this group on SQLite: the test bootstraps `root` and signs in (`admin_session`), then `ordinary_env` gives a second, non-admin person.
- `doc.py` is merged and final. `doc_rev.py` is another ticket's file (T09b): its helpers `_Number`, `_Code` and `_revision` are final in the tree, its command bodies may still be stubs. Import the helpers; do not copy them and do not edit either file.


## Allowed paths
- `packages/tl-cli/src/tl_cli/review.py` (edit)
- `packages/tl-cli/tests/test_cli_review.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09f.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09f-test_cli_review.py.txt` to `packages/tl-cli/tests/test_cli_review.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_review.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_review.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 8 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_documents` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
